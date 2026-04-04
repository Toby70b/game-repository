"""
Lambda handler — inbound adapter. Translates the Lambda invocation into a call to the application service.
"""

import logging
import os

from ports import ImportGamesUseCase
from service import GameImportService
from adapters.steam_api import SteamApiAdapter
from adapters.dynamodb_repo import DynamoDbGameRepository

logging.getLogger().setLevel(logging.INFO)

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "25"))


def handler(event, context):
    """Inbound adapter: translate the Lambda invocation into a use-case call."""
    use_case: ImportGamesUseCase = GameImportService(
        source=SteamApiAdapter(),
        repo=DynamoDbGameRepository(),
        batch_size=BATCH_SIZE,
    )
    return use_case.import_games()
