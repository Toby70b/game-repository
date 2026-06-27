import logging
import os

import boto3
from botocore.exceptions import ClientError

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
        except ClientError as e:
            if e.response["Error"]["Code"] == "ParameterNotFound":
                logger.warning("Param %s is not set in parameter store", self._param_name)
                return None
            # Surface transient/permission errors instead of masking them as "unset".
            raise
        return int(response["Parameter"]["Value"])

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
