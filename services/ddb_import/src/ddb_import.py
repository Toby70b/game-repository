"""
Lambda handler — inbound adapter.

Hexagonal architecture layers
──────────────────────────────
  Domain           : domain/game.py
  Inbound port     : ports.ImportGamesUseCase
  Outbound ports   : ports.GameSource, ports.GameRepository
  Application svc  : service.GameImportService   (implements inbound port)
  Outbound adapters: adapters/steam_api.py, adapters/dynamodb_repo.py
  Inbound adapter  : ddb_import.py               (this file — Lambda handler)
"""

import logging
import os

from ports import ImportGamesUseCase
from service import GameImportService
from adapters.steam_api import SteamApiAdapter
from adapters.dynamodb_repo import DynamoDbGameRepository

logging.basicConfig(level=logging.INFO)

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "25"))


def handler(event, context):
    """Inbound adapter: translate the Lambda invocation into a use-case call."""
    use_case: ImportGamesUseCase = GameImportService(
        source=SteamApiAdapter(),
        repo=DynamoDbGameRepository(),
        batch_size=BATCH_SIZE,
    )
    return use_case.import_games()
