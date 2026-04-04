import logging
import os
import uuid

import boto3

from domain.game import Game
from ports import GameRepository

logger = logging.getLogger(__name__)


class DynamoDbGameRepository(GameRepository):
    """Outbound adapter: persists Game objects to a DynamoDB table."""

    def __init__(self) -> None:
        dynamodb = boto3.resource("dynamodb")
        self._table = dynamodb.Table(os.environ["TABLE_NAME"])
        self._index = os.environ["STEAM_GAME_ID_INDEX"]

    def retrieve_existing_steam_ids(self) -> set[str]:
        """Scan the steam_game_id GSI and paginate through the results, returning
        a set of all steam_game_ids already present in the table."""
        existing: set[str] = set()
        paginator = self._table.meta.client.get_paginator("scan")

        for page in paginator.paginate(
            TableName=self._table.name,
            IndexName=self._index,
            ProjectionExpression="steam_game_id",
        ):
            for item in page.get("Items", []):
                sid = item.get("steam_game_id", {}).get("S")
                if sid:
                    existing.add(sid)

        logger.info("Loaded %d existing steam_game_ids from table", len(existing))
        return existing

    def persist_games(self, games: list[Game]) -> list[Game]:
        """Write a list of games to DynamoDB. Returns the list of persisted games."""
        with self._table.batch_writer() as batch:
            for game in games:
                batch.put_item(Item={
                    "game_id": str(uuid.uuid4()),
                    "steam_game_id": game.steam_game_id,
                    "title": game.title,
                })
        return games
