import os
from pathlib import Path
from re import sub

from jinja2 import Template

from constants.constants import Constants, Paths, TKGCommands, ComponentPrefix, AkoType
from lib.tkg_cli_client import TkgCliClient
from model.run_config import RunConfig
from model.spec import Bootstrap
from model.status import HealthEnum, Info
from util.cmd_helper import CmdHelper
from util.file_helper import FileHelper
from util.git_helper import Git
from util.govc_helper import get_alb_ip_address
from util.logger_helper import LoggerHelper, log
from util.ssh_helper import SshHelper
from util.ssl_helper import get_base64_cert
from util.tanzu_utils import TanzuUtils
from workflows.cluster_common_workflow import ClusterCommonWorkflow
import subprocess
import shutil

logger = LoggerHelper.get_logger (Path (__file__).stem)


class MgmtClusterWorkflow:
    def __init__(self, run_config: RunConfig):
        self.run_config = run_config
        self.bootstrap: Bootstrap = self.run_config.spec.bootstrap
        self.cluster_name = self.run_config.spec.tkg.management.cluster.name
        self.tanzu_client = TkgCliClient()
        logger.info ("Current deployment state: %s", self.run_config.state)
        self._pre_validate ()

    @log ("generate tkg config from master spec")
    def _template_deploy_yaml(self):
        # todo: fix get ip to something better
        self.run_config.spec.avi.fqdn = get_alb_ip_address (self.run_config)
        deploy_yaml = FileHelper.read_resource (Paths.TKG_MGMT_SPEC_J2)
        t = Template (deploy_yaml)
        FileHelper.write_to_file (
            t.render (config=self.run_config,
                      avi_cert=get_base64_cert (self.run_config.spec.avi.fqdn),
                      avi_label_key=AkoType.KEY, avi_label_value=AkoType.VALUE,
                      cluster_vip_nw=ComponentPrefix.CLUSTER_VIP_NW),
            Paths.TKG_MGMT_DEPLOY_CONFIG)

    def _pre_validate(self):
        if self.run_config.state.mgmt.deployed:
            logger.info ("Management cluster is deployed, and in version : %s",
                         self.run_config.state.mgmt.version)
            if self.run_config.state.mgmt.version == self.run_config.desired_state.version.tkg:
                logger.info ("Management cluster is already on correct version(%s)",
                             self.run_config.state.mgmt.version)
                exit (0)
            if self.run_config.state.mgmt.version not in self.run_config.support_matrix[
                "matrix"].keys ():
                raise ValueError (
                    f"Current Tanzu version({self.run_config.state.mgmt.version}) is unsupported")

            # todo: version comparison change
            if self.run_config.desired_state.version.tkg < self.run_config.state.mgmt.version:
                raise ValueError (
                    f"""Downgrading version is not possible 
                    [from: {self.run_config.state.mgmt.version}, to: {self.run_config.desired_state.version.tkg}]""")

            if self.run_config.desired_state.version.tkg not in \
                    self.run_config.support_matrix["matrix"].keys ():
                raise ValueError (
                    f"Desired Tanzu version({self.run_config.desired_state.version.tkg}) is unsupported")

            if self.run_config.desired_state.version.tkg not in \
                    self.run_config.support_matrix["upgrade_path"].get (
                            self.run_config.state.mgmt.version):
                raise ValueError (
                    f"There are no upgrade path available for tkg: {self.run_config.state.mgmt.version}")

        elif self.run_config.desired_state.version.tkg not in \
                self.run_config.support_matrix["matrix"].keys ():
            raise ValueError (
                f"Tanzu version({self.run_config.desired_state.version.tkg}) specified in desired state is unsupported"
            )

        # with SshHelper(self.bootstrap.server, self.bootstrap.username,
        #                CmdHelper.decode_password(self.bootstrap.password),
        #                self.run_config.spec.onDocker) as ssh:
        #     code, version_raw = ssh.run_cmd_output(TKGCommands.VERSION)
        #     version = [line for line in version_raw.split("\n") if "version" in line][0]
        #     if not any(k in version for k in self.run_config.support_matrix["matrix"].keys()):
        #         raise ValueError(f"Tanzu cli version unsupported. \n{version}")

        #     if self.run_config.desired_state.version.tkg not in version:
        #         raise ValueError(
        #             f"Desired TKG version[{self.run_config.desired_state.version.tkg}] doesn't match tanzu cli version"
        #         )

    def _check_management_cluster_exists(self, cluster_name):
        try:
            cluster_list = self.tanzu_client.get_all_clusters ()
        except Exception as ex:
            logger.error ("Exception occurred: ", ex)
            return False
        mgmt_clu = [c for c in cluster_list if
                    Constants.MANAGEMENT_ROLE in c["roles"] and c[
                        "name"] == cluster_name]
        return any (mgmt_clu)

    @log ("Deploying management cluster")
    def deploy_mgmt_clu(self):
        if self.run_config.state.mgmt.deployed:
            logger.info ("Management cluster is deployed, and in version : %s",
                         self.run_config.state.mgmt.version)
            return
        self._template_deploy_yaml ()
        TanzuUtils (self.run_config.root_dir).push_config_without_errors (logger)
        # with SshHelper(self.bootstrap.server, self.bootstrap.username,
        #                CmdHelper.decode_password(self.bootstrap.password),
        #                self.run_config.spec.onDocker) as ssh:
        #     if not self.tanzu_client:
        #         self.tanzu_client = TkgCliClient(ssh)
        file_path = Paths.TKG_MGMT_CONFIG_PATH
        copy_cmd = "cp -rf {} {}".format (Paths.TKG_MGMT_DEPLOY_CONFIG, file_path)
        # subprocess.check_output(copy_cmd)
        # subprocess.run(cmd, stdout=subprocess.PIPE, input=ip)
        shutil.copyfile (Paths.TKG_MGMT_DEPLOY_CONFIG, file_path)
        # subprocess.run(copy_cmd)
        subprocess.check_output (TKGCommands.VERSION, shell=True)
        # subprocess.run(TKGCommands.VERSION)
        # ssh.run_cmd(TKGCommands.VERSION)
        cluster_name = self.run_config.spec.tkg.management.cluster.name
        logger.info ("Check if management cluster is already deployed..")

        # if self._check_management_cluster_exists(cluster_name=cluster_name):
        #     logger.warn("Management cluster already deployed")
        #     return
        # if self.run_config.desired_state.bomImageTag:
        #     tag = self.run_config.desired_state.bomImageTag
        #     logger.info(f"Updating BOM image tag: {tag}")
        #     # tanzu management-cluster create command will return exit
        #     1 status. This is expected.
        #     ssh.run_cmd(cmd=TKGCommands.UPDATE_TKG_BOM.format(bom_image_tag=tag),
        #     ignore_errors=True)
        # else:
        #     logger.warn(
        #         "bomImageTag not specified in desired_state.
        #         Deployment will use cli bundle's default BOM. "
        #         "Provide bomImageTag if any updated base image files are to be used."
        #     )
        subprocess.check_output (TKGCommands.MGMT_DEPLOY.format (file_path=file_path),
                                 shell=True)

        # if self.run_config.spec.tkg.management.ldap is not None:
        #     ClusterCommonWorkflow(ssh).check_app_reconciled("pinniped", "tkg-system")
        # ClusterCommonWorkflow(ssh).commit_kubeconfig(self.run_config.root_dir,
        # "management")

        # if self.run_config.desired_state.version.tkg == "1.3.1":
        #     self._register_tmc(ssh)

        self._update_state (
            msg=f"Successful management cluster deployment [{self.cluster_name}]")

    @log ("Updating state file")
    def _update_state(self, msg="Successful management cluster deployment"):
        state_file_path = os.path.join (self.run_config.root_dir, Paths.STATE_PATH)
        self.run_config.state.mgmt = Info (
            deployed=True, health=HealthEnum.UP,
            version=self.run_config.desired_state.version.tkg,
            name=self.cluster_name
        )
        FileHelper.dump_state (self.run_config.state, state_file_path)
        Git.add_all_and_commit (os.path.dirname (state_file_path), msg)

    def _register_tmc(self, ssh: SshHelper):
        if not self.run_config.spec.tkg.common.tmcRegistrationUrl:
            logger.info ("TMC registration url is empty, skipping tmc registration")
            return
        logger.info ("Registering management cluster to TMC")
        ssh.run_cmd (
            TKGCommands.REGISTER_TMC.format (
                url=self.run_config.spec.tkg.common.tmcRegistrationUrl),
            msg="TMC Registration successful."
        )

    @log ("Upgrading tanzu management cluster")
    def upgrade_mgmt_1_3_x(self, ssh, timeout="60m0s", verbose=True):
        logger.info ("Login with management context and cleanup")
        ssh.run_cmd (
            TKGCommands.MGMT_UPGRADE_CLEANUP.format (cluster_name=self.cluster_name),
            # it may fail but expected
            ignore_errors=True,
            msg="Cleanup Successful",
        )
        logger.info (f"Upgrade cluster: {self.cluster_name}")
        cmd_option = TKGCommands.TIMEOUT_OPTION.format (
            timeout=timeout) if timeout else ""
        cmd_option += " -v 9" if verbose else ""
        ssh.run_cmd (TKGCommands.MGMT_UPGRADE.format (options=cmd_option))

    @log ("Upgrading tanzu management cluster")
    def upgrade_mgmt_1_4_x(self):
        cluster = self.run_config.spec.tkg.management.cluster.name
        self.tanzu_client.login (cluster_name=cluster)
        self.tanzu_client.management_cluster_upgrade (cluster_name=cluster)
        if not self.tanzu_client.retriable_check_cluster_exists (cluster_name=cluster):
            msg = f"Cluster: {cluster} not in running state"
            logger.error (msg)
            raise Exception (msg)

    def upgrade_workflow(self):
        if not self.run_config.state.mgmt.deployed:
            logger.warn ("Management cluster is not deployed")
            # should not fail for day0
            return
        TanzuUtils (self.run_config.root_dir).push_config (logger)
        # with SshHelper (self.bootstrap.server, self.bootstrap.username,
        #                 CmdHelper.decode_password (self.bootstrap.password),
        #                 self.run_config.spec.onDocker) as ssh:
        #     if not self.tanzu_client:
        #         self.tanzu_client = TkgCliClient (ssh)
        #     # todo: backup old kube config
        self.upgrade_mgmt_1_4_x ()
        # todo: check if pods are up and running
        # ClusterCommonWorkflow (ssh).commit_kubeconfig (self.run_config.root_dir,
                                                        #    "management")
        self._update_state (
            f"Successful management cluster upgrade [{self.cluster_name}]")
