import json
import os
import time
from pathlib import Path
from util import cmd_runner

import requests
import urllib3
from avi.sdk.avi_api import ApiSession, AviCredentials
from requests import HTTPError
from tqdm import tqdm

from constants.api_payloads import AlbPayload
from constants.constants import AlbCloudType, AlbLicenseTier, ControllerLocation, MarketPlaceUrl
from model.run_config import RunConfig
from model.spec import NetworkSegment
from util.cmd_helper import CmdHelper
from util.logger_helper import LoggerHelper, log

logger = LoggerHelper.get_logger(Path(__file__).stem)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# Reference: https://github.com/vmware/alb-sdk/blob/eng/python/avi/sdk/README.md


def login(func):
    def inner(*args, **kwargs):
        logger.debug("-" * 80)
        api_creds = AviCredentials()
        self = args[0]
        api_creds.update_from_ansible_module(self.avi_api_spec)
        self.api = ApiSession.get_session(
            api_creds.controller,
            api_creds.username,
            password=api_creds.password,
            timeout=api_creds.timeout,
            tenant=api_creds.tenant,
            tenant_uuid=api_creds.tenant_uuid,
            token=api_creds.token,
            port=api_creds.port,
        )
        result = func(*args, **kwargs)
        self.api.close()
        logger.debug("-" * 80)
        return result

    return inner


class AviApiSpec:
    params = dict()
    """Ref: 
        https://docs.ansible.com/ansible/latest/collections/community/network/avi_api_version_module.html#ansible-collections-community-network-avi-api-version-module
    """

    def __init__(
            self,
            ip,
            username="admin",
            password="58NFaGDJm(PJH0G",
            api_version="16.4.4",
            tenant="",
            tenant_uuid="",
            token="",
            session_id="",
            csrftoken="",
    ) -> None:
        self.params = dict(
            controller=ip,
            username=username,
            password=password,
            old_password="58NFaGDJm(PJH0G",
            api_version=api_version,
            tenant=tenant,
            tenant_uuid=tenant_uuid,
            port=None,
            timeout=300,
            token=token,
            session_id=session_id,
            csrftoken=csrftoken,
        )

def getProductSlugId(productName, headers):
    try:
        product = requests.get(
            MarketPlaceUrl.PRODUCT_SEARCH_URL, headers=headers,
            verify=False)
        if product.status_code != 200:
            return None, "Failed to search  product " + productName + " on Marketplace."
        for pro in product.json()["response"]["dataList"]:
            if str(pro["displayname"]) == productName:
                return str(pro["slug"]), "SUCCESS"
    except Exception as e:
        return None, str(e)

def pushAviToContenLibraryMarketPlace(jsonspec):
    rcmd = cmd_runner.RunCmd()
    try:
        find_command = "govc library.ls /{}/".format(ControllerLocation.CONTROLLER_CONTENT_LIBRARY)
        logger.info('Running find for existing library')
        output = rcmd.run_cmd_output(find_command)
        logger.info('Library found: {}'.format(output) )
        if str(output[0]).__contains__(ControllerLocation.CONTROLLER_NAME):
            logger.info("Avi controller is already present in content library")
            return "SUCCESS", 200
    except:
        pass
    my_file = Path("/tmp/" + ControllerLocation.CONTROLLER_NAME + ".ova")
    data_center = jsonspec['envSpec']['vcenterDetails']['vcenterDatacenter']
    data_store = jsonspec['envSpec']['vcenterDetails']['vcenterDatastore']
    reftoken = jsonspec['envSpec']['marketplaceSpec']['refreshToken']
    avi_version = ControllerLocation.VSPHERE_AVI_VERSION
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "refreshToken": reftoken
    }
    json_object = json.dumps(payload, indent=4)
    sess = requests.request("POST", MarketPlaceUrl.URL + "/api/v1/user/login", headers=headers,
                            data=json_object, verify=False)
    logger.info('Session details: {}'.format(sess.status_code))
    if sess.status_code != 200:
        return None, "Failed to login and obtain csp-auth-token"
    else:
        token = sess.json()["access_token"]
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "csp-auth-token": token
    }
    if my_file.exists():
        logger.info("Avi ova is already downloaded")
    else:
        logger.info("Downloading avi controller from MarketPlace")
        solutionName = ControllerLocation.MARKETPLACE_AVI_SOLUTION_NAME
        # if str(MarketPlaceUrl.API_URL).__contains__("stg"):
        #    slug = "false"
        # else:
        slug = "true"
        _solutionName = getProductSlugId(MarketPlaceUrl.AVI_PRODUCT, headers)
        logger.info('Solution name from marketplace: {}'.format(_solutionName))
        if _solutionName[0] is None:
            return None, "Failed to find product on Marketplace " + str(_solutionName[1])
        solutionName = _solutionName[0]
        product = requests.get(MarketPlaceUrl.API_URL + "/products/" +
                               solutionName + "?isSlug=" + slug + "&ownorg=false", headers=headers, verify=False)
        if product.status_code != 200:
            return None, "Failed to Obtain Product ID"
        else:
            ls = []
            product_id = product.json()['response']['data']['productid']
            logger.info('Product ID: {}'.format(product_id))
            for metalist in product.json()['response']['data']['productdeploymentfilesList']:
                if metalist["appversion"] == avi_version:
                    objectid = metalist['fileid']
                    filename = metalist['name']
                    ls.append(filename)
                    logger.info('filename: {}'.format(filename))
                    break
        payload = {
            "deploymentFileId": objectid,
            "eulaAccepted": "true",
            "productId": product_id
        }

        json_object = json.dumps(payload, indent=4).replace('\"true\"', 'true')
        presigned_url = requests.request("POST",
                                         MarketPlaceUrl.URL + "/api/v1/products/" + product_id + "/download",
                                         headers=headers, data=json_object, verify=False)
        if presigned_url.status_code != 200:
            logger.error('Error on request. Code: {}\n Error: {}'.format(presigned_url.status_code,
                                                                         presigned_url.text))
            return None, "Failed to obtain pre-signed URL"
        else:
            download_url = presigned_url.json()["response"]["presignedurl"]

        response_csfr = requests.request("GET", download_url, headers=headers, verify=False, timeout=600)
        if response_csfr.status_code != 200:
            return None, response_csfr.text
        else:
            command = "rm -rf {}".format(ls[0])
            rcmd.run_cmd_only(command)
            with open(ls[0], 'wb') as f:
                f.write(response_csfr.content)
        command = "mv {} /tmp/{}/.ova".format(ls[0], ControllerLocation.CONTROLLER_NAME)
        rcmd.run_cmd_only(command)
        logger.info(
            "Avi ova downloaded  at location " + "/tmp/" + ControllerLocation.CONTROLLER_NAME + ".ova")
    find_command = "govc library.ls"
    output = rcmd.run_cmd_output(find_command)
    if str(output[0]).__contains__(ControllerLocation.CONTROLLER_CONTENT_LIBRARY):
        logger.info(ControllerLocation.CONTROLLER_CONTENT_LIBRARY + " is already present")
    else:
        find_command = "govc library.create -ds={ds} -dc={dc} {libraryname}".format(ds = data_store,
                                                                                    dc=data_center,
                                                                                  libraryname=ControllerLocation.CONTROLLER_CONTENT_LIBRARY)
        output = rcmd.run_cmd_output(find_command)
        if 'error' in output:
            return None, "Failed to create content library"
    find_command = ["govc", "library.ls", "/" + ControllerLocation.CONTROLLER_CONTENT_LIBRARY + "/"]
    output = rcmd.runShellCommandAndReturnOutputAsList(find_command)
    if output[1] != 0:
        return None, "Failed to find items in content library"
    if str(output[0]).__contains__(ControllerLocation.CONTROLLER_NAME):
        logger.info("Avi controller is already present in content library")
    else:
        logger.info("Pushing Avi controller to content library")
        import_command = ["govc", "library.import", ControllerLocation.CONTROLLER_CONTENT_LIBRARY,
                          "/tmp/" + ControllerLocation.CONTROLLER_NAME + ".ova"]
        output = rcmd.runShellCommandAndReturnOutputAsList(import_command)
        if output[1] != 0:
            return None, "Failed to upload avi controller to content library"
    return "SUCCESS", 200

def downloadAviControllerAndPushToContentLibrary(vcenter_ip, vcenter_username, password, jsonspec):
    try:
        os.putenv("GOVC_URL", "https://" + vcenter_ip + "/sdk")
        os.putenv("GOVC_USERNAME", vcenter_username)
        os.putenv("GOVC_PASSWORD", password)
        os.putenv("GOVC_INSECURE", "true")
        rcmd = cmd_runner.RunCmd()
        logger.info('Check if library is already present')
        VC_Content_Library_name = jsonspec['envSpec']['vcenterDetails']["contentLibraryName"]
        VC_AVI_OVA_NAME = jsonspec['envSpec']['vcenterDetails']["aviOvaName"]
        find_command = ["govc", "library.ls", "/" + VC_Content_Library_name + "/"]
        output = rcmd.runShellCommandAndReturnOutputAsList(find_command)
        if str(output[0]).__contains__(VC_Content_Library_name):
            logger.info(VC_Content_Library_name + " is already present")
        else:
            logger.info(VC_Content_Library_name + " is not present in the content library")
            res = pushAviToContenLibraryMarketPlace(jsonspec)
            find_command = ["govc", "library.ls", "/" + VC_Content_Library_name + "/"]
            output = rcmd.runShellCommandAndReturnOutputAsList(find_command)
            if output[1] != 0:
                return None, "Failed to find items in content library"
            if str(output[0]).__contains__(VC_AVI_OVA_NAME):
                logger.info(VC_AVI_OVA_NAME + " avi controller is already present in content library")
            else:
                logger.error(VC_AVI_OVA_NAME + " need to be present in content library for internet "
                                                               "restricted env, please push avi "
                                                               "controller to content library.")
                return None, VC_AVI_OVA_NAME + " not present in the content library " + VC_Content_Library_name
        return "SUCCESS", 200
    except Exception as e:
        return None, str(e)

def ra_avi_download(jsonspec):

    vcenter = jsonspec['envSpec']['vcenterDetails']["vcenterAddress"]
    vcenter_user = jsonspec['envSpec']['vcenterDetails']["vcenterSsoUser"]
    vcpass_base64 = jsonspec['envSpec']['vcenterDetails']['vcenterSsoPasswordBase64']
    vcpass = CmdHelper.decode_base64(vcpass_base64)
    refresh_token = jsonspec['envSpec']['marketplaceSpec']['refreshToken']
    os.putenv("GOVC_URL", "https://" + vcenter + "/sdk")
    os.putenv("GOVC_USERNAME", vcenter_user)
    os.putenv("GOVC_PASSWORD", vcpass)
    os.putenv("GOVC_INSECURE", "true")
    if not refresh_token:
        logger.info("refreshToken not provided")
        rcmd = cmd_runner.RunCmd()
        logger.info('Check if library is already present')
        VC_Content_Library_name = jsonspec['envSpec']['vcenterDetails']["contentLibraryName"]
        VC_AVI_OVA_NAME = jsonspec['envSpec']['vcenterDetails']["aviOvaName"]
        find_command = ["govc", "library.ls", "/" + VC_Content_Library_name + "/"]
        output = rcmd.runShellCommandAndReturnOutputAsList(find_command)
        if str(output[0]).__contains__(VC_Content_Library_name):
            logger.info(VC_Content_Library_name + " is already present")
            return True
        else:
            logger.info(VC_Content_Library_name + " is not present in the content library")
            return False
    else:
        logger.info("Fetching ALB..")
        down = downloadAviControllerAndPushToContentLibrary(vcenter, vcenter_user, vcpass, jsonspec)
        if down[0] is None:
            logger.error('Error encountered in fetching avi')
            return False
        return True



class AviApiHelper:
    def __init__(self, avi_api_spec: AviApiSpec, run_config: RunConfig) -> None:
        self.avi_api_spec = avi_api_spec
        self.ip = avi_api_spec.params["controller"]
        self.run_config: RunConfig = run_config
        self.api: ApiSession = None

    @log("Wait for controller to be UP!!")
    def wait_for_controller(self) -> None:
        count = 60
        while count > 0:
            try:
                response = requests.get(f"https://{self.ip}", verify=False)
                logger.debug("status code: %s", response.status_code)
                if response.status_code == requests.codes.ok:
                    logger.info("Server UP")
                    return
            except:
                pass
            print("Waiting for 10 seconds")
            time.sleep(10)
            count -= 1
        logger.warn("status code: %s", response.status_code)
        raise Exception("Server not UP after 10 min!!!")

    @login
    def get_api_version(self) -> dict:
        return self.api.remote_api_version["Version"]

    @log("Change Credentials for firstboot")
    def change_credentials(self) -> dict:
        api_creds = AviCredentials()
        api_creds.update_from_ansible_module(self.avi_api_spec)
        old_password = self.avi_api_spec.params.get("old_password")
        data = {"old_password": old_password, "password": api_creds.password}

        first_pwd = old_password
        second_pwd = api_creds.password

        password_changed = False
        try:
            logger.info("Test with default password")
            api = ApiSession.get_session(
                api_creds.controller,
                api_creds.username,
                password=first_pwd,
                timeout=api_creds.timeout,
                tenant=api_creds.tenant,
                tenant_uuid=api_creds.tenant_uuid,
                token=api_creds.token,
                port=api_creds.port,
            )

            rsp = api.put("useraccount", data=data)
            if rsp:
                password_changed = True
        except Exception:
            pass
        if not password_changed:
            try:
                self.get_api_version()
                password_changed = True
                rsp = {"msg": "password already changed"}
            except Exception:
                pass
        if password_changed:
            logger.info("Password changed")
            return rsp
        else:
            raise Exception("Password change error")

    @staticmethod
    def get_ip_obj(ip, type):
        return {"addr": ip, "type": type}

    @staticmethod
    def get_dns_obj(ip):
        return AviApiHelper.get_ip_obj(ip, "V4")

    @staticmethod
    def get_ntp_obj(ip):
        return AviApiHelper.get_ip_obj(ip, "DNS")

    @login
    @log("Set DNS and NTP")
    def set_dns_ntp(self) -> dict:
        # get configuration
        conf_dict = self.api.get("systemconfiguration").json()

        # update configuration
        conf_dict["email_configuration"]["smtp_type"] = "SMTP_NONE"
        conf_dict["dns_configuration"]["server_list"] = list(
            map(AviApiHelper.get_dns_obj, self.run_config.spec.avi.conf.dns))
        conf_dict["ntp_configuration"]["ntp_servers"] = list(
            map(AviApiHelper.get_ntp_obj, self.run_config.spec.avi.conf.ntp))

        return self.api.put("systemconfiguration", data=conf_dict).json()

    @login
    @log("Disable Welcome screen after login")
    def disable_welcome_screen(self):
        data = {
            "replace": {
                "welcome_workflow_complete": "true",
                "global_tenant_config": {
                    "tenant_vrf": False,
                    "se_in_provider_context": False,
                    "tenant_access_to_provider_se": True,
                },
            }
        }
        return self.api.patch("systemconfiguration", data=data, api_version=self.get_api_version()).json()

    @login
    @log("Set backup  passphrase")
    def set_backup_passphrase(self):
        bkup_uuid = self.api.get("backupconfiguration", api_version=self.get_api_version()).json()["results"][0]["uuid"]
        data = {"add": {"backup_passphrase": self.run_config.spec.avi.conf.backup.passphrase}}
        return self.api.patch(f"backupconfiguration/{bkup_uuid}", data=data, api_version=self.get_api_version()).json()

    @login
    @log("Generate SSL Certificate and update system certificate")
    def generate_ssl_cert(self):
        sslcerts = self.api.get("sslkeyandcertificate").json()
        data = {
            "type": "SSL_CERTIFICATE_TYPE_SYSTEM",
            "name": self.run_config.spec.avi.conf.cert.commonName,
            "certificate_base64": True,
            "key_base64": True,
            "certificate": {
                "days_until_expire": 365,
                "self_signed": True,
                "subject": {
                    "organization": "VMware INC",
                    "locality": "Palo Alto",
                    "state": "CA",
                    "country": "US",
                    "common_name": self.run_config.spec.avi.conf.cert.commonName,
                    "organization_unit": "VMwareEngineering",
                },
                "subject_alt_names": [self.api.controller_ip],
            },
            "key_params": {"algorithm": "SSL_KEY_ALGORITHM_RSA", "rsa_params": {"key_size": "SSL_KEY_2048_BITS"}},
        }
        if not any(x["name"] == self.run_config.spec.avi.conf.cert.commonName for x in sslcerts["results"]):
            url = self.api.post("sslkeyandcertificate", data=data, api_version=self.get_api_version()).json()["url"]
        else:
            url = next(
                x["url"] for x in sslcerts["results"] if x["name"] == self.run_config.spec.avi.conf.cert.commonName)
        sysconfig = self.api.get("systemconfiguration").json()
        logger.debug(f"sysconfig:  {sysconfig}")
        # replace certificate
        sysconfig["portal_configuration"]["sslkeyandcertificate_refs"] = [url]
        print(sysconfig)
        return self.api.put("systemconfiguration", data=sysconfig, api_version=self.get_api_version()).json()

    def get_cloud_uuid(self) -> str:
        cloud_rsp = self.api.get("cloud").json()
        if any(x["name"] == self.run_config.spec.avi.cloud.name for x in cloud_rsp["results"]):
            return next(x for x in cloud_rsp["results"] if x["name"] == self.run_config.spec.avi.cloud.name)["uuid"]
        else:
            logger.warn("cloud not yet available")

    def get_pg(self, cloud_uuid_obj):
        return self.api.post(
            "vimgrvcenterruntime/retrieve/portgroups", data=cloud_uuid_obj, api_version=self.get_api_version()
        ).json()["resource"]["vcenter_pg_names"]

    @login
    @log("Configure cloud")
    def configure_cloud(self):
        cloud_rsp = self.api.get("cloud").json()
        logger.debug(f"cloud_rsp {cloud_rsp}")

        cloud_req = {
            "name": self.run_config.spec.avi.cloud.name,
            "vcenter_configuration": {
                "username": self.run_config.spec.vsphere.username,
                "password": f"{CmdHelper.decode_base64(self.run_config.spec.vsphere.password)}",
                "vcenter_url": self.run_config.spec.vsphere.server,
                "privilege": "WRITE_ACCESS",
                "datacenter": self.run_config.spec.avi.cloud.dc,
            },
            "apic_mode": False,
            "dhcp_enabled": True,
            "mtu": 1500,
            "prefer_static_routes": False,
            "enable_vip_static_routes": False,
            "license_type": "LIC_CORES",
            "ipam_provider_ref": "",
            "dns_provider_ref": "",
        }

        if not any(x["name"] == self.run_config.spec.avi.cloud.name for x in cloud_rsp["results"]):
            new_cloud_rsp = self.api.post("cloud", data=cloud_req, api_version=self.get_api_version()).json()
        else:
            new_cloud_rsp = next(x for x in cloud_rsp["results"] if x["name"] == self.run_config.spec.avi.cloud.name)
            present_ipam, output = self.configure_ipam_dns_precheck(self.run_config.spec.avi.cloud.ipamProfileName)
            # add more validation
            if present_ipam and new_cloud_rsp["ipam_provider_ref"] == output["uuid"]:
                logger.warn("Cloud IPAM already configured")
                cloud_req["ipam_provider_ref"] = output["uuid"]

            present_dns, output = self.configure_ipam_dns_precheck(self.run_config.spec.avi.cloud.dnsProfile.name)
            if present_dns and new_cloud_rsp["dns_provider_ref"] == output["uuid"]:
                logger.warn("Cloud DNS already configured")
                cloud_req["dns_provider_ref"] = output["uuid"]
            if not (present_ipam and present_dns):
                self.api.put(
                    f"cloud/{new_cloud_rsp['uuid']}", data=cloud_req, api_version=self.get_api_version()
                ).json()
        cloud_uuid_obj = {"cloud_uuid": new_cloud_rsp["uuid"]}
        # time.sleep(300)
        pg_resources = self.get_pg(cloud_uuid_obj)

        count = 5
        while not any(pg["name"] == self.run_config.spec.avi.cloud.network for pg in pg_resources) and count > 0:
            logger.warn("No PortGroups found with name %s, waiting for 10s", self.run_config.spec.avi.cloud.network)
            time.sleep(10)
            count -= 1
            pg_resources = self.get_pg(cloud_uuid_obj)
        if not any(pg["name"] == self.run_config.spec.avi.cloud.network for pg in pg_resources):
            raise ValueError(f"Portgroup {self.run_config.spec.avi.cloud.network} not available in Avi")

        pg_uuid = next(pg["uuid"] for pg in pg_resources if pg["name"] == self.run_config.spec.avi.cloud.network)

        se_groups = self.api.get(
            "serviceenginegroup-inventory",
            api_version=self.get_api_version(),
            params={"cloud_ref.uuid": new_cloud_rsp["uuid"]},
        ).json()["results"]
        se_grp_config = next(x["config"] for x in se_groups if x["config"]["name"] == "Default-Group")
        se_grp_url = se_grp_config["url"]
        # configure HA in SE group
        self.configure_se_grp(se_grp_config["uuid"])

        cloud_req["vcenter_configuration"][
            "management_network"
        ] = f"https://{self.run_config.spec.vsphere.server}/api/vimgrnwruntime/{pg_uuid}"
        cloud_req["ipam_provider_ref"] = self.configure_ipam()["url"]
        cloud_req["dns_provider_ref"] = self.configure_dns()["url"]
        cloud_req["se_group_template_ref"] = se_grp_url
        return self.api.put(f"cloud/{new_cloud_rsp['uuid']}", data=cloud_req, api_version=self.get_api_version()).json()

    def configure_ipam_dns_precheck(self, name: str) -> tuple:
        ipam_dns_profiles = self.api.get("ipamdnsproviderprofile", api_version=self.get_api_version()).json()
        if any(x["name"] == name for x in ipam_dns_profiles["results"]):
            logger.info("IPAM/DNS Profile already exist")
            return True, next(x for x in ipam_dns_profiles["results"] if x["name"] == name)
        return False, None

    def get_ipam_uuid(self, cloud_uuid, ipamdnsproviderprofile_name, page=1):
        ipam_resp = self.api.get("ipamdnsproviderprofile").json()
        count = ipam_resp["count"]
        logger.debug(f"ipam count: {count}, page: {page}")

        if any(x["name"] == ipamdnsproviderprofile_name for x in ipam_resp["results"]):
            return next(x["uuid"] for x in ipam_resp["results"] if x["name"] == ipamdnsproviderprofile_name)
        if ((page - 1) * 20 + len(ipam_resp["results"])) != count:
            return self.get_ipam_uuid(cloud_uuid, ipamdnsproviderprofile_name, page + 1)
        return False

    def get_se_group_uuid(self, cloud_uuid, se_group_name, page=1):
        serviceengine_resp = self.api.get("serviceenginegroup").json()
        count = serviceengine_resp["count"]
        logger.debug(f"serviceengine count: {count}, page: {page}")

        if any(x["name"] == se_group_name for x in serviceengine_resp["results"]):
            return next(x["uuid"] for x in serviceengine_resp["results"] if x["name"] == se_group_name)
        if ((page - 1) * 20 + len(serviceengine_resp["results"])) != count:
            return self.get_serviceengine_uuid(cloud_uuid, se_group_name, page + 1)
        return False

    def get_ssl_uuid(self, cloud_uuid, common_name, page=1):
        ssl_resp = self.api.get("sslkeyandcertificate").json()
        count = ssl_resp["count"]
        logger.debug(f"SSL count: {count}, page: {page}")
        if any(x["name"] == common_name for x in ssl_resp["results"]):
            return next(x["uuid"] for x in ssl_resp["results"] if x["name"] == common_name)
        if ((page - 1) * 20 + len(ssl_resp["results"])) != count:
            return self.get_ssl_uuid(cloud_uuid, common_name, page + 1)

    @log()
    def get_network_inventory(self, cloud_uuid, page=1):
        return self.api.get(
            "network-inventory", api_version=self.get_api_version(), params={"cloud_ref.uuid": cloud_uuid, "page": page}
        ).json()

    def get_network_uuid(self, cloud_uuid, network_name, page=1):
        network_resp = self.get_network_inventory(cloud_uuid, page)
        count = network_resp["count"]
        logger.debug(f"network count: {count}, page: {page}")

        if any(x["config"]["name"] == network_name for x in network_resp["results"]):
            return next(x["config"]["uuid"] for x in network_resp["results"] if x["config"]["name"] == network_name)
        if ((page - 1) * 20 + len(network_resp["results"])) != count:
            return self.get_network_uuid(cloud_uuid, network_name, page + 1)
        return False

    @log("Configure IPAM")
    def configure_ipam(self) -> dict:
        present, output = self.configure_ipam_dns_precheck(self.run_config.spec.avi.cloud.ipamProfileName)
        if present:
            return output
        count = 5
        network_name = self.run_config.spec.avi.dataNetwork.name
        while count > 0:
            network_uuid = self.get_network_uuid(self.get_cloud_uuid(), network_name)
            if network_uuid:
                break
            logger.warn("No networks found with name %s, waiting for 10s", network_name)
            time.sleep(10)
            count -= 1

        if not network_uuid:
            # todo: add in prevalidate
            raise ValueError(f"Network with name {network_name} not available")
        data = {
            "name": self.run_config.spec.avi.cloud.ipamProfileName,
            "internal_profile": {
                "ttl": 30,
                "usable_networks": [{"nw_ref": f"https://{self.api.controller_ip}/api/network/{network_uuid}"}],
            },
            "allocate_ip_in_vrf": False,
            "type": "IPAMDNS_TYPE_INTERNAL",
            "gcp_profile": {"match_se_group_subnet": False, "use_gcp_network": False},
            "azure_profile": {"use_enhanced_ha": False, "use_standard_alb": False},
        }
        return self.api.post("ipamdnsproviderprofile", api_version=self.get_api_version(), data=data).json()

    @log("Configure DNS")
    def configure_dns(self) -> dict:
        present, output = self.configure_ipam_dns_precheck(self.run_config.spec.avi.cloud.dnsProfile.name)
        if present:
            return output
        data = {
            "name": self.run_config.spec.avi.cloud.dnsProfile.name,
            "internal_profile": {
                "ttl": 30,
                "dns_service_domain": [
                    {"domain_name": self.run_config.spec.avi.cloud.dnsProfile.domain, "pass_through": True}
                ],
            },
            "allocate_ip_in_vrf": False,
            "type": "IPAMDNS_TYPE_INTERNAL_DNS",
            "gcp_profile": {"match_se_group_subnet": False, "use_gcp_network": False},
            "azure_profile": {"use_enhanced_ha": False, "use_standard_alb": False},
        }
        return self.api.post("ipamdnsproviderprofile", api_version=self.get_api_version(), data=data).json()

    @login
    @log("Configure static IP pool")
    def configure_static_ip_pool(self) -> dict:
        network_name = self.run_config.spec.avi.dataNetwork.name
        network_uuid = self.get_network_uuid(self.get_cloud_uuid(), network_name)
        if not network_uuid:
            raise ValueError(f"Network with name {network_name} not available")

        net_dvpg = self.api.get(f"network/{network_uuid}", api_version=self.get_api_version()).json()
        logger.debug("Networks for dvpg %s: %s", network_name, net_dvpg)

        # todo: append instead of replace
        net_dvpg["configured_subnets"] = [
            {
                "prefix": {
                    "ip_addr": {"addr": f'{self.run_config.spec.avi.dataNetwork.cidr.split("/")[0]}', "type": "V4"},
                    "mask": int(f'{self.run_config.spec.avi.dataNetwork.cidr.split("/")[1]}'),
                },
                "static_ip_ranges": [
                    {
                        "range": {
                            "begin": {"addr": f'{self.run_config.spec.avi.dataNetwork.staticRange.split("-")[0]}',
                                      "type": "V4"},
                            "end": {"addr": f'{self.run_config.spec.avi.dataNetwork.staticRange.split("-")[1]}',
                                    "type": "V4"},
                        },
                        "type": "STATIC_IPS_FOR_VIP",
                    }
                ],
            }
        ]

        return self.api.put(f"network/{network_uuid}", data=net_dvpg, api_version=self.get_api_version()).json()

    @login
    @log("Configure default SE group")
    def configure_se_grp(self, se_grp_uuid):
        api_version = self.get_api_version()
        se_grp_data = self.api.get(f"serviceenginegroup/{se_grp_uuid}", api_version=api_version).json()
        se_grp_data["ha_mode"] = "HA_MODE_LEGACY_ACTIVE_STANDBY"
        se_grp_data["algo"] = "PLACEMENT_ALGO_DISTRIBUTED"
        se_grp_data["active_standby"] = True
        se_grp_data["max_scaleout_per_vs"] = 2
        return self.api.put(
            f"serviceenginegroup/{se_grp_uuid}",
            api_version=api_version,
            data=se_grp_data,
        ).json()

    def get_group_object_by_uuid(self, group, uuid):
        try:
            response = self.api.get(f"{group}/{uuid}", verify=False)
            if response.status_code == requests.codes.ok:
                return response.json()
        except:
            return None

    def get_group(self, group):
        try:
            response = self.api.get(f"{group}", verify=False)
            if response.status_code == requests.codes.ok:
                return response.json()
        except:
            return None

    def validate_avi_data_network_config(self):
        status = True
        msg = []

        network_uuid = self.get_network_uuid(self.get_cloud_uuid(), self.run_config.spec.avi.dataNetwork.name)
        network = self.get_group_object_by_uuid("network", network_uuid)

        if not network:
            msg.append("Network management config validation failed. ")
            status = False
        else:
            subnet = network['configured_subnets'][0]
            cidr = self.run_config.spec.avi.dataNetwork.cidr.split('/')[0]
            if cidr != subnet['prefix']['ip_addr']['addr']:
                msg.append("Network subnet prefix config validation failed. ")
                status = False
            begin = self.run_config.spec.avi.dataNetwork.staticRange.split('-')[0]
            end = self.run_config.spec.avi.dataNetwork.staticRange.split('-')[1]
            if begin != subnet["static_ranges"][0]["begin"]["addr"] or \
                    end != subnet["static_ranges"][0]["end"]["addr"]:
                msg.append("Network static ip address range failed. ")
                status = False

        if status:
            msg.append("Network validation passed. ")
        return msg, status

    def validate_avi_cloud_config(self):
        status = True
        msg = []

        cloud_rsp = self.api.get("cloud-inventory", api_version=self.get_api_version()).json()
        cloud = next(x for x in cloud_rsp["results"] if x["config"]["name"] == self.run_config.spec.avi.cloud.name)
        if not cloud:
            msg.append("Cloud server doesn't exist. ")
            status = False

        config = cloud["config"]
        vcenter_config = config["vcenter_configuration"]
        if vcenter_config["privilege"] != "WRITE_ACCESS":
            msg.append("Privilege access validation check failed. ")
            status = False

        pg_name = self.run_config.spec.avi.cloud.network
        pg_uuid = self.get_network_uuid(self.get_cloud_uuid(), pg_name)
        mgmt_net_res = self.get_group_object_by_uuid("vimgrnwruntime", pg_uuid)
        if not mgmt_net_res or mgmt_net_res["url"] != vcenter_config["management_network"]:
            msg.append("Network management config validation failed. ")
            status = False

        ipam_uuid = self.get_ipam_uuid(self.get_cloud_uuid(), self.run_config.spec.avi.cloud.ipamProfileName)
        ipam_res = self.get_group_object_by_uuid("ipamdnsproviderprofile", ipam_uuid)
        if not ipam_res or ipam_res["url"] != config["ipam_provider_ref"]:
            msg.append("IPAM config validation failed. ")
            status = False

        dns_uuid = self.get_ipam_uuid(self.get_cloud_uuid(), self.run_config.spec.avi.cloud.dnsProfile.name)
        dns_res = self.get_group_object_by_uuid("ipamdnsproviderprofile", dns_uuid)
        if not dns_res or dns_res["url"] != config["dns_provider_ref"]:
            msg.append("DNS config validation failed. ")
            status = False

        se_group_uuid = self.get_se_group_uuid(self.get_cloud_uuid(), self.run_config.spec.avi.cloud.mgmtSEGroup)
        se_group_res = self.get_group_object_by_uuid("serviceenginegroup", se_group_uuid)
        if not se_group_res or se_group_res["url"] != config["se_group_template_ref"]:
            msg.append("Service engine group template validation failed. ")
            status = False

        if config["dhcp_enabled"] or not config["prefer_static_routes"]:
            msg.append("Static routes not enabled. ")

        ssl_uuid = self.get_ssl_uuid("sslkeyandcertificate", self.run_config.spec.avi.conf.cert.commonName)
        ssl_res = self.get_group_object_by_uuid("sslkeyandcertificate", ssl_uuid)
        if not ssl_res or ssl_res["name"] != self.run_config.spec.avi.conf.cert.commonName:
            msg.append("SSL certificate validation failed. ")
            status = False

        if cloud['status']['state'] != "CLOUD_STATE_PLACEMENT_READY":
            msg.append(f"Cloud status is {cloud['status']['state']}")
            status = False

        # if cloud['status']['se_image_state'][0]['state'] != "IMG_GEN_COMPLETE":
        #     msg.append(f"SE Image status is {cloud['status']['se_image_state'][0]['state']}")
        #     status = False

        if vcenter_config["datacenter"] != self.run_config.spec.avi.cloud.dc:
            msg.append(f"Datacenter configured is {vcenter_config['datacenter']}")
            status = False

        if status:
            msg.append("Cloud validation check passed. ")

        return msg, status

    @login
    @log("Validate Spec file")
    def validate_avi_controller(self):

        cloud_valid_msg, cloud_valid_status = self.validate_avi_cloud_config()
        data_valid_msg, data_valid_status = self.validate_avi_data_network_config()

        msg = "".join(cloud_valid_msg) + "".join(data_valid_msg)

        if cloud_valid_status and data_valid_status:
            return msg, True
        else:
            return msg, False

    @login
    def create_cloud(self, cloud_type: AlbCloudType):
        cloud_name = self.run_config.spec.avi.cloud.name
        alb_cloud = self.api.get("cloud", params={"name": cloud_name}, api_version=self.get_api_version()).json()[
            "results"]
        if len(alb_cloud) == 0:
            if cloud_type == AlbCloudType.NONE:
                body = AlbPayload.CREATE_NONE_CLOUD.format(cloud_name=self.run_config.spec.avi.cloud.name)
            else:
                msg = f"Only None type cloud creation is supported. Requested for {cloud_type} type."
                logger.error(msg)
                raise ValueError(msg)
            logger.info(f"Creating cloud [{cloud_name}]")
            res = self.api.post("cloud", data=json.loads(body), api_version=self.get_api_version())
            try:
                res.raise_for_status()
            except HTTPError as ex:
                logger.error(f"Failed to create cloud [{cloud_name}]. Response: {res.text}")
                raise ex
            return res.json()
        else:
            logger.info(f"Found existing cloud [{cloud_name}]. Skipping creation.")
        return alb_cloud[0]

    @login
    def create_se_group(self, se_group_name):
        cloud_name = self.run_config.spec.avi.cloud.name
        alb_cloud = self.api.get("cloud", params={"name": cloud_name}, api_version=self.get_api_version()).json()[
            "results"]
        if len(alb_cloud) == 0:
            raise ValueError(f"Failed to create SE group {se_group_name}. Cloud [{cloud_name}] not found.")

        se_group = \
            self.api.get("serviceenginegroup",
                         params={"cloud_ref.uuid": alb_cloud[0]["uuid"], "name": se_group_name}).json()[
                "results"]
        if len(se_group) == 0:
            logger.info(f"Creating SE group [{se_group_name}] on cloud [{cloud_name}]")
            body = AlbPayload.CREATE_SE_GROUP.format(name=se_group_name, cloud_url=alb_cloud[0]["url"])
            res = self.api.post("serviceenginegroup", data=json.loads(body), api_version=self.get_api_version())
            try:
                res.raise_for_status()
            except HTTPError as ex:
                logger.error(f"Failed to create SE group. Response: {res.text}")
                raise ex
            return res.json()
        else:
            logger.info(f"Found existing SE group [{se_group_name}] on cloud [{cloud_name}]. Skipping creation.")
        return se_group[0]

    @login
    def create_network(self, network_name, network: NetworkSegment):
        cloud_name = self.run_config.spec.avi.cloud.name
        alb_cloud = self.api.get("cloud", params={"name": cloud_name}, api_version=self.get_api_version()).json()[
            "results"]
        if len(alb_cloud) == 0:
            raise ValueError(f"Failed to create network {network_name}. Cloud [{cloud_name}] not found.")

        alb_network = \
            self.api.get("network", params={"cloud_ref.uuid": alb_cloud[0]["uuid"], "name": network_name}).json()[
                "results"]

        if len(alb_network) == 0:
            logger.info(f"Creating network [{network_name}] on cloud [{cloud_name}]")
            ip, netmask = network.gatewayCidr.split('/')
            body = AlbPayload.CREATE_NETWORK.format(name=network_name, cloud_url=alb_cloud[0]["url"], subnet_ip=ip,
                                                    netmask=netmask, static_ip_start=network.staticIpStart,
                                                    static_ip_end=network.staticIpEnd)
            res = self.api.post("network", data=json.loads(body), api_version=self.get_api_version())
            try:
                res.raise_for_status()
            except HTTPError as ex:
                logger.error(f"Failed to create network. Response: {res.text}")
                raise ex
            return res.json()
        else:
            logger.info(f"Found existing network [{network_name}] on cloud [{cloud_name}]. Skipping creation.")
        return alb_network[0]

    @login
    def create_ipam_profile(self, profile_name, usable_network_urls):
        alb_ipam_profile = self.api.get("ipamdnsproviderprofile", params={"name": profile_name},
                                        api_version=self.get_api_version()).json()["results"]
        if len(alb_ipam_profile) == 0:
            logger.info(f"Creating IPAM profile [{profile_name}]")
            ipam_networks = [json.loads(AlbPayload.IPAM_NETWORK.format(network_url=nw)) for nw in usable_network_urls]
            body = AlbPayload.CREATE_INTERNAL_IPAM.format(name=profile_name, ipam_networks=json.dumps(ipam_networks))
            res = self.api.post("ipamdnsproviderprofile", data=json.loads(body),
                                api_version=self.get_api_version())
            try:
                res.raise_for_status()
            except HTTPError as ex:
                logger.error(f"Failed to create IPAM profile. Response: {res.text}")
                raise ex
            return res.json()
        else:
            logger.info(f"Found existing IPAM profile [{profile_name}]. Skipping creation.")
        return alb_ipam_profile[0]

    @login
    def update_se_group_and_ipam_profile(self, se_group_url, ipam_profile_url):
        cloud_name = self.run_config.spec.avi.cloud.name
        alb_cloud = self.api.get("cloud", params={"name": cloud_name}, api_version=self.get_api_version()).json()[
            "results"]
        if len(alb_cloud) == 0:
            raise ValueError(f"Failed to update SE group and IPAM profile. Cloud [{cloud_name}] not found.")
        if all(["se_group_template_ref" in alb_cloud[0] and se_group_url in alb_cloud[0]["se_group_template_ref"],
                "ipam_provider_ref" in alb_cloud[0] and ipam_profile_url in alb_cloud[0]["ipam_provider_ref"]]):
            logger.info(f"SE Group and IPAM profiles already updated on cloud [{cloud_name}]. Skipping update.")
            return alb_cloud[0]
        logger.info(f"Updating SE group and IPAM profile for cloud [{cloud_name}]")
        cloud = alb_cloud[0]
        cloud["ipam_provider_ref"] = ipam_profile_url
        cloud["se_group_template_ref"] = se_group_url

        res = self.api.put(f"cloud/{cloud['uuid']}", data=cloud, api_version=self.get_api_version())
        try:
            res.raise_for_status()
        except HTTPError as ex:
            logger.error(f"Failed to update SE group and IPAM profile of cloud {cloud_name}. Response: {res.text}")
            raise ex
        return res.json()

    @login
    def generate_se_ova(self):
        cloud_name = self.run_config.spec.avi.cloud.name
        alb_cloud = self.api.get("cloud", params={"name": cloud_name}, api_version=self.get_api_version()).json()[
            "results"]
        if len(alb_cloud) == 0:
            raise ValueError(f"Failed to generate SE OVA. Cloud [{cloud_name}] not found.")

        logger.info(f"Generating SE OVA for cloud [{cloud_name}]")
        body = AlbPayload.GENERATE_SE_OVA.format(cloud_uuid=alb_cloud[0]["uuid"])
        res = self.api.post("fileservice/seova", data=json.loads(body), api_version=self.get_api_version())
        try:
            res.raise_for_status()
        except HTTPError as ex:
            logger.error(f"Failed to generate SE OVA. Response: {res.text}")
            raise ex
        return res.text

    @login
    def download_se_ova(self, file_path, replace_existing=False):
        if not replace_existing and os.path.exists(file_path):
            logger.info(f"File already exists at {file_path}. Skipping download.")
            return file_path
        elif os.path.exists(file_path):
            os.remove(file_path)
        self.generate_se_ova()
        cloud_name = self.run_config.spec.avi.cloud.name
        alb_cloud = self.api.get("cloud", params={"name": cloud_name}, api_version=self.get_api_version()).json()[
            "results"]
        if len(alb_cloud) == 0:
            raise ValueError(f"Failed to generate SE OVA. Cloud [{cloud_name}] not found.")

        logger.info(f"Downloading SE OVA for cloud [{cloud_name}]")
        file_name = file_path.split('/')[-1]
        with self.api.get("fileservice/seova",
                          params={"file_format": "ova", "cloud_uuid": {alb_cloud[0]["uuid"]}},
                          api_version=self.get_api_version()) as res:
            try:
                res.raise_for_status()
            except HTTPError as ex:
                logger.error(f"Failed to get SE OVA. Response: {res.text}")
                raise ex
            block_size = 1024 * 1024
            total_size_in_bytes = int(res.headers.get('content-length', 0))
            logger.info(f"File size: {total_size_in_bytes}Bytes")
            with tqdm.wrapattr(open(file_path, "wb"), "write",
                               miniters=1, desc=file_name,
                               total=int(res.headers.get('content-length', 0))) as fout:
                for chunk in res.iter_content(chunk_size=block_size):
                    fout.write(chunk)

        if not os.path.exists(file_path) or os.path.getsize(file_path) != total_size_in_bytes:
            raise Exception(f"Error while downloading file {file_name}. ")
        return file_path

    @login
    def get_auth_token(self):
        cloud_name = self.run_config.spec.avi.cloud.name
        alb_cloud = self.api.get("cloud", params={"name": cloud_name}).json()["results"]
        if len(alb_cloud) == 0:
            raise ValueError(f"Failed to generate token. Cloud [{cloud_name}] not found.")

        res = self.api.get("securetoken-generate", params={"cloud_uuid": alb_cloud[0]["uuid"]},
                           api_version=self.get_api_version())
        try:
            res.raise_for_status()
        except HTTPError as ex:
            logger.error(f"Failed to get auth token. Response: {res.text}")
            raise ex
        return res.json()["auth_token"]

    @login
    def get_cluster_uuid(self):
        res = self.api.get("cluster", api_version=self.get_api_version())
        try:
            res.raise_for_status()
        except HTTPError as ex:
            logger.error(f"Failed to get cluster UUID. Response: {res.text}")
            raise ex
        return res.json()["uuid"]

    def patch_license_tier(self, license_tier: AlbLicenseTier):
        body = AlbPayload.PATCH_DEFAULT_LICENSE_TIER.format(license_tier=license_tier)
        # Field (default_license_tier) is introduced in later versions(v17_2_5)
        res = self.api.patch("systemconfiguration", data=json.loads(body), api_version="17.2.5")
        try:
            res.raise_for_status()
        except HTTPError as ex:
            logger.error(f"Failed to patch default license tier. Response: {res.text}")
            raise ex
        return res.json()

    def get_service_engine(self, name):
        cloud_name = self.run_config.spec.avi.cloud.name
        alb_cloud = self.api.get("cloud", params={"name": cloud_name}).json()["results"]
        if len(alb_cloud) == 0:
            raise ValueError(f"Failed to get SE. Cloud [{cloud_name}] not found.")

        res = self.api.get("serviceengine", params={"cloud_ref.uuid": alb_cloud[0]["uuid"], "name": name},
                           api_version=self.get_api_version())
        try:
            res.raise_for_status()
        except HTTPError as ex:
            logger.error(f"Failed to get SE by name: {name}. Response: {res.text}")
            raise ex
        return res.json()["results"]

    def update_se_engine(self, se_name, se_group_url, mac_addresses):
        service_engine = self.get_service_engine(se_name)
        if len(service_engine) == 0:
            raise ValueError(f"Failed to update SE [{se_name}]. SE not found.")
        logger.info(f"Updating SE [{se_name}]")
        se = service_engine[0]
        se["se_group_ref"] = se_group_url

        for vnic in se["data_vnics"]:
            for k, v in vnic.items():
                if v in mac_addresses.values():
                    vnic["dhcp_enabled"] = True
                    break

        res = self.api.put(f"serviceengine/{se['uuid']}", data=se, api_version=self.get_api_version())
        try:
            res.raise_for_status()
        except HTTPError as ex:
            logger.error(f"Failed to update SE [{se_name}]. Response: {res.text}")
            raise ex
        return res.json()

    def get_vrf_context(self, name):
        cloud_name = self.run_config.spec.avi.cloud.name
        alb_cloud = self.api.get("cloud", params={"name": cloud_name}, api_version=self.get_api_version()).json()[
            "results"]
        if len(alb_cloud) == 0:
            raise ValueError(f"Failed to get VRF context. Cloud [{cloud_name}] not found.")

        res = self.api.get("vrfcontext", params={"cloud_ref.uuid": alb_cloud[0]["uuid"], "name": name})
        try:
            res.raise_for_status()
        except HTTPError as ex:
            logger.error(f"Failed to get VRF context named [{name}] for cloud [{cloud_name}]. Response: {res.text}")
            raise ex
        return res.json()["results"]

    def patch_vrf_context(self, vrf_uuid, id_next_hop_map):
        routes = [json.loads(AlbPayload.VRF_STATIC_ROUTE.format(route_id=k, next_hop_ip=v)) for k, v in
                  id_next_hop_map.items()]
        body = AlbPayload.PATCH_VRF_CONTEXT.format(vrf_routes_list=json.dumps(routes))
        logger.info(f"Patching VRF context: [{vrf_uuid}]")
        res = self.api.patch(f"vrfcontext/{vrf_uuid}", data=json.loads(body), api_version=self.get_api_version())
        try:
            res.raise_for_status()
        except HTTPError as ex:
            logger.error(f"Failed to update VRF context [{vrf_uuid}]. Response: {res.text}")
            raise ex
        return res.json()
