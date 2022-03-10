#!/usr/local/bin/python3

import os
from pathlib import Path
import time
from retry import retry
import json

from constants.constants import Paths, AlbPrefix, AlbCloudType, ComponentPrefix, AlbLicenseTier, VmPowerState, \
    AlbVrfContext, ControllerLocation
from model.run_config import RunConfig
from model.status import HealthEnum, Info, State
from util.avi_api_helper import AviApiHelper, AviApiSpec, ra_avi_download
from util.cmd_helper import CmdHelper, timer
from util.file_helper import FileHelper
from util.git_helper import Git
from util.govc_helper import deploy_avi_controller_ova, get_alb_ip_address, export_govc_env_vars, \
    template_avi_se_govc_config, import_ova, change_vm_network, connect_networks, \
    change_vms_power_state, wait_for_vm_to_get_ip, find_vm_by_name, update_vm_cpu_memory, get_vm_power_state, \
    get_vm_mac_addresses
from util.logger_helper import LoggerHelper, log
from util.marketplace_helper import fetch_avi_ova

logger = LoggerHelper.get_logger(Path(__file__).stem)


class RALBWorkflow:
    def __init__(self, run_config: RunConfig) -> None:
        self.run_config = run_config
        if not self.run_config.spec.avi.cloud.name:
            self.run_config.spec.avi.cloud.name = AlbPrefix.CLOUD_NAME
        if not self.run_config.spec.avi.cloud.mgmtSEGroup:
            self.run_config.spec.avi.cloud.mgmtSEGroup = AlbPrefix.MGMT_SE_GROUP
        if not self.run_config.spec.avi.cloud.workloadSEGroupPrefix:
            self.run_config.spec.avi.cloud.mgmtSEGroup = AlbPrefix.WORKLOAD_SE_GROUP
        self.version = None
        with open(ControllerLocation.SPEC_FILE_PATH) as f:
            self.jsonspec = json.load(f)


    @log("Updating status to resource")
    def update_success_status(self):
        state_file_path = os.path.join(self.run_config.root_dir, Paths.STATE_PATH)
        state: State = FileHelper.load_state(state_file_path)
        state.avi = Info(name=self.run_config.spec.avi.vmName, deployed=True, health=HealthEnum.UP,
                         version=self.version)
        FileHelper.dump_state(state, state_file_path)
        Git.add_all_and_commit(os.path.dirname(state_file_path), "Successful NSX ALB deployment")

    @timer
    def avi_controller_setup(self):
        if self.run_config.state.avi.deployed:
            logger.debug("NSX-ALB is deployed")
            return
        avi_status = ra_avi_download(self.jsonspec)
        # deploy OVA
        # ova_path = os.path.join(self.run_config.root_dir, Paths.ALB_OVA_PATH)
        # if not Path(ova_path).is_file():
        #     logger.warn("Missing ova in path from resource: %s", ova_path)
        #     if not self.run_config.spec.avi.ovaPath:
        #         logger.info(
        #             "No Ova file provided. Downloading from MarketPkace"
        #         )
        #         download_status, status, ova_location = fetch_avi_ova(specfile=Paths.SPEC_FILE_PATH)
        #         if download_status is None:
        #             logger.error(f"Downloading Avi Ova Failed. Msg: {status}")
        #         elif download_status:
        #             logger.info(f"Downloading Avi Ova has completed. Msg: {status}")
        #             ControllerLocation.OVA_LOCATION = ova_location

        refreshToken = self.jsonspec['envSpec']['marketplaceSpec']['refreshToken']


        # deploy_avi_controller_ova(self.run_config)
        # ip = get_alb_ip_address(self.run_config)
        # logger.info("IP Address: %s", ip)
        #
        # avi = AviApiHelper(
        #     AviApiSpec(ip, "admin", CmdHelper.decode_base64(self.run_config.spec.avi.password)),
        #     self.run_config)
        # avi.wait_for_controller()
        #
        # # Configure Avi Controller
        # avi.change_credentials()
        # self.version = avi.get_api_version()
        # logger.info("Server Version: %s", self.version)  # Get Version
        # avi.patch_license_tier(AlbLicenseTier.ESSENTIALS)
        # avi.set_dns_ntp()
        # avi.disable_welcome_screen()
        # avi.set_backup_passphrase()
        # avi.generate_ssl_cert()  # cert generation
        # # todo: tmp fix
        # avi.disable_welcome_screen()
        # avi.set_backup_passphrase()


