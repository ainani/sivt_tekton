from pathlib import Path

from lib.kubectl_client import KubectlClient
from model.run_config import RunConfig
from util.cmd_helper import CmdHelper
from util.logger_helper import LoggerHelper
from util.ssh_helper import SshHelper, pretty_boundary

logger = LoggerHelper.get_logger(Path(__file__).stem)


class RepaveWorkflow:
    def __init__(self, run_config: RunConfig):
        self.run_config = run_config

    @pretty_boundary
    def repave(self, ssh, cluster_name):
        logger.info(f"Repaving cluster : {cluster_name}")
        if not (
                self.run_config.state.shared_services.deployed
                and len(self.run_config.state.workload_clusters) == len(self.run_config.spec.tkg.workloadClusters)
                and not (any(not wl.deployed for wl in self.run_config.state.workload_clusters))
        ):
            logger.info("clusters are not deployed, skipping repave")
            return
        kubectl_client = KubectlClient(ssh)
        # todo: check pods health
        kubectl_client.set_cluster_context(cluster_name)
        node_count = kubectl_client.get_node_count()
        if node_count <= 1:
            raise ValueError(f"Insufficient Nodes, node_count = {node_count}")
        node_name = kubectl_client.get_oldest_node()
        kubectl_client.drain_pods_from_node(node_name)
        kubectl_client.delete_node(node_name)
        kubectl_client.wait_for_ready_nodes(node_count, 20)
        logger.info(f"Repave complete for cluster : {cluster_name}")

    def repave_ss_cluster(self):
        if not self.run_config.spec.tkg.sharedService.worker.repave:
            logger.info("Repave is disabled for shared services cluster")
            return
        with SshHelper(
                self.run_config.spec.bootstrap.server,
                self.run_config.spec.bootstrap.username,
                CmdHelper.decode_password(self.run_config.spec.bootstrap.password),
                self.run_config.spec.onDocker
        ) as ssh:
            self.repave(ssh, self.run_config.spec.tkg.sharedService.cluster.name)

    def repave_wl_cluster(self):
        with SshHelper(
                self.run_config.spec.bootstrap.server,
                self.run_config.spec.bootstrap.username,
                CmdHelper.decode_password(self.run_config.spec.bootstrap.password),
                self.run_config.spec.onDocker
        ) as ssh:
            for wl in self.run_config.spec.tkg.workloadClusters:
                if not wl.worker.repave:
                    logger.info(f"Repave is disabled for workload cluster : {wl.cluster.name}")
                    return
                self.repave(ssh, wl.cluster.name)
