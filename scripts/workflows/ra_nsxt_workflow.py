


import os, sys
import json
from constants.constants import Paths
from lib.tkg_cli_client import TkgCliClient
from model.run_config import RunConfig, ScaleConfig
from util.logger_helper import LoggerHelper
import traceback
from util.common_utils import checkenv
from util.cmd_runner import RunCmd
logger = LoggerHelper.get_logger(name='nsxt_workflow')
from lib.nsx_client import Nsxt_Client
    

from constants.constants import ServiceName
from constants.nsxt_constants import Policy_Name, VCF, GroupNameCgw, FirewallRuleCgw
    
class RaNSXTWorkflow:
    def __init__(self, run_config: RunConfig):
        self.run_config = run_config
        self.jsonpath = os.path.join(self.run_config.root_dir, Paths.MASTER_SPEC_PATH)
        self.tanzu_client = TkgCliClient()
        self.rcmd = RunCmd()

        with open(self.jsonpath) as f:
            self.jsonspec = json.load(f)
        check_env_output = checkenv(self.jsonspec)
        if check_env_output is None:
            msg = "Failed to connect to VC. Possible connection to VC is not available or " \
                  "incorrect spec provided."
            raise Exception(msg)



    def configureAviNsxtConfig(self):

        nsxtClient = Nsxt_Client(self.run_config)
        gatewayAddress = self.jsonspec['tkgComponentSpec']['tkgSharedserviceSpec'][
            'tkgSharedserviceGatewayCidr']
        dhcpStart = self.jsonspec['tkgComponentSpec']['tkgSharedserviceSpec'][
            'tkgSharedserviceDhcpStartRange']
        dhcpEnd = self.jsonspec['tkgComponentSpec']['tkgSharedserviceSpec'][
            'tkgSharedserviceDhcpEndRange']
        dnsServers = self.jsonspec['envSpec']['infraComponents']['dnsServersIp']
        network = nsxtClient.getNetworkIp(gatewayAddress)
        shared_network_name = self.jsonspec['tkgComponentSpec']['tkgSharedserviceSpec'][
            'tkgSharedserviceNetworkName']
        shared_segment = nsxtClient.createNsxtSegment(shared_network_name, gatewayAddress,
                                        dhcpStart,
                                        dhcpEnd, dnsServers, network, True)
        if shared_segment[1] != 200:
            logger.error("Failed to create shared segments" + str(shared_segment[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create shared segments" + str(shared_segment[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        dhcp = nsxtClient.createVcfDhcpServer()
        if dhcp[1] != 200:
            logger.error("Failed to create dhcp server " + str(dhcp[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create dhcp server " + str(dhcp[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        cluster_wip = self.jsonspec['tkgComponentSpec']['tkgClusterVipNetwork'][
            'tkgClusterVipNetworkName']
        gatewayAddress = self.jsonspec['tkgComponentSpec']['tkgClusterVipNetwork'][
            'tkgClusterVipNetworkGatewayCidr']
        network = nsxtClient.getNetworkIp(gatewayAddress)
        segment = nsxtClient.createNsxtSegment(cluster_wip,
                                    gatewayAddress,
                                    dhcpStart,
                                    dhcpEnd, dnsServers, network, False)
        if segment[1] != 200:
            logger.error(
                "Failed to create  segments " + cluster_wip + " " + str(segment[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create shared segment " + cluster_wip + " " + str(segment[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        mgmt_data = self.jsonspec['tkgMgmtDataNetwork']['tkgMgmtDataNetworkName']
        gatewayAddress = self.jsonspec['tkgMgmtDataNetwork']['tkgMgmtDataNetworkGatewayCidr']
        network = nsxtClient.getNetworkIp(gatewayAddress)
        segment = nsxtClient.createNsxtSegment(mgmt_data,
                                    gatewayAddress,
                                    dhcpStart,
                                    dhcpEnd, dnsServers, network, False)
        if segment[1] != 200:
            logger.error("Failed to create  segments " + mgmt_data + " " + str(segment[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create shared segment " + mgmt_data + " " + str(segment[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        avi_mgmt = self.jsonspec['tkgComponentSpec']['aviMgmtNetwork'][
            'aviMgmtNetworkName']
        avi_gatewayAddress = self.jsonspec['tkgComponentSpec']['aviMgmtNetwork'][
            'aviMgmtNetworkGatewayCidr']
        segment = nsxtClient.createNsxtSegment(avi_mgmt,
                                    avi_gatewayAddress,
                                    dhcpStart,
                                    dhcpEnd, dnsServers, network, False)
        if segment[1] != 200:
            logger.error("Failed to create  segments " + avi_mgmt + " " + str(segment[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create shared segment " + avi_mgmt + " " + str(segment[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        ip = nsxtClient.get_ip_address("eth0")
        if ip is None:
            logger.error("Failed to get arcas vm ip")
            d = {
                "responseType": "ERROR",
                "msg": "Failed to get arcas vm ip",
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        arcas_group = nsxtClient.createGroup(VCF.ARCAS_GROUP, None,
                                "true", ip)
        if arcas_group[1] != 200:
            logger.error(
                "Failed to create  group " + VCF.ARCAS_GROUP + " " + str(
                    arcas_group[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create group " + VCF.ARCAS_GROUP + " " + str(
                    arcas_group[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        arcas_svc = nsxtClient.createVipService(ServiceName.ARCAS_SVC, "8888")
        if arcas_svc[1] != 200:
            logger.error(
                "Failed to create service " + ServiceName.ARCAS_SVC + " " + str(
                    arcas_svc[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create service " + ServiceName.ARCAS_SVC + " " + str(
                    arcas_svc[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        arcas_svc = nsxtClient.createVipService(ServiceName.ARCAS_BACKEND_SVC, "5000")
        if arcas_svc[1] != 200:
            logger.error(
                "Failed to create service " + ServiceName.ARCAS_BACKEND_SVC + " " + str(
                    arcas_svc[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create service " + ServiceName.ARCAS_BACKEND_SVC + " " + str(
                    arcas_svc[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        avi_mgmt_group = nsxtClient.createGroup(GroupNameCgw.DISPLAY_NAME_VCF_AVI_Management_Network_Group_CGW, avi_mgmt,
                                    False, None)
        if avi_mgmt_group[1] != 200:
            logger.error(
                "Failed to create  group " + GroupNameCgw.DISPLAY_NAME_VCF_AVI_Management_Network_Group_CGW + " " + str(
                    avi_mgmt_group[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create group " + GroupNameCgw.DISPLAY_NAME_VCF_AVI_Management_Network_Group_CGW + " " + str(
                    avi_mgmt_group[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        cluster_vip_group = nsxtClient.createGroup(GroupNameCgw.DISPLAY_NAME_VCF_CLUSTER_VIP_NETWORK_Group_CGW, cluster_wip,
                                        False, None)
        if cluster_vip_group[1] != 200:
            logger.error(
                "Failed to create  group " + GroupNameCgw.DISPLAY_NAME_VCF_CLUSTER_VIP_NETWORK_Group_CGW + " " + str(
                    cluster_vip_group[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create  group " + GroupNameCgw.DISPLAY_NAME_VCF_CLUSTER_VIP_NETWORK_Group_CGW + " " + str(
                    cluster_vip_group[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        shared_service_group = nsxtClient.createGroup(GroupNameCgw.DISPLAY_NAME_VCF_TKG_SharedService_Group_CGW,
                                        shared_network_name, False, None)
        if shared_service_group[1] != 200:
            logger.error(
                "Failed to create group " + GroupNameCgw.DISPLAY_NAME_VCF_TKG_SharedService_Group_CGW + " " + str(
                    shared_service_group[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create  group " + GroupNameCgw.DISPLAY_NAME_VCF_TKG_SharedService_Group_CGW + " " + str(
                    shared_service_group[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        mgmt = self.jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgMgmtNetworkName']
        mgmt_group = nsxtClient.createGroup(GroupNameCgw.DISPLAY_NAME_VCF_TKG_Management_Network_Group_CGW, mgmt, False, None)
        if mgmt_group[1] != 200:
            logger.error(
                "Failed to create group " + GroupNameCgw.DISPLAY_NAME_VCF_TKG_Management_Network_Group_CGW + " " + str(
                    mgmt_group[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create group " + GroupNameCgw.DISPLAY_NAME_VCF_TKG_Management_Network_Group_CGW + " " + str(
                    mgmt_group[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        dns = self.jsonspec['envSpec']['infraComponents']['dnsServersIp']
        dns_group = nsxtClient.createGroup(GroupNameCgw.DISPLAY_NAME_VCF_DNS_IPs_Group,
                                None, "true", dns)
        if dns_group[1] != 200:
            logger.error(
                "Failed to create group " + GroupNameCgw.DISPLAY_NAME_VCF_DNS_IPs_Group + " " + str(
                    dns_group[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create group " + GroupNameCgw.DISPLAY_NAME_VCF_DNS_IPs_Group + " " + str(
                    dns_group[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        ntp = self.jsonspec['envSpec']['infraComponents']['ntpServers']
        ntp_group = nsxtClient.createGroup(GroupNameCgw.DISPLAY_NAME_VCF_NTP_IPs_Group,
                                None, "true", ntp)
        if ntp_group[1] != 200:
            logger.error(
                "Failed to create group " + GroupNameCgw.DISPLAY_NAME_VCF_NTP_IPs_Group + " " + str(
                    ntp_group[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create group " + GroupNameCgw.DISPLAY_NAME_VCF_NTP_IPs_Group + " " + str(
                    ntp_group[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        vCenter = self.jsonspec['envSpec']['vcenterDetails']['vcenterAddress']
        if not nsxtClient.is_ipv4(vCenter):
            vCenter = nsxtClient.getIpFromHost(vCenter)
            if vCenter is None:
                logger.error('Failed to fetch VC ip')
                d = {
                    "responseType": "ERROR",
                    "msg": "Failed to fetch VC ip",
                    "ERROR_CODE": 500
                }
                return json.dumps(d), 500
        vc_group = nsxtClient.createGroup(GroupNameCgw.DISPLAY_NAME_VCF_vCenter_IP_Group,
                            None, "true", vCenter)
        if vc_group[1] != 200:
            logger.error(
                "Failed to create group " + GroupNameCgw.DISPLAY_NAME_VCF_vCenter_IP_Group + " " + str(
                    vc_group[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create group " + GroupNameCgw.DISPLAY_NAME_VCF_vCenter_IP_Group + " " + str(
                    vc_group[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        ips = nsxtClient.getESXIips()
        if ips[0] is None:
            logger.error(
                "Failed to create get esxi ip " + ips[1])
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create get esxi ip " + ips[1],
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        esx_group = nsxtClient.createGroup(VCF.ESXI_GROUP,
                                None, "true", ips[0])
        logger.debug(esx_group)
        if esx_group[1] != 200:
            logger.error(
                "Failed to create group " + VCF.ESXI_GROUP + " " + str(
                    esx_group[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create group " + VCF.ESXI_GROUP + " " + str(
                    esx_group[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        headers_ = nsxtClient.grabNsxtHeaders()
        logger.debug(headers_)
        if headers_[0] is None:
            d = {
                "responseType": "ERROR",
                "msg": "Failed to nsxt info " + str(headers_[1]),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        teir1 = nsxtClient.getTier1Details(headers_)
        logger.debug(teir1)
        if teir1[0] is None:
            d = {
                "responseType": "ERROR",
                "msg": "Failed to tier1 details" + str(teir1[1]),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        payload = {"action": "ALLOW",
                "display_name": FirewallRuleCgw.DISPLAY_NAME_VCF_ARCAS_UI,
                "logged": False,
                "source_groups": ["ANY"],
                "destination_groups": [
                    arcas_group[0]["path"]],
                "services": ["/infra/services/SSH", "/infra/services/" + ServiceName.ARCAS_SVC],
                "scope": [teir1[0]]
                }
        arcas_fw = nsxtClient.createFirewallRule(Policy_Name.POLICY_NAME, FirewallRuleCgw.DISPLAY_NAME_VCF_ARCAS_UI, payload)
        logger.debug(arcas_fw)
        if arcas_fw[1] != 200:
            logger.error(
                "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_ARCAS_UI + " " + str(
                    arcas_fw[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_ARCAS_UI + " " + str(
                    arcas_fw[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        payload = {"action": "ALLOW",
                "display_name": FirewallRuleCgw.DISPLAY_NAME_VCF_ARCAS_BACKEND,
                "logged": False,
                "source_groups": ["ANY"],
                "destination_groups": [
                    arcas_group[0]["path"]],
                "services": ["/infra/services/" + ServiceName.ARCAS_BACKEND_SVC],
                "scope": [teir1[0]]
                }
        arcas_fw = nsxtClient.createFirewallRule(Policy_Name.POLICY_NAME, FirewallRuleCgw.DISPLAY_NAME_VCF_ARCAS_BACKEND,
                                    payload)
        if arcas_fw[1] != 200:
            logger.error(
                "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_ARCAS_BACKEND + " " + str(
                    arcas_fw[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create firewall " + GroupNameCgw.DISPLAY_NAME_VCF_ARCAS_BACKEND + " " + str(
                    arcas_fw[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        payload = {"action": "ALLOW",
                "display_name": FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_DNS,
                "logged": False,
                "source_groups": [avi_mgmt_group[0]["path"],
                                    mgmt_group[0]["path"],
                                    shared_service_group[0]["path"]],
                "destination_groups": [
                    dns_group[0]["path"]],
                "services": ["/infra/services/DNS", "/infra/services/DNS-UDP"],
                "scope": [teir1[0]]
                }
        fw = nsxtClient.createFirewallRule(Policy_Name.POLICY_NAME, FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_DNS, payload)
        if fw[1] != 200:
            logger.error(
                "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_DNS + " " + str(
                    fw[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create firewall " + GroupNameCgw.DISPLAY_NAME_VCF_TKG_and_AVI_DNS + " " + str(
                    fw[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        payload = {"action": "ALLOW",
                "display_name": FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_NTP,
                "logged": False,
                "source_groups": [avi_mgmt_group[0]["path"],
                                    mgmt_group[0]["path"],
                                    shared_service_group[0]["path"]],
                "destination_groups": [
                    ntp_group[0]["path"]],
                "services": ["/infra/services/NTP"],
                "scope": [teir1[0]]
                }
        fw_vip = nsxtClient.createFirewallRule(Policy_Name.POLICY_NAME, FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_NTP,
                                    payload)
        if fw_vip[1] != 200:
            logger.error(
                "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_NTP + " " + str(
                    fw_vip[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_NTP + " " + str(
                    fw_vip[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        payload = {"action": "ALLOW",
                "display_name": FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_to_vCenter,
                "logged": False,
                "source_groups": [avi_mgmt_group[0]["path"],
                                    mgmt_group[0]["path"],
                                    shared_service_group[0]["path"]],
                "destination_groups": [
                    vc_group[0]["path"]],
                "services": ["/infra/services/HTTPS"],
                "scope": [teir1[0]]
                }
        fw_vip = nsxtClient.createFirewallRule(Policy_Name.POLICY_NAME,
                                    FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_to_vCenter, payload)
        if fw_vip[1] != 200:
            logger.error(
                "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_to_vCenter + " " + str(
                    fw_vip[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_to_vCenter + " " + str(
                    fw_vip[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        payload = {"action": "ALLOW",
                "display_name": VCF.ESXI_FW,
                "logged": False,
                "source_groups": [mgmt_group[0]["path"],
                                    avi_mgmt_group[0]["path"]],
                "destination_groups": [
                    esx_group[0]["path"]],
                "services": ["/infra/services/HTTPS"],
                "scope": [teir1[0]]
                }
        fw_esx = nsxtClient.createFirewallRule(Policy_Name.POLICY_NAME,
                                    VCF.ESXI_FW, payload)
        if fw_esx[1] != 200:
            logger.error(
                "Failed to create firewall " + VCF.ESXI_FW + " " + str(
                    fw_esx[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create firewall " + VCF.ESXI_FW + " " + str(
                    fw_esx[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        payload = {"action": "ALLOW",
                "display_name": FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_to_Internet,
                "logged": False,
                "source_groups": [mgmt_group[0]["path"],
                                    shared_service_group[0]["path"]],
                "destination_groups": ["ANY"],
                "services": ["ANY"],
                "scope": [teir1[0]]
                }
        fw_vip = nsxtClient.createFirewallRule(Policy_Name.POLICY_NAME,
                                    FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_to_Internet, payload)
        if fw_vip[1] != 200:
            logger.error(
                "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_to_Internet + " " + str(
                    fw_vip[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_AVI_to_Internet + " " + str(
                    fw_vip[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        payload = {"action": "ALLOW",
                "display_name": FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_TKGtoAVIMgmt,
                "logged": False,
                "source_groups": [
                    mgmt_group[0]["path"],
                    shared_service_group[0]["path"]],
                "destination_groups": [
                    avi_mgmt_group[0]["path"]],
                "services": ["/infra/services/HTTPS", "/infra/services/ICMP-ALL"],
                "scope": [teir1[0]]
                }
        fw_vip = nsxtClient.createFirewallRule(Policy_Name.POLICY_NAME, FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_TKGtoAVIMgmt,
                                    payload)
        if fw_vip[1] != 200:
            logger.error(
                "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_TKGtoAVIMgmt + " " + str(
                    fw_vip[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_and_TKGtoAVIMgmt + " " + str(
                    fw_vip[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        vip = nsxtClient.createVipService(ServiceName.KUBE_VIP_VCF_SERVICE, "6443")
        if vip[1] != 200:
            logger.error(
                "Failed to create service " + ServiceName.KUBE_VIP_VCF_SERVICE + " " + str(
                    vip[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create service " + ServiceName.KUBE_VIP_VCF_SERVICE + " " + str(
                    vip[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        payload = {"action": "ALLOW",
                "display_name": FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_CLUSTER_VIP_CGW,
                "logged": False,
                "source_groups": [
                    mgmt_group[0]["path"],
                    shared_service_group[0]["path"]],
                "destination_groups": [
                    cluster_vip_group[0]["path"]],
                "services": ["/infra/services/" + ServiceName.KUBE_VIP_VCF_SERVICE],
                "scope": [teir1[0]]
                }
        fw_vip = nsxtClient.createFirewallRule(Policy_Name.POLICY_NAME, FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_CLUSTER_VIP_CGW,
                                    payload)
        if fw_vip[1] != 200:
            logger.error(
                "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_CLUSTER_VIP_CGW + " " + str(
                    fw_vip[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_CLUSTER_VIP_CGW + " " + str(
                    fw_vip[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        update = nsxtClient.updateDefaultRule(Policy_Name.POLICY_NAME)
        if update[1] != 200:
            logger.error(
                "Failed to default rule " + str(update[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to default rule " + str(update[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        else:
            d = {
                "responseType": "SUCCESS",
                "msg": "VCF pre configuration successful",
                "ERROR_CODE": 200
            }
        return json.dumps(d), 200       

    def configureWorkloadNsxtConfig(self):

        nsxtClient = Nsxt_Client(self.run_config)
        gatewayAddress = self.jsonspec['tkgWorkloadComponents']['tkgWorkloadGatewayCidr']
        dhcp_start = self.jsonspec['tkgWorkloadComponents']['tkgWorkloadDhcpStartRange']
        dhcp_end = self.jsonspec['tkgWorkloadComponents']['tkgWorkloadDhcpEndRange']
        dnsServers = self.jsonspec['envSpec']['infraComponents']['dnsServersIp']
        network = nsxtClient.getNetworkIp(gatewayAddress)
        workload_network_name = self.jsonspec['tkgWorkloadComponents']['tkgWorkloadNetworkName']
        workload_segment = nsxtClient.createNsxtSegment(workload_network_name, gatewayAddress,
                                                dhcp_start,
                                                dhcp_end, dnsServers, network, True)
        if workload_segment[1] != 200:
            logger.error("Failed to create workload segments" + str(workload_segment[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create workload segments" + str(workload_segment[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        worklod_group = nsxtClient.createGroup(GroupNameCgw.DISPLAY_NAME_VCF_TKG_Workload_Networks_Group_CGW,
                                    workload_network_name,
                                    False, None)
        if worklod_group[1] != 200:
            logger.error(
                "Failed to create  group " + GroupNameCgw.DISPLAY_NAME_VCF_TKG_Workload_Networks_Group_CGW + " " + str(
                    worklod_group[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create group " + GroupNameCgw.DISPLAY_NAME_VCF_TKG_Workload_Networks_Group_CGW + " " + str(
                    worklod_group[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        headers_ = nsxtClient.grabNsxtHeaders()
        if headers_[0] is None:
            d = {
                "responseType": "ERROR",
                "msg": "Failed to nsxt info " + str(headers_[1]),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        domainName = nsxtClient.getDomainName(headers_, "default")
        if domainName[0] is None:
            d = {
                "responseType": "ERROR",
                "msg": "Failed to get domain name " + str(domainName[1]),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        uri = "https://" + headers_[2] + "/policy/api/v1/infra/domains/" + domainName[0] + "/groups"
        output = nsxtClient.getList(headers_[1], uri)
        if output[1] != 200:
            logger.error("Failed to get list of groups " + str(output[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to get list of groups " + str(output[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        teir1 = nsxtClient.getTier1Details(headers_)
        if teir1[0] is None:
            d = {
                "responseType": "ERROR",
                "msg": "Failed to tier1 details" + str(headers_[1]),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        payload = {"action": "ALLOW",
                    "display_name": FirewallRuleCgw.DISPLAY_NAME_VCF_WORKLOAD_TKG_and_AVI_DNS,
                    "logged": False,
                    "source_groups": [
                        nsxtClient.checkObjectIsPresentAndReturnPath(output[0],
                                                            GroupNameCgw.DISPLAY_NAME_VCF_TKG_Workload_Networks_Group_CGW)[
                            1],
                        nsxtClient.checkObjectIsPresentAndReturnPath(output[0],
                                                            GroupNameCgw.DISPLAY_NAME_VCF_TKG_Management_Network_Group_CGW)[
                            1]
                    ],
                    "destination_groups": [
                        nsxtClient.checkObjectIsPresentAndReturnPath(output[0],
                                                            GroupNameCgw.DISPLAY_NAME_VCF_DNS_IPs_Group)[
                            1],
                        nsxtClient.checkObjectIsPresentAndReturnPath(output[0],
                                                            GroupNameCgw.DISPLAY_NAME_VCF_NTP_IPs_Group)[
                            1],
                        nsxtClient.checkObjectIsPresentAndReturnPath(output[0],
                                                            GroupNameCgw.DISPLAY_NAME_VCF_TKG_Workload_Networks_Group_CGW)[
                            1],
                        nsxtClient.checkObjectIsPresentAndReturnPath(output[0],
                                                            GroupNameCgw.DISPLAY_NAME_VCF_CLUSTER_VIP_NETWORK_Group_CGW)[
                            1]
                    ],
                    "services": ["/infra/services/DNS",
                                "/infra/services/DNS-UDP",
                                "/infra/services/NTP",
                                "/infra/services/" + ServiceName.KUBE_VIP_VCF_SERVICE],
                    "scope": [teir1[0]]
                    }
        fw = nsxtClient.createFirewallRule(Policy_Name.POLICY_NAME, FirewallRuleCgw.DISPLAY_NAME_VCF_WORKLOAD_TKG_and_AVI_DNS,
                                payload)
        if fw[1] != 200:
            logger.error(
                "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_WORKLOAD_TKG_and_AVI_DNS + " " + str(
                    fw[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create firewall " + GroupNameCgw.DISPLAY_NAME_VCF_WORKLOAD_TKG_and_AVI_DNS + " " + str(
                    fw[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        payload = {"action": "ALLOW",
                    "display_name": FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_WORKLOAD_to_vCenter,
                    "logged": False,
                    "source_groups": [
                        nsxtClient.checkObjectIsPresentAndReturnPath(output[0],
                                                            GroupNameCgw.DISPLAY_NAME_VCF_TKG_Workload_Networks_Group_CGW)[
                            1]
                    ],
                    "destination_groups": [
                        nsxtClient.checkObjectIsPresentAndReturnPath(output[0],
                                                            GroupNameCgw.DISPLAY_NAME_VCF_vCenter_IP_Group)[
                            1]
                    ],
                    "services": ["/infra/services/HTTPS"],
                    "scope": [teir1[0]]
                    }
        fw = nsxtClient.createFirewallRule(Policy_Name.POLICY_NAME, FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_WORKLOAD_to_vCenter,
                                payload)
        if fw[1] != 200:
            logger.error(
                "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_TKG_WORKLOAD_to_vCenter + " " + str(
                    fw[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create firewall " + GroupNameCgw.DISPLAY_NAME_VCF_TKG_WORKLOAD_to_vCenter + " " + str(
                    fw[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        payload = {"action": "ALLOW",
                    "display_name": FirewallRuleCgw.DISPLAY_NAME_VCF_WORKLOAD_TKG_and_AVI_to_Internet,
                    "logged": False,
                    "source_groups": [nsxtClient.checkObjectIsPresentAndReturnPath(output[0],
                                                                        GroupNameCgw.DISPLAY_NAME_VCF_TKG_Workload_Networks_Group_CGW)[
                                            1]
                                        ],
                    "destination_groups": ["ANY"],
                    "services": ["ANY"],
                    "scope": [teir1[0]]
                    }
        fw = nsxtClient.createFirewallRule(Policy_Name.POLICY_NAME,
                                FirewallRuleCgw.DISPLAY_NAME_VCF_WORKLOAD_TKG_and_AVI_to_Internet,
                                payload)
        if fw[1] != 200:
            logger.error(
                "Failed to create firewall " + FirewallRuleCgw.DISPLAY_NAME_VCF_WORKLOAD_TKG_and_AVI_to_Internet + " " + str(
                    fw[0]['msg']))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create firewall " + GroupNameCgw.DISPLAY_NAME_VCF_WORKLOAD_TKG_and_AVI_to_Internet + " " + str(
                    fw[0]['msg']),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        else:
            d = {
                "responseType": "SUCCESS",
                "msg": "VCF pre configuration successful",
                "ERROR_CODE": 200
            }
        return json.dumps(d), 200 
        
