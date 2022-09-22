#!/usr/local/bin/python3

#  Copyright 2022 VMware, Inc
#  SPDX-License-Identifier: BSD-2-Clause
import json
import os
import requests

from constants.constants import Paths, KubernetesOva, MarketPlaceUrl

from util.logger_helper import LoggerHelper, log
from util.cmd_helper import CmdHelper
from model.run_config import RunConfig
from util.tkg_util import TkgUtil
from util.common_utils import checkenv
from util.govc_client import GovcClient
from util.local_cmd_helper import LocalCmdHelper
from util import cmd_runner
from util.cleanup_util import CleanUpUtil
from util.common_utils import envCheck
from util.avi_api_helper import getProductSlugId
logger = LoggerHelper.get_logger(name='Pre Setup')


class GenerateTektonDockerImage:
    """PreSetup class is responsible to perform Pre Checks before deploying any of clusters/nodes"""
    def __init__(self, root_dir, run_config: RunConfig) -> None:
        self.run_config = run_config
        self.version = None
        self.jsonpath = None
        self.state_file_path = os.path.join(root_dir, Paths.STATE_PATH)
        self.tkg_util_obj = TkgUtil(run_config=self.run_config)
        self.tkg_version_dict = self.tkg_util_obj.get_desired_state_tkg_version()
        if "tkgs" in self.tkg_version_dict:
            self.jsonpath = os.path.join(self.run_config.root_dir, Paths.TKGS_WCP_MASTER_SPEC_PATH)
            self.tkg_version = self.tkg_version_dict["tkgs"]
        elif "tkgm" in self.tkg_version_dict:
            self.jsonpath = os.path.join(self.run_config.root_dir, Paths.MASTER_SPEC_PATH)
            self.tkg_version = self.tkg_version_dict["tkgm"]
        else:
            raise Exception(f"Could not find supported TKG version: {self.tkg_version_dict}")

        with open(self.jsonpath) as f:
            self.jsonspec = json.load(f)
        self.env = envCheck(self.run_config)
        if self.env[1] != 200:
            logger.error("Wrong env provided " + self.env[0])
            d = {
                "responseType": "ERROR",
                "msg": "Wrong env provided " + self.env[0],
                "ERROR_CODE": 500
            }
        self.env = self.env[0]

        check_env_output = checkenv(self.jsonspec)
        if check_env_output is None:
            msg = "Failed to connect to VC. Possible connection to VC is not available or " \
                  "incorrect spec provided."
            raise Exception(msg)
        self.govc_client = GovcClient(self.jsonspec, LocalCmdHelper())
        self.kube_config = os.path.join(self.run_config.root_dir, Paths.REPO_KUBE_TKG_CONFIG)
        self.kube_version = KubernetesOva.KUBERNETES_OVA_LATEST_VERSION
        self.reftoken = self.jsonspec['envSpec']['marketplaceSpec']['refreshToken']

    def generate_tkn_docker_image(self) -> None:
        """
        Method to get vCenter Details from JSON file
        :return: None
        """
        # READ refresh token from values.yaml

        self.get_meta_details_marketplace()

    def get_meta_details_marketplace(self):
        file_grp = ["Tanzu Cli", "Kubectl Cluster CLI", "Yaml processor"]
        solutionName = KubernetesOva.MARKETPLACE_KUBERNETES_SOLUTION_NAME
        logger.debug(("Solution Name: {}".format(solutionName)))

        for grp in file_grp:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            payload = {
                "refreshToken": self.reftoken
            }
            json_object = json.dumps(payload, indent=4)
            sess = requests.request("POST", MarketPlaceUrl.URL + "/api/v1/user/login", headers=headers,
                                    data=json_object, verify=False)
            if sess.status_code != 200:
                return None, "Failed to login and obtain csp-auth-token"
            else:
                self.token = sess.json()["access_token"]

            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "csp-auth-token": self.token
            }
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
                self.product_id = product.json()['response']['data']['productid']

                for metalist in product.json()['response']['data']['metafilesList']:
                    if metalist['appversion'] == self.tkg_version:
                        if metalist["version"] == self.kube_version[1:] and str(metalist["groupname"]).strip("\t") \
                                == grp:
                            self.objectid = metalist["metafileobjectsList"][0]['fileid']
                            self.file_name = metalist["metafileobjectsList"][0]['filename']
                            self.app_version = metalist['appversion']
                            self.metafileid = metalist['metafileid']
                            break
            logger.info("ovaName: {ovaName} app_version: {app_version} metafileid: {metafileid}".format(ovaName=self.file_name,
                                                                                                        app_version=self.app_version,
                                                                                                        metafileid=self.metafileid))
            if (self.objectid or self.file_name or self.app_version or self.metafileid) is None:
                return None, "Failed to find the file details in Marketplace"
            self.download_files_from_marketplace()

    def download_files_from_marketplace(self):
            logger.info("Downloading file - " + self.file_name)
            rcmd = cmd_runner.RunCmd()
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "csp-auth-token": self.token
            }
            payload = {
                "eulaAccepted": "true",
                "appVersion": self.app_version,
                "metafileid": self.metafileid,
                "metafileobjectid": self.objectid
            }

            json_object = json.dumps(payload, indent=4).replace('\"true\"', 'true')
            logger.info('--------')
            logger.info('Marketplaceurl: {url} data: {data}'.format(url=MarketPlaceUrl.URL, data=json_object))
            presigned_url = requests.request("POST",
                                             MarketPlaceUrl.URL + "/api/v1/products/" + self.product_id + "/download",
                                             headers=headers, data=json_object, verify=False)
            logger.info('presigned_url: {}'.format(presigned_url))
            logger.info('presigned_url text: {}'.format(presigned_url.text))
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
                ova_path = "/tmp/" + self.file_name
                curl_download_cmd = 'curl -X GET {d_url} --output {tmp_path}'.format(d_url=download_url,
                                                                                     tmp_path=ova_path)
                rcmd.run_cmd_only(curl_download_cmd)
            else:
                logger.info('Error in presigned url/key: {} '.format(data_read.split('\n')[0]))
                return None, "Invalid key/url"

            return self.file_name, "File download successful"
