import json
from pathlib import Path

from constants.constants import TmcCommands
from retry import retry
from util.logger_helper import LoggerHelper, log, log_debug
from util.ssh_helper import SshHelper

logger = LoggerHelper.get_logger(Path(__file__).stem)

class TmcCliClient:

    def __init__(self, ssh: SshHelper):
        self.ssh = ssh

    def tmc_login(self, api_token):
        return self.ssh.run_cmd(TmcCommands.LOGIN.format(token=api_token))

    def get_kubeconfig(self, cluster_name, file):
        get_kubeconfig_cmd = TmcCommands.GET_KUBECONFIG.format(cluster_name=cluster_name, file=file)
        return self.ssh.run_cmd(get_kubeconfig_cmd)

    def attach_cluster(self, cluster_name, cluster_group):
        attach_cluster_cmd = TmcCommands.ATTACH_CLUSTER.format(cluster_name=cluster_name, cluster_group=cluster_group)
        return self.ssh.run_cmd(attach_cluster_cmd)