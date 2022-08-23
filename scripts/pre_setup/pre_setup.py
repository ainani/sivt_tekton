#!/usr/local/bin/python3

#  Copyright 2022 VMware, Inc
#  SPDX-License-Identifier: BSD-2-Clause
import json
import os
import ruamel.yaml # pip install ruamel.yaml
from constants.constants import Paths, Avi_Version, Avi_Tkgs_Version
from util.avi_api_helper import obtain_avi_version, check_controller_is_up
from util.logger_helper import LoggerHelper, log
from util.cmd_helper import CmdHelper
from model.run_config import RunConfig
from util.tkg_util import TkgUtil
from util.common_utils import checkenv
from util.govc_client import GovcClient
from util.local_cmd_helper import LocalCmdHelper

logger = LoggerHelper.get_logger(name='Pre Setup')

class PreSetup:
    def __init__(self, root_dir, run_config: RunConfig) -> None:
        self.run_config = run_config
        self.version = None
        self.jsonpath = None
        self.state_file_path = os.path.join(root_dir, Paths.STATE_PATH)
        self.tkg_util_obj = TkgUtil(run_config=self.run_config)
        self.tkg_version_dict = self.tkg_util_obj.get_desired_state_tkg_version()
        if "tkgs" in self.tkg_version_dict:
            self.jsonpath = os.path.join(self.run_config.root_dir, Paths.TKGS_WCP_MASTER_SPEC_PATH)
        elif "tkgm" in self.tkg_version_dict:
            self.jsonpath = os.path.join(self.run_config.root_dir, Paths.MASTER_SPEC_PATH)
        else:
            raise Exception(f"Could not find supported TKG version: {self.tkg_version_dict}")

        with open(self.jsonpath) as f:
            self.jsonspec = json.load(f)

        check_env_output = checkenv(self.jsonspec)
        if check_env_output is None:
            msg = "Failed to connect to VC. Possible connection to VC is not available or " \
                  "incorrect spec provided."
            raise Exception(msg)
        self.govc_client = GovcClient(self.jsonspec, LocalCmdHelper())
        self.isEnvTkgs_wcp = TkgUtil.isEnvTkgs_wcp(self.jsonspec)
        self.isEnvTkgs_ns = TkgUtil.isEnvTkgs_ns(self.jsonspec)
        self.get_vcenter_details()
        self.get_avi_details()

    def get_vcenter_details(self):
        """
        Method to get vCenter Details from JSON file
        :return:
        """
        self.vcenter_dict = {}
        try:
            self.vcenter_dict.update({'vcenter_ip': self.jsonspec['envSpec']['vcenterDetails']['vcenterAddress'],
                                      'vcenter_password': CmdHelper.decode_base64(
                                          self.jsonspec['envSpec']['vcenterDetails']['vcenterSsoPasswordBase64']),
                                      'vcenter_username': self.jsonspec['envSpec']['vcenterDetails']['vcenterSsoUser'],
                                      'vcenter_cluster_name': self.jsonspec['envSpec']['vcenterDetails']['vcenterCluster'],
                                      'vcenter_datacenter': self.jsonspec['envSpec']['vcenterDetails']['vcenterDatacenter'],
                                      'vcenter_data_store': self.jsonspec['envSpec']['vcenterDetails']['vcenterDatastore']
                                      })
        except KeyError as e:
            logger.warning(f"Field {e} not configured in vcenterDetails")
            pass

    def get_avi_details(self):
        self.avi_dict = {}
        if self.isEnvTkgs_wcp:
            self.avi_dict.update({"avi_fqdn": self.jsonspec['tkgsComponentSpec']['aviComponents']['aviController01Fqdn']})
        else:
            self.avi_dict.update(
                {"avi_fqdn": self.jsonspec['tkgComponentSpec']['aviComponents']['aviController01Fqdn']})

    def pre_check_avi(self):
        """
        Method to check that AVI is deployed or not already
        """
        if TkgUtil.isEnvTkgs_wcp(self.jsonspec):
            avi_required = Avi_Tkgs_Version.VSPHERE_AVI_VERSION
        else:
            avi_required = Avi_Version.VSPHERE_AVI_VERSION

        state_dict = {"avi":{"deployed": False,
                             "version": avi_required,
                             "health": "DOWN",
                             "name": self.avi_dict["avi_fqdn"]}}
        msg = "AVI not deployed"

        # Verify AVI deployed
        ip = self.govc_client.get_vm_ip(vm_name=self.avi_dict["avi_fqdn"],
                                   datacenter_name=self.vcenter_dict["vcenter_datacenter"])[0]
        if ip is None:
            msg = "Could not find VM IP"
            return state_dict, msg
        deployed_avi_version = obtain_avi_version(ip, self.jsonspec)
        if deployed_avi_version[0] is None:
            return state_dict, msg

        # AVI Deployed --> Verify AVI version
        if deployed_avi_version[0] == avi_required:
            state_dict["avi"]["deployed"] = True
        else:
            state_dict["avi"]["version"] = deployed_avi_version[0]
            msg = f"AVI Version mis-matched : Deployed: {deployed_avi_version[0]} & Required: {avi_required}"
            return state_dict, msg

        # AVI Deployed --> AVI Version Verified --> Verify AVI name
        # TODO: How to verify avi fqdn name

        # AVI Deployed --> AVI Version --> AVI name --> Verify AVI state
        if "UP" in check_controller_is_up(ip):
            state_dict["avi"]["deployed"] = True
            state_dict["avi"]["health"] = "UP"
        else:
            msg = "AVI state not UP: Deployed but AVI is not UP"
            return state_dict, msg

        # Update state.yml file
        self.update_state_yml(state_dict)
        return state_dict, "Pre Check PASSED for AVI"

    def update_state_yml(self, state_dict: dict):
        config, ind, bsi = ruamel.yaml.util.load_yaml_guess_indent(open(self.state_file_path))
        for key, val in state_dict.items():
            instances = config[key]
            for item_key, item_val in val.items():
                instances[item_key] = item_val

        yaml = ruamel.yaml.YAML()
        yaml.indent(mapping=ind, sequence=ind, offset=bsi)
        with open(self.state_file_path, 'w') as fp:
            yaml.dump(config, fp)
