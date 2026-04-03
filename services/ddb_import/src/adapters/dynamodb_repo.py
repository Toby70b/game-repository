import logging
import uuid

import boto3

from domain.game import Game
from ports import GameRepository

logger = logging.getLogger(__name__)


class DynamoDbGameRepository(GameRepository):
    """Outbound adapter: persists Game objects to a DynamoDB table."""

    def __init__(self, table_name: str) -> None:
        dynamodb = boto3.resource("dynamodb")
        self._table = dynamodb.Table(table_name)

    def load_existing_steam_ids(self) -> set[str]:
        """Paginate through the GSI projecting only steam_game_id, return as a set.
        One scan instead of one query per game."""
        existing: set[str] = set()
        paginator = self._table.meta.client.get_paginator("scan")

        for page in paginator.paginate(
            TableName=self._table.name,
            IndexName="gsi_steam_game_id",
            ProjectionExpression="steam_game_id",
        ):
            for item in page.get("Items", []):
                sid = item.get("steam_game_id", {}).get("S")
                if sid:
                    existing.add(sid)

        logger.info("Loaded %d existing steam_game_ids from table", len(existing))
        return existing

    def put_batch(self, games: list[Game]) -> int:
        """Write up to 25 items using batch_writer (handles retries automatically)."""
        written = 0
        with self._table.batch_writer() as batch:
            for game in games:
                batch.put_item(Item={
                    "game_id": str(uuid.uuid4()),
                    "steam_game_id": game.steam_game_id,
                    "title": game.title,
                })
                written += 1
        return written

