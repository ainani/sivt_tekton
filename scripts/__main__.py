import os
from pathlib import Path

import click
import yaml

from constants.constants import Paths, Task, ControllerLocation
from lib.csp_client import CspClient
from lib.vmc_client import VmcClient
from model.desired_state import DesiredState
from model.run_config import RunConfig, DeploymentPlatform, VmcConfig
from model.spec import MasterSpec
from model.status import State, get_fresh_state
from util.cmd_helper import CmdHelper
from util.env_validation import EnvValidator
from util.file_helper import FileHelper
from util.git_helper import Git
from util.logger_helper import LoggerHelper
from util.ssh_helper import SshHelper
from util.ssl_helper import get_thumbprint, get_colon_formatted_thumbprint
from util.tanzu_utils import TanzuUtils
from workflows.ra_alb_workflow import RALBWorkflow
from workflows.cluster_common_workflow import ClusterCommonWorkflow
from workflows.mgmt_cluster_workflow import MgmtClusterWorkflow
from workflows.repave_workflow import RepaveWorkflow
from workflows.shared_cluster_workflow import SharedClusterWorkflow
from workflows.workload_cluster_workflow import WorkloadClusterWorkflow
from util.glue_parser import file_linker

logger = LoggerHelper.get_logger("__main__")


def load_vmc_config(run_config: RunConfig):
    run_config.vmc.csp_access_token = CspClient(config=run_config).get_access_token()
    vmc_client = VmcClient(config=run_config)
    org = vmc_client.find_org_by_name(run_config.spec.vmc.orgName)
    run_config.vmc.org_id = vmc_client.get_org_id(org)
    sddc = vmc_client.find_sddc_by_name(run_config.vmc.org_id, run_config.spec.vmc.sddcName)
    run_config.vmc.sddc_id = vmc_client.get_sddc_id(sddc)
    run_config.vmc.nsx_reverse_proxy_url = vmc_client.get_nsx_reverse_proxy_url(sddc)
    run_config.vmc.vc_mgmt_ip = vmc_client.get_vcenter_ip(sddc)
    run_config.vmc.vc_cloud_user = vmc_client.get_vcenter_cloud_user(sddc)
    run_config.vmc.vc_cloud_password = vmc_client.get_vcenter_cloud_password(sddc)
    run_config.vmc.vc_tls_thumbprint = get_colon_formatted_thumbprint(get_thumbprint(run_config.vmc.vc_mgmt_ip))
    return run_config


def load_run_config(root_dir):
    spec: MasterSpec = FileHelper.load_spec(os.path.join(root_dir, Paths.MASTER_SPEC_PATH))
    state_file_path = os.path.join(root_dir, Paths.STATE_PATH)
    if not os.path.exists(state_file_path):
        logger.error("state file missing")
        return
    state: State = FileHelper.load_state(state_file_path)
    desired_state: DesiredState = FileHelper.load_desired_state(os.path.join(root_dir, Paths.DESIRED_STATE_PATH))
    support_matrix = yaml.safe_load(FileHelper.read_resource(Paths.SUPPORT_MATRIX_FILE))
    run_config = RunConfig(root_dir=root_dir, spec=spec, state=state, desired_state=desired_state,
                           support_matrix=support_matrix, deployment_platform=DeploymentPlatform.VSPHERE, vmc=None)
    """if spec.vmc:
        run_config.deployment_platform = DeploymentPlatform.VMC
        run_config.vmc = VmcConfig(csp_access_token="", org_id="", sddc_id="", nsx_reverse_proxy_url="", vc_mgmt_ip="",
                                   vc_cloud_user="", vc_cloud_password="", vc_tls_thumbprint="")
        run_config = load_vmc_config(run_config)
    """
    return run_config


@click.group()
@click.option("--root-dir", default=".tmp")
@click.pass_context
def cli(ctx, root_dir):
    ctx.ensure_object(dict)
    ctx.obj["ROOT_DIR"] = root_dir

    # glue parser
    json_spec_path = os.path.join(ctx.obj["ROOT_DIR"], Paths.JSON_SPEC_PATH)
    ControllerLocation.SPEC_FILE_PATH = json_spec_path
    deployment_config_filepath = os.path.join(ctx.obj["ROOT_DIR"], Paths.MASTER_SPEC_PATH)
    file_linker(json_spec_path, deployment_config_filepath)
    # prevalidation
    if not Path(deployment_config_filepath).is_file():
        logger.warn("Missing config in path: %s", deployment_config_filepath)
    os.makedirs(Paths.TMP_DIR, exist_ok=True)

@cli.group()
@click.pass_context
def avi(ctx):
    ctx.ensure_object(dict)


@avi.command(name="deploy")
@click.pass_context
def avi_deploy(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    RALBWorkflow(run_config=run_config).avi_controller_setup()


@avi.command(name="validate")
@click.pass_context
def avi_validate(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    ALBWorkflow(run_config).avi_controller_validate()


@cli.group()
@click.pass_context
def mgmt(ctx):
    click.echo(f"root dir is {ctx.obj['ROOT_DIR']}")


@mgmt.command(name="deploy")
@click.pass_context
def mgmt_deploy(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    MgmtClusterWorkflow(run_config).deploy_mgmt_clu()


@mgmt.command(name="pre-config")
@click.pass_context
def mgmt_pre_config(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    # NsxtWorkflow(run_config).execute_workflow()
    RALBWorkflow(run_config).alb_mgmt_config()


@mgmt.command(name="upgrade")
@click.pass_context
def mgmt_upgrade(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    MgmtClusterWorkflow(run_config).upgrade_workflow()


@cli.group()
@click.pass_context
def shared_services(ctx):
    ctx.ensure_object(dict)


@shared_services.command(name="deploy-cluster")
@click.pass_context
def ss_cluster_deploy(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    SharedClusterWorkflow(run_config).execute_workflow(Task.DEPLOY_CLUSTER)


@shared_services.command(name="deploy-cert-mgr")
@click.pass_context
def ss_deploy_cert_mgr(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    SharedClusterWorkflow(run_config).execute_workflow(Task.DEPLOY_CERT_MANAGER)


@shared_services.command(name="deploy-contour")
@click.pass_context
def ss_deploy_contour(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    SharedClusterWorkflow(run_config).execute_workflow(Task.DEPLOY_CONTOUR)


@shared_services.command(name="deploy-external-dns")
@click.pass_context
def ss_deploy_external_dns(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    SharedClusterWorkflow(run_config).execute_workflow(Task.DEPLOY_EXTERNAL_DNS)


@shared_services.command(name="deploy-harbor")
@click.pass_context
def ss_deploy_harbor(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    SharedClusterWorkflow(run_config).execute_workflow(Task.DEPLOY_HARBOR)

@shared_services.command(name="attach-cluster-to-tmc")
@click.pass_context
def ss_attach_cluster_to_tmc(ctx):
    SharedClusterWorkflow(ctx.obj["ROOT_DIR"]).execute_workflow(Task.ATTACH_CLUSTER_TO_TMC)

@shared_services.command(name="upgrade-cluster")
@click.pass_context
def ss_cluster_upgrade(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    SharedClusterWorkflow(run_config).upgrade_workflow(Task.UPGRADE_CLUSTER)


@shared_services.command(name="upgrade-contour")
@click.pass_context
def ss_upgrade_contour(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    SharedClusterWorkflow(run_config).upgrade_workflow(Task.UPGRADE_CONTOUR)


@shared_services.command(name="upgrade-external-dns")
@click.pass_context
def ss_upgrade_external_dns(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    SharedClusterWorkflow(run_config).upgrade_workflow(Task.UPGRADE_EXTERNAL_DNS)


@shared_services.command(name="upgrade-harbor")
@click.pass_context
def ss_upgrade_harbor(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    SharedClusterWorkflow(run_config).upgrade_workflow(Task.UPGRADE_HARBOR)


@shared_services.command(name="repave")
@click.pass_context
def ss_repave_env(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    RepaveWorkflow(run_config).repave_ss_cluster()


@cli.group()
@click.pass_context
def workload_clusters(ctx):
    ctx.ensure_object(dict)


@workload_clusters.command(name="deploy")
@click.pass_context
def wl_deploy(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    WorkloadClusterWorkflow(run_config).execute_workflow(Task.DEPLOY_CLUSTER)


@workload_clusters.command(name="deploy-cert-mgr")
@click.pass_context
def wl_deploy_cert_mgr(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    WorkloadClusterWorkflow(run_config).execute_workflow(Task.DEPLOY_CERT_MANAGER)


@workload_clusters.command(name="deploy-contour")
@click.pass_context
def wl_deploy_contour(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    WorkloadClusterWorkflow(run_config).execute_workflow(Task.DEPLOY_CONTOUR)


@workload_clusters.command(name="deploy-grafana")
@click.pass_context
def wl_deploy_grafana(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    WorkloadClusterWorkflow(run_config).execute_workflow(Task.DEPLOY_GRAFANA)


@workload_clusters.command(name="deploy-prometheus")
@click.pass_context
def wl_deploy_prometheus(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    WorkloadClusterWorkflow(run_config).execute_workflow(Task.DEPLOY_PROMETHEUS)


@workload_clusters.command(name="attach-cluster-to-tmc")
@click.pass_context
def wl_attach_cluster_to_tmc(ctx):
    WorkloadClusterWorkflow(ctx.obj["ROOT_DIR"]).execute_workflow(Task.ATTACH_CLUSTER_TO_TMC)

@workload_clusters.command(name="upgrade")
@click.pass_context
def wl_upgrade(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    WorkloadClusterWorkflow(run_config).upgrade_workflow()


@workload_clusters.command(name="repave")
@click.pass_context
def wl_repave_env(ctx):
    run_config = load_run_config(ctx.obj["ROOT_DIR"])
    RepaveWorkflow(run_config).repave_wl_cluster()


@cli.command(name="pull-kubeconfig")
@click.pass_context
def pull_kubeconfig(ctx):
    TanzuUtils(ctx.obj["ROOT_DIR"]).pull_config()


@cli.group(name="validate")
@click.pass_context
def validate(ctx):
    ctx.ensure_object(dict)


@validate.command(name="spec")
@click.pass_context
def validate_spec(ctx):
    root_dir = ctx.obj["ROOT_DIR"]
    state_file_path = os.path.join(root_dir, Paths.STATE_PATH)
    try:
        if not os.path.exists(state_file_path):
            logger.info("No state file present, creating empty state file")
            FileHelper.dump_state(get_fresh_state(), state_file_path)
            Git.add_all_and_commit(os.path.dirname(state_file_path), "Added new state file")
            try:
                FileHelper.clear_kubeconfig(root_dir)
                Git.add_all_and_commit(os.path.join(root_dir, Paths.KUBECONFIG_REPO), "cleanup kubeconfigs")
            except Exception as ex:
                logger.error(str(ex))
    except (FileNotFoundError, IOError, OSError):
        logger.error("Invalid state file, content:%s", FileHelper.read_file(state_file_path))
        return
        # logger.info("pushing fresh spec file")
        # FileHelper.dump_state(get_fresh_state(), state_file_path)
        # Git.add_all_and_commit(os.path.dirname(state_file_path), "Update valid state file")

    state: State = FileHelper.load_state(state_file_path)
    desired_state: DesiredState = FileHelper.load_desired_state(os.path.join(root_dir, Paths.DESIRED_STATE_PATH))

    # logger.debug("spec: \n%s", FileHelper.yaml_from_model(spec))
    logger.debug("***state*** \n%s", FileHelper.yaml_from_model(state))
    logger.debug("***desired_state*** \n%s", FileHelper.yaml_from_model(desired_state))

    logger.info("Validated Spec, State, Desired state")


@validate.command(name="env")
@click.pass_context
def validate_env(ctx):
    root_dir = ctx.obj["ROOT_DIR"]
    EnvValidator(root_dir).validate_all()


@cli.command(name="prepare-env")
@click.pass_context
def validate(ctx):
    root_dir = ctx.obj["ROOT_DIR"]
    EnvValidator(root_dir).prepare_env()


@cli.command(hidden=True)
def test():
    logger.warn("Only for testing.. hidden option")


@cli.group(hidden=True)
@click.pass_context
def dev(ctx):
    logger.warn("Only for testing.. hidden option")
    ctx.ensure_object(dict)


@dev.command()
@click.pass_context
def cleanup(ctx):
    root_dir = ctx.obj["ROOT_DIR"]
    state_file_path = os.path.join(root_dir, Paths.STATE_PATH)
    try:
        if os.path.exists(state_file_path):
            os.remove(state_file_path)
            Git.add_all_and_commit(os.path.dirname(state_file_path), "Delete state file for testing")
        FileHelper.clear_kubeconfig(root_dir)
        Git.add_all_and_commit(os.path.join(root_dir, Paths.KUBECONFIG_REPO), "cleanup kubeconfigs")
    except Exception as e:
        logger.error(e)


@cli.command(name="check-health")
@click.pass_context
def check_health(ctx):
    root_dir = ctx.obj["ROOT_DIR"]
    spec = FileHelper.load_spec(os.path.join(root_dir, Paths.MASTER_SPEC_PATH))
    with SshHelper(
            spec.bootstrap.server, spec.bootstrap.username, CmdHelper.decode_password(spec.bootstrap.password),
            spec.onDocker
    ) as ssh:
        ClusterCommonWorkflow(ssh).check_health(root_dir, spec)


if __name__ == "__main__":
    cli(obj={})
