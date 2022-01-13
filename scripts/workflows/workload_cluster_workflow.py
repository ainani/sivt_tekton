import os
from pathlib import Path

from jinja2 import Template

from constants.constants import (TKG_EXTENSIONS_ROOT, Constants, Paths, Task)
from lib.kubectl_client import KubectlClient
from lib.tkg_cli_client import TkgCliClient
from model.run_config import RunConfig
from model.spec import GrafanaSpec, WorkloadCluster
from model.status import (ExtensionState, HealthEnum, WorkloadClusterInfo, WorkloadExtensionState)
from util.cmd_helper import CmdHelper
from util.file_helper import FileHelper
from util.git_helper import Git
from util.logger_helper import LoggerHelper, log, log_debug
from util.ssh_helper import SshHelper
from util.tanzu_utils import TanzuUtils
from workflows.cluster_common_workflow import ClusterCommonWorkflow

logger = LoggerHelper.get_logger(Path(__file__).stem)


class WorkloadClusterWorkflow:
    def __init__(self, run_config: RunConfig):
        self.run_config = run_config
        self.extensions_root = TKG_EXTENSIONS_ROOT[self.run_config.desired_state.version.tkg]
        self.extensions_dir = Paths.TKG_EXTENSIONS_DIR.format(extensions_root=self.extensions_root)
        self.cluster_to_deploy = None
        self.tkg_cli_client: TkgCliClient = None
        self.kubectl_client: KubectlClient = None
        self.ssh: SshHelper = None
        self.kube_config = os.path.join(self.run_config.root_dir, Paths.REPO_KUBE_TKG_CONFIG)
        self.common_workflow: ClusterCommonWorkflow = None
        # Following values must be set in upgrade scenarios
        # prev_version Specifies current running version as per state.yml
        self.prev_version = None
        self.prev_extensions_root = None
        self.prev_extensions_dir = None

    @log_debug
    def _template_deploy_yaml(self, cluster):
        deploy_yaml = FileHelper.read_resource(Paths.VSPHERE_WORKLOAD_SERVICES_SPEC_J2)
        t = Template(deploy_yaml)
        return t.render(spec=self.run_config.spec, wl_cluster=cluster)

    def initialize_clients(self, ssh):
        if not self.tkg_cli_client:
            self.tkg_cli_client = TkgCliClient(ssh)
        if not self.kubectl_client:
            self.kubectl_client = KubectlClient(ssh)
        if not self.ssh:
            self.ssh = ssh
        if not self.common_workflow:
            self.common_workflow = ClusterCommonWorkflow(ssh)

    @log("Updating state file")
    def _update_state(self, task: Task, msg="Successful workload cluster deployment"):
        ext_state = ExtensionState(deployed=False, upgraded=False)
        wl_info = WorkloadClusterInfo(
            deployed=True,
            health=HealthEnum.UP,
            version=self.run_config.desired_state.version.tkg,
            name=self.cluster_to_deploy,
            extensions=WorkloadExtensionState(certManager=ext_state, contour=ext_state, prometheus=ext_state,
                                              grafana=ext_state)
        )
        if self.get_cluster_state():
            index = next(
                i for i, j in enumerate(self.run_config.state.workload_clusters) if j.name == self.cluster_to_deploy)
            if task == Task.DEPLOY_CLUSTER:
                self.run_config.state.workload_clusters[index] = WorkloadClusterInfo(
                    deployed=True,
                    health=HealthEnum.UP,
                    version=self.run_config.desired_state.version.tkg,
                    name=self.cluster_to_deploy,
                    extensions=WorkloadExtensionState(certManager=ext_state, contour=ext_state, prometheus=ext_state,
                                                      grafana=ext_state))
            elif task == Task.UPGRADE_CLUSTER:
                ext_state = ExtensionState(deployed=True, upgraded=False)
                self.run_config.state.workload_clusters[index] = WorkloadClusterInfo(
                    deployed=True,
                    health=HealthEnum.UP,
                    version=self.run_config.desired_state.version.tkg,
                    name=self.cluster_to_deploy,
                    extensions=WorkloadExtensionState(certManager=ext_state, contour=ext_state, prometheus=ext_state,
                                                      grafana=ext_state))
            elif task in (Task.DEPLOY_CERT_MANAGER, Task.UPGRADE_CERT_MANAGER):
                self.run_config.state.workload_clusters[index].extensions.certManager = ExtensionState(deployed=True,
                                                                                                       upgraded=True)
            elif task in (Task.DEPLOY_CONTOUR, Task.UPGRADE_CONTOUR):
                self.run_config.state.workload_clusters[index].extensions.contour = ExtensionState(deployed=True,
                                                                                                   upgraded=True)
            elif task in (Task.DEPLOY_GRAFANA, Task.UPGRADE_GRAFANA):
                self.run_config.state.workload_clusters[index].extensions.grafana = ExtensionState(deployed=True,
                                                                                                   upgraded=True)
            elif task in (Task.DEPLOY_PROMETHEUS, Task.UPGRADE_PROMETHEUS):
                self.run_config.state.workload_clusters[index].extensions.prometheus = ExtensionState(deployed=True, upgraded=True)
            elif task == Task.ATTACH_CLUSTER_TO_TMC:
                self.run_config.state.workload_clusters[index].integrations.tmc.deployed = True
        else:
            self.run_config.state.workload_clusters.append(wl_info)
        state_file_path = os.path.join(self.run_config.root_dir, Paths.STATE_PATH)
        FileHelper.dump_state(self.run_config.state, state_file_path)
        Git.add_all_and_commit(os.path.dirname(state_file_path), msg)

    def get_cluster_state(self) -> WorkloadClusterInfo:
        if any(clu.name == self.cluster_to_deploy for clu in self.run_config.state.workload_clusters):
            return next(clu for clu in self.run_config.state.workload_clusters if clu.name == self.cluster_to_deploy)
        return None

    def _pre_validate(self, current_version) -> bool:
        if self.run_config.state.shared_services.deployed:
            logger.info("Shared service cluster is deployed, and in version : %s", current_version)
            if current_version == self.run_config.desired_state.version.tkg:
                logger.info("Shared service cluster is already on correct version(%s)", current_version)
                return False
            if current_version not in self.run_config.support_matrix["matrix"].keys():
                raise ValueError(f"Current Tanzu version({current_version}) is unsupported")

            if self.run_config.desired_state.version.tkg < current_version:
                raise ValueError(
                    f"Downgrading version is not possible[from: {current_version}, to: {self.run_config.desired_state.version.tkg}]"
                )

            if self.run_config.desired_state.version.tkg not in self.run_config.support_matrix["matrix"].keys():
                raise ValueError(f"Desired Tanzu version({self.run_config.desired_state.version.tkg}) is unsupported")

            if self.run_config.desired_state.version.tkg not in self.run_config.support_matrix["upgrade_path"].get(
                    current_version):
                raise ValueError(f"There are no upgrade path available for tkg: {current_version}")
        elif self.run_config.desired_state.version.tkg not in self.run_config.support_matrix["matrix"].keys():
            raise ValueError(
                f"Tanzu version({self.run_config.desired_state.version.tkg}) specified in desired state is unsupported"
            )
        return True

    @log("Updating Grafana Admin password")
    def _update_grafana_admin_password(self, spec: GrafanaSpec):
        if self.run_config.desired_state.version.tkg < "1.4.0":
            remote_file = os.path.join(self.extensions_dir, Paths.GRAFANA_CONFIG)
        else:
            remote_file = Paths.REMOTE_GRAFANA_DATA_VALUES
        local_file = Paths.LOCAL_GRAFANA_DATA_VALUES.format(root_dir=self.run_config.root_dir)

        logger.info(f"Fetching and saving data values yml to {local_file}")
        self.ssh.copy_file_from_remote(remote_file, local_file)

        encoded_password = CmdHelper.encode_base64(spec.adminPassword)
        logger.info(f"Updating admin password in local copy of grafana-data-values.yaml")
        # Replacing string with pattern matching instead of loading yaml because comments
        # in yaml file will be lost during boxing/unboxing of yaml data
        FileHelper.replace_pattern(
            src=local_file,
            target=local_file,
            pattern_replacement_list=[(Constants.GRAFANA_ADMIN_PASSWORD_TOKEN,
                                       Constants.GRAFANA_ADMIN_PASSWORD_VALUE.format(password=encoded_password))],
        )

        logger.info(f"Updating grafana-data-values.yaml on bootstrap VM")
        self.ssh.copy_file(local_file, remote_file)

    @log("Updating namespace in grafana-data-values.yaml")
    def _update_grafana_namespace(self, remote_file):
        local_file = Paths.LOCAL_GRAFANA_DATA_VALUES.format(root_dir=self.run_config.root_dir)

        logger.info(f"Fetching and saving data values yml to {local_file}")
        self.ssh.copy_file_from_remote(remote_file, local_file)

        new_namespace = "tanzu-system-dashboards"

        FileHelper.replace_pattern(
            src=local_file,
            target=local_file,
            pattern_replacement_list=[(Constants.GRAFANA_DATA_VALUES_NAMESPACE,
                                       Constants.GRAFANA_DATA_VALUES_NEW_NAMESPACE.format(namespace=new_namespace))],
        )

        self.ssh.copy_file(local_file, remote_file)

    @log("Deploying contour extension")
    def _deploy_contour(self):
        """
        Wrapper method for deploying contour on Tanzu k8s cluster
        :return:
        """
        self.common_workflow.create_namespace_for_extension(
            namespace=Constants.TANZU_SYSTEM_INGRESS,
            config_file=Paths.CONTOUR_NAMESPACE_CONFIG,
            extension_name=Constants.CONTOUR_APP,
            work_dir=self.extensions_dir,
            sa_name=Constants.CONTOUR_SERVICE_ACCOUNT,
        )
        logger.info("Copying contour-data-values yml")
        self.common_workflow.copy_config_file(
            work_dir=self.extensions_dir,
            source=Paths.VSPHERE_ALB_CONTOUR_CONFIG_EXAMPLE,
            destination=Paths.VSPHERE_ALB_CONTOUR_CONFIG,
        )
        self.common_workflow.create_secret_for_extension(
            secret_name=Constants.CONTOUR_DATA_VALUES,
            namespace=Constants.TANZU_SYSTEM_INGRESS,
            config_file=Paths.VSPHERE_ALB_CONTOUR_CONFIG,
            work_dir=self.extensions_dir,
        )
        self.common_workflow.reconcile_extension(
            app_name=Constants.CONTOUR_APP,
            namespace=Constants.TANZU_SYSTEM_INGRESS,
            config_file=Paths.CONTOUR_EXTENSION_CONFIG,
            work_dir=self.extensions_dir,
            cluster_to_deploy=self.cluster_to_deploy,
        )
        logger.debug(self.kubectl_client.get_all_pods())
        self._update_state(task=Task.DEPLOY_CONTOUR, msg=f'Contour installation complete on {self.cluster_to_deploy}')
        logger.info("Contour installation complete")

    @log("Deploying prometheus extension")
    def _deploy_prometheus(self):
        """
        Wrapper method for deploying prometheus on Tanzu k8s cluster
        :return:
        """
        self.common_workflow.create_namespace_for_extension(
            namespace=Constants.TANZU_SYSTEM_MONITORING,
            config_file=Paths.PROMETHEUS_NAMESPACE_CONFIG,
            extension_name=Constants.PROMETHEUS_APP,
            work_dir=self.extensions_dir,
            sa_name=Constants.PROMETHEUS_SERVICE_ACCOUNT,
        )
        logger.info("Copying prometheus-data-values yml")
        self.common_workflow.copy_config_file(
            work_dir=self.extensions_dir, source=Paths.PROMETHEUS_CONFIG_EXAMPLE, destination=Paths.PROMETHEUS_CONFIG
        )
        self.common_workflow.create_secret_for_extension(
            secret_name=Constants.PROMETHEUS_DATA_VALUES,
            namespace=Constants.TANZU_SYSTEM_MONITORING,
            config_file=Paths.PROMETHEUS_CONFIG,
            work_dir=self.extensions_dir,
        )
        self.common_workflow.reconcile_extension(
            app_name=Constants.PROMETHEUS_APP,
            namespace=Constants.TANZU_SYSTEM_MONITORING,
            config_file=Paths.PROMETHEUS_EXTENSION_CONFIG,
            work_dir=self.extensions_dir,
            cluster_to_deploy=self.cluster_to_deploy,
        )
        logger.debug(self.kubectl_client.get_all_pods())
        self._update_state(task=Task.DEPLOY_PROMETHEUS,
                           msg=f'Prometheus installation complete on {self.cluster_to_deploy}')
        logger.info("Prometheus installation complete")

    @log("Installing contour package")
    def _install_contour_package(self):
        for cluster in self.run_config.state.workload_clusters:
            if cluster.name == self.cluster_to_deploy:
                logger.debug(f"Current state of packages: {cluster.extensions}")
                if cluster.extensions.contour.deployed:
                    logger.info("Contour package already deployed. Skipping deployment.")
                else:
                    version = self.common_workflow.get_available_package_version(cluster_name=self.cluster_to_deploy,
                                                                                 package=Constants.CONTOUR_PACKAGE,
                                                                                 name=Constants.CONTOUR_DISPLAY_NAME)
                    logger.info("Copying contour-data-values.yml")
                    self.ssh.copy_file(Paths.LOCAL_VSPHERE_ALB_CONTOUR_CONFIG, Paths.REMOTE_VSPHERE_ALB_CONTOUR_CONFIG)

                    self.common_workflow.install_package(cluster_name=self.cluster_to_deploy,
                                                         package=Constants.CONTOUR_PACKAGE,
                                                         namespace=self.run_config.spec.tkg.sharedService.packagesTargetNamespace,
                                                         name=Constants.CONTOUR_APP, version=version,
                                                         values=Paths.REMOTE_VSPHERE_ALB_CONTOUR_CONFIG)
                    logger.debug(self.kubectl_client.get_all_pods())
                    logger.info('Contour installation complete')
                    self._update_state(task=Task.DEPLOY_CONTOUR,
                                       msg=f'Contour installation complete on {self.cluster_to_deploy}')

    @log("Installing cert_manager package")
    def _install_cert_manager_package(self):
        for cluster in self.run_config.state.workload_clusters:
            if cluster.name == self.cluster_to_deploy:
                logger.debug(f"Current state of packages: {cluster.extensions}")
                if cluster.extensions.certManager.deployed:
                    logger.info("Cert Manager package already deployed. Skipping deployment.")
                else:
                    version = self.common_workflow.get_available_package_version(cluster_name=self.cluster_to_deploy,
                                                                                 package=Constants.CERT_MGR_PACKAGE,
                                                                                 name=Constants.CERT_MGR_DISPLAY_NAME)
                    self.common_workflow.install_package(cluster_name=self.cluster_to_deploy,
                                                         package=Constants.CERT_MGR_PACKAGE,
                                                         namespace=self.run_config.spec.tkg.sharedService.packagesTargetNamespace,
                                                         name=Constants.CERT_MGR_APP, version=version)
                    logger.debug(self.kubectl_client.get_all_pods())
                    logger.info('Cert manager installation complete')
                    self._update_state(task=Task.DEPLOY_CERT_MANAGER,
                                       msg=f'Cert manager installation complete on {self.cluster_to_deploy}')

    @log("Installing prometheus package")
    def _install_prometheus_package(self, clu: WorkloadCluster):
        for cluster in self.run_config.state.workload_clusters:
            if cluster.name == self.cluster_to_deploy:
                logger.debug(f"Current state of packages: {cluster.extensions}")
                if cluster.extensions.prometheus.deployed:
                    logger.info("Prometheus package already deployed. Skipping deployment.")
                else:
                    version = self.common_workflow.get_available_package_version(cluster_name=self.cluster_to_deploy,
                                                                                 package=Constants.PROMETHEUS_PACKAGE,
                                                                                 name=Constants.PROMETHEUS_APP)

                    logger.info("Generating prometheus configuration template")
                    self.common_workflow.generate_spec_template(name=Constants.PROMETHEUS_APP,
                                                                package=Constants.PROMETHEUS_PACKAGE,
                                                                version=version,
                                                                template_path=Paths.REMOTE_PROMETHEUS_DATA_VALUES,
                                                                on_docker=self.run_config.spec.onDocker)

                    logger.info("Removing comments from prometheus-data-values.yml")
                    self.ssh.run_cmd(f"yq -i eval '... comments=\"\"' {Paths.REMOTE_PROMETHEUS_DATA_VALUES}")

                    self.common_workflow.install_package(cluster_name=self.cluster_to_deploy,
                                                         package=Constants.PROMETHEUS_PACKAGE,
                                                         namespace=clu.packagesTargetNamespace,
                                                         name=Constants.PROMETHEUS_APP, version=version,
                                                         values=Paths.REMOTE_PROMETHEUS_DATA_VALUES)
                    logger.debug(self.kubectl_client.get_all_pods())
                    logger.info('Prometheus installation complete')
                    self._update_state(task=Task.DEPLOY_PROMETHEUS,
                                       msg=f'Prometheus installation complete on {self.cluster_to_deploy}')

    @log("Installing grafana package")
    def _install_grafana_package(self, spec: GrafanaSpec):
        for cluster in self.run_config.state.workload_clusters:
            if cluster.name == self.cluster_to_deploy:
                logger.debug(f"Current state of packages: {cluster.extensions}")
                if cluster.extensions.grafana.deployed:
                    logger.info("Grafana package already deployed. Skipping deployment.")
                else:
                    version = self.common_workflow.get_available_package_version(cluster_name=self.cluster_to_deploy,
                                                                                 package=Constants.GRAFANA_PACKAGE,
                                                                                 name=Constants.GRAFANA_APP)

                    logger.info("Generating Grafana configuration template")
                    self.common_workflow.generate_spec_template(name=Constants.GRAFANA_APP,
                                                                package=Constants.GRAFANA_PACKAGE,
                                                                version=version,
                                                                template_path=Paths.REMOTE_GRAFANA_DATA_VALUES,
                                                                on_docker=self.run_config.spec.onDocker)

                    logger.info("Updating Grafana admin password")
                    self._update_grafana_admin_password(spec=spec)

                    logger.info("Creating namespace for grafana")
                    self.kubectl_client.set_cluster_context(cluster_name=self.cluster_to_deploy)

                    logger.info("Updating namespace in grafana config file")
                    self._update_grafana_namespace(remote_file=Paths.REMOTE_GRAFANA_DATA_VALUES)

                    logger.info("Removing comments from grafana-data-values.yaml")
                    self.ssh.run_cmd(f"yq -i eval '... comments=\"\"' {Paths.REMOTE_GRAFANA_DATA_VALUES}")

                    self.common_workflow.install_package(cluster_name=self.cluster_to_deploy,
                                                         package=Constants.GRAFANA_PACKAGE,
                                                         namespace=self.run_config.spec.tkg.sharedService.packagesTargetNamespace,
                                                         name=Constants.GRAFANA_APP, version=version,
                                                         values=Paths.REMOTE_GRAFANA_DATA_VALUES)

                    logger.debug(self.kubectl_client.get_all_pods())
                    logger.info('Grafana installation complete')
                    self._update_state(task=Task.DEPLOY_GRAFANA,
                                       msg=f'Grafana installation complete on {self.cluster_to_deploy}')

    def _attach_cluster_to_tmc(self):
        if self.run_config.spec.integrations.tmc.isEnabled == 'false':
            logger.info("Integration of cluster with Tmc is not enabled. So skipping this task.")
        else:
            for cluster in self.run_config.state.workload_clusters:
                if cluster.name == self.cluster_to_deploy:
                    if cluster.integrations.tmc.attached:
                        logger.info("Cluster is already attached to Tmc.")
                    else:
                        if self.run_config.spec.integrations.tmc.clusterGroup == None:
                            cluster_group = 'default'
                        else:
                            cluster_group = self.run_config.spec.integrations.tmc.clusterGroup
                        self.common_workflow.attach_cluster_to_tmc(cluster_name=self.cluster_to_deploy, cluster_group=cluster_group, api_token=self.run_config.spec.integrations.tmc.apiToken)
                        self._update_state(task=Task.ATTACH_CLUSTER_TO_TMC,
                               msg=f'Cluster attachment to Tmc completed for {self.cluster_to_deploy}')

    @log("Deploying grafana extension")
    def _deploy_grafana(self, spec: GrafanaSpec):
        """
        Wrapper method for deploying grafana on Tanzu k8s cluster
        :return:
        """
        self.common_workflow.create_namespace_for_extension(
            namespace=Constants.TANZU_SYSTEM_MONITORING,
            config_file=Paths.GRAFANA_NAMESPACE_CONFIG,
            extension_name=Constants.GRAFANA_APP,
            work_dir=self.extensions_dir,
            sa_name=Constants.GRAFANA_SERVICE_ACCOUNT,
        )
        logger.info("Copying grafana-data-values yml")
        self.common_workflow.copy_config_file(
            work_dir=self.extensions_dir, source=Paths.GRAFANA_CONFIG_EXAMPLE, destination=Paths.GRAFANA_CONFIG
        )
        self._update_grafana_admin_password(spec=spec)
        self.common_workflow.create_secret_for_extension(
            secret_name=Constants.GRAFANA_DATA_VALUES,
            namespace=Constants.TANZU_SYSTEM_MONITORING,
            config_file=Paths.GRAFANA_CONFIG,
            work_dir=self.extensions_dir,
        )
        self.common_workflow.reconcile_extension(
            cluster_to_deploy=self.cluster_to_deploy,
            app_name=Constants.GRAFANA_APP,
            namespace=Constants.TANZU_SYSTEM_MONITORING,
            config_file=Paths.GRAFANA_EXTENSION_CONFIG,
            work_dir=self.extensions_dir,
        )
        logger.debug(self.kubectl_client.get_all_pods())
        self._update_state(task=Task.DEPLOY_GRAFANA, msg=f'Grafana installation complete on {self.cluster_to_deploy}')
        logger.info("Grafana installation complete")

    @log("Upgrading contour extension")
    def _upgrade_contour(self):
        """
        Wrapper method for upgrading contour on Tanzu k8s cluster
        :return:
        """
        self.common_workflow.delete_extension(cluster_name=self.cluster_to_deploy,
                                              extension_name=Constants.CONTOUR_APP,
                                              namespace=Constants.TANZU_SYSTEM_INGRESS)
        self.common_workflow.delete_tmc_extensions_mgr(cluster_name=self.cluster_to_deploy,
                                                       work_dir=self.prev_extensions_dir)
        self.common_workflow.install_kapp_controller(cluster_name=self.cluster_to_deploy, work_dir=self.extensions_dir)
        self.common_workflow.install_cert_manager(cluster_to_deploy=self.cluster_to_deploy,
                                                  work_dir=self.extensions_root)
        # TODO: Replace with modular approach + remove hardcoded current secret file name
        options = "-o 'go-template={{ index .data \"contour-data-values.yaml\" }}' | base64 -d > current-contour-data-values.yaml"
        self.kubectl_client.get_secret_details(secret_name=Constants.CONTOUR_DATA_VALUES,
                                               namespace=Constants.TANZU_SYSTEM_INGRESS,
                                               work_dir=self.extensions_dir,
                                               options=options)
        self.common_workflow.copy_config_file(work_dir=self.extensions_dir, source="current-contour-data-values.yaml",
                                              destination=Paths.VSPHERE_ALB_CONTOUR_CONFIG)
        self.common_workflow.update_secret_for_extension(secret_name=Constants.CONTOUR_DATA_VALUES,
                                                         namespace=Constants.TANZU_SYSTEM_INGRESS,
                                                         config_file=Paths.VSPHERE_ALB_CONTOUR_CONFIG,
                                                         work_dir=self.extensions_dir)
        self.common_workflow.reconcile_extension(app_name=Constants.CONTOUR_APP,
                                                 namespace=Constants.TANZU_SYSTEM_INGRESS,
                                                 config_file=Paths.CONTOUR_EXTENSION_CONFIG,
                                                 work_dir=self.extensions_dir,
                                                 cluster_to_deploy=self.cluster_to_deploy)
        logger.debug(self.kubectl_client.get_all_pods())
        logger.info('Contour upgrade complete')

    @log("Upgrading prometheus extension")
    def _upgrade_prometheus(self):
        """
        Wrapper method for upgrading prometheus on Tanzu k8s cluster
        :return:
        """
        # Extension objects are deleted when tmc ext mgr is deleted while contour upgrade
        # Not removing tmc extensions mgr here, since contour upgrade has already done that.
        self.common_workflow.install_kapp_controller(cluster_name=self.cluster_to_deploy, work_dir=self.extensions_dir)
        self.common_workflow.install_cert_manager(cluster_to_deploy=self.cluster_to_deploy,
                                                  work_dir=self.extensions_root)
        # TODO: Replace with modular approach + remove hardcoded current secret file name
        options = "-o 'go-template={{ index .data \"prometheus-data-values.yaml\" }}' | base64 -d > current-prometheus-data-values.yaml"
        self.kubectl_client.get_secret_details(secret_name=Constants.PROMETHEUS_DATA_VALUES,
                                               namespace=Constants.TANZU_SYSTEM_MONITORING,
                                               work_dir=self.extensions_dir,
                                               options=options)
        self.common_workflow.copy_config_file(work_dir=self.extensions_dir,
                                              source="current-prometheus-data-values.yaml",
                                              destination=Paths.PROMETHEUS_CONFIG)
        self.common_workflow.update_secret_for_extension(secret_name=Constants.PROMETHEUS_DATA_VALUES,
                                                         namespace=Constants.TANZU_SYSTEM_MONITORING,
                                                         config_file=Paths.PROMETHEUS_CONFIG,
                                                         work_dir=self.extensions_dir)
        self.common_workflow.reconcile_extension(app_name=Constants.PROMETHEUS_APP,
                                                 namespace=Constants.TANZU_SYSTEM_MONITORING,
                                                 config_file=Paths.PROMETHEUS_EXTENSION_CONFIG,
                                                 work_dir=self.extensions_dir,
                                                 cluster_to_deploy=self.cluster_to_deploy)
        logger.debug(self.kubectl_client.get_all_pods())
        logger.info('Prometheus upgrade complete')

    @log("Upgrading prometheus extension")
    def _upgrade_grafana(self):
        """
        Wrapper method for upgrading grafana on Tanzu k8s cluster
        :return:
        """
        # Extension objects are deleted when tmc ext mgr is deleted while contour upgrade
        # Not removing tmc extensions mgr here, since contour upgrade has already done that.
        self.common_workflow.install_kapp_controller(cluster_name=self.cluster_to_deploy, work_dir=self.extensions_dir)
        self.common_workflow.install_cert_manager(cluster_to_deploy=self.cluster_to_deploy,
                                                  work_dir=self.extensions_root)
        # TODO: Replace with modular approach + remove hardcoded current secret file name
        options = "-o 'go-template={{ index .data \"grafana-data-values.yaml\" }}' | base64 -d > current-grafana-data-values.yaml"
        self.kubectl_client.get_secret_details(secret_name=Constants.GRAFANA_DATA_VALUES,
                                               namespace=Constants.TANZU_SYSTEM_MONITORING,
                                               work_dir=self.extensions_dir,
                                               options=options)
        self.common_workflow.copy_config_file(work_dir=self.extensions_dir, source="current-grafana-data-values.yaml",
                                              destination=Paths.GRAFANA_CONFIG)
        self.common_workflow.update_secret_for_extension(secret_name=Constants.GRAFANA_DATA_VALUES,
                                                         namespace=Constants.TANZU_SYSTEM_MONITORING,
                                                         config_file=Paths.GRAFANA_CONFIG,
                                                         work_dir=self.extensions_dir)
        self.common_workflow.reconcile_extension(app_name=Constants.GRAFANA_APP,
                                                 namespace=Constants.TANZU_SYSTEM_MONITORING,
                                                 config_file=Paths.GRAFANA_EXTENSION_CONFIG,
                                                 work_dir=self.extensions_dir,
                                                 cluster_to_deploy=self.cluster_to_deploy)
        logger.debug(self.kubectl_client.get_all_pods())
        logger.info('Grafana upgrade complete')

    @log("Executing shared services cluster workflow for v1.3.x")
    def execute_workflow_1_3_x(self, task: Task):
        # TODO: check current state w.r.t status yml
        state = FileHelper.load_state(os.path.join(self.run_config.root_dir, Paths.STATE_PATH))
        logger.info("Infra state: %s", state)

        TanzuUtils(self.run_config.root_dir).push_config(logger)

        with SshHelper(
                self.run_config.spec.bootstrap.server, self.run_config.spec.bootstrap.username,
                CmdHelper.decode_password(self.run_config.spec.bootstrap.password),
                self.run_config.spec.onDocker
        ) as ssh:
            self.initialize_clients(ssh)

            for cluster in self.run_config.spec.tkg.workloadClusters:
                self.cluster_to_deploy = cluster.cluster.name
                if task == Task.DEPLOY_CLUSTER:
                    cluster_state = self.get_cluster_state()
                    if cluster_state and cluster_state.deployed:
                        logger.info("Workload cluster is deployed, and in version : %s", cluster_state.version)
                        continue

                    # generate tkg config from master spec
                    templated_spec = self._template_deploy_yaml(cluster)
                    local_spec_file = os.path.join(
                        self.run_config.root_dir, f"{self.cluster_to_deploy}-{Paths.VSPHERE_WORKLOAD_SERVICES_SPEC}"
                    )

                    logger.info(f"Writing templated spec to: {local_spec_file}")
                    FileHelper.dump_spec(templated_spec, local_spec_file)

                    ssh.copy_file(local_spec_file, Paths.TKG_WORKLOAD_CLUSTER_CONFIG_PATH)
                    self.common_workflow.deploy_tanzu_k8s_cluster(
                        cluster_to_deploy=self.cluster_to_deploy, file_path=Paths.TKG_WORKLOAD_CLUSTER_CONFIG_PATH
                    )
                    if self.run_config.desired_state.version.tkg == "1.3.0":
                        self.common_workflow.install_tmc_extensions_mgr(cluster_to_deploy=self.cluster_to_deploy,
                                                                        work_dir=self.extensions_dir)
                    elif self.run_config.desired_state.version.tkg == "1.3.1":
                        self.common_workflow.install_kapp_controller(cluster_name=self.cluster_to_deploy,
                                                                     work_dir=self.extensions_dir)
                    self._update_state(task=Task.DEPLOY_CLUSTER,
                                       msg=f"Successful Workload Cluster deployment [{self.cluster_to_deploy}]")
                    self.common_workflow.commit_kubeconfig(self.run_config.root_dir, "Workload")
                elif task == Task.DEPLOY_CERT_MANAGER:
                    self.common_workflow.install_cert_manager(
                        cluster_to_deploy=self.cluster_to_deploy, work_dir=self.extensions_root
                    )
                    logger.info('Cert manager installation complete')
                    self._update_state(task=Task.DEPLOY_CERT_MANAGER,
                                       msg=f'Cert manager installation complete on {self.cluster_to_deploy}')
                else:
                    if not cluster.extensionsSpec:
                        logger.warn(
                            "extensions_spec not found in workload services. No extensions/packages will be installed. ")
                    elif task == Task.DEPLOY_CONTOUR:
                        self._deploy_contour()
                    elif task == Task.DEPLOY_PROMETHEUS:
                        self._deploy_prometheus()
                    elif task == Task.DEPLOY_GRAFANA:
                        self._deploy_grafana(cluster.extensionsSpec.grafana)
                    else:
                        valid_tasks = [Task.DEPLOY_CLUSTER, Task.DEPLOY_CONTOUR, Task.DEPLOY_PROMETHEUS,
                                       Task.DEPLOY_GRAFANA]
                        err = f"Invalid task provided: {task}. Valid tasks: {valid_tasks}"
                        logger.error(err)
                        raise Exception(err)

        logger.info("Workload Cluster Workflow complete!")

    @log("Executing shared services cluster workflow for v1.4.x")
    def execute_workflow_1_4_x(self, task: Task):
        logger.info("infra state: %s", self.run_config.state)
        TanzuUtils(self.run_config.root_dir).push_config(logger)
        with SshHelper(self.run_config.spec.bootstrap.server, self.run_config.spec.bootstrap.username,
                       CmdHelper.decode_password(self.run_config.spec.bootstrap.password),
                       self.run_config.spec.onDocker) as ssh:
            self.initialize_clients(ssh)
            for cluster in self.run_config.spec.tkg.workloadClusters:
                self.cluster_to_deploy = cluster.cluster.name
                if task == Task.DEPLOY_CLUSTER:
                    cluster_state = self.get_cluster_state()
                    if cluster_state and cluster_state.deployed:
                        logger.info("Workload cluster is deployed, and in version : %s", cluster_state.version)
                        continue

                    # generate tkg config from master spec
                    templated_spec = self._template_deploy_yaml(cluster)
                    local_spec_file = os.path.join(
                        self.run_config.root_dir, f"{self.cluster_to_deploy}-{Paths.VSPHERE_WORKLOAD_SERVICES_SPEC}"
                    )

                    logger.info(f"Writing templated spec to: {local_spec_file}")
                    FileHelper.dump_spec(templated_spec, local_spec_file)

                    ssh.copy_file(local_spec_file, Paths.TKG_WORKLOAD_CLUSTER_CONFIG_PATH)
                    self.common_workflow.deploy_tanzu_k8s_cluster(
                        cluster_to_deploy=self.cluster_to_deploy, file_path=Paths.TKG_WORKLOAD_CLUSTER_CONFIG_PATH
                    )
                    self._update_state(task=Task.DEPLOY_CLUSTER,
                                       msg=f"Successful Workload Cluster deployment [{self.cluster_to_deploy}]")
                    self.common_workflow.commit_kubeconfig(self.run_config.root_dir, "Workload")
                elif task == Task.DEPLOY_CERT_MANAGER:
                    self._install_cert_manager_package()
                    logger.info('Cert manager package installation complete')
                    self._update_state(task=Task.DEPLOY_CERT_MANAGER,
                                       msg=f'Cert manager package installation complete on {self.cluster_to_deploy}')
                elif task == Task.ATTACH_CLUSTER_TO_TMC:
                    self._attach_cluster_to_tmc()
                else:
                    if not cluster.extensionsSpec:
                        logger.warn(
                            "extensions_spec not found in workload services. No extensions/packages will be installed. ")
                    elif task == Task.DEPLOY_CONTOUR:
                        self._install_contour_package()
                    elif task == Task.DEPLOY_PROMETHEUS:
                        self._install_prometheus_package(cluster)
                    elif task == Task.DEPLOY_GRAFANA:
                        self._install_grafana_package(cluster.extensionsSpec.grafana)
                    else:
                        valid_tasks = [Task.DEPLOY_CLUSTER, Task.DEPLOY_CERT_MANAGER, Task.DEPLOY_CONTOUR,
                                       Task.DEPLOY_PROMETHEUS, Task.DEPLOY_GRAFANA]
                        err = f"Invalid task provided: {task}. Valid tasks: {valid_tasks}"
                        logger.error(err)
                        raise Exception(err)

        logger.info("Workload Cluster Workflow complete!")

    def execute_workflow(self, task: Task):
        if self.run_config.desired_state.version.tkg < "1.4.0":
            self.execute_workflow_1_3_x(task)
        else:
            self.execute_workflow_1_4_x(task)

    @log("Execute Upgrade Workload cluster workflow")
    def upgrade_workflow(self):
        with SshHelper(
                self.run_config.spec.bootstrap.server, self.run_config.spec.bootstrap.username,
                CmdHelper.decode_password(self.run_config.spec.bootstrap.password),
                self.run_config.spec.onDocker
        ) as ssh:
            ssh.copy_file(self.kube_config, Paths.KUBE_CONFIG_TARGET_PATH)
            for cluster in self.run_config.spec.tkg.workloadClusters:
                self.cluster_to_deploy = cluster.cluster.name
                self.prev_version = next(
                    (c.version for c in self.run_config.state.workload_clusters if c.name == self.cluster_to_deploy),
                    None)
                self.prev_extensions_root = TKG_EXTENSIONS_ROOT[self.prev_version]
                self.prev_extensions_dir = Paths.TKG_EXTENSIONS_DIR.format(extensions_root=self.prev_extensions_root)
                if not self.get_cluster_state().deployed:
                    logger.error("Workload cluster is not deployed")
                if not self._pre_validate(self.get_cluster_state().version):
                    continue
                if self.run_config.desired_state.version.tkg < "1.4.0":
                    self.common_workflow.upgrade_k8s_cluster_1_3_x(cluster_name=self.cluster_to_deploy,
                                                                   mgmt_cluster_name=self.run_config.spec.tkg.management.cluster.name)
                else:
                    self.common_workflow.upgrade_k8s_cluster_1_4_x(cluster_name=self.cluster_to_deploy,
                                                                   mgmt_cluster_name=self.run_config.spec.tkg.management.cluster.name)
                # todo add validation to check if wl cluster is updated

                self._upgrade_contour()
                if cluster.extensionsSpec:
                    self._upgrade_prometheus()
                    self._upgrade_grafana()
                else:
                    logger.warn(f"extensions_spec not found in {self.cluster_to_deploy} spec. No extensions will be "
                                f"upgraded. ")

                self._update_state(task=Task.UPGRADE_CLUSTER,
                                   msg=f"Successful workload cluster upgrade [{self.cluster_to_deploy}]")
                self.common_workflow.commit_kubeconfig(self.run_config.root_dir, "upgrade workload")
