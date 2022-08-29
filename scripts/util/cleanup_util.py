#!/usr/local/bin/python3

#  Copyright 2022 VMware, Inc
#  SPDX-License-Identifier: BSD-2-Clause
import time
import json
from util.ShellHelper import runShellCommandAndReturnOutput, runProcess, runShellCommandAndReturnOutputAsList, \
    verifyPodsAreRunning
from util.logger_helper import LoggerHelper, log
from constants.constants import RegexPattern

logger = LoggerHelper.get_logger(name='Pre Setup')


class CleanUpUtil:
    def __int__(self):
        pass

    def is_management_cluster_exists(self, mgmt_cluster: str) -> bool:
        """
        Method to check that if Tanzu management cluster exists or not

        :param: mgmt_cluster: Name of management cluster to be checked that exists or not
        :return: bool
                 True -> If management cluster exists, else
                 False
        """
        try:
            tanzu_mgmt_get_cmd = ["tanzu", "management-cluster", "get"]
            cmd_out = runShellCommandAndReturnOutput(tanzu_mgmt_get_cmd)
            if cmd_out[1] == 0:
                try:
                    if cmd_out[0].__contains__(mgmt_cluster):
                        return True
                    else:
                        return False
                except:
                    return False
            else:
                return False
        except:
            return False

    def delete_mgmt_cluster(self, mgmt_cluster):
        try:
            logger.info("Delete Management cluster - " + mgmt_cluster)
            delete_command = ["tanzu", "management-cluster", "delete", "--force", "-y"]
            runProcess(delete_command)

            deleted = False
            count = 0
            while count < 360 and not deleted:
                if self.is_management_cluster_exists(mgmt_cluster):
                    logger.debug("Management cluster is still not deleted... retrying in 10s")
                    time.sleep(10)
                    count = count + 1
                else:
                    deleted = True
                    break

            if not deleted:
                logger.error(
                    "Management cluster " + mgmt_cluster + " is not deleted even after " + str(count * 5)
                    + "s")
                return False
            else:
                return True
        except Exception as e:
            logger.error(str(e))
            return False

    def delete_cluster(self, cluster):
        try:
            logger.info("Initiating deletion of cluster - " + cluster)
            delete = ["tanzu", "cluster", "delete", cluster, "-y"]
            delete_status = runShellCommandAndReturnOutputAsList(delete)
            if delete_status[1] != 0:
                logger.error("Command to delete - " + cluster + " Failed")
                logger.debug(delete_status[0])
                d = {
                    "responseType": "ERROR",
                    "msg": "Failed delete cluster - " + cluster,
                    "ERROR_CODE": 500
                }
                return json.dumps(d), 500
            cluster_running = ["tanzu", "cluster", "list"]
            command_status = runShellCommandAndReturnOutputAsList(cluster_running)
            if command_status[1] != 0:
                logger.error("Failed to run command to check status of workload cluster - " + cluster)
                return False
            deleting = True
            count = 0
            while count < 360 and deleting:
                if verifyPodsAreRunning(cluster, command_status[0], RegexPattern.deleting) or \
                        verifyPodsAreRunning(cluster, command_status[0], RegexPattern.running):
                    logger.info("Waiting for " + cluster + " deletion to complete...")
                    logger.info("Retrying in 10s...")
                    time.sleep(10)
                    count = count + 1
                    command_status = runShellCommandAndReturnOutputAsList(cluster_running)
                else:
                    deleting = False
            if not deleting:
                return True

            logger.error("waited for " + str(count * 5) + "s")
            return False
        except Exception as e:
            logger.error("Exception occurred while deleting cluster " + str(e))
            return False
