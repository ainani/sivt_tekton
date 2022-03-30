import os
import json
from constants.constants import Paths, RepaveTkgCommands
from lib.tkg_cli_client import TkgCliClient
from model.run_config import RunConfig
from util.logger_helper import LoggerHelper
from workflows.cluster_common_workflow import ClusterCommonWorkflow
import traceback
from util.common_utils import downloadAndPushKubernetesOvaMarketPlace, checkenv, \
    download_upgrade_binaries, untar_binary, locate_binary_tmp
from util.cmd_runner import RunCmd
logger = LoggerHelper.get_logger(name='ra_workload_scale_workflow')

class RaWorkloadScaleWorkflow:
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

    def add_node(self, cluster_name, control_plane_node_count, worker_node_count):
        self.ssh.run_cmd_only(
            RepaveTkgCommands.ADD_NODES.format(
                cluster_name=cluster_name,
                control_plane_node_count=control_plane_node_count,
                worker_node_count=worker_node_count,
            )
        )

    def scale(self):
        try:
            # precheck for right entries in scale.yml to identify the cluster
            # to be scaled and the controlnode and worker node to be scaled

            if not self.scaledetails.execute:
                logger.info("Scale operation is not enabled.")
                d = {
                    "responseType": "SUCCESS",
                    "msg": "Scale operation is not enabled",
                    "ERROR_CODE": 200
                }

                logger.info("Workload cluster configured Successfully")
                return json.dumps(d), 200


        except Exception:
            logger.error("Error Encountered: {}".format(traceback.format_exc()))

