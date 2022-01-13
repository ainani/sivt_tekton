import json
from pathlib import Path

from constants.api_payloads import NsxTPayload
from constants.constants import ComponentPrefix, VmcNsxtGateways, FirewallRulePrefix, NsxtScopes, NsxtServicePaths
from lib.nsxt_client import NsxtClient
from model.run_config import RunConfig
from util.logger_helper import LoggerHelper, log

logger = LoggerHelper.get_logger(Path(__file__).stem)


class NsxtWorkflow:
    def __init__(self, run_config: RunConfig):
        self.run_config = run_config
        self.nsxt_client: NsxtClient = NsxtClient(self.run_config)

    @log("Get mapping of segment names and their config details from input config spec.")
    def _get_segments_from_spec(self):
        """
        Get mapping of segment names and their config details from input config spec.
        :return: dict containing mapping of segment names to the segment spec from the input config spec.
        """
        segments = dict()
        segments[ComponentPrefix.MGMT_CLU_NW] = self.run_config.spec.tkg.management.segment
        segments[ComponentPrefix.MGMT_DATA_VIP_NW] = self.run_config.spec.tkg.management.dataVipSegment
        segments[ComponentPrefix.SHARED_CLU_NW] = self.run_config.spec.tkg.sharedService.segment
        segments[ComponentPrefix.ALB_MGMT_NW] = self.run_config.spec.avi.segment
        segments[ComponentPrefix.CLUSTER_VIP_NW] = self.run_config.spec.tkg.management.clusterVipSegment
        for i, v in enumerate(self.run_config.spec.tkg.workloadClusters):
            nw_key = f"{ComponentPrefix.WORKLOAD_CLU_NW}_{i}"
            segments[nw_key] = v.segment
            data_vip_key = f"{ComponentPrefix.WORKLOAD_DATA_VIP_NW}_{i}"
            segments[data_vip_key] = v.dataVipSegment
        return segments

    @log("Create required segments on NSX-T")
    def _create_segments(self):
        """
        Create required segments on NSX-T.
        :return: dict mapping ComponentPrefix with respective segment paths
        """
        # Get segments to create
        segments = self._get_segments_from_spec()
        nsxt_segments = self.nsxt_client.list_segments(VmcNsxtGateways.CGW)
        segment_paths = dict()
        try:
            for segment_id, details in segments.items():
                logger.info(f"Checking if segment exists with id: {segment_id}")
                segment = NsxtClient.find_object(nsxt_segments, segment_id)
                if not segment:
                    logger.info(f"Segment [{segment_id}] not found.")
                    seg_details = self.nsxt_client.create_segment("cgw", segment_id, segment=details,
                                                                  dns_servers=self.run_config.spec.tkg.common.dnsServers)
                    segment_paths[segment_id] = NsxtClient.get_object_path(seg_details)
                else:
                    segment_paths[segment_id] = NsxtClient.get_object_path(segment)
                    logger.info(f"Segment [{segment_id}] already exists. Skipping creation.")
        except Exception as ex:
            logger.error("Failed to create segments.")
            raise ex
        return segment_paths

    @log("Get mapping of group and their config details from input config spec.")
    def _get_groups(self, gateway_id: VmcNsxtGateways, segment_paths):
        """
        Get mapping of group and their config details from input config spec
        :param gateway_id: gateway ID for which the mapping is needed.
        :param segment_paths: dict mapping segment names to the segment paths
        :return: dict mapping group names to the group membership expression spec.
        """
        groups = dict()
        groups[ComponentPrefix.MGMT_CLU_NW] = NsxTPayload.PATH_EXPRESSION.format(
            paths=json.dumps([segment_paths[ComponentPrefix.MGMT_CLU_NW]]))
        groups[ComponentPrefix.SHARED_CLU_NW] = NsxTPayload.PATH_EXPRESSION.format(
            paths=json.dumps([segment_paths[ComponentPrefix.SHARED_CLU_NW]]))
        groups[ComponentPrefix.CLUSTER_VIP_NW] = NsxTPayload.PATH_EXPRESSION.format(
            paths=json.dumps([segment_paths[ComponentPrefix.CLUSTER_VIP_NW]]))
        groups[ComponentPrefix.ALB_MGMT_NW] = NsxTPayload.PATH_EXPRESSION.format(
            paths=json.dumps([segment_paths[ComponentPrefix.ALB_MGMT_NW]]))
        for i, v in enumerate(self.run_config.spec.tkg.workloadClusters):
            group_key = f"{ComponentPrefix.WORKLOAD_CLU_NW}_{i}"
            groups[group_key] = NsxTPayload.PATH_EXPRESSION.format(paths=json.dumps([segment_paths[group_key]]))
        if gateway_id == VmcNsxtGateways.CGW:
            groups[ComponentPrefix.DNS_IPS] = NsxTPayload.IP_ADDRESS_EXPRESSION.format(
                ip_addresses=json.dumps(self.run_config.spec.tkg.common.dnsServers))
            groups[ComponentPrefix.NTP_IPS] = NsxTPayload.IP_ADDRESS_EXPRESSION.format(
                ip_addresses=json.dumps(self.run_config.spec.tkg.common.ntpServers))
            groups[ComponentPrefix.VC_IP] = NsxTPayload.IP_ADDRESS_EXPRESSION.format(
                ip_addresses=json.dumps([self.run_config.vmc.vc_mgmt_ip]))
        return groups

    @log("Create required inventory groups on NSX-T.")
    def _create_groups(self, segment_paths):
        """
        Create required inventory groups on NSX-T
        :param segment_paths: dict containing mapping of segment names to the segment paths
        :return: dict mapping group names to respective object paths
        """
        group_paths = dict()
        for gw_id in (VmcNsxtGateways.CGW, VmcNsxtGateways.MGW):
            try:
                group_paths[gw_id] = dict()
                groups = self._get_groups(gw_id, segment_paths)
                nsxt_groups = self.nsxt_client.list_groups(gw_id)
                for group_id, details in groups.items():
                    group = NsxtClient.find_object(nsxt_groups, group_id)
                    if not group:
                        grp_details = self.nsxt_client.create_group(gw_id, group_id, expression=details)
                        group_paths[gw_id][group_id] = NsxtClient.get_object_path(grp_details)
                    else:
                        group_paths[gw_id][group_id] = NsxtClient.get_object_path(group)
                        logger.info(f"Group [{group_id}] already exists. Skipping creation.")
            except Exception as ex:
                logger.error(f"Failed to create groups on {gw_id} gateway")
                raise ex
        return group_paths

    @log("Create required services on NSX-T")
    def _create_services(self):
        """
        Create required services on NSX-T
        :return: dict mapping service names to object paths
        """
        service_paths = dict()
        try:
            logger.info(f"Checking if {ComponentPrefix.KUBE_VIP_SERVICE} service exists.")
            services = self.nsxt_client.list_services()
            service_id = ComponentPrefix.KUBE_VIP_SERVICE
            service = NsxtClient.find_object(services, service_id)
            if not service:
                logger.info("Creating NSX-T service for accessing kube API on port 6443")
                ser_details = self.nsxt_client.create_service(service_id=service_id,
                                                              service_entry_name=ComponentPrefix.KUBE_VIP_SERVICE_ENTRY)
                service_paths[service_id] = NsxtClient.get_object_path(ser_details)
            else:
                service_paths[service_id] = NsxtClient.get_object_path(service)
                logger.info(f"Service [{service_id}] already exists. Skipping creation.")
        except Exception as ex:
            logger.error(f"Failed to create service: {ComponentPrefix.KUBE_VIP_SERVICE}")
            raise ex
        return service_paths

    @staticmethod
    @log("Get mapping of rule names and their configuration details")
    def _get_firewall_rules(gateway_id: VmcNsxtGateways, group_paths, service_paths):
        """
        Get mapping of rule names and their configuration details
        :param gateway_id: gateway object ID for creating the firewall rules
        :param group_paths: dict mapping group names to object paths
        :param service_paths: dict mapping service names to service paths
        :return: dict mapping rule names with configuration details
        """
        rules = dict()
        grp_paths = group_paths[gateway_id]
        if gateway_id == VmcNsxtGateways.CGW:
            rules[FirewallRulePrefix.INFRA_TO_NTP] = {
                "source": [grp_paths[ComponentPrefix.ALB_MGMT_NW], grp_paths[ComponentPrefix.MGMT_CLU_NW],
                           grp_paths[ComponentPrefix.SHARED_CLU_NW]],
                "destination": [grp_paths[ComponentPrefix.NTP_IPS]],
                "scope": [NsxtScopes.CGW_ALL],
                "services": [NsxtServicePaths.NTP]
            }
            rules[FirewallRulePrefix.INFRA_TO_DNS] = {
                "source": [grp_paths[ComponentPrefix.ALB_MGMT_NW], grp_paths[ComponentPrefix.MGMT_CLU_NW],
                           grp_paths[ComponentPrefix.SHARED_CLU_NW]],
                "destination": [grp_paths[ComponentPrefix.DNS_IPS]],
                "scope": [NsxtScopes.CGW_ALL],
                "services": [NsxtServicePaths.DNS, NsxtServicePaths.DNS_UDP]
            }
            rules[FirewallRulePrefix.INFRA_TO_VC] = {
                "source": [grp_paths[ComponentPrefix.ALB_MGMT_NW], grp_paths[ComponentPrefix.MGMT_CLU_NW],
                           grp_paths[ComponentPrefix.SHARED_CLU_NW]],
                "destination": [grp_paths[ComponentPrefix.VC_IP]],
                "scope": [NsxtScopes.CGW_ALL],
                "services": [NsxtServicePaths.HTTPS]
            }
            rules[FirewallRulePrefix.INFRA_TO_ANY] = {
                "source": [grp_paths[ComponentPrefix.MGMT_CLU_NW], grp_paths[ComponentPrefix.SHARED_CLU_NW]],
                "destination": ["ANY"],
                "scope": [NsxtScopes.CGW_ALL],
                "services": [NsxtServicePaths.ANY]
            }
            rules[FirewallRulePrefix.INFRA_TO_ALB] = {
                "source": [grp_paths[ComponentPrefix.MGMT_CLU_NW], grp_paths[ComponentPrefix.SHARED_CLU_NW]],
                "destination": [grp_paths[ComponentPrefix.ALB_MGMT_NW]],
                "scope": [NsxtScopes.CGW_ALL],
                "services": [NsxtServicePaths.HTTPS]
            }
            rules[FirewallRulePrefix.INFRA_TO_CLUSTER_VIP] = {
                "source": [grp_paths[ComponentPrefix.MGMT_CLU_NW], grp_paths[ComponentPrefix.SHARED_CLU_NW]],
                "destination": [grp_paths[ComponentPrefix.CLUSTER_VIP_NW]],
                "scope": [NsxtScopes.CGW_ALL],
                "services": [service_paths[ComponentPrefix.KUBE_VIP_SERVICE]]
            }
        else:
            rules[FirewallRulePrefix.INFRA_TO_VC] = {
                "source": [grp_paths[ComponentPrefix.ALB_MGMT_NW], grp_paths[ComponentPrefix.MGMT_CLU_NW],
                           grp_paths[ComponentPrefix.SHARED_CLU_NW]],
                "destination": [grp_paths[ComponentPrefix.ESXI]],
                "scope": [NsxtScopes.MGW],
                "services": [NsxtServicePaths.HTTPS]
            }
            rules[FirewallRulePrefix.MGMT_TO_ESXI] = {
                "source": [grp_paths[ComponentPrefix.MGMT_CLU_NW]],
                "destination": [grp_paths[ComponentPrefix.ESXI]],
                "scope": [NsxtScopes.MGW],
                "services": [NsxtServicePaths.HTTPS]
            }
        return rules

    @log("Create required gateway firewall rules.")
    def _create_gateway_firewall_rules(self, group_paths, service_paths):
        """
        Create required gateway firewall rules.
        :param group_paths: dict mapping group names to object paths
        :param service_paths: dict mapping service names to service paths
        :return: None
        """
        for gw_id in (VmcNsxtGateways.CGW, VmcNsxtGateways.MGW):
            try:
                rules = NsxtWorkflow._get_firewall_rules(gw_id, group_paths, service_paths)
                nsxt_rules = self.nsxt_client.list_gateway_firewall_rules(gw_id)
                for rule_id, details in rules.items():
                    if not NsxtClient.find_object(nsxt_rules, rule_id):
                        self.nsxt_client.create_gateway_firewall_rule(gw_id, rule_id, **details)
                    else:
                        logger.info(f"Firewall rule [{rule_id}] already exists on {gw_id} gateway. Skipping creation.")
            except Exception as ex:
                logger.error(f"Failed to create firewall rules on {gw_id} gateway")
                raise ex

    def execute_workflow(self):
        if not self.run_config.spec.vmc:
            logger.info("Not a VMC deployment. Skipping NSX-T configurations..")
            return

        # Create logical segments
        segment_paths = self._create_segments()

        # Create inventory groups
        group_paths = self._create_groups(segment_paths)

        # Include existing group paths
        mgw_groups = self.nsxt_client.list_groups(VmcNsxtGateways.MGW)
        esxi_group = NsxtClient.find_object(mgw_groups, ComponentPrefix.ESXI)
        group_paths[VmcNsxtGateways.MGW][ComponentPrefix.ESXI] = NsxtClient.get_object_path(esxi_group)

        # Create inventory services
        service_paths = self._create_services()

        # Create gateway firewall rules
        self._create_gateway_firewall_rules(group_paths, service_paths)
