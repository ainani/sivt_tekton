from pathlib import Path

import requests

from model.run_config import RunConfig
from util.logger_helper import LoggerHelper, log

logger = LoggerHelper.get_logger(Path(__file__).stem)


class CspClient:
    def __init__(self, config: RunConfig):
        CspClient.validate_run_config(config)
        self.refresh_token = config.spec.vmc.cspApiToken

    @staticmethod
    def validate_run_config(config):
        if not all([config.spec.vmc, config.spec.vmc.cspApiToken]):
            raise ValueError("Failed to initialise CspClient. Required values not found in run config.")

    @log("Generate CSP access token using refresh token")
    def get_access_token(self):
        url = "https://console.cloud.vmware.com/csp/gateway/am/api/auth/api-tokens/authorize"
        query_params = {
            "refresh_token": self.refresh_token
        }
        r = requests.post(url, params=query_params)
        logger.debug(f"Response code: {r.status_code}\nResponse Body: {r.text}")
        r.raise_for_status()
        return r.json()["access_token"]
