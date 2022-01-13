import os
from pathlib import Path

import click

from constants.constants import Paths
from util.file_helper import FileHelper
from util.govc_helper import teardown_env
from util.logger_helper import LoggerHelper

logger = LoggerHelper.get_logger("__main__")


@click.group()
@click.option("--root-dir", default=".tmp")
@click.pass_context
def dev(ctx, root_dir):
    ctx.ensure_object(dict)
    ctx.obj["ROOT_DIR"] = root_dir

    # prevalidation
    deployment_config_filepath = os.path.join(ctx.obj["ROOT_DIR"], Paths.MASTER_SPEC_PATH)
    if not Path(deployment_config_filepath).is_file():
        logger.warn("Missing config in path: %s", deployment_config_filepath)

    os.makedirs(Paths.TMP_DIR, exist_ok=True)


@dev.command()
@click.pass_context
def teardown(ctx):
    root_dir = ctx.obj["ROOT_DIR"]
    spec = FileHelper.load_spec(os.path.join(root_dir, Paths.MASTER_SPEC_PATH))
    teardown_env(spec)


if __name__ == "__main__":
    dev(obj={})
