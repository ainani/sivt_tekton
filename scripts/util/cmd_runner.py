import os
import traceback
import logging
from pathlib import Path
import shutil
import subprocess
import shlex
from util.logger_helper import LoggerHelper

__author__ = 'smuthukumar'

logger = LoggerHelper.get_logger(Path(__file__).stem)
logging.getLogger("paramiko").setLevel(logging.WARNING)


"""
ToDO:
 1. for local run command with no output
 2. for local run command with output
 3. for local run long running command in background
 4. for file copy 
"""

class RunCmd:

    def run_cmd_only(self, cmd: str, ignore_errors=False, msg=None):
        logger.debug(f"Running cmd: {cmd}")
        try:
            subprocess.call(shlex.split(cmd), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            logger.error(f"Error: {traceback.format_exc()}\n Error executing: {cmd}")

    def run_cmd_output(self, cmd: str) -> tuple:

        logger.debug(f"Running cmd: {cmd.strip()}")
        try:
            cmd_out = subprocess.check_output(cmd, shell=True, encoding='UTF-8')
            return cmd_out
        except Exception:
            logger.error(f"Error: {traceback.format_exc()}")
            return None

    def local_file_copy(self, srcfile, destfile, follow_symlinks=False):
        logger.debug(f"Copying file {srcfile} to {destfile}")
        try:
            shutil.copyfile(srcfile, destfile, follow_symlinks=follow_symlinks)
        except FileNotFoundError:
            logger.error (f"Error: {traceback.format_exc ()}")


