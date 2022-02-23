#!/usr/local/bin/python3

import os
from pathlib import Path
import time
from retry import retry

from constants.constants import Paths, AlbPrefix, AlbCloudType, ComponentPrefix, AlbLicenseTier, VmPowerState, \
    AlbVrfContext
from model.run_config import RunConfig
from model.status import HealthEnum, Info, State
from util.avi_api_helper import AviApiHelper, AviApiSpec
from util.cmd_helper import CmdHelper, timer
from util.file_helper import FileHelper
from util.git_helper import Git
from util.govc_helper import deploy_avi_controller_ova, get_alb_ip_address, export_govc_env_vars, \
    template_avi_se_govc_config, import_ova, change_vm_network, connect_networks, \
    change_vms_power_state, wait_for_vm_to_get_ip, find_vm_by_name, update_vm_cpu_memory, get_vm_power_state, \
    get_vm_mac_addresses
from util.logger_helper import LoggerHelper, log

logger = LoggerHelper.get_logger(Path(__file__).stem)


class ALBWorkflow:
    def __init__(self, run_config: RunConfig) -> None:
        self.run_config = run_config
        if not self.run_config.spec.avi.cloud.name:
            self.run_config.spec.avi.cloud.name = AlbPrefix.CLOUD_NAME
        if not self.run_config.spec.avi.cloud.mgmtSEGroup:
            self.run_config.spec.avi.cloud.mgmtSEGroup = AlbPrefix.MGMT_SE_GROUP
        if not self.run_config.spec.avi.cloud.workloadSEGroupPrefix:
            self.run_config.spec.avi.cloud.mgmtSEGroup = AlbPrefix.WORKLOAD_SE_GROUP
        self.version = None

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
        # deploy OVA
        ova_path = os.path.join(self.run_config.root_dir, Paths.ALB_OVA_PATH)
        if not Path(ova_path).is_file():
            logger.warn("Missing ova in path from resource: %s", ova_path)
            if not self.run_config.spec.avi.ovaPath:
                logger.error(
                    "Missing ova file url in spec. ova file location is mandatory if resource is not available"
                )
                return
        deploy_avi_controller_ova(self.run_config)
        # Get Ip Address
        ip = get_alb_ip_address(self.run_config)
        logger.info("IP Address: %s", ip)

        avi = AviApiHelper(AviApiSpec(ip, "admin", CmdHelper.decode_password(self.run_config.spec.avi.password)),
                           self.run_config)

        avi.wait_for_controller()

        # Configure Avi Controller
        avi.change_credentials()
        self.version = avi.get_api_version()
        logger.info("Server Version: %s", self.version)  # Get Version
        avi.patch_license_tier(AlbLicenseTier.ESSENTIALS)
        avi.set_dns_ntp()
        avi.disable_welcome_screen()
        avi.set_backup_passphrase()
        avi.generate_ssl_cert()  # cert generation
        self.configure_alb_cloud()

        # todo: tmp fix
        avi.disable_welcome_screen()
        avi.set_backup_passphrase()

        # update for including configure cloud account details

        self.update_success_status()




    @timer
    def avi_controller_validate(self):
        ip = self.run_config.spec.avi.deployment.parameters.ip
        avi = AviApiHelper(AviApiSpec(ip, "admin", CmdHelper.decode_password(self.run_config.spec.avi.password)),
                           self.run_config)

        msg, status = avi.validate_avi_controller()
        if status:
            logger.info(f"Avi controller validation has passed, msg: {msg}")
        else:
            logger.error(f"Validation check failed. Msg: {msg}\nAvi controller validation has failed.")

    @timer
    def configure_alb_cloud(self):
        ip = get_alb_ip_address(self.run_config)
        avi = AviApiHelper(AviApiSpec(ip, "admin", CmdHelper.decode_password(
                           self.run_config.spec.avi.password)),
                           self.run_config)
        avi.configure_cloud()
        avi.configure_static_ip_pool()

    def deploy_se_vms(self, ova_path, vms, networks):
        avi = AviApiHelper(
            AviApiSpec('35.163.7.218', "admin", CmdHelper.decode_password(self.run_config.spec.avi.password)),
            self.run_config)
        controller_ip = get_alb_ip_address(self.run_config)
        dc = self.run_config.spec.avi.deployment.datacenter
        ds = self.run_config.spec.avi.deployment.datastore
        rp = self.run_config.spec.avi.deployment.resourcePool
        folder = self.run_config.spec.avi.deployment.folder
        logger.info("Exporting env vars")
        export_govc_env_vars(self.run_config)
        vm_ips = dict()
        for se_vm_name in vms:
            if not find_vm_by_name(se_vm_name):
                spec = {
                    "placeholder_nw": ComponentPrefix.ALB_MGMT_NW.value,
                    "auth_token": avi.get_auth_token(),
                    "cluster_uuid": avi.get_cluster_uuid(),
                    "controller_ip": controller_ip,
                    "vm_name": se_vm_name
                }
                logger.info("Templating deployment options")
                options = template_avi_se_govc_config(spec)

                logger.info("Import SE OVA")
                import_ova(options=options, dc=dc, ds=ds, folder=folder, res_pool=rp, ova_file=ova_path,
                           name=se_vm_name, template=False, replace_existing=False)
            else:
                logger.info(f"VM already exists by name: {se_vm_name}. Skipping deployment.")

            if get_vm_power_state(se_vm_name) == VmPowerState.OFF:
                logger.info("Update placeholder networks")
                change_vm_network(se_vm_name, networks)

                logger.info("Connect NICs")
                net = [f"ethernet-{i}" for i in range(len(networks))]
                connect_networks(se_vm_name, net)

                logger.info("Update CPU and memory allocation")
                update_vm_cpu_memory(se_vm_name, cpus=2, memory=4096)

                logger.info("Power ON")
                change_vms_power_state([se_vm_name], VmPowerState.ON)
            else:
                logger.info("VM already powered on. Skipping reconfigurations.")

            logger.info("Waiting for IP")
            vm_ips[se_vm_name] = wait_for_vm_to_get_ip(se_vm_name)

        return vm_ips

    @retry(ValueError, tries=6, delay=10, logger=logger)
    def wait_for_se_to_appear(self, avi: AviApiHelper, names):
        errors = []
        service_engines = []
        for name in names:
            se = avi.get_service_engine(name)
            if not se or len(se) == 0:
                errors.append(f"SE with name {name} not found yet.")
            else:
                service_engines.append(se[0])
        if len(errors) > 0:
            raise ValueError("\n".join(errors))
        return service_engines

    @staticmethod
    def get_routes_not_present(vrf_context, next_hop_ips):
        """

        :param vrf_context: vrf context
        :param next_hop_ips: List of IPs which should be present as next-hop in the routes
        :return: a tuple containing 2 elements: list of IPs which are not present as a next-hop IP in any route and
        next available(unassigned) route ID
        """
        next_route_id = 1
        if "static_routes" not in vrf_context or len(vrf_context["static_routes"]) == 0:
            return next_hop_ips, next_route_id

        available_hops = []
        for route in vrf_context["static_routes"]:
            available_hops.append(route["next_hop"]["addr"])
            next_route_id = max(next_route_id, route["route_id"])
        hops_not_found = [hop for hop in next_hop_ips if hop not in available_hops]
        return hops_not_found, next_route_id

    @retry(ValueError, tries=6, delay=10, logger=logger)
    def wait_for_se_to_connect(self, avi: AviApiHelper, names):
        errors = []
        service_engines = []
        for name in names:
            se = avi.get_service_engine(name)
            if not se or len(se) == 0:
                errors.append(f"SE with name {name} not found yet.")
            elif not se[0]["se_connected"]:
                errors.append(f"SE with name {name} not connected yet.")
            else:
                service_engines.append(se[0])
        if len(errors) > 0:
            raise ValueError("\n".join(errors))
        return service_engines

    def check_update_vrf_context(self, avi: AviApiHelper):
        vrf = avi.get_vrf_context(name=AlbVrfContext.GLOBAL)
        if len(vrf) == 0:
            msg = f"No VRF context found with name: {AlbVrfContext.GLOBAL}"
            logger.error(msg)
            raise ValueError(msg)

        next_hops = [cidr.split('/')[0] for cidr in (self.run_config.spec.tkg.management.dataVipSegment.gatewayCidr,
                                                     self.run_config.spec.tkg.management.clusterVipSegment.gatewayCidr)]
        hops_to_create, next_route_id = ALBWorkflow.get_routes_not_present(vrf, next_hops)
        if len(hops_to_create) == 0:
            logger.info("All required routes are present. Skipping route configuration.")
        else:
            id_hop_ip_map = dict()
            for index, hop_ip in enumerate(hops_to_create):
                id_hop_ip_map[next_route_id + index] = hop_ip
            vrf = avi.patch_vrf_context(vrf[0]['uuid'], id_hop_ip_map)

        logger.info("ALB management configuration complete")

    @timer
    def alb_mgmt_config(self):
        avi = AviApiHelper(
            AviApiSpec('35.163.7.218', "admin", CmdHelper.decode_password(self.run_config.spec.avi.password)),
            self.run_config)
        cloud = avi.create_cloud(AlbCloudType.NONE)
        se_group = avi.create_se_group(AlbPrefix.MGMT_SE_GROUP)
        clu_vip = avi.create_network(ComponentPrefix.CLUSTER_VIP_NW,
                                     self.run_config.spec.tkg.management.clusterVipSegment)
        mgmt_vip = avi.create_network(ComponentPrefix.MGMT_DATA_VIP_NW,
                                      self.run_config.spec.tkg.management.dataVipSegment)
        ipam_nw = [clu_vip["url"], mgmt_vip["url"]]
        ipam = avi.create_ipam_profile(self.run_config.spec.avi.cloud.ipamProfileName, ipam_nw)
        cloud = avi.update_se_group_and_ipam_profile(se_group["url"], ipam["url"])
        ova = avi.download_se_ova(os.path.join(self.run_config.root_dir, Paths.ALB_SE_OVA_PATH))
        logger.info(f"Service Engine OVA available at: {ova}")
        prefix = AlbPrefix.MGMT_SE_NODE.value
        vms = [f"{prefix}_0{index + 1}" for index in range(2)]
        networks = [
            ComponentPrefix.ALB_MGMT_NW.value,
            ComponentPrefix.MGMT_CLU_NW.value,
            ComponentPrefix.MGMT_DATA_VIP_NW.value,
            ComponentPrefix.SHARED_CLU_NW.value,
            ComponentPrefix.CLUSTER_VIP_NW.value
        ]
        vm_ips = self.deploy_se_vms(ova, vms, networks)
        logger.info("SE VMs deployed successfully.")
        for vm_name, ip_address in vm_ips.items():
            logger.debug(f"VM name: {vm_name}, IP address: {ip_address}")
        self.wait_for_se_to_appear(avi, names=vm_ips.values())

        for vm_name, ip_address in vm_ips.items():
            mac_addresses = get_vm_mac_addresses(vm_name)
            avi.update_se_engine(ip_address, se_group["url"], mac_addresses)

        service_engines = self.wait_for_se_to_connect(avi, names=vm_ips.values())

        self.check_update_vrf_context(avi)
