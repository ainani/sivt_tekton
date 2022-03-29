import os
import json
from constants.constants import Paths, RepaveTkgCommands, TKGCommands
from lib.tkg_cli_client import TkgCliClient
from model.run_config import RunConfig
from util.logger_helper import LoggerHelper
import traceback
from util.common_utils import downloadAndPushKubernetesOvaMarketPlace, checkenv, \
    download_upgrade_binaries, untar_binary, locate_binary_tmp
from util.cmd_runner import RunCmd
logger = LoggerHelper.get_logger(name='scale_workflow')

class ScaleWorkflow:
    def __init__(self, run_config: RunConfig):
        self.run_config = run_config
        # logger.info("Current deployment state: %s", self.run_config.state)
        jsonpath = os.path.join(self.run_config.root_dir, Paths.MASTER_SPEC_PATH)
        self.tanzu_client = TkgCliClient()
        self.rcmd = RunCmd()

        with open(jsonpath) as f:
            self.jsonspec = json.load(f)

        # check_env_output = checkenv(self.jsonspec)
        # if check_env_output is None:
        #     msg = "Failed to connect to VC. Possible connection to VC is not available or " \
        #           "incorrect spec provided."
        #     raise Exception(msg)

        self.scaledetails = self.run_config.scaledetails.scaleinfo

    # def add_node(self, cluster_name, control_plane_node_count, worker_node_count):
    #     self.ssh.run_cmd_only(
    #         RepaveTkgCommands.ADD_NODES.format(
    #             cluster_name=cluster_name,
    #             control_plane_node_count=control_plane_node_count,
    #             worker_node_count=worker_node_count,
    #         )
    #     )

    def get_cluster_dict(self):

        """
        Execute tanzu login
        tanzu cluster list --include-management-cluster --output json
        format to dict
        :return: cluster dict if succeeded
                 None if failed
        """
        logger.info("Fetching cluster details")
        try:
            cluster_dict = self.tanzu_client.get_all_clusters()
            logger.info("Cluster dict")
            logger.info(cluster_dict)
            return cluster_dict
        except Exception:
            logger.error("Error Encountered")
            logger.error(traceback.format_exc())
            return None

    def get_cluster_state(self, cluster):

        """
        Checks if clustername is given in scale-repave.yml
        if cluster name is present,
         check for cluster exist
         check for cluster
        :param cluster:
        :return:
        """
        pass

    def execute_scale(self):
        try:
            # precheck for right entries in scale-repave.yml to identify the cluster
            # to be scaled and the controlnode and worker node to be scaled

            if not self.scaledetails.execute:
                logger.info("Scale operation is not enabled.")
                d = {
                    "responseType": "SUCCESS",
                    "msg": "Scale operation is not enabled",
                    "ERROR_CODE": 200
                }
                return json.dumps(d), 200

            # There is atleast one scale operation to be present
            # Best possible to avoid repetation is to dump cluster list to dict
            # And then to check cluster exists and also scale operation of controlplane
            # and workers specified in scale-repave yaml file are higher than the existing
            # clusters. Same dictionary can be reused for mgmt, shared and workload clusters

            self.fetched_cluster_dict = self.get_cluster_dict()
            # # Check if mgmt needs scaling
            # if not self.scaledetails.mgmt.execute_scale:
            #     logger.info("Scale operation is not enabled.")
            # else:
            #     logger.info("Starting scaling of management cluster")
            #     cluster_name = self.scaledetails.mgmt.clustername
            #     cluster_state = self.get_cluster_state(cluster=cluster_name)

        except Exception:
            logger.error("Error Encountered: {}".format(traceback.format_exc()))

