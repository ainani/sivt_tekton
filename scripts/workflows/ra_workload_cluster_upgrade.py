import os
import json
from constants.constants import Paths, UpgradeVersions
from lib.tkg_cli_client import TkgCliClient
from model.run_config import RunConfig
from util.logger_helper import LoggerHelper
from workflows.cluster_common_workflow import ClusterCommonWorkflow
import traceback
from util.common_utils import downloadAndPushKubernetesOvaMarketPlace, checkenv

logger = LoggerHelper.get_logger(name='ra_shared_upgrade_workflow')

class RaWorkloadUpgradeWorkflow:
    def __init__(self, run_config: RunConfig):
        self.run_config = run_config
        logger.info("Current deployment state: %s", self.run_config.state)
        jsonpath = os.path.join(self.run_config.root_dir, Paths.MASTER_SPEC_PATH)
        self.tanzu_client = TkgCliClient()
        with open(jsonpath) as f:
            self.jsonspec = json.load(f)

        check_env_output = checkenv(self.jsonspec)
        if check_env_output is None:
            msg = "Failed to connect to VC. Possible connection to VC is not available or " \
                  "incorrect spec provided."
            raise Exception(msg)

    def upgrade_workflow(self):
        try:
            # Precheck
            logger.info(("Checking if required template is already present"))
            kubernetes_ova_os = \
                self.jsonspec["tkgComponentSpec"]["tkgMgmtComponents"][
                    "tkgMgmtBaseOs"]
            kubernetes_ova_version = UpgradeVersions.KUBERNETES_OVA_LATEST_VERSION
            down_status = downloadAndPushKubernetesOvaMarketPlace(self.jsonspec,
                                                                  kubernetes_ova_version,
                                                                  kubernetes_ova_os,
                                                                  upgrade=True)
            if down_status[0] is None:
                logger.error(down_status[1])
                d = {
                    "responseType": "ERROR",
                    "msg": down_status[1],
                    "ERROR_CODE": 500
                }
                logger.error("Error: {}".format(json.dumps(d)))
                msg = "Failed to download template..."
                raise Exception(msg)
            else:
                mgmt_cluster = self.jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgMgmtClusterName']
                cluster = self.jsonspec['tkgWorkloadComponents']['tkgSharedserviceClusterName']
                self.tanzu_client.login(cluster_name=mgmt_cluster)
                if self.tanzu_client.tanzu_cluster_upgrade(cluster_name=cluster) is None:
                    msg = "Failed to upgrade {} cluster".format(cluster)
                    logger.error("Error: {}".format(msg))
                    raise Exception(msg)

                if not self.tanzu_client.retriable_check_cluster_exists(cluster_name=cluster):
                    msg = f"Cluster: {cluster} not in running state"
                    logger.error(msg)
                    raise Exception(msg)
                logger.info("Checking for services status...")
                cluster_status = self.tanzu_client.get_all_clusters()
                workload_health = ClusterCommonWorkflow.check_cluster_health(cluster_status, cluster)
                if workload_health == "UP":
                    msg = f"Workload Cluster {cluster} upgraded successfully"
                    logger.info(msg)
                else:
                    msg = f"Workload Cluster {cluster} failed to upgrade"
                    logger.error(msg)
                    raise Exception(msg)

        except Exception:
            logger.error("Error Encountered: {}".format(traceback.format_exc()))




