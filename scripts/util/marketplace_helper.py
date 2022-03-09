import json
import requests
import urllib3
from requests import HTTPError
import constants
from util import cmd_runner
from constants.constants import Paths, MarketPlaceUrl, ControllerLocation
from util.logger_helper import LoggerHelper
from pathlib import Path

logger = LoggerHelper.get_logger(Path(__file__).stem)

def fetch_avi_ova(specfile):
    rcmd = cmd_runner.RunCmd()
    ova_location = "/tmp/{}.ova".format(ControllerLocation.CONTROLLER_NAME)
    with open(specfile) as f:
        jsonspec = json.load(f)
    dsname = jsonspec['envSpec']['vcenterDetails']['vcenterDatastore']
    avi_version = ControllerLocation.VSPHERE_AVI_VERSION
    reftoken = jsonspec['envSpec']['marketplaceSpec']['refreshToken']
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
    token = ''
    if sess.status_code != 200:
        logger.error(
            "Unable to login using the provided token"
        )
        return None, "Failed to login. Invalid token", "Invalid"
    else:
        token = sess.json()["access_token"]
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "csp-auth-token": token
    }
    solution_name = ControllerLocation.MARKETPLACE_AVI_SOLUTION_NAME
    if str(MarketPlaceUrl.API_URL).__contains__("stg"):
        slug = "false"
    else:
        slug = "true"
    product = requests.get(MarketPlaceUrl.API_URL + "/products/" +
                           solution_name + "?isSlug=" + slug + "&ownorg=false", headers=headers,
                           verify=False)
    ls = []
    product_id = product.json()['response']['data']['productid']
    objectid = ''
    for metalist in product.json()['response']['data']['productdeploymentfilesList']:
        if metalist["appversion"] in avi_version:
            objectid = metalist['fileid']
            filename = metalist['name']
            ls.append(filename)
            break
    payload = {
        "deploymentFileId": objectid,
        "eulaAccepted": "true",
        "productId": product_id
    }
    json_object = json.dumps(payload, indent=4).replace('\"true\"', 'true')
    marketplace_url = MarketPlaceUrl.URL + "/api/v1/products/" + product_id + "/download"
    presigned_url = requests.request("POST", marketplace_url, headers=headers, data=json_object,
                                     verify=False)
    download_url = ''
    if presigned_url.status_code != 200:
        logger.error(
            "Unable to fetch the product download url"
        )
        return None, "Failed to obtain product url", "Invalid"
    else:
        download_url = presigned_url.json()["response"]["presignedurl"]
    response_csfr = requests.request("GET", download_url, headers=headers,
                                     verify=False, timeout=600)
    if response_csfr.status_code != 200:
        logger.error(f"Failed to download ova. Msg: {response_csfr.text}")
        return None, response_csfr.text, "Invalid"
    else:
        command = "rm -rf {}".format(ls[0])
        rcmd.run_cmd_only(command)
    with open(ls[0], 'wb') as f:
        f.write(response_csfr.content)
    command = "mv {ls} {dest}".format(ls=ls[0], dest=ova_location)
    rcmd.run_cmd_only(command)
    return True, "Completed", ova_location
