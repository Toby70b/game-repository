import logging
import os
import uuid
from dataclasses import dataclass

import boto3

from domain.game import Game
from ports import GameRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GameItem:
    """Persistence entity representing a DynamoDB Games table item."""
    game_id: str
    steam_game_id: str
    game_title: str

    @classmethod
    def from_game(cls, game: Game) -> "GameItem":
        return cls(
            game_id=str(uuid.uuid4()),
            steam_game_id=game.steam_game_id,
            game_title=game.game_title,
        )

    def to_item(self) -> dict:
        return {
            "game_id": self.game_id,
            "steam_game_id": self.steam_game_id,
            "game_title": self.game_title,
        }


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
                sid = item.get("steam_game_id")
                if sid:
                    existing.add(sid)

        logger.info("Loaded %d existing steam_game_ids from table", len(existing))
        return existing

    def persist_games(self, games: list[Game]) -> list[Game]:
        """Write a list of games to DynamoDB. Returns the list of persisted games."""
        with self._table.batch_writer() as batch:
            for game in games:
                item = GameItem.from_game(game)
                batch.put_item(Item=item.to_item())
        return games
