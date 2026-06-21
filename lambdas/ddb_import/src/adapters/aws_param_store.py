import logging
import os

import boto3

from ports import LastImportTimestampStore

logger = logging.getLogger(__name__)


class AwsParamStore(LastImportTimestampStore):
    """
    Outbound adapter: retrieves and otherwise manages parameters in AWS Parameter Store.
    """

    def __init__(self) -> None:
        self._param_name = os.environ["LAST_MODIFIED_PARAM"]
        self._ssm = boto3.client("ssm")

    def get_last_import_timestamp(self) -> int | None:
        try:
            response = self._ssm.get_parameter(Name=self._param_name)
            return int(response["Parameter"]["Value"])
        except Exception as e:
            logger.warning("Error when attempting to read param %s from aws parameter store: %s"
                           , self._param_name, str(e))
            return None

    def set_last_import_timestamp(self, timestamp: int) -> None:
        try:
            self._ssm.put_parameter(
                Name=self._param_name,
                Value=str(timestamp),
                Type="String",
                Overwrite=True,
            )
            logger.info("Updated %s to %d", self._param_name, timestamp)
        except Exception as e:
            logger.error("Failed to update parameter %s: %s", self._param_name, str(e))
        raise
