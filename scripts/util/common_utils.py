import os
import traceback
import json
from util import cmd_runner
from pathlib import Path
import logging
from constants.constants import Paths, ControllerLocation, KubernetesOva, MarketPlaceUrl, VrfType
from util.logger_helper import LoggerHelper
import requests
from util.avi_api_helper import getProductSlugId
from util.replace_value import replaceValueSysConfig, replaceValue
from util.file_helper import FileHelper
from util.ShellHelper import runShellCommandAndReturnOutput
from util.cmd_helper import CmdHelper

logger = LoggerHelper.get_logger('common_utils')
logging.getLogger("paramiko").setLevel(logging.WARNING)

def createSubscribedLibrary(vcenter_ip, vcenter_username, password, jsonspec):
    try:
        os.putenv("GOVC_URL", "https://" + vcenter_ip + "/sdk")
        os.putenv("GOVC_USERNAME", vcenter_username)
        os.putenv("GOVC_PASSWORD", password)
        os.putenv("GOVC_INSECURE", "true")
        url = "https://wp-content.vmware.com/v2/latest/lib.json"
        rcmd = cmd_runner.RunCmd()
        data_center = str(jsonspec['envSpec']['vcenterDetails']['vcenterDatacenter'])
        data_store = str(jsonspec['envSpec']['vcenterDetails']['vcenterDatastore'])
        find_command = ["govc", "library.ls"]
        output = rcmd.runShellCommandAndReturnOutputAsList(find_command)
        if str(output[0]).__contains__(ControllerLocation.SUBSCRIBED_CONTENT_LIBRARY):
            logger.info(ControllerLocation.SUBSCRIBED_CONTENT_LIBRARY + " is already present")
        else:
            create_command = ["govc", "library.create", "-sub=" + url, "-ds=" + data_store, "-dc=" + data_center,
                              "-sub-autosync=true", "-sub-ondemand=true",
                              ControllerLocation.SUBSCRIBED_CONTENT_LIBRARY]
            output = rcmd.runShellCommandAndReturnOutputAsList(create_command)
            if output[1] != 0:
                return None, "Failed to create content library"
            logger.info("Content library created successfully")
    except Exception as e:
        return None, "Failed"
    return "SUCCESS", "LIBRARY"

def getOvaMarketPlace(filename, refreshToken, version, baseOS):

    rcmd = cmd_runner.RunCmd()
    filename = filename + ".ova"
    solutionName = KubernetesOva.MARKETPLACE_KUBERNETES_SOLUTION_NAME
    if baseOS == "photon":
        ova_groupname = KubernetesOva.MARKETPLACE_PHOTON_GROUPNAME
    else:
        ova_groupname = KubernetesOva.MARKETPLACE_UBUTNU_GROUPNAME

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "refreshToken": refreshToken
    }
    json_object = json.dumps(payload, indent=4)
    sess = requests.request("POST", MarketPlaceUrl.URL + "/api/v1/user/login", headers=headers,
                            data=json_object, verify=False)
    if sess.status_code != 200:
        return None, "Failed to login and obtain csp-auth-token"
    else:
        token = sess.json()["access_token"]

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "csp-auth-token": token
    }

    objectid = None
    #if str(MarketPlaceUrl.API_URL).__contains__("stg"):
        #slug = "false"
    #else:
    slug = "true"

    _solutionName = getProductSlugId(MarketPlaceUrl.TANZU_PRODUCT, headers)
    if _solutionName[0] is None:
        return None, "Failed to find product on Marketplace " + str(_solutionName[1])
    solutionName = _solutionName[0]
    product = requests.get(
        MarketPlaceUrl.API_URL + "/products/" + solutionName + "?isSlug=" + slug + "&ownorg=false", headers=headers,
        verify=False)

    if product.status_code != 200:
        return None, "Failed to Obtain Product ID"
    else:
        product_id = product.json()['response']['data']['productid']
        for metalist in product.json()['response']['data']['metafilesList']:
            if metalist["version"] == version[1:] and str(metalist["groupname"]).strip("\t") == ova_groupname:
                objectid = metalist["metafileobjectsList"][0]['fileid']
                ovaName = metalist["metafileobjectsList"][0]['filename']
                app_version = metalist['appversion']
                metafileid = metalist['metafileid']

    if (objectid or ovaName or app_version or metafileid) is None:
        return None, "Failed to find the file details in Marketplace"

    logger.info("Downloading kfubernetes ova - " + ovaName)

    payload = {
        "eulaAccepted": "true",
        "appVersion": app_version,
        "metafileid": metafileid,
        "metafileobjectid": objectid
    }

    json_object = json.dumps(payload, indent=4).replace('\"true\"', 'true')
    presigned_url = requests.request("POST",
                                     MarketPlaceUrl.URL + "/api/v1/products/" + product_id + "/download",
                                     headers=headers, data=json_object, verify=False)
    if presigned_url.status_code != 200:
        return None, "Failed to obtain pre-signed URL"
    else:
        download_url = presigned_url.json()["response"]["presignedurl"]

    curl_inspect_cmd = 'curl -I -X GET {} --output /tmp/resp.txt'.format(download_url)
    rcmd.run_cmd_only(curl_inspect_cmd)
    with open('/tmp/resp.txt', 'r') as f:
        data_read = f.read()
    if 'HTTP/1.1 200 OK' in data_read:
        logger.info('Proceed to Download')
        ova_path = "/tmp/" + filename
        curl_download_cmd = 'curl -X GET {d_url} --output {tmp_path}'.format(d_url=download_url,
                                                                             tmp_path=ova_path)
        rcmd.run_cmd_only(curl_download_cmd)
    else:
        logger.info('Error in presigned url/key: {} '.format(data_read.split('\n')[0]))
        return None, "Invalid key/url"

    return filename, "Kubernetes OVA download successful"


def downloadAndPushToVCMarketPlace(file, datacenter, datastore, networkName, clusterName, refresToken, ovaVersion,
                                   ovaOS, jsonspec):
    my_file = Path("/tmp/" + file + ".ova")
    rcmd = cmd_runner.RunCmd()
    if not my_file.exists():
        logger.info("Downloading kubernetes ova from MarketPlace")
        download_status = getOvaMarketPlace(file, refresToken, ovaVersion, ovaOS)
        if download_status[0] is None:
            return None, download_status[1]
        logger.info("Kubernetes ova downloaded  at location " + "/tmp/" + file)
    else:
        logger.info("Kubernetes ova is already downloaded")
    kube_config = FileHelper.read_resource(Paths.KUBE_OVA_CONFIG)
    kube_config_file = "/tmp/kubeova.json"
    FileHelper.write_to_file(kube_config, kube_config_file)
    replaceValueSysConfig(kube_config_file, "Name", "name", file)
    replaceValue(kube_config_file, "NetworkMapping", "Network", networkName)
    logger.info("Pushing " + file + " to vcenter and making as template")
    vcenter_ip = jsonspec['envSpec']['vcenterDetails']['vcenterAddress']
    vcenter_username = jsonspec['envSpec']['vcenterDetails']['vcenterSsoUser']
    enc_password = jsonspec['envSpec']['vcenterDetails']['vcenterSsoPasswordBase64']
    password = CmdHelper.decode_base64(enc_password)
    os.putenv("GOVC_URL", "https://" + vcenter_ip + "/sdk")
    os.putenv("GOVC_USERNAME", vcenter_username)
    os.putenv("GOVC_PASSWORD", password)
    os.putenv("GOVC_INSECURE", "true")
    command_template = ["govc", "import.ova", "-options", kube_config_file, "-dc="+datacenter,
                        "-ds=" + datastore, "-pool=" + clusterName + "/Resources",
                        "/tmp/" + file + ".ova"]
    output = rcmd.runShellCommandAndReturnOutputAsList(command_template)
    if output[1] != 0:
        return None, "Failed export kubernetes ova to vCenter"
    return "SUCCESS", "DEPLOYED"

def downloadAndPushKubernetesOvaMarketPlace(jsonspec, version, baseOS):
    try:
        rcmd = cmd_runner.RunCmd()
        networkName = str(jsonspec["tkgComponentSpec"]["tkgMgmtComponents"]["tkgMgmtNetworkName"])
        data_store = str(jsonspec['envSpec']['vcenterDetails']['vcenterDatastore'])
        vCenter_datacenter = jsonspec['envSpec']['vcenterDetails']['vcenterDatacenter']
        vCenter_cluster = jsonspec['envSpec']['vcenterDetails']['vcenterCluster']
        refToken = jsonspec['envSpec']['marketplaceSpec']['refreshToken']
        if baseOS == "photon":
            file = KubernetesOva.MARKETPLACE_PHOTON_KUBERNETES_FILE_NAME + "-" + version
            template = KubernetesOva.MARKETPLACE_PHOTON_KUBERNETES_FILE_NAME + "-" + version
        elif baseOS == "ubuntu":
            file = KubernetesOva.MARKETPLACE_UBUNTU_KUBERNETES_FILE_NAME + "-" + version
            template = KubernetesOva.MARKETPLACE_UBUNTU_KUBERNETES_FILE_NAME + "-" + version
        else:
            return None, "Invalid ova type " + baseOS
        govc_command = ["govc", "ls", "/" + vCenter_datacenter + "/vm"]
        output = rcmd.runShellCommandAndReturnOutputAsList(govc_command)
        if str(output[0]).__contains__(template):
            logger.info(template + " is already present in vcenter")
            return "SUCCESS", "ALREADY_PRESENT"
        download = downloadAndPushToVCMarketPlace(file, vCenter_datacenter, data_store, networkName,
                                                          vCenter_cluster, refToken,
                                                          version, baseOS, jsonspec)
        if download[0] is None:
            return None, download[1]
        return "SUCCESS", "DEPLOYED"

    except Exception as e:
        return None, str(e)

def getCloudStatus(ip, csrf2, aviVersion, cloudName):
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": csrf2[1],
        "referer": "https://" + ip + "/login",
        "x-avi-version": aviVersion,
        "x-csrftoken": csrf2[0]
    }
    body = {}
    url = "https://" + ip + "/api/cloud"
    response_csrf = requests.request("GET", url, headers=headers, data=body, verify=False)
    if response_csrf.status_code != 200:
        return None, response_csrf.text
    else:
        for re in response_csrf.json()["results"]:
            if re['name'] == cloudName:
                os.system("rm -rf newCloudInfo.json")
                with open("./newCloudInfo.json", "w") as outfile:
                    json.dump(response_csrf.json(), outfile)
                return re["url"], "SUCCESS"
    return "NOT_FOUND", "SUCCESS"

def seperateNetmaskAndIp(cidr):
    return str(cidr).split("/")

def getSECloudStatus(ip, csrf2, aviVersion, seGroupName):
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": csrf2[1],
        "referer": "https://" + ip + "/login",
        "x-avi-version": aviVersion,
        "x-csrftoken": csrf2[0]
    }
    body = {}
    json_object = json.dumps(body, indent=4)
    url = "https://" + ip + "/api/serviceenginegroup"
    response_csrf = requests.request("GET", url, headers=headers, data=json_object, verify=False)
    if response_csrf.status_code != 200:
        return None, response_csrf.text
    else:
        for re in response_csrf.json()["results"]:
            if re['name'] == seGroupName:
                return re["url"], "SUCCESS"
    return "NOT_FOUND", "SUCCESS"

def getVrfAndNextRoutId(ip, csrf2, cloudUuid, typen, routIp, aviVersion):
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": csrf2[1],
        "referer": "https://" + ip + "/login",
        "x-avi-version": aviVersion,
        "x-csrftoken": csrf2[0]
    }
    body = {}
    routId = 0
    url = "https://" + ip + "/api/vrfcontext/?name.in=" + typen + "&cloud_ref.uuid=" + cloudUuid
    response_csrf = requests.request("GET", url, headers=headers, data=body, verify=False)
    if response_csrf.status_code != 200:
        return None, response_csrf.text
    else:
        liist = []
        for re in response_csrf.json()['results']:
            if re['name'] == typen:
                try:
                    for st in re['static_routes']:
                        liist.append(int(st['route_id']))
                        print(st['next_hop']['addr'])
                        print(routIp)
                        if st['next_hop']['addr'] == routIp:
                            return re['url'], "Already_Configured"
                    liist.sort()
                    routId = int(liist[-1]) + 1
                except:
                    pass
                if typen == VrfType.MANAGEMENT:
                    routId = 1
                return re['url'], routId
            else:
                return None, "NOT_FOUND"
        return None, "NOT_FOUND"

def addStaticRoute(ip, csrf2, vrfUrl, routeIp, routId, aviVersion):
    if routId == 0:
        routId = 1
    body = {
        "add": {
            "static_routes": [
                {
                    "prefix": {
                        "ip_addr": {
                            "addr": "0.0.0.0",
                            "type": "V4"
                        },
                        "mask": 0
                    },
                    "next_hop": {
                        "addr": routeIp,
                        "type": "V4"
                    },
                    "route_id": routId
                }
            ]
        }
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": csrf2[1],
        "referer": "https://" + ip + "/login",
        "x-avi-version": aviVersion,
        "x-csrftoken": csrf2[0]
    }
    url = vrfUrl
    json_object = json.dumps(body, indent=4)
    response_csrf = requests.request("PATCH", url, headers=headers, data=json_object, verify=False)
    if response_csrf.status_code != 200:
        return None, response_csrf.text
    else:
        return "SUCCESS", 200


def getSeNewBody(newCloudUrl, seGroupName, clusterUrl, dataStore):
    body = {
        "max_vs_per_se": 10,
        "min_scaleout_per_vs": 2,
        "max_scaleout_per_vs": 4,
        "max_se": 10,
        "vcpus_per_se": 2,
        "memory_per_se": 4096,
        "disk_per_se": 15,
        "max_cpu_usage": 80,
        "min_cpu_usage": 30,
        "se_deprovision_delay": 120,
        "auto_rebalance": False,
        "se_name_prefix": "Avi",
        "vs_host_redundancy": True,
        "vcenter_folder": "AviSeFolder",
        "vcenter_datastores_include": True,
        "vcenter_datastore_mode": "VCENTER_DATASTORE_SHARED",
        "cpu_reserve": False,
        "mem_reserve": True,
        "ha_mode": "HA_MODE_SHARED_PAIR",
        "algo": "PLACEMENT_ALGO_PACKED",
        "buffer_se": 0,
        "active_standby": False,
        "placement_mode": "PLACEMENT_MODE_AUTO",
        "se_dos_profile": {
            "thresh_period": 5
        },
        "auto_rebalance_interval": 300,
        "aggressive_failure_detection": False,
        "realtime_se_metrics": {
            "enabled": False,
            "duration": 30
        },
        "vs_scaleout_timeout": 600,
        "vs_scalein_timeout": 30,
        "connection_memory_percentage": 50,
        "extra_config_multiplier": 0,
        "vs_scalein_timeout_for_upgrade": 30,
        "log_disksz": 10000,
        "os_reserved_memory": 0,
        "hm_on_standby": True,
        "per_app": False,
        "distribute_load_active_standby": False,
        "auto_redistribute_active_standby_load": False,
        "dedicated_dispatcher_core": False,
        "cpu_socket_affinity": False,
        "num_flow_cores_sum_changes_to_ignore": 8,
        "least_load_core_selection": True,
        "extra_shared_config_memory": 0,
        "se_tunnel_mode": 0,
        "se_vs_hb_max_vs_in_pkt": 256,
        "se_vs_hb_max_pkts_in_batch": 64,
        "se_thread_multiplier": 1,
        "async_ssl": False,
        "async_ssl_threads": 1,
        "se_udp_encap_ipc": 0,
        "se_tunnel_udp_port": 1550,
        "archive_shm_limit": 8,
        "significant_log_throttle": 100,
        "udf_log_throttle": 100,
        "non_significant_log_throttle": 100,
        "ingress_access_mgmt": "SG_INGRESS_ACCESS_ALL",
        "ingress_access_data": "SG_INGRESS_ACCESS_ALL",
        "se_sb_dedicated_core": False,
        "se_probe_port": 7,
        "se_sb_threads": 1,
        "ignore_rtt_threshold": 5000,
        "waf_mempool": True,
        "waf_mempool_size": 64,
        "host_gateway_monitor": False,
        "vss_placement": {
            "num_subcores": 4,
            "core_nonaffinity": 2
        },
        "flow_table_new_syn_max_entries": 0,
        "disable_csum_offloads": False,
        "disable_gro": True,
        "disable_tso": False,
        "enable_hsm_priming": False,
        "distribute_queues": False,
        "vss_placement_enabled": False,
        "enable_multi_lb": False,
        "n_log_streaming_threads": 1,
        "free_list_size": 1024,
        "max_rules_per_lb": 150,
        "max_public_ips_per_lb": 30,
        "self_se_election": True,
        "minimum_connection_memory": 20,
        "shm_minimum_config_memory": 4,
        "heap_minimum_config_memory": 8,
        "disable_se_memory_check": False,
        "memory_for_config_update": 15,
        "num_dispatcher_cores": 0,
        "ssl_preprocess_sni_hostname": True,
        "se_dpdk_pmd": 0,
        "se_use_dpdk": 0,
        "min_se": 1,
        "se_pcap_reinit_frequency": 0,
        "se_pcap_reinit_threshold": 0,
        "disable_avi_securitygroups": False,
        "se_flow_probe_retries": 2,
        "vs_switchover_timeout": 300,
        "config_debugs_on_all_cores": False,
        "vs_se_scaleout_ready_timeout": 60,
        "vs_se_scaleout_additional_wait_time": 0,
        "se_dp_hm_drops": 0,
        "disable_flow_probes": False,
        "dp_aggressive_hb_frequency": 100,
        "dp_aggressive_hb_timeout_count": 10,
        "bgp_state_update_interval": 60,
        "max_memory_per_mempool": 64,
        "app_cache_percent": 10,
        "app_learning_memory_percent": 0,
        "datascript_timeout": 1000000,
        "se_pcap_lookahead": False,
        "enable_gratarp_permanent": False,
        "gratarp_permanent_periodicity": 10,
        "reboot_on_panic": True,
        "se_flow_probe_retry_timer": 40,
        "se_lro": True,
        "se_tx_batch_size": 64,
        "se_pcap_pkt_sz": 69632,
        "se_pcap_pkt_count": 0,
        "distribute_vnics": False,
        "se_dp_vnic_queue_stall_event_sleep": 0,
        "se_dp_vnic_queue_stall_timeout": 10000,
        "se_dp_vnic_queue_stall_threshold": 2000,
        "se_dp_vnic_restart_on_queue_stall_count": 3,
        "se_dp_vnic_stall_se_restart_window": 3600,
        "se_pcap_qdisc_bypass": True,
        "se_rum_sampling_nav_percent": 1,
        "se_rum_sampling_res_percent": 100,
        "se_rum_sampling_nav_interval": 1,
        "se_rum_sampling_res_interval": 2,
        "se_kni_burst_factor": 0,
        "max_queues_per_vnic": 1,
        "se_rl_prop": {
            "msf_num_stages": 1,
            "msf_stage_size": 16384
        },
        "app_cache_threshold": 5,
        "core_shm_app_learning": False,
        "core_shm_app_cache": False,
        "pcap_tx_mode": "PCAP_TX_AUTO",
        "se_dp_max_hb_version": 2,
        "resync_time_interval": 65536,
        "use_hyperthreaded_cores": True,
        "se_hyperthreaded_mode": "SE_CPU_HT_AUTO",
        "compress_ip_rules_for_each_ns_subnet": True,
        "se_vnic_tx_sw_queue_size": 256,
        "se_vnic_tx_sw_queue_flush_frequency": 0,
        "transient_shared_memory_max": 30,
        "log_malloc_failure": True,
        "se_delayed_flow_delete": True,
        "se_txq_threshold": 2048,
        "se_mp_ring_retry_count": 500,
        "dp_hb_frequency": 100,
        "dp_hb_timeout_count": 10,
        "pcap_tx_ring_rd_balancing_factor": 10,
        "use_objsync": True,
        "se_ip_encap_ipc": 0,
        "se_l3_encap_ipc": 0,
        "handle_per_pkt_attack": True,
        "per_vs_admission_control": False,
        "objsync_port": 9001,
        "objsync_config": {
            "objsync_cpu_limit": 30,
            "objsync_reconcile_interval": 10,
            "objsync_hub_elect_interval": 60
        },
        "se_dp_isolation": False,
        "se_dp_isolation_num_non_dp_cpus": 0,
        "cloud_ref": newCloudUrl,
        "vcenter_datastores": [{
            "datastore_name": dataStore
        }],
        "service_ip_subnets": [],
        "auto_rebalance_criteria": [],
        "auto_rebalance_capacity_per_se": [],
        "vcenter_clusters": {
            "include": True,
            "cluster_refs": [
                clusterUrl
            ]
        },
        "license_tier": "ENTERPRISE",
        "license_type": "LIC_CORES",
        "se_bandwidth_type": "SE_BANDWIDTH_UNLIMITED",
        "name": seGroupName
    }
    return json.dumps(body, indent=4)

def getClusterStatusOnTanzu(management_cluster, typen):
    try:
        if typen == "management":
            list = ["tanzu", "management-cluster", "get"]
        else:
            list = ["tanzu", "cluster", "get"]
        o = runShellCommandAndReturnOutput(list)
        if o[1] == 0:
            try:
                if o[0].__contains__(management_cluster) and o[0].__contains__("running"):
                    return True
                else:
                    return False
            except:
                return False
        else:
            return False
    except:
        return False

def runSsh(vc_user):
    os.system("rm -rf /root/.ssh/id_rsa")
    os.system("ssh-keygen -t rsa -b 4096 -C '" + vc_user + "' -f /root/.ssh/id_rsa -N ''")
    os.system("eval $(ssh-agent)")
    os.system("ssh-add /root/.ssh/id_rsa")
    with open('/root/.ssh/id_rsa.pub', 'r') as f:
        re = f.readline()
    return re

def getVipNetworkIpNetMask(ip, csrf2, name, aviVersion):
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": csrf2[1],
        "referer": "https://" + ip + "/login",
        "x-avi-version": aviVersion,
        "x-csrftoken": csrf2[0]
    }
    body = {}
    url = "https://" + ip + "/api/network"
    try:
        response_csrf = requests.request("GET", url, headers=headers, data=body, verify=False)
        if response_csrf.status_code != 200:
            return None, response_csrf.text
        else:
            for re in response_csrf.json()["results"]:
                if re['name'] == name:
                    for sub in re["configured_subnets"]:
                        return str(sub["prefix"]["ip_addr"]["addr"]) + "/" + str(sub["prefix"]["mask"]), "SUCCESS"
            else:
                next_url = None if not response_csrf.json()["next"] else response_csrf.json()["next"]
                while len(next_url) > 0:
                    response_csrf = requests.request("GET", next_url, headers=headers, data=body, verify=False)
                    for re in response_csrf.json()["results"]:
                        if re['name'] == name:
                            for sub in re["configured_subnets"]:
                                return str(sub["prefix"]["ip_addr"]["addr"]) + "/" + str(
                                    sub["prefix"]["mask"]), "SUCCESS"
                    next_url = None if not response_csrf.json()["next"] else response_csrf.json()["next"]
        return "NOT_FOUND", "FAILED"
    except KeyError:
        return "NOT_FOUND", "FAILED"
