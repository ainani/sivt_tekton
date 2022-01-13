import os
from pathlib import Path

from constants.constants import Paths
from model.desired_state import DesiredState
from model.spec import Bootstrap, MasterSpec
from model.status import State

from util.cmd_helper import CmdHelper
from util.file_helper import FileHelper
from util.logger_helper import LoggerHelper
from util.ssh_helper import SshHelper

logger = LoggerHelper.get_logger(Path(__file__).stem)


class TanzuUtils:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.spec: MasterSpec = FileHelper.load_spec(os.path.join(self.root_dir, Paths.MASTER_SPEC_PATH))
        self.bootstrap: Bootstrap = self.spec.bootstrap
        self.desired_state: DesiredState = FileHelper.load_desired_state(
            os.path.join(self.root_dir, Paths.DESIRED_STATE_PATH)
        )
        self.state: State = FileHelper.load_state(os.path.join(self.root_dir, Paths.STATE_PATH))
        self.repo_kube_config = os.path.join(self.root_dir, Paths.REPO_KUBE_CONFIG)
        self.repo_kube_tkg_config = os.path.join(self.root_dir, Paths.REPO_KUBE_TKG_CONFIG)
        self.repo_tanzu_config = os.path.join(self.root_dir, Paths.REPO_TANZU_CONFIG)
        self.repo_tanzu_config_new = os.path.join(self.root_dir, Paths.REPO_TANZU_CONFIG_NEW)

        FileHelper.make_parent_dirs(self.repo_kube_config)
        FileHelper.make_parent_dirs(self.repo_kube_tkg_config)
        FileHelper.make_parent_dirs(self.repo_tanzu_config)
        FileHelper.make_parent_dirs(self.repo_tanzu_config_new)

    def pull_config(self):
        with SshHelper(self.bootstrap.server, self.bootstrap.username, CmdHelper.decode_password(self.bootstrap.password), self.spec.onDocker) as ssh:
            self.pull_kube_config(ssh)
            self.pull_kube_tkg_config(ssh)
            self.pull_tanzu_config(ssh)

    def pull_kube_config(self, ssh: SshHelper):
        remote_kube_config = Paths.REMOTE_KUBE_CONFIG
        try:
            ssh.run_cmd(f"ls {remote_kube_config}")
        except Exception as ex:
            return
        ssh.copy_file_from_remote(remote_kube_config, self.repo_kube_config)

    def pull_kube_tkg_config(self, ssh):
        remote_kube_config = Paths.REMOTE_KUBE_TKG_CONFIG
        try:
            ssh.run_cmd(f"ls {remote_kube_config}")
        except Exception as ex:
            return
        ssh.copy_file_from_remote(remote_kube_config, self.repo_kube_tkg_config)

    def pull_tanzu_config(self, ssh):
        if self.desired_state.version.tkg >= '1.4.0':
            remote_tanzu_config_new = Paths.REMOTE_TANZU_CONFIG_NEW
            try:
                ssh.run_cmd(f"ls {remote_tanzu_config_new}")
            except Exception as ex:
                return
            ssh.copy_file_from_remote(remote_tanzu_config_new, self.repo_tanzu_config_new)
        else:
            remote_tanzu_config = Paths.REMOTE_TANZU_CONFIG
            try:
                ssh.run_cmd(f"ls {remote_tanzu_config}")
            except Exception as ex:
                return
            ssh.copy_file_from_remote(remote_tanzu_config, self.repo_tanzu_config)

    def push_config(self, logger):
        logger.info("Copying config files")
        with SshHelper(self.bootstrap.server, self.bootstrap.username, CmdHelper.decode_password(self.bootstrap.password), self.spec.onDocker) as ssh:
            ssh.run_cmd("mkdir -p /root/.kube /root/.kube-tkg")
            ssh.copy_file(self.repo_kube_tkg_config, Paths.REMOTE_KUBE_TKG_CONFIG)
            ssh.copy_file(self.repo_kube_config, Paths.REMOTE_KUBE_CONFIG)
            if self.desired_state.version.tkg >= '1.4.0' and not self.state.shared_services.upgradedFrom:
                ssh.copy_file(self.repo_tanzu_config_new, Paths.REMOTE_TANZU_CONFIG_NEW)
            elif self.desired_state.version.tkg == '1.4.0':
                    ssh.copy_file(self.repo_tanzu_config, Paths.REMOTE_TANZU_CONFIG_NEW)
            else:
                # For versions 1.3.0 and 1.3.1
                ssh.copy_file(self.repo_tanzu_config, Paths.REMOTE_TANZU_CONFIG)

    def push_config_without_errors(self, logger):
        try:
            self.push_config(logger)
        except Exception as e:
            logger.error("Unable to push config to remote containers")
