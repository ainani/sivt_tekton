from constants.constants import ControllerLocation, Repo, AppName, RegexPattern
from pathlib import Path
import base64
from util.common_utils import installCertManagerAndContour, getVersionOfPackage, waitForGrepProcessWithoutChangeDir
import json
from util.logger_helper import LoggerHelper
import logging
from util.ShellHelper import grabPipeOutput, verifyPodsAreRunning, \
    runShellCommandAndReturnOutputAsList, runShellCommandAndReturnOutput
import time
import os

logger = LoggerHelper.get_logger('common_utils')
logging.getLogger("paramiko").setLevel(logging.WARNING)


def certChanging(harborCertPath, harborCertKeyPath, harborPassword, host):
    os.system("chmod +x common/inject.sh")
    location = "harbor-data-values.yaml"

    if harborCertPath and harborCertKeyPath:
        harbor_cert = Path(harborCertPath).read_text()
        harbor_cert_key = Path(harborCertKeyPath).read_text()
        certContent = harbor_cert
        certKeyContent = harbor_cert_key
        command_harbor_change_host_password_cert = ["sh", "./common/inject.sh",
                                                    location,
                                                    harborPassword, host, certContent, certKeyContent]
        state_harbor_change_host_password_cert = runShellCommandAndReturnOutput(
            command_harbor_change_host_password_cert)
        if state_harbor_change_host_password_cert[1] == 500:
            d = {
                "responseType": "ERROR",
                "msg": "Failed to change host, password and cert " + str(state_harbor_change_host_password_cert[0]),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
    else:
        command_harbor_change_host_password_cert = ["sh", "./common/inject.sh",
                                                    location,
                                                    harborPassword, host, "", ""]
        state_harbor_change_host_password_cert = runShellCommandAndReturnOutput(
            command_harbor_change_host_password_cert)
        if state_harbor_change_host_password_cert[1] == 500:
            d = {
                "responseType": "ERROR",
                "msg": "Failed to change host, password and cert " + str(state_harbor_change_host_password_cert[0]),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
    d = {
        "responseType": "SUCCESS",
        "msg": "Updated harbor data-values yaml",
        "ERROR_CODE": 200
    }
    return json.dumps(d), 200


def installHarbor14(service, repo_address, harborCertPath, harborCertKeyPath, harborPassword, host):
    main_command = ["tanzu", "package", "installed", "list", "-A"]
    sub_command = ["grep", AppName.HARBOR]
    out = grabPipeOutput(main_command, sub_command)
    if not verifyPodsAreRunning(AppName.HARBOR, out[0], RegexPattern.RECONCILE_SUCCEEDED):
        timer = 0
        logger.info("Validating contour and certmanger is running")
        command = ["tanzu", "package", "installed", "list", "-A"]
        status = runShellCommandAndReturnOutputAsList(command)
        verify_contour = False
        verify_cert_manager = False
        while timer < 600:
            if verify_contour or verifyPodsAreRunning(AppName.CONTOUR, status[0], RegexPattern.RECONCILE_SUCCEEDED):
                logger.info("Contour is running")
                verify_contour = True
            if verify_cert_manager or verifyPodsAreRunning(AppName.CERT_MANAGER, status[0], RegexPattern.RECONCILE_SUCCEEDED):
                verify_cert_manager = True
                logger.info("Cert Manager is running")

            if verify_contour and verify_cert_manager:
                break
            else:
                timer = timer + 30
                time.sleep(30)
                status = runShellCommandAndReturnOutputAsList(command)
                logger.info("Waited for " + str(timer) + "s, retrying for contour and cert manager to be running")
        if not verify_contour:
            logger.error("Contour is not running")
            d = {
                "responseType": "ERROR",
                "msg": "Contour is not running ",
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        if not verify_cert_manager:
            logger.error("Cert manager is not running")
            d = {
                "responseType": "ERROR",
                "msg": "Cert manager is not running ",
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        state = getVersionOfPackage("harbor.tanzu.vmware.com")
        if state is None:
            d = {
                "responseType": "ERROR",
                "msg": "Failed to get Version of package contour.tanzu.vmware.com",
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        logger.info("Deploying harbor")
        logger.info("Harbor version " + state)
        get_url_command = ["kubectl", "-n", "tanzu-package-repo-global", "get", "packages",
                           "harbor.tanzu.vmware.com." + state, "-o",
                           "jsonpath='{.spec.template.spec.fetch[0].imgpkgBundle.image}'"]
        logger.info("Getting harbor url")
        status = runShellCommandAndReturnOutputAsList(get_url_command)
        if status[1] != 0:
            logger.error("Failed to get harbor image url " + str(status[0]))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to get harbor image url " + str(status[0]),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        logger.info("Got harbor url " + str(status[0][0]).replace("'", ""))
        pull = ["imgpkg", "pull", "-b", str(status[0][0]).replace("'", ""), "-o", "/tmp/harbor-package"]
        status = runShellCommandAndReturnOutputAsList(pull)
        if status[1] != 0:
            logger.error("Failed to pull harbor packages " + str(status[0]))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to get harbor image url " + str(status[0]),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        os.system("rm -rf ./harbor-data-values.yaml")
        os.system("cp /tmp/harbor-package/config/values.yaml ./harbor-data-values.yaml")
        command_harbor_genrate_psswd = ["sh", "/tmp/harbor-package/config/scripts/generate-passwords.sh",
                                        "harbor-data-values.yaml"]
        state_harbor_genrate_psswd = runShellCommandAndReturnOutputAsList(command_harbor_genrate_psswd)
        if state_harbor_genrate_psswd[1] == 500:
            logger.error("Failed to generate password " + str(state_harbor_genrate_psswd[0]))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to generate password " + str(state_harbor_genrate_psswd[0]),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        cer = certChanging(harborCertPath, harborCertKeyPath, harborPassword, host)
        if cer[1] != 200:
            logger.error(cer[0].json['msg'])
            d = {
                "responseType": "ERROR",
                "msg": cer[0].json['msg'],
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        os.system("chmod +x common/injectValue.sh")
        command = ["sh", "./common/injectValue.sh", "harbor-data-values.yaml", "remove"]
        runShellCommandAndReturnOutputAsList(command)
        command = ["tanzu", "package", "install", "harbor", "--package-name", "harbor.tanzu.vmware.com", "--version",
                   state, "--values-file", "./harbor-data-values.yaml", "--namespace", "package-tanzu-system-registry",
                   "--create-namespace"]
        runShellCommandAndReturnOutputAsList(command)
        os.system("chmod +x ./common/create_secrets.sh")
        apply = ["sh", "./common/create_secrets.sh"]
        apply_state = runShellCommandAndReturnOutput(apply)
        if apply_state[1] != 0:
            logger.error("Failed to create secrets " + str(apply_state[0]))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create secrets " + str(apply_state[0]),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        logger.info(apply_state[0])

        state = waitForGrepProcessWithoutChangeDir(main_command, sub_command, AppName.HARBOR,
                                                   RegexPattern.RECONCILE_SUCCEEDED)
        if state[1] != 200:
            logger.error(state[0].json['msg'])
            d = {
                "responseType": "ERROR",
                "msg": state[0].json['msg'],
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        logger.info("Deployed harbor successfully")
        d = {
            "responseType": "SUCCESS",
            "msg": "Deployed harbor successfully",
            "ERROR_CODE": 200
        }
        return json.dumps(d), 200
    else:
        logger.info("Harbor is already deployed and running")
        d = {
            "responseType": "SUCCESS",
            "msg": "Harbor is already deployed and running",
            "ERROR_CODE": 200
        }
        return json.dumps(d), 200

def deployExtentions(jsonspec):

    aviVersion = ControllerLocation.VSPHERE_AVI_VERSION
    shared_cluster_name = jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceClusterName']
    str_enc = str(jsonspec['harborSpec']['harborPasswordBase64'])
    base64_bytes = str_enc.encode('ascii')
    enc_bytes = base64.b64decode(base64_bytes)
    password = enc_bytes.decode('ascii').rstrip("\n")
    harborPassword = password
    host = jsonspec['harborSpec']['harborFqdn']
    harborCertPath = jsonspec['harborSpec']['harborCertPath']
    harborCertKeyPath = jsonspec['harborSpec']['harborCertKeyPath']
    checkHarborEnabled = jsonspec['harborSpec']['enableHarborExtension']
    if str(checkHarborEnabled).lower() == "true":
        isHarborEnabled = True
    else:
        isHarborEnabled = False
    repo_address = Repo.PUBLIC_REPO
    if not repo_address.endswith("/"):
        repo_address = repo_address + "/"
    repo_address = repo_address.replace("https://", "").replace("http://", "")
    cert_ext_status = installCertManagerAndContour(jsonspec, shared_cluster_name, repo_address)
    if cert_ext_status[1] != 200:
        logger.error(cert_ext_status[0].json['msg'])
        d = {
            "responseType": "ERROR",
            "msg": cert_ext_status[0].json['msg'],
            "ERROR_CODE": 500
        }
        return json.dumps(d), 500

    if not isHarborEnabled:
        service = "disable"
    if service == "registry" or service == "all":
        logger.info("Validate harbor is running")
        state = installHarbor14(service, repo_address, harborCertPath, harborCertKeyPath, harborPassword, host)
        if state[1] != 200:
            logger.error(state[0].json['msg'])
            d = {
                "responseType": "ERROR",
                "msg": state[0].json['msg'],
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
    logger.info("Configured all extentions successfully")
    d = {
        "responseType": "SUCCESS",
        "msg": "Configured all extentions successfully",
        "ERROR_CODE": 200
    }
    return json.dumps(d), 200
