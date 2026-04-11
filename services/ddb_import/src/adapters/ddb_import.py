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


def handler(event, context):
    use_case: ImportGamesUseCase = GameImportService(
        source=SteamApiAdapter(),
        repo=DynamoDbGameRepository(),
    )
    return use_case.import_games()
