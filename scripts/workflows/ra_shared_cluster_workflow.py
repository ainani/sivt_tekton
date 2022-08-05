#  Copyright 2021 VMware, Inc
#  SPDX-License-Identifier: BSD-2-Clause

import os
from pathlib import Path
import traceback
import time
import json
import base64
import ruamel
from model.vsphereSpec import VsphereMasterSpec
from constants.constants import TKG_EXTENSIONS_ROOT, ControllerLocation, KubectlCommands, \
    Paths, Task, ResourcePoolAndFolderName, PLAN, Sizing, ClusterType, RegexPattern, AkoType,\
    AppName, Avi_Tkgs_Version, Avi_Version, Cloud, Env
from jinja2 import Template
from lib.kubectl_client import KubectlClient
from lib.tkg_cli_client import TkgCliClient
from model.run_config import RunConfig
from model.status import (ExtensionState, HealthEnum, SharedExtensionState,
                          State)
from tqdm import tqdm
from util.cmd_helper import CmdHelper
from util.file_helper import FileHelper
from util.git_helper import Git
from util.logger_helper import LoggerHelper, log, log_debug
from util.ssh_helper import SshHelper
from util.tanzu_utils import TanzuUtils
from util.cmd_runner import RunCmd
from util.common_utils import downloadAndPushKubernetesOvaMarketPlace, runSsh, getNetworkFolder, \
    deployCluster, registerWithTmcOnSharedAndWorkload, registerTanzuObservability, checkenv, getVipNetworkIpNetMask, \
        obtain_second_csrf, createClusterFolder
from util.vcenter_operations import createResourcePool, create_folder
from util.ShellHelper import runShellCommandAndReturnOutputAsList, verifyPodsAreRunning,\
    grabKubectlCommand, grabPipeOutput
from workflows.cluster_common_workflow import ClusterCommonWorkflow
from util.shared_config import deployExtentions
from util.tkg_util import TkgUtil



logger = LoggerHelper.get_logger(Path(__file__).stem)


class RaSharedClusterWorkflow:
    def __init__(self, run_config: RunConfig):
        self.run_config = run_config
        self.tkg_util_obj = TkgUtil(run_config=self.run_config)
        self.tkg_version_dict = self.tkg_util_obj.get_desired_state_tkg_version()
        self.desired_state_tkg_version = None
        if "tkgs" in self.tkg_version_dict:
            self.jsonpath = os.path.join(self.run_config.root_dir, Paths.TKGS_WCP_MASTER_SPEC_PATH)
            self.desired_state_tkg_version = self.tkg_version_dict['tkgs']
        elif "tkgm" in self.tkg_version_dict:
            self.jsonpath = os.path.join(self.run_config.root_dir, Paths.MASTER_SPEC_PATH)
            self.desired_state_tkg_version = self.tkg_version_dict['tkgm']
        else:
            raise Exception(f"Could not find supported TKG version: {self.tkg_version_dict}")
        
        #self.extensions_root = TKG_EXTENSIONS_ROOT[self.desired_state_tkg_version]
        #self.extensions_dir = Paths.TKG_EXTENSIONS_DIR.format(extensions_root=self.extensions_root)
        # Specifies current running version as per state.yml
        self.current_version = self.run_config.state.shared_services.version
        self.prev_version = self.run_config.state.shared_services.upgradedFrom or self.run_config.state.shared_services.version
        self.tkg_cli_client = TkgCliClient()
        self.kubectl_client =  KubectlClient()
        self.common_workflow = ClusterCommonWorkflow()
        # Following values must be set in upgrade scenarios
        self.prev_extensions_root = None
        self.prev_extensions_dir = None
        jsonpath = os.path.join(self.run_config.root_dir, Paths.MASTER_SPEC_PATH)
        with open(jsonpath) as f:
            self.jsonspec = json.load(f)
        self.rcmd = RunCmd()

        check_env_output = checkenv(self.jsonspec)
        if check_env_output is None:
            msg = "Failed to connect to VC. Possible connection to VC is not available or " \
                  "incorrect spec provided."
            raise Exception(msg)


    def _template_deploy_yaml(self):
        deploy_yaml = FileHelper.read_resource(Paths.VSPHERE_SHARED_SERVICES_SPEC_J2)
        t = Template(deploy_yaml)
        return t.render(spec=self.run_config.spec)


    def isAviHaEnabled(self):
        try:
            if TkgUtil.isEnvTkgs_wcp(self.jsonspec):
                enable_avi_ha = self.jsonspec['tkgsComponentSpec']['aviComponents']['enableAviHa']
            else:
                enable_avi_ha = self.jsonspec['tkgComponentSpec']['aviComponents']['enableAviHa']
            if str(enable_avi_ha).lower() == "true":
                return True
            else:
                return False
        except:
            return False


    def createAkoFile(self,ip, shared_cluster_name, tkgMgmtDataVipCidr, tkgMgmtDataPg):
        repository = 'projects.registry.vmware.com/tkg/ako'

        data = dict(
            apiVersion='networking.tkg.tanzu.vmware.com/v1alpha1',
            kind='AKODeploymentConfig',
            metadata=dict(
                finalizers=['ako-operator.networking.tkg.tanzu.vmware.com'],
                generation=1,
                name='install-ako-for-shared-services-cluster',
            ),
            spec=dict(
                adminCredentialRef=dict(
                    name='avi-controller-credentials',
                    namespace='tkg-system-networking'),
                certificateAuthorityRef=dict(
                    name='avi-controller-ca',
                    namespace='tkg-system-networking'
                ),
                cloudName=Cloud.CLOUD_NAME_VSPHERE,
                clusterSelector=dict(
                    matchLabels=dict(
                        type=AkoType.SHARED_CLUSTER_SELECTOR
                    )
                ),
                controller=ip,
                dataNetwork=dict(cidr=tkgMgmtDataVipCidr, name=tkgMgmtDataPg),
                extraConfigs=dict(ingress=dict(defaultIngressController=False, reopository=repository, disableIngressClass=True)),
                serviceEngineGroup=Cloud.SE_GROUP_NAME_VSPHERE
            )
        )
        with open(Paths.CLUSTER_PATH + shared_cluster_name + '/tkgvsphere-ako-shared-services-cluster.yaml', 'w') as outfile:
            yaml = ruamel.yaml.YAML()
            yaml.indent(mapping=2, sequence=4, offset=3)
            yaml.dump(data, outfile)
        
    @log("Updating state file")
    def _update_state(self, task: Task, msg="Successful shared cluster deployment"):
        state_file_path = os.path.join(self.run_config.root_dir, Paths.STATE_PATH)
        state: State = FileHelper.load_state(state_file_path)
        self.cluster_to_deploy = self.jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceClusterName']
        if task == Task.DEPLOY_CLUSTER:
            state.shared_services.deployed = True
            state.shared_services.name = self.cluster_to_deploy
            state.shared_services.version = self.desired_state_tkg_version
            state.shared_services.health = HealthEnum.UP
        elif task == Task.UPGRADE_CLUSTER:
            ext_state = ExtensionState(deployed=True, upgraded=False)
            state.shared_services.upgradedFrom = state.shared_services.version
            state.shared_services.version = self.desired_state_tkg_version
            state.shared_services.name = self.cluster_to_deploy
            state.shared_services.health = HealthEnum.UP
            state.shared_services.extensions = SharedExtensionState(certManager=ext_state,
                                                                    contour=ext_state,
                                                                    externalDns=ext_state,
                                                                    harbor=ext_state)
        elif task == Task.DEPLOY_CERT_MANAGER or task == Task.UPGRADE_CERT_MANAGER:
            state.shared_services.extensions.certManager = ExtensionState(deployed=True,
                                                                          upgraded=True)
        elif task == Task.DEPLOY_CONTOUR or task == Task.UPGRADE_CONTOUR:
            state.shared_services.extensions.contour = ExtensionState(deployed=True, upgraded=True)
        elif task == Task.DEPLOY_EXTERNAL_DNS or task == Task.UPGRADE_EXTERNAL_DNS:
            state.shared_services.extensions.externalDns = ExtensionState(deployed=True,
                                                                          upgraded=True)
        elif task == Task.DEPLOY_HARBOR or task == Task.UPGRADE_HARBOR:
            state.shared_services.extensions.harbor = ExtensionState(deployed=True, upgraded=True)
        elif task == Task.ATTACH_CLUSTER_TO_TMC:
            state.shared_services.integrations.tmc.attached = True

        FileHelper.dump_state(state, state_file_path)

    def _attach_cluster_to_tmc(self, jsonspec):
        try:
            cluster_group = 'default'
            api_token = jsonspec['envSpec']["saasEndpoints"]['tmcDetails']['tmcRefreshToken']
            self.common_workflow.attach_cluster_to_tmc(cluster_name=self.cluster_to_deploy,
                                                       cluster_group=cluster_group,
                                                       api_token=self.spec.integrations.tmc.apiToken)
            self._update_state(task=Task.ATTACH_CLUSTER_TO_TMC,
                               msg=f'Cluster attachment to Tmc completed for '
                                   f'{self.cluster_to_deploy}')
            return True
        except Exception:
            logger.error("Error Encountered in Attaching to TMC: {}".format(traceback.format_exc()))
            return False

    @log('Deploy Shared Services Cluster')
    def deploy(self):

        json_dict = self.jsonspec
        vsSpec = VsphereMasterSpec.parse_obj(json_dict)
        aviVersion = Avi_Tkgs_Version.VSPHERE_AVI_VERSION if TkgUtil.isEnvTkgs_wcp(self.jsonspec) else Avi_Version.VSPHERE_AVI_VERSION
        vcpass_base64 = self.jsonspec['envSpec']['vcenterDetails']['vcenterSsoPasswordBase64']
        password = CmdHelper.decode_base64(vcpass_base64)
        vcenter_username = self.jsonspec['envSpec']['vcenterDetails']['vcenterSsoUser']
        vcenter_ip = self.jsonspec['envSpec']['vcenterDetails']['vcenterAddress']
        cluster_name = self.jsonspec['envSpec']['vcenterDetails']['vcenterCluster']
        data_center = self.jsonspec['envSpec']['vcenterDetails']['vcenterDatacenter']
        data_store = self.jsonspec['envSpec']['vcenterDetails']['vcenterDatastore']
        parent_resourcepool = self.jsonspec['envSpec']['vcenterDetails']['resourcePoolName']
        refToken = self.jsonspec['envSpec']['marketplaceSpec']['refreshToken']
        kubernetes_ova_os = self.jsonspec["tkgComponentSpec"]["tkgMgmtComponents"]["tkgSharedserviceBaseOs"]
        kubernetes_ova_version = self.jsonspec["tkgComponentSpec"]["tkgMgmtComponents"]["tkgSharedserviceKubeVersion"]
        if refToken:
            logger.info("Kubernetes OVA configs for shared services cluster")
            down_status = downloadAndPushKubernetesOvaMarketPlace(self.jsonspec,
                                                                  kubernetes_ova_version,
                                                                  kubernetes_ova_os)
            if down_status[0] is None:
                logger.error(down_status[1])
                d = {
                    "responseType": "ERROR",
                    "msg": down_status[1],
                    "ERROR_CODE": 500
                }
                return json.dumps(d), 500
        else:
            logger.info("MarketPlace refresh token is not provided, "
                        "skipping the download of kubernetes ova")
        try:
            isCreated4 = createResourcePool(vcenter_ip, vcenter_username, password,
                                            cluster_name,
                                            ResourcePoolAndFolderName.SHARED_RESOURCE_POOL_NAME_VCENTER,
                                            parent_resourcepool)
            if isCreated4 is not None:
                logger.info("Created resource pool " +
                            ResourcePoolAndFolderName.SHARED_RESOURCE_POOL_NAME_VCENTER)
        except Exception as e:
            logger.error("Failed to create resource pool " + str(e))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create resource pool " + str(e),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        try:
            isCreated1 = create_folder(vcenter_ip, vcenter_username, password,
                                       data_center,
                                       ResourcePoolAndFolderName.SHARED_FOLDER_NAME_VSPHERE)
            if isCreated1 is not None:
                logger.info("Created folder " + ResourcePoolAndFolderName.SHARED_FOLDER_NAME_VSPHERE)
        except Exception as e:
            logger.error("Failed to create folder " + str(e))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to create folder " + str(e),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500, str(e)
        management_cluster = self.jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgMgmtClusterName']
        try:
            ssh_key = runSsh(vcenter_username)
            # with open('/root/.ssh/id_rsa.pub', 'r') as f:
            #     re = f.readline()
        except Exception as e:
            logger.error("Failed to ssh key from config file " + str(e))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to ssh key from config file " + str(e),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        #Init tanzu cli plugins
        tanzu_init_cmd = "tanzu plugin sync"
        command_status = self.rcmd.run_cmd_output(tanzu_init_cmd)
        logger.debug("Tanzu plugin output: {}".format(command_status))
        podRunninng = ["tanzu", "cluster", "list"]
        command_status = self.rcmd.runShellCommandAndReturnOutputAsList(podRunninng)
        if command_status[1] != 0:
            logger.error("Failed to run command to check status of pods")
            d = {
                "responseType": "ERROR",
                "msg": "Failed to run command to check status of pods",
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500

        shared_cluster_name = self.jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceClusterName']
        cluster_plan = self.jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceDeploymentType']
        if cluster_plan == PLAN.DEV_PLAN:
            additional_command = ""
            machineCount = self.jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceWorkerMachineCount']
        elif cluster_plan == PLAN.PROD_PLAN:
            additional_command = "--high-availability"
            machineCount = self.jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceWorkerMachineCount']
        else:
            logger.error("Un supported control plan provided please specify prod or dev " + cluster_plan)
            d = {
                "responseType": "ERROR",
                "msg": "Un supported control plan provided please specify prod or dev " + cluster_plan,
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        size = str(self.jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceSize'])

        if size.lower() == "medium":
            cpu = Sizing.medium['CPU']
            memory = Sizing.medium['MEMORY']
            disk = Sizing.medium['DISK']
        elif size.lower() == "large":
            cpu = Sizing.large['CPU']
            memory = Sizing.large['MEMORY']
            disk = Sizing.large['DISK']
        elif size.lower() == "extra-large":
            cpu = Sizing.extraLarge['CPU']
            memory = Sizing.extraLarge['MEMORY']
            disk = Sizing.extraLarge['DISK']
        elif size.lower() == "custom":
            cpu = self.jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceCpuSize']
            disk = self.jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceStorageSize']
            control_plane_mem_gb = self.jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceMemorySize']
            memory = str(int(control_plane_mem_gb) * 1024)
        else:
            logger.error("Un supported cluster size please specify large/extra-large/custom " + size)
            d = {
                "responseType": "ERROR",
                "msg": "Un supported cluster size please specify large/extra-large/custom " + size,
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500

        shared_service_network = self.jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgMgmtNetworkName']
        vsphere_password = password
        _base64_bytes = vsphere_password.encode('ascii')
        _enc_bytes = base64.b64encode(_base64_bytes)
        vsphere_password = _enc_bytes.decode('ascii')
        datacenter_path = "/" + data_center
        datastore_path = datacenter_path + "/datastore/" + data_store
        shared_folder_path = datacenter_path + "/vm/" + ResourcePoolAndFolderName.SHARED_FOLDER_NAME_VSPHERE
        if parent_resourcepool:
            shared_resource_path = datacenter_path + "/host/" + cluster_name + "/Resources/" \
                                   + parent_resourcepool + "/" + \
                                   ResourcePoolAndFolderName.SHARED_RESOURCE_POOL_NAME_VCENTER
        else:
            shared_resource_path = datacenter_path + "/host/" + cluster_name + "/Resources/" \
                                   + ResourcePoolAndFolderName.SHARED_RESOURCE_POOL_NAME_VCENTER
        shared_network_path = getNetworkFolder(shared_service_network, vcenter_ip, vcenter_username,
                                               password)
        if not shared_network_path:
            logger.error("Network folder not found for " + shared_service_network)
            d = {
                "responseType": "ERROR",
                "msg": "Network folder not found for " + shared_service_network,
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        # if self.run_config.state.shared_services.deployed:
        #     logger.info("Shared cluster is deployed, and in version : %s",
        #                 self.run_config.state.shared_services.version)
        #     return "SUCCESS", 200
        with open('/root/.ssh/id_rsa.pub', 'r') as f:
            re = f.readline()

        deploy_status = deployCluster(shared_cluster_name, cluster_plan,
                                      data_center, data_store, shared_folder_path,
                                      shared_network_path,
                                      vsphere_password, shared_resource_path, vcenter_ip,
                                      re, vcenter_username, machineCount, size,
                                      ClusterType.SHARED, vsSpec, self.jsonspec)
        if deploy_status[0] is None:
            logger.error("Failed to deploy cluster " + deploy_status[1])
            d = {
                "responseType": "ERROR",
                "msg": "Failed to deploy cluster " + deploy_status[1],
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        isCheck = True
        logger.info('Checking for cluster state...')
        count = 0
        if isCheck:
            command_status = runShellCommandAndReturnOutputAsList(podRunninng)
            if command_status[1] != 0:
                logger.error(
                    "Failed to check pods are running " + str(command_status[0]))
                d = {
                    "responseType": "ERROR",
                    "msg": "Failed to check pods are running " + str(command_status[0]),
                    "ERROR_CODE": 500
                }
                return json.dumps(d), 500
            while not verifyPodsAreRunning(shared_cluster_name, command_status[0],
                                           RegexPattern.running) and count < 60:
                command_status = runShellCommandAndReturnOutputAsList(podRunninng)
                if command_status[1] != 0:
                    logger.error(
                        "Failed to check pods are running " + str(command_status[0]))
                    d = {
                        "responseType": "ERROR",
                        "msg": "Failed to check pods are running " + str(command_status[0]),
                        "ERROR_CODE": 500
                    }
                    return json.dumps(d), 500
                count = count + 1
                time.sleep(30)
                logger.info("Waited for  " + str(count * 30) + "s, retrying.")
        if not verifyPodsAreRunning(shared_cluster_name, command_status[0], RegexPattern.running):
            logger.error(
                shared_cluster_name + " is not running on waiting " + str(count * 30) + "s")
            d = {
                "responseType": "ERROR",
                "msg": shared_cluster_name + " is not running on waiting " + str(count * 30) + "s",
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        commands = ["tanzu", "management-cluster", "kubeconfig", "get", management_cluster,
                    "--admin"]
        kubeContextCommand = grabKubectlCommand(commands, RegexPattern.SWITCH_CONTEXT_KUBECTL)
        if kubeContextCommand is None:
            logger.error("Failed to get switch to management cluster context command")
            d = {
                "responseType": "ERROR",
                "msg": "Failed to get switch to management cluster context command",
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        lisOfSwitchContextCommand = str(kubeContextCommand).split(" ")
        status = runShellCommandAndReturnOutputAsList(lisOfSwitchContextCommand)
        if status[1] != 0:
            logger.error(
                "Failed to get switch to management cluster context " + str(status[0]))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to get switch to management cluster context " + str(status[0]),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500

        

        if self.isAviHaEnabled():
            avi_fqdn = self.jsonspec['tkgComponentSpec']['aviComponents']['aviClusterFqdn']
        else:
            avi_fqdn = self.jsonspec['tkgComponentSpec']['aviComponents']['aviController01Fqdn']
        if avi_fqdn is None:
            logger.error("Failed to get ip of avi controller")
            d = {
                "responseType": "ERROR",
                "msg": "Failed to get ip of avi controller",
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        try:
            tkg_mgmt_data_pg = self.jsonspec['tkgMgmtDataNetwork']['tkgMgmtDataNetworkName']
            tkg_cluster_vip_name = self.jsonspec['tkgComponentSpec']['tkgClusterVipNetwork']['tkgClusterVipNetworkName']
        except Exception as e:
            logger.error("One of the following values is not present in input file: "
                                    "tkgMgmtDataNetworkName, tkgClusterVipNetworkName")
            logger.error(str(e))
            d = {
                "responseType": "ERROR",
                "msg": "One of the following values is not present in input file: tkgMgmtDataNetworkName, "
                    "tkgClusterVipNetworkName",
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500

        if not createClusterFolder(shared_cluster_name):
            d = {
            "responseType": "ERROR",
            "msg": "Failed to create directory: " + Paths.CLUSTER_PATH + shared_cluster_name,
            "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        logger.info("The config files for shared services cluster will be located at: " + Paths.CLUSTER_PATH + shared_cluster_name)
        if TkgUtil.isEnvTkgs_wcp(self.jsonspec):
            avienc_pass = str(self.jsonspec['tkgsComponentSpec']['aviComponents']['aviPasswordBase64'])
        else:
            avienc_pass = str(self.jsonspec['tkgComponentSpec']['aviComponents']['aviPasswordBase64'])
        csrf2 = obtain_second_csrf(avi_fqdn, avienc_pass)
        if csrf2 is None:
            logger.error("Failed to get csrf from new set password")
            d = {
                "responseType": "ERROR",
                "msg": "Failed to get csrf from new set password",
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        tkg_mgmt_data_netmask = getVipNetworkIpNetMask(avi_fqdn, csrf2, tkg_mgmt_data_pg, aviVersion)
        if tkg_mgmt_data_netmask[0] is None or tkg_mgmt_data_netmask[0] == "NOT_FOUND":
            logger.error("Failed to get TKG Management Data netmask")
            d = {
                "responseType": "ERROR",
                "msg": "Failed to get TKG Management Data netmask",
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        tkg_cluster_vip_netmask = getVipNetworkIpNetMask(avi_fqdn, csrf2, tkg_cluster_vip_name, aviVersion)
        if tkg_cluster_vip_netmask[0] is None or tkg_cluster_vip_netmask[0] == "NOT_FOUND":
            logger.error("Failed to get Cluster VIP netmask")
            d = {
                "responseType": "ERROR",
                "msg": "Failed to get Cluster VIP netmask",
                "ERROR_CODE": 500
            }
            return json(d), 500
        logger.info("Creating AKODeploymentConfig for shared services cluster...")
        self.createAkoFile(avi_fqdn, shared_cluster_name, tkg_mgmt_data_netmask[0], tkg_mgmt_data_pg)
        yaml_file_path = Paths.CLUSTER_PATH + shared_cluster_name + "/tkgvsphere-ako-shared-services-cluster.yaml"
        listOfCommand = ["kubectl", "create", "-f", yaml_file_path]
        status = runShellCommandAndReturnOutputAsList(listOfCommand)
        if status[1] != 0:
            if not str(status[0]).__contains__("already has a value"):
                logger.error("Failed to apply ako" + str(status[0]))
                d = {
                    "responseType": "ERROR",
                    "msg": "Failed to create new AkoDeploymentConfig " + str(status[0]),
                    "ERROR_CODE": 500
                }
                return json.dumps(d), 500
        logger.info("Successfully created a new AkoDeploymentConfig for shared services cluster")

        podRunninng_ako_main = ["kubectl", "get", "pods", "-A"]
        podRunninng_ako_grep = ["grep", AppName.AKO]
        count_ako = 0
        command_status_ako = grabPipeOutput(podRunninng_ako_main, podRunninng_ako_grep)
        found = False
        if verifyPodsAreRunning(AppName.AKO, command_status_ako[0], RegexPattern.RUNNING):
            found = True

        while not verifyPodsAreRunning(AppName.AKO, command_status_ako[0],
                                       RegexPattern.RUNNING) and count_ako < 20:
            command_status = grabPipeOutput(podRunninng_ako_main, podRunninng_ako_grep)
            if verifyPodsAreRunning(AppName.AKO, command_status[0], RegexPattern.RUNNING):
                found = True
                break
            count_ako = count_ako + 1
            time.sleep(30)
            logger.info("Waited for  " + str(count_ako * 30) + "s, retrying.")
        if not found:
            logger.error("Ako pods are not running on waiting " + str(count_ako * 30))
            d = {
                "responseType": "ERROR",
                "msg": "Ako pods are not running on waiting " + str(count_ako * 30),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        if count_ako > 30:
            for i in tqdm(range(60), desc="Waiting for ako pods to be up…", ascii=False, ncols=75):
                time.sleep(1)

        logger.info("Setting Label for created cluster")
        lisOfCommand = ["kubectl", "label", "cluster.cluster.x-k8s.io/" + shared_cluster_name,
                        "cluster-role.tkg.tanzu.vmware.com/tanzu-services=""", "--overwrite=true"]
        status = runShellCommandAndReturnOutputAsList(lisOfCommand)
        if status[1] != 0:
            logger.error("Failed to apply k8s label " + str(status[0]))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to apply k8s label " + str(status[0]),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        lisOfCommand = ["kubectl", "label", "cluster",
                        shared_cluster_name, AkoType.KEY + "=" + AkoType.SHARED_CLUSTER_SELECTOR, "--overwrite=true"]
        status = runShellCommandAndReturnOutputAsList(lisOfCommand)
        logger.info("Running label cmd: {}".format(status))
        if status[1] != 0:
            if not str(status[0]).__contains__("already has a value"):
                logger.error("Failed to apply ako label " + str(status[0]))
                d = {
                    "responseType": "ERROR",
                    "msg": "Failed to apply ako label " + str(status[0]),
                    "ERROR_CODE": 500
                }
                return json.dumps(d), 500
        else:
            logger.info("Status: {}".format(status[0]))
        commands_shared = ["tanzu", "cluster", "kubeconfig", "get", shared_cluster_name, "--admin"]
        kubeContextCommand_shared = grabKubectlCommand(commands_shared,
                                                       RegexPattern.SWITCH_CONTEXT_KUBECTL)
        if kubeContextCommand_shared is None:
            logger.error("Failed to get switch to shared cluster context command")
            d = {
                "responseType": "ERROR",
                "msg": "Failed to get switch to shared cluster context command",
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        lisOfSwitchContextCommand_shared = str(kubeContextCommand_shared).split(" ")
        status = runShellCommandAndReturnOutputAsList(lisOfSwitchContextCommand_shared)
        if status[1] != 0:
            logger.error(
                "Failed to get switch to shared cluster context " + str(status[0]))
            d = {
                "responseType": "ERROR",
                "msg": "Failed to get switch to shared cluster context " + str(status[0]),
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500


        logger.info('Attaching to TMC if enabled...')
        tmc_required = str(
            self.jsonspec['envSpec']["saasEndpoints"]['tmcDetails']['tmcAvailability'])
        tmc_flag = False
        if tmc_required.lower() == "true":
            tmc_flag = True
        elif tmc_required.lower() == "false":
            tmc_flag = False
            logger.info("Tmc registration is disabled")
        else:
            logger.error("Wrong tmc selection attribute provided " + tmc_required)
            d = {
                "responseType": "ERROR",
                "msg": "Wrong tmc selection attribute provided " + tmc_required,
                "ERROR_CODE": 500
            }
            return json.dumps(d), 500
        if tmc_flag:
            state = registerWithTmcOnSharedAndWorkload(self.jsonspec, shared_cluster_name, "shared")
            if state[1] != 200:
                logger.error(state[0].json['msg'])
                d = {
                    "responseType": "ERROR",
                    "msg": state[0].json['msg'],
                    "ERROR_CODE": 500
                }
                return json.dumps(d), 500
        #to_enable = self.jsonspec["envSpec"]["saasEndpoints"]["tanzuObservabilityDetails"]["tanzuObservabilityAvailability"]
        to = registerTanzuObservability(shared_cluster_name, size, self.jsonspec)
        if to[1] != 200:
            logger.error(to[0].json['msg'])
            return to[0], to[1]
        d = {
            "responseType": "SUCCESS",
            "msg": "Successfully deployed  cluster " + shared_cluster_name,
            "SUCCESS_CODE": 200
        }
        logger.info("Successfully completed deploying Shared Services Cluster.")

        return json.dumps(d), 200


