import os
import json
from constants.constants import Paths, UpgradeVersions
from lib.tkg_cli_client import TkgCliClient
from model.run_config import RunConfig
from util.logger_helper import LoggerHelper
from workflows.cluster_common_workflow import ClusterCommonWorkflow
import traceback
from util.common_utils import downloadAndPushKubernetesOvaMarketPlace

logger = LoggerHelper.get_logger(name='ra_mgmt_upgrade_workflow')

class RaMgmtUpgradeWorkflow:
    def __init__(self, run_config: RunConfig):
        self.run_config = run_config
        logger.info ("Current deployment state: %s", self.run_config.state)
        jsonpath = os.path.join(self.run_config.root_dir, Paths.MASTER_SPEC_PATH)
        self.tanzu_client = TkgCliClient()
        with open(jsonpath) as f:
            self.jsonspec = json.load(f)

    def upgrade_workflow(self):
        try:
            # Precheck if template is present else download it if marketplace token is provided
            # if template is already present skip to execution of upgrade
            # if template is not present and marketplace token is provided, proceed to download
            # from market place and place it as template and proceed to upgrade execution
            # if neither template nor marketplace token is provided, bail out with failure
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
                logger.info("MarketPlace refresh token is not provided,"
                            "and unable to locate required template. Please place the required "
                            "template or provide marketplace token Existing...")
                raise Exception(d["msg"])
            else:

                # execute upgrade
                cluster = self.jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgMgmtClusterName']
                self.tanzu_client.login(cluster_name=cluster)
                if self.tanzu_client.management_cluster_upgrade(cluster_name=cluster) is None:
                    msg= "Failed to upgrade Management cluster"
                    logger.error("Error: {}".format(msg))
                    raise Exception(msg)

                if not self.tanzu_client.retriable_check_cluster_exists(cluster_name=cluster):
                    msg = f"Cluster: {cluster} not in running state"
                    logger.error(msg)
                    raise Exception(msg)

                logger.info("Checking for services status...")
                cluster_status = self.tanzu_client.get_all_clusters()
                mgmt_health = ClusterCommonWorkflow.check_cluster_health(cluster_status, cluster)
                if mgmt_health == "UP":
                    msg = f"Management Cluster {cluster} upgraded successfully"
                    logger.info(msg)
                else:
                    msg = f"Management Cluster {cluster} failed to upgrade"
                    logger.error(msg)
                    raise Exception(msg)

        except Exception:
            logger.error("Error Encountered: {}".format(traceback.format_exc()))




