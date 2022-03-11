import subprocess

from flask import current_app
from util.base_cmd_helper import BaseCmdHelper


class LocalCmdHelper(BaseCmdHelper):
    def run_cmd(self, cmd: str, ignore_errors=False) -> int:
        current_app.logger.info(f"Running local command: {cmd}")
        command = cmd.split()
        op = subprocess.run(command, check=not ignore_errors)
        current_app.logger.info(f"Command exit code: {op.returncode}")
        return op.returncode

    def run_cmd_output(self, cmd: str, ignore_errors=False) -> tuple:
        current_app.logger.info(f"Running local command: {cmd}")
        command = cmd.split()
        op = subprocess.run(command, check=not ignore_errors, capture_output=True)
        current_app.logger.info(f"Command exit code: {op.returncode}; STDOUT: {op.stdout}; STDERR: {op.stderr}")
        return op.returncode, op.stdout.decode()
