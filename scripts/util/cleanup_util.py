#!/usr/local/bin/python3

#  Copyright 2022 VMware, Inc
#  SPDX-License-Identifier: BSD-2-Clause
import time
from util.ShellHelper import runShellCommandAndReturnOutput, runProcess
from util.logger_helper import LoggerHelper, log
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
