import os
from pathlib import Path
import traceback

from constants.constants import (TKG_EXTENSIONS_ROOT, Constants,
                                 KubectlCommands, Paths, Task)
from jinja2 import Template
from lib.kubectl_client import KubectlClient
from lib.tkg_cli_client import TkgCliClient
from model.run_config import RunConfig
from model.status import (ExtensionState, HealthEnum, SharedExtensionState,
                          State)
from util.cmd_helper import CmdHelper
from util.file_helper import FileHelper
from util.git_helper import Git
from util.logger_helper import LoggerHelper, log, log_debug
from util.ssh_helper import SshHelper
from util.tanzu_utils import TanzuUtils
from util.cmd_runner import RunCmd

from workflows.cluster_common_workflow import ClusterCommonWorkflow

logger = LoggerHelper.get_logger(Path(__file__).stem)


class SharedClusterWorkflow:
    def __init__(self, run_config: RunConfig):
        self.run_config = run_config
        self.extensions_root = TKG_EXTENSIONS_ROOT[self.run_config.desired_state.version.tkg]
        self.extensions_dir = Paths.TKG_EXTENSIONS_DIR.format(extensions_root=self.extensions_root)
        self.cluster_to_deploy = self.run_config.spec.tkg.sharedService.cluster.name
        # Specifies current running version as per state.yml
        self.current_version = self.run_config.state.shared_services.version
        self.prev_version = self.run_config.state.shared_services.upgradedFrom or self.run_config.state.shared_services.version
        self.tkg_cli_client: TkgCliClient = None
        self.kubectl_client: KubectlClient = None
        self.ssh: SshHelper = None
        self.runcmd: RunCmd = None
        self.common_workflow: ClusterCommonWorkflow = None
        self._pre_validate()
        # Following values must be set in upgrade scenarios
        self.prev_extensions_root = None
        self.prev_extensions_dir = None

    @log_debug
    def _template_deploy_yaml(self):
        deploy_yaml = FileHelper.read_resource(Paths.VSPHERE_SHARED_SERVICES_SPEC_J2)
        t = Template(deploy_yaml)
        return t.render(spec=self.run_config.spec)

    @log_debug
    def _check_services_role(self, cluster):
        return Constants.TANZU_SERVICES_ROLE in cluster['roles']

    def _pre_validate(self):
        if self.run_config.state.shared_services.deployed:
            logger.info("Shared service cluster is deployed, and in version : %s", self.current_version)
            if self.current_version == self.run_config.desired_state.version.tkg:
                logger.info("Shared service cluster is already on correct version(%s)", self.current_version)
                return
            if self.current_version not in self.run_config.support_matrix["matrix"].keys():
                raise ValueError(f"Current Tanzu version({self.current_version}) is unsupported")

            if self.run_config.desired_state.version.tkg < self.current_version:
                raise ValueError(
                    f"Downgrading version is not possible[from: {self.current_version}, to: {self.run_config.desired_state.version.tkg}]"
                )

            if self.run_config.desired_state.version.tkg not in self.run_config.support_matrix["matrix"].keys():
                raise ValueError(f"Desired Tanzu version({self.run_config.desired_state.version.tkg}) is unsupported")

            if self.run_config.desired_state.version.tkg not in self.run_config.support_matrix["upgrade_path"].get(
                    self.current_version):
                raise ValueError(f"There are no upgrade path available for tkg: {self.current_version}")

    def initialize_clients(self, runcmd):
        if not self.tkg_cli_client:
            self.tkg_cli_client = TkgCliClient(runcmd)
        if not self.kubectl_client:
            self.kubectl_client = KubectlClient(runcmd)
        # if not self.ssh:
        #     self.ssh = ssh
        if not self.common_workflow:
            self.common_workflow = ClusterCommonWorkflow(runcmd)

    @log("Updating state file")
    def _update_state(self, task: Task, msg="Successful shared cluster deployment"):
        state_file_path = os.path.join(self.run_config.root_dir, Paths.STATE_PATH)
        state: State = FileHelper.load_state(state_file_path)
        if task == Task.DEPLOY_CLUSTER:
            state.shared_services.deployed = True
            state.shared_services.name = self.cluster_to_deploy
            state.shared_services.version = self.run_config.desired_state.version.tkg
            state.shared_services.health = HealthEnum.UP
        elif task == Task.UPGRADE_CLUSTER:
            ext_state = ExtensionState(deployed=True, upgraded=False)
            state.shared_services.upgradedFrom = state.shared_services.version
            state.shared_services.version = self.run_config.desired_state.version.tkg
            state.shared_services.name = self.cluster_to_deploy
            state.shared_services.health = HealthEnum.UP
            state.shared_services.extensions = SharedExtensionState(certManager=ext_state, contour=ext_state,
                                                                    externalDns=ext_state, harbor=ext_state)
        elif task == Task.DEPLOY_CERT_MANAGER or task == Task.UPGRADE_CERT_MANAGER:
            state.shared_services.extensions.certManager = ExtensionState(deployed=True, upgraded=True)
        elif task == Task.DEPLOY_CONTOUR or task == Task.UPGRADE_CONTOUR:
            state.shared_services.extensions.contour = ExtensionState(deployed=True, upgraded=True)
        elif task == Task.DEPLOY_EXTERNAL_DNS or task == Task.UPGRADE_EXTERNAL_DNS:
            state.shared_services.extensions.externalDns = ExtensionState(deployed=True, upgraded=True)
        elif task == Task.DEPLOY_HARBOR or task == Task.UPGRADE_HARBOR:
            state.shared_services.extensions.harbor = ExtensionState(deployed=True, upgraded=True)
        elif task == Task.ATTACH_CLUSTER_TO_TMC:
            state.shared_services.integrations.tmc.attached = True

        FileHelper.dump_state(state, state_file_path)
        Git.add_all_and_commit(os.path.dirname(state_file_path), msg)

    @log("Adding shared services label")
    def _add_shared_services_label(self):
        cluster_list = self.tkg_cli_client.get_cluster_details(self.cluster_to_deploy)

        if any(cluster_list) and self._check_services_role(cluster_list[0]):
            logger.info(f'Services label already set for cluster: {self.cluster_to_deploy}')
        else:
            self.kubectl_client.add_services_label(cluster_name=self.cluster_to_deploy,
                                                   mgmt_cluster_name=self.run_config.spec.tkg.management.cluster.name)

            cluster_list = self.tkg_cli_client.get_cluster_details(self.cluster_to_deploy)
            if any(cluster_list) and not self._check_services_role(cluster_list[0]):
                err_msg = f'Services label not set for cluster: {self.cluster_to_deploy}'
                logger.error(err_msg)
                raise Exception(err_msg)

    @log("Generating harbor passwords")
    def _generate_harbor_passwords(self):
        cmd = f"""
                cd {self.extensions_dir};
                bash {Paths.HARBOR_GENERATE_PASSWORDS} {Paths.HARBOR_CONFIG}
                """
        # self.ssh.run_cmd(cmd)
        self.runcmd.run_cmd_only(cmd)

    def _update_harbor_data_values(self, remote_file):

        local_file = Paths.LOCAL_HARBOR_DATA_VALUES.format(root_dir=self.run_config.root_dir)

        logger.info(f"Fetching and saving data values yml to {local_file}")
        # self.ssh.copy_file_from_remote(remote_file, local_file)
        self.runcmd.local_file_copy(remote_file, local_file)

        harbor_spec = self.run_config.spec.tkg.sharedService.extensionsSpec.harbor

        logger.info(f"Updating admin password in local copy of harbor-data-values.yaml")
        # Replacing string with pattern matching instead of loading yaml because comments
        # in yaml file will be lost during boxing/unboxing of yaml data
        replacement_list = [(Constants.HARBOR_ADMIN_PASSWORD_TOKEN,
                             Constants.HARBOR_ADMIN_PASSWORD_SUB.format(password=harbor_spec.adminPassword)),
                            (Constants.HARBOR_HOSTNAME_TOKEN,
                             Constants.HARBOR_HOSTNAME_SUB.format(hostname=harbor_spec.hostname))]
        logger.debug(f"Replacement spec: {replacement_list}")
        FileHelper.replace_pattern(src=local_file, target=local_file, pattern_replacement_list=replacement_list)

        logger.info(f"Updating harbor-data-values.yaml on bootstrap VM")
        # self.ssh.copy_file(local_file, remote_file)
        self.runcmd.local_file_copy(local_file, remote_file)

    @log("Getting harbor CA certificate")
    def _get_harbor_ca_cert(self, namespace):
        options = KubectlCommands.FILTER_JSONPATH.format(template="\"{.data.ca\\.crt}\"")
        output = self.kubectl_client.get_harbor_cert(namespace=namespace, options=options)
        filename = Paths.LOCAL_HARBOR_CA_CERT.format(root_dir=self.run_config.root_dir)
        logger.info(f"Saving harbor cert to {filename}")
        FileHelper.write_to_file(content=CmdHelper.decode_base64(output), file=filename)

    def _update_external_dns_data_values(self, remote_file):
        local_file = Paths.LOCAL_EXTERNAL_DNS_DATA_VALUES.format(root_dir=self.run_config.root_dir)

        logger.info(f"Fetching and saving data values yml to {local_file}")
        # self.ssh.copy_file_from_remote(remote_file, local_file)
        self.runcmd.local_file_copy(remote_file, local_file)

        dns_spec = self.run_config.spec.tkg.sharedService.extensionsSpec.externalDnsRfc2136

        logger.info(f"Updating values in local copy of external-dns-data-values.yaml")
        # Replacing string with pattern matching instead of loading yaml because comments
        # in yaml file will be lost during boxing/unboxing of yaml data
        replacement_list = [(Constants.RFC2136_DNS_SERVER_TOKEN,
                             Constants.RFC2136_DNS_SERVER_SUB.format(server=dns_spec.dnsServer)),
                            (Constants.RFC2136_DNS_DOMAIN_TOKEN,
                             Constants.RFC2136_DNS_DOMAIN_SUB.format(domain=dns_spec.domainName)),
                            (Constants.RFC2136_DNS_TSIG_KEY_TOKEN,
                             Constants.RFC2136_DNS_TSIG_KEY_SUB.format(tsig_key=dns_spec.tsigKeyName)),
                            (Constants.RFC2136_DNS_TSIG_SECRET_TOKEN,
                             Constants.RFC2136_DNS_TSIG_SECRET_SUB.format(tsig_secret=dns_spec.tsigSecret))
                            ]
        logger.debug(f"Replacement spec: {replacement_list}")
        FileHelper.replace_pattern(src=local_file, target=local_file, pattern_replacement_list=replacement_list)

        logger.info(f"Updating external-dns-data-values.yaml on bootstrap VM")
        # self.ssh.copy_file(local_file, remote_file)
        self.runcmd.local_file_copy(local_file, remote_file)

    def _install_cert_manager_package(self):
        logger.debug(f"Current state of packages: {self.run_config.state.shared_services.extensions}")
        if self.run_config.state.shared_services.extensions.certManager.deployed:
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
            msg = f'Cert manager installation complete on {self.cluster_to_deploy}'
            logger.info(msg)
            self._update_state(task=Task.DEPLOY_CERT_MANAGER, msg=msg)

    def _install_contour_package(self):
        logger.debug(f"Current state of packages: {self.run_config.state.shared_services.extensions}")
        if self.run_config.state.shared_services.extensions.contour.deployed:
            logger.info("Contour package already deployed. Skipping deployment.")
        else:
            version = self.common_workflow.get_available_package_version(cluster_name=self.cluster_to_deploy,
                                                                         package=Constants.CONTOUR_PACKAGE,
                                                                         name=Constants.CONTOUR_DISPLAY_NAME)

            logger.info("Copying contour-data-values.yml")
            # self.ssh.copy_file(Paths.LOCAL_VSPHERE_ALB_CONTOUR_CONFIG, Paths.REMOTE_VSPHERE_ALB_CONTOUR_CONFIG)
            self.runcmd.local_file_copy(Paths.LOCAL_VSPHERE_ALB_CONTOUR_CONFIG,
                                        Paths.REMOTE_VSPHERE_ALB_CONTOUR_CONFIG)

            self.common_workflow.install_package(cluster_name=self.cluster_to_deploy, package=Constants.CONTOUR_PACKAGE,
                                                 namespace=self.run_config.spec.tkg.sharedService.packagesTargetNamespace,
                                                 name=Constants.CONTOUR_APP, version=version,
                                                 values=Paths.REMOTE_VSPHERE_ALB_CONTOUR_CONFIG)
            logger.debug(self.kubectl_client.get_all_pods())
            msg = f'Contour installation complete on {self.cluster_to_deploy}'
            logger.info(msg)
            self._update_state(task=Task.DEPLOY_CONTOUR, msg=msg)

    def _install_external_dns_package(self):
        if not self.run_config.spec.tkg.sharedService.extensionsSpec.externalDnsRfc2136:
            logger.info("External DNS spec not found. Skipping installation.")
            return
        logger.debug(f"Current state of package: {self.run_config.state.shared_services.extensions}")
        if self.run_config.state.shared_services.extensions.externalDns.deployed:
            logger.info("External DNS package already deployed. Skipping deployment.")
        else:
            version = self.common_workflow.get_available_package_version(cluster_name=self.cluster_to_deploy,
                                                                         package=Constants.EXTERNAL_DNS_PACKAGE,
                                                                         name=Constants.EXTERNAL_DNS_DISPLAY_NAME)

            logger.info("Copying external-dns-data-values.yaml")
            # self.ssh.copy_file(Paths.LOCAL_EXTERNAL_DNS_WITH_CONTOUR, Paths.REMOTE_EXTERNAL_DNS_WITH_CONTOUR)
            self.runcmd.local_file_copy(Paths.LOCAL_EXTERNAL_DNS_WITH_CONTOUR, Paths.REMOTE_EXTERNAL_DNS_WITH_CONTOUR)

            self._update_external_dns_data_values(remote_file=Paths.REMOTE_EXTERNAL_DNS_WITH_CONTOUR)

            self.common_workflow.install_package(cluster_name=self.cluster_to_deploy,
                                                 package=Constants.EXTERNAL_DNS_PACKAGE,
                                                 namespace=self.run_config.spec.tkg.sharedService.packagesTargetNamespace,
                                                 name=Constants.EXTERNAL_DNS_APP, version=version,
                                                 values=Paths.REMOTE_EXTERNAL_DNS_WITH_CONTOUR)
            logger.debug(self.kubectl_client.get_all_pods())
            msg = f'External DNS installation complete on {self.cluster_to_deploy}'
            logger.info(msg)
            self._update_state(task=Task.DEPLOY_EXTERNAL_DNS, msg=msg)

    def _install_harbor_package(self):
        logger.debug(f"Current state of package: {self.run_config.state.shared_services.extensions}")
        if self.run_config.state.shared_services.extensions.harbor.deployed:
            logger.info("Harbor package already deployed. Skipping deployment.")
        else:
            version = self.common_workflow.get_available_package_version(cluster_name=self.cluster_to_deploy,
                                                                         package=Constants.HARBOR_PACKAGE,
                                                                         name=Constants.HARBOR_DISPLAY_NAME)

            logger.info("Generating Harbor configuration template")
            self.common_workflow.generate_spec_template(name=Constants.HARBOR_APP, package=Constants.HARBOR_PACKAGE,
                                                        version=version, template_path=Paths.REMOTE_HARBOR_DATA_VALUES,
                                                        on_docker=self.run_config.spec.onDocker)

            logger.info("Updating data values based on inputs")
            self._update_harbor_data_values(remote_file=Paths.REMOTE_HARBOR_DATA_VALUES)

            logger.info("Removing comments from harbor-data-values.yaml")
            # self.ssh.run_cmd(f"yq -i eval '... comments=\"\"' {Paths.REMOTE_HARBOR_DATA_VALUES}")
            self.runcmd.run_cmd_only(f"yq -i eval '... comments=\"\"' {Paths.REMOTE_HARBOR_DATA_VALUES}")

            self.common_workflow.install_package(cluster_name=self.cluster_to_deploy, package=Constants.HARBOR_PACKAGE,
                                                 namespace=self.run_config.spec.tkg.sharedService.packagesTargetNamespace,
                                                 name=Constants.HARBOR_APP, version=version,
                                                 values=Paths.REMOTE_HARBOR_DATA_VALUES)
            logger.debug(self.kubectl_client.get_all_pods())
            logger.info('Harbor installation complete')
            self._update_state(task=Task.DEPLOY_HARBOR,
                               msg=f'Harbor installation complete on {self.cluster_to_deploy}')

    def _attach_cluster_to_tmc(self):
        if self.spec.integrations.tmc.isEnabled == 'false':
            logger.info("Integration of cluster with Tmc is not enabled. So skipping this task.")
        else:
            if self.state.shared_services.integrations.tmc.attached:
                logger.info("Cluster is already attached to Tmc.")
            else:
                if self.spec.integrations.tmc.clusterGroup is None:
                    cluster_group = 'default'
                else:
                    cluster_group = self.spec.integrations.tmc.clusterGroup
                self.common_workflow.attach_cluster_to_tmc(cluster_name=self.cluster_to_deploy, cluster_group=cluster_group, api_token=self.spec.integrations.tmc.apiToken)
                self._update_state(task=Task.ATTACH_CLUSTER_TO_TMC,
                               msg=f'Cluster attachment to Tmc completed for {self.cluster_to_deploy}')

    @log("Deploying contour extension")
    def _deploy_contour(self):
        """
        Wrapper method for deploying contour on Tanzu k8s cluster
        :return:
        """
        logger.debug(f"Current state of extensions: {self.run_config.state.shared_services.extensions}")
        if self.run_config.state.shared_services.extensions.contour.deployed:
            logger.info("Contour extension already deployed. Skipping deployment.")
        else:
            self.common_workflow.create_namespace_for_extension(namespace=Constants.TANZU_SYSTEM_INGRESS,
                                                                config_file=Paths.CONTOUR_NAMESPACE_CONFIG,
                                                                extension_name=Constants.CONTOUR_APP,
                                                                work_dir=self.extensions_dir,
                                                                sa_name=Constants.CONTOUR_SERVICE_ACCOUNT)
            logger.info('Copying contour-data-values yml')
            self.common_workflow.copy_config_file(work_dir=self.extensions_dir,
                                                  source=Paths.VSPHERE_ALB_CONTOUR_CONFIG_EXAMPLE,
                                                  destination=Paths.VSPHERE_ALB_CONTOUR_CONFIG)
            self.common_workflow.create_secret_for_extension(secret_name=Constants.CONTOUR_DATA_VALUES,
                                                             namespace=Constants.TANZU_SYSTEM_INGRESS,
                                                             config_file=Paths.VSPHERE_ALB_CONTOUR_CONFIG,
                                                             work_dir=self.extensions_dir)
            self.common_workflow.reconcile_extension(app_name=Constants.CONTOUR_APP,
                                                     namespace=Constants.TANZU_SYSTEM_INGRESS,
                                                     config_file=Paths.CONTOUR_EXTENSION_CONFIG,
                                                     work_dir=self.extensions_dir,
                                                     cluster_to_deploy=self.cluster_to_deploy)
            logger.debug(self.kubectl_client.get_all_pods())
            logger.info('Contour installation complete')
            self._update_state(task=Task.DEPLOY_CONTOUR,
                               msg=f'Contour installation complete on {self.cluster_to_deploy}')
            self.common_workflow.commit_kubeconfig(self.run_config.root_dir, "contour service for shared")

    def _deploy_external_dns(self):
        """
        Wrapper method for deploying external DNS extension on Tanzu k8s shared cluster
        :return:
        """
        if not self.run_config.spec.tkg.sharedService.extensionsSpec.externalDnsRfc2136:
            logger.info("External DNS spec not found. Skipping installation.")
            return
        logger.debug(f"Current state of extensions: {self.run_config.state.shared_services.extensions}")
        if self.run_config.state.shared_services.extensions.externalDns.deployed:
            logger.info("External DNS extension already deployed. Skipping deployment.")
        else:
            self.common_workflow.install_kapp_controller(cluster_name=self.cluster_to_deploy,
                                                         work_dir=self.extensions_dir)
            self.common_workflow.create_namespace_for_extension(namespace=Constants.TANZU_SYSTEM_SERVICE_DISCOVERY,
                                                                config_file=Paths.EXTERNAL_DNS_NAMESPACE_CONFIG,
                                                                extension_name=Constants.EXTERNAL_DNS_APP,
                                                                work_dir=self.extensions_dir,
                                                                sa_name=Constants.EXTERNAL_DNS_SERVICE_ACCOUNT)
            logger.info('Copying external-dns-data-values yml')
            self.common_workflow.copy_config_file(work_dir=self.extensions_dir,
                                                  source=Paths.EXTERNAL_DNS_WITH_CONTOUR_EXAMPLE,
                                                  destination=Paths.EXTERNAL_DNS_CONFIG)
            self._update_external_dns_data_values(
                remote_file=os.path.join(self.extensions_dir, Paths.EXTERNAL_DNS_CONFIG))
            self.common_workflow.create_secret_for_extension(secret_name=Constants.EXTERNAL_DNS_DATA_VALUES,
                                                             namespace=Constants.TANZU_SYSTEM_SERVICE_DISCOVERY,
                                                             config_file=Paths.EXTERNAL_DNS_CONFIG,
                                                             work_dir=self.extensions_dir)
            self.common_workflow.reconcile_extension(app_name=Constants.EXTERNAL_DNS_APP,
                                                     namespace=Constants.TANZU_SYSTEM_SERVICE_DISCOVERY,
                                                     config_file=Paths.EXTERNAL_DNS_EXTENSION_CONFIG,
                                                     work_dir=self.extensions_dir,
                                                     cluster_to_deploy=self.cluster_to_deploy)
            logger.debug(self.kubectl_client.get_all_pods())
            logger.info('External DNS installation complete')
            self._update_state(task=Task.DEPLOY_EXTERNAL_DNS,
                               msg=f'External DNS installation complete on {self.cluster_to_deploy}')
            self.common_workflow.commit_kubeconfig(self.run_config.root_dir, "External dns service for shared")

    @log("Deploying harbor extension")
    def _deploy_harbor(self):
        """
        Wrapper method for deploying harbor on Tanzu k8s shared cluster
        :return:
        """
        logger.debug(f"Current state of extensions: {self.run_config.state.shared_services.extensions}")
        if self.run_config.state.shared_services.extensions.harbor.deployed:
            logger.info("Harbor extension already deployed. Skipping deployment.")
        else:
            self.common_workflow.create_namespace_for_extension(namespace=Constants.TANZU_SYSTEM_REGISTRY,
                                                                config_file=Paths.HARBOR_NAMESPACE_CONFIG,
                                                                extension_name=Constants.HARBOR_APP,
                                                                work_dir=self.extensions_dir,
                                                                sa_name=Constants.HARBOR_SERVICE_ACCOUNT)
            logger.info('Copying harbor-data-values yml')
            self.common_workflow.copy_config_file(work_dir=self.extensions_dir,
                                                  source=Paths.HARBOR_CONFIG_EXAMPLE,
                                                  destination=Paths.HARBOR_CONFIG)
            self._generate_harbor_passwords()
            self._update_harbor_data_values(remote_file=os.path.join(self.extensions_dir, Paths.HARBOR_CONFIG))
            self.common_workflow.create_secret_for_extension(secret_name=Constants.HARBOR_DATA_VALUES,
                                                             namespace=Constants.TANZU_SYSTEM_REGISTRY,
                                                             config_file=Paths.HARBOR_CONFIG,
                                                             work_dir=self.extensions_dir)
            self.common_workflow.reconcile_extension(app_name=Constants.HARBOR_APP,
                                                     namespace=Constants.TANZU_SYSTEM_REGISTRY,
                                                     config_file=Paths.HARBOR_EXTENSION_CONFIG,
                                                     work_dir=self.extensions_dir,
                                                     cluster_to_deploy=self.cluster_to_deploy)
            logger.debug(self.kubectl_client.get_all_pods())
            self._get_harbor_ca_cert(namespace=Constants.TANZU_SYSTEM_REGISTRY)
            msg = f'Harbor installation complete on {self.cluster_to_deploy}'
            logger.info(msg)
            self._update_state(task=Task.DEPLOY_HARBOR, msg=msg)
            self.common_workflow.commit_kubeconfig(self.run_config.root_dir, msg)

    @log("Upgrading contour extension")
    def _upgrade_contour(self):
        """
        Wrapper method for upgrading contour on Tanzu k8s cluster
        :return: 
        """
        logger.debug(f"Current state of extensions: {self.run_config.state.shared_services.extensions}")
        contour_state = self.run_config.state.shared_services.extensions.contour
        logger.debug(f"Current state of extensions: {self.run_config.state.shared_services.extensions}")
        if contour_state.deployed:
            if contour_state.upgraded:
                logger.info("Contour extension already upgraded. Skipping upgrade.")
            else:
                # self.common_workflow.delete_extension(cluster_name=self.cluster_to_deploy,
                #                                       extension_name=Constants.CONTOUR_APP,
                #                                       namespace=Constants.TANZU_SYSTEM_INGRESS)
                self.common_workflow.delete_tmc_extensions_mgr(cluster_name=self.cluster_to_deploy,
                                                               work_dir=self.prev_extensions_dir)
                self.common_workflow.install_kapp_controller(cluster_name=self.cluster_to_deploy,
                                                             work_dir=self.extensions_dir)
                self.common_workflow.install_cert_manager(cluster_to_deploy=self.cluster_to_deploy,
                                                          work_dir=self.extensions_root)
                self._update_state(task=Task.UPGRADE_CERT_MANAGER,
                                   msg=f"Cert Manager upgrade complete on {self.cluster_to_deploy}")
                # TODO: Replace with modular approach + remove hardcoded current secret file name
                options = "-o 'go-template={{ index .data \"contour-data-values.yaml\" }}' | base64 -d > current-contour-data-values.yaml"
                self.kubectl_client.get_secret_details(secret_name=Constants.CONTOUR_DATA_VALUES,
                                                       namespace=Constants.TANZU_SYSTEM_INGRESS,
                                                       work_dir=self.extensions_dir,
                                                       options=options)
                self.common_workflow.copy_config_file(work_dir=self.extensions_dir,
                                                      source="current-contour-data-values.yaml",
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
                msg = f"Contour upgrade complete on {self.cluster_to_deploy}"
                logger.info(msg)
                self._update_state(task=Task.UPGRADE_CONTOUR, msg=msg)
                self.common_workflow.commit_kubeconfig(self.run_config.root_dir, msg)
        else:
            err = "Cannot upgrade Contour as it is not deployed"
            logger.error(err)
            raise Exception(err)

    @log("Upgrading external DNS extension")
    def _upgrade_external_dns(self):
        """
        Wrapper method for upgrading external DNS extension on Tanzu k8s cluster
        :return:
        """
        if not self.run_config.spec.tkg.sharedService.extensionsSpec.externalDnsRfc2136:
            logger.info("External DNS spec not found. Skipping upgrade.")
            return
        logger.debug(f"Current state of extensions: {self.run_config.state.shared_services.extensions}")
        dns_state = self.run_config.state.shared_services.extensions.externalDns
        logger.debug(f"Current state of extensions: {self.run_config.state.shared_services.extensions}")
        if dns_state.deployed:
            if dns_state.upgraded:
                logger.info("External DNS extension already upgraded. Skipping upgrade.")
            else:
                # Extension objects are deleted when tmc ext mgr is deleted while contour upgrade
                # self.common_workflow.delete_extension(cluster_name=self.cluster_to_deploy,
                #                                       extension_name=Constants.HARBOR_APP,
                #                                       namespace=Constants.TANZU_SYSTEM_REGISTRY)
                # Not removing tmc extensions mgr here, since contour upgrade has already done that.
                self.common_workflow.install_kapp_controller(cluster_name=self.cluster_to_deploy,
                                                             work_dir=self.extensions_dir)
                # TODO: Replace with modular approach + remove hardcoded current secret file name
                options = "-o 'go-template={{ index .data \"external-dns-data-values.yaml\" }}' | base64 -d > current-external-dns--data-values.yaml"
                self.kubectl_client.get_secret_details(secret_name=Constants.EXTERNAL_DNS_DATA_VALUES,
                                                       namespace=Constants.TANZU_SYSTEM_SERVICE_DISCOVERY,
                                                       work_dir=self.extensions_dir,
                                                       options=options)
                self.common_workflow.copy_config_file(work_dir=self.extensions_dir,
                                                      source="current-external-dns--data-values.yaml",
                                                      destination=Paths.EXTERNAL_DNS_CONFIG)
                self.common_workflow.update_secret_for_extension(secret_name=Constants.EXTERNAL_DNS_DATA_VALUES,
                                                                 namespace=Constants.TANZU_SYSTEM_SERVICE_DISCOVERY,
                                                                 config_file=Paths.EXTERNAL_DNS_CONFIG,
                                                                 work_dir=self.extensions_dir)
                self.common_workflow.reconcile_extension(app_name=Constants.EXTERNAL_DNS_APP,
                                                         namespace=Constants.TANZU_SYSTEM_SERVICE_DISCOVERY,
                                                         config_file=Paths.EXTERNAL_DNS_EXTENSION_CONFIG,
                                                         work_dir=self.extensions_dir,
                                                         cluster_to_deploy=self.cluster_to_deploy)
                logger.debug(self.kubectl_client.get_all_pods())
                msg = f"External DNS upgrade complete on {self.cluster_to_deploy}"
                logger.info(msg)
                self._update_state(task=Task.UPGRADE_EXTERNAL_DNS, msg=msg)
                self.common_workflow.commit_kubeconfig(self.run_config.root_dir, msg)
        else:
            err = "Cannot upgrade External DNS as it is not deployed"
            logger.error(err)
            raise Exception(err)

    @log("Upgrading harbor extension")
    def _upgrade_harbor(self):
        """
        Wrapper method for deploying harbor on Tanzu k8s shared cluster
        :return:
        """
        logger.debug(f"Current state of extensions: {self.run_config.state.shared_services.extensions}")
        harbor_state = self.run_config.state.shared_services.extensions.harbor
        if harbor_state.deployed:
            if harbor_state.upgraded:
                logger.info("Harbor extension already upgraded. Skipping upgrade.")
            else:
                # Extension objects are deleted when tmc ext mgr is deleted while contour upgrade
                # self.common_workflow.delete_extension(cluster_name=self.cluster_to_deploy,
                #                                       extension_name=Constants.HARBOR_APP,
                #                                       namespace=Constants.TANZU_SYSTEM_REGISTRY)
                # Not removing tmc extensions mgr here, since contour upgrade has already done that.
                self.common_workflow.install_kapp_controller(cluster_name=self.cluster_to_deploy,
                                                             work_dir=self.extensions_dir)
                # TODO: Replace with modular approach + remove hardcoded current secret file name
                options = "-o 'go-template={{ index .data \"harbor-data-values.yaml\" }}' | base64 -d > current-harbor-data-values.yaml"
                self.kubectl_client.get_secret_details(secret_name=Constants.HARBOR_DATA_VALUES,
                                                       namespace=Constants.TANZU_SYSTEM_REGISTRY,
                                                       work_dir=self.extensions_dir,
                                                       options=options)
                self.common_workflow.copy_config_file(work_dir=self.extensions_dir,
                                                      source="current-harbor-data-values.yaml",
                                                      destination=Paths.HARBOR_CONFIG)
                self.common_workflow.update_secret_for_extension(secret_name=Constants.HARBOR_DATA_VALUES,
                                                                 namespace=Constants.TANZU_SYSTEM_REGISTRY,
                                                                 config_file=Paths.HARBOR_CONFIG,
                                                                 work_dir=self.extensions_dir)
                self.common_workflow.reconcile_extension(app_name=Constants.HARBOR_APP,
                                                         namespace=Constants.TANZU_SYSTEM_REGISTRY,
                                                         config_file=Paths.HARBOR_EXTENSION_CONFIG,
                                                         work_dir=self.extensions_dir,
                                                         cluster_to_deploy=self.cluster_to_deploy)
                logger.debug(self.kubectl_client.get_all_pods())
                logger.info("Harbor upgrade complete")
                self._update_state(task=Task.UPGRADE_HARBOR, msg=f"Harbor upgrade complete on {self.cluster_to_deploy}")
                self.common_workflow.commit_kubeconfig(self.run_config.root_dir, "harbour ext service for shared")
        else:
            err = "Cannot upgrade Harbor as it is not deployed."
            logger.error(err)
            raise Exception(err)

    @log("Executing shared services cluster workflow for v1.3.x")
    def execute_workflow_1_3_x(self, task: Task):
        logger.info("infra state: %s", self.run_config.state)
        TanzuUtils(self.run_config.root_dir).push_config(logger)
        # with SshHelper(self.run_config.spec.bootstrap.server, self.run_config.spec.bootstrap.username,
        #                CmdHelper.decode_password(self.run_config.spec.bootstrap.password),
        #                self.run_config.spec.onDocker) as ssh:
        try:
            self.initialize_clients(self.runcmd)
            if task == Task.DEPLOY_CLUSTER:
                logger.debug(f"Current state of shared cluster: {self.run_config.state.shared_services}")
                if self.run_config.state.shared_services.deployed:
                    logger.info("Shared cluster is deployed, and in version : %s",
                                self.run_config.state.shared_services.version)
                    return
                # generate tkg config from master spec
                templated_spec = self._template_deploy_yaml()
                local_spec_file = os.path.join(self.run_config.root_dir, Paths.VSPHERE_SHARED_SERVICES_SPEC)

                logger.info(f'Writing templated spec to: {local_spec_file}')
                FileHelper.dump_spec(templated_spec, local_spec_file)
                # ssh.copy_file(local_spec_file, Paths.TKG_SHARED_SERVICES_CONFIG_PATH)
                self.runcmd.local_file_copy(local_spec_file, Paths.TKG_SHARED_SERVICES_CONFIG_PATH)
                self.common_workflow.deploy_tanzu_k8s_cluster(cluster_to_deploy=self.cluster_to_deploy,
                                                              file_path=Paths.TKG_SHARED_SERVICES_CONFIG_PATH)
                self._add_shared_services_label()
                if self.run_config.desired_state.version.tkg == "1.3.0":
                    self.common_workflow.install_tmc_extensions_mgr(cluster_to_deploy=self.cluster_to_deploy,
                                                                    work_dir=self.extensions_dir)
                elif self.run_config.desired_state.version.tkg == "1.3.1":
                    self.common_workflow.install_kapp_controller(cluster_name=self.cluster_to_deploy,
                                                                 work_dir=self.extensions_dir)

                self._update_state(task=task, msg=f"Successful Shared Cluster deployment [{self.cluster_to_deploy}]")
                self.common_workflow.commit_kubeconfig(self.run_config.root_dir, "shared")
            elif task == Task.DEPLOY_CERT_MANAGER:
                self.common_workflow.install_cert_manager(cluster_to_deploy=self.cluster_to_deploy,
                                                          work_dir=self.extensions_root)
                logger.info('Cert manager installation complete')
                self._update_state(task=Task.DEPLOY_CERT_MANAGER,
                                   msg=f'Cert manager installation complete on {self.cluster_to_deploy}')
            else:
                if not self.run_config.spec.tkg.sharedService.extensionsSpec:
                    logger.warn(
                        "extensions_spec not found in shared services. No extensions/packages will be installed. ")
                elif task == Task.DEPLOY_CONTOUR:
                    self._deploy_contour()
                elif task == Task.DEPLOY_EXTERNAL_DNS:
                    self._deploy_external_dns()
                elif task == Task.DEPLOY_HARBOR:
                    self._deploy_harbor()
                else:
                    valid_tasks = [Task.DEPLOY_CLUSTER, Task.DEPLOY_CONTOUR, Task.DEPLOY_EXTERNAL_DNS,
                                   Task.DEPLOY_HARBOR]
                    err = f"Invalid task provided: {task}. Valid tasks: {valid_tasks}"
                    logger.error(err)
                    raise Exception(err)
        except Exception:
            logger.error(f"{traceback.format_exc()}")

        logger.info('Shared Cluster Workflow complete!')

    @log("Executing shared services cluster workflow for v1.4.x")
    def execute_workflow_1_4_x(self, task: Task):
        logger.info("infra state: %s", self.run_config.state)
        TanzuUtils(self.run_config.root_dir).push_config(logger)
        # with SshHelper(self.run_config.spec.bootstrap.server, self.run_config.spec.bootstrap.username,
        #                CmdHelper.decode_password(self.run_config.spec.bootstrap.password),
        #                self.run_config.spec.onDocker) as ssh:
        try:
            self.runcmd: RunCmd = None
            self.initialize_clients(self.runcmd)
            if task == Task.DEPLOY_CLUSTER:
                logger.debug(f"Current state of shared cluster: {self.run_config.state.shared_services}")
                if self.run_config.state.shared_services.deployed:
                    logger.info("Shared cluster is deployed, and in version : %s",
                                self.run_config.state.shared_services.version)
                    return
                # generate tkg config from master spec
                templated_spec = self._template_deploy_yaml()
                local_spec_file = os.path.join(self.run_config.root_dir, Paths.VSPHERE_SHARED_SERVICES_SPEC)

                logger.info(f'Writing templated spec to: {local_spec_file}')
                FileHelper.dump_spec(templated_spec, local_spec_file)
                self.runcmd.local_file_copy(local_spec_file, Paths.TKG_SHARED_SERVICES_CONFIG_PATH)
                # ssh.copy_file(local_spec_file, Paths.TKG_SHARED_SERVICES_CONFIG_PATH)
                self.common_workflow.deploy_tanzu_k8s_cluster(cluster_to_deploy=self.cluster_to_deploy,
                                                              file_path=Paths.TKG_SHARED_SERVICES_CONFIG_PATH)
                self._add_shared_services_label()

                self._update_state(task=task, msg=f"Successful Shared Cluster deployment [{self.cluster_to_deploy}]")
                self.common_workflow.commit_kubeconfig(self.run_config.root_dir, "shared")
            elif task == Task.DEPLOY_CERT_MANAGER:
                self._install_cert_manager_package()
            elif task == Task.ATTACH_CLUSTER_TO_TMC:
                self._attach_cluster_to_tmc()
            else:
                if not self.run_config.spec.tkg.sharedService.extensionsSpec:
                    logger.warn(
                        "extensions_spec not found in shared services. No extensions/packages will be installed. ")
                elif task == Task.DEPLOY_CONTOUR:
                    self._install_contour_package()
                elif task == Task.DEPLOY_EXTERNAL_DNS:
                    self._install_external_dns_package()
                elif task == Task.DEPLOY_HARBOR:
                    self._install_harbor_package()
                else:
                    valid_tasks = [Task.DEPLOY_CLUSTER, Task.DEPLOY_CERT_MANAGER, Task.DEPLOY_CONTOUR,
                                   Task.DEPLOY_EXTERNAL_DNS, Task.DEPLOY_HARBOR]
                    err = f"Invalid task provided: {task}. Valid tasks: {valid_tasks}"
                    logger.error(err)
                    raise Exception(err)
        except Exception:
            logger.error(f"{traceback.format_exc()}")

        logger.info('Shared Cluster Workflow complete!')

    def execute_workflow(self, task: Task):
        if self.run_config.desired_state.version.tkg < "1.4.0":
            self.execute_workflow_1_3_x(task)
        else:
            self.execute_workflow_1_4_x(task)

    def upgrade_workflow(self, task: Task):
        # with SshHelper(self.run_config.spec.bootstrap.server, self.run_config.spec.bootstrap.username,
        #                CmdHelper.decode_password(self.run_config.spec.bootstrap.password),
        #                self.run_config.spec.onDocker) as ssh:
        try:
            self.initialize_clients(self.runcmd)
            self.prev_extensions_root = TKG_EXTENSIONS_ROOT[self.prev_version]
            self.prev_extensions_dir = Paths.TKG_EXTENSIONS_DIR.format(extensions_root=self.prev_extensions_root)
            if task == Task.UPGRADE_CLUSTER:
                logger.debug(f"Current state of shared cluster: {self.run_config.state.shared_services}")
                if self.current_version == self.run_config.desired_state.version.tkg:
                    logger.info("Shared service cluster is already on correct version(%s)", self.current_version)
                    return
                if self.run_config.desired_state.version.tkg < "1.4.0":
                    self.common_workflow.upgrade_k8s_cluster_1_3_x(cluster_name=self.cluster_to_deploy,
                                                                   mgmt_cluster_name=self.run_config.spec.tkg.management.cluster.name)
                else:
                    self.common_workflow.upgrade_k8s_cluster_1_4_x(cluster_name=self.cluster_to_deploy,
                                                                   mgmt_cluster_name=self.run_config.spec.tkg.management.cluster.name)

                self._update_state(task=task, msg=f"Successful Shared Cluster upgrade [{self.cluster_to_deploy}]")
                self.common_workflow.commit_kubeconfig(self.run_config.root_dir, "upgrade shared")
            else:
                if not self.run_config.spec.tkg.sharedService.extensionsSpec:
                    logger.warn("extensions_spec not found in shared services. No extensions will be upgraded. ")
                elif task == Task.UPGRADE_CONTOUR:
                    self._upgrade_contour()
                elif task == Task.UPGRADE_HARBOR:
                    self._upgrade_harbor()
                elif task == Task.UPGRADE_EXTERNAL_DNS:
                    self._upgrade_external_dns()
                else:
                    valid_tasks = [Task.UPGRADE_CLUSTER, Task.UPGRADE_CONTOUR, Task.UPGRADE_EXTERNAL_DNS,
                                   Task.UPGRADE_HARBOR]
                    err = f"Invalid task provided: {task}. Valid tasks: {valid_tasks}"
                    logger.error(err)
                    raise Exception(err)
            logger.info('Shared Cluster Workflow complete!')
        except Exception:
            logger.error(f"{traceback.format_exc()}")