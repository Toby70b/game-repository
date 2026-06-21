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
        """Build an item for a brand-new game, minting a fresh primary key."""
        return cls(
            game_id=str(uuid.uuid4()),
            steam_game_id=game.steam_game_id,
            game_title=game.game_title,
        )

    @classmethod
    def from_existing(cls, game: Game, game_id: str) -> "GameItem":
        """Build an item for an already-persisted game, reusing its primary key so
        the write overwrites the existing row rather than creating a duplicate."""
        return cls(
            game_id=game_id,
            steam_game_id=game.steam_game_id,
            game_title=game.game_title,
        )

    def to_ddb_record(self) -> dict:
        return {
            "game_id": self.game_id,
            "steam_game_id": self.steam_game_id,
            "game_title": self.game_title,
        }


@dataclass(frozen=True)
class ExistingGame:
    """The persisted identity and title of a game already in the table, looked up
    by steam_game_id. Keeps the surrogate game_id confined to the adapter."""
    game_id: str
    game_title: str


class DynamoDbGameRepository(GameRepository):
    """Outbound adapter: persists Game objects to a DynamoDB table."""

    def __init__(self) -> None:
        dynamodb = boto3.resource("dynamodb")
        self._table = dynamodb.Table(os.environ["TABLE_NAME"])
        self._index = os.environ["STEAM_GAME_ID_INDEX"]
        # Snapshot the table's current games once, up front: both the title
        # comparison (via existing_titles) and primary-key resolution (via
        # upsert_games) read from this single scan. Updated in place as we write.
        self._existing_games: dict[str, ExistingGame] = self._scan_existing()

    def _scan_existing(self) -> dict[str, ExistingGame]:
        existing: dict[str, ExistingGame] = {}
        scan_kwargs = {
            "IndexName": self._index,
            "ProjectionExpression": "game_id, steam_game_id, game_title",
        }

        while True:
            page = self._table.scan(**scan_kwargs)

            for item in page.get("Items", []):
                sid = item.get("steam_game_id")
                if sid:
                    existing[sid] = ExistingGame(
                        game_id=item["game_id"],
                        game_title=item.get("game_title", ""),
                    )

            last_evaluated_key = page.get("LastEvaluatedKey")
            if not last_evaluated_key:
                break

            scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

        logger.info("Loaded %d existing games from table", len(existing))
        return existing

    def existing_titles(self) -> dict[str, str]:
        """Return steam_game_id -> current game_title for every persisted game.
        Exposes only domain-level data; the surrogate game_id stays internal."""
        return {sid: game.game_title for sid, game in self._existing_games.items()}

    def upsert_games(self, games: list[Game]) -> list[Game]:
        """Write the given games, reusing the existing primary key when the game is
        already present and minting one otherwise, so updates overwrite rather than
        duplicate. The caller decides which games need writing. Returns them."""
        existing = self._existing_games

        with self._table.batch_writer() as batch:
            for game in games:
                prior = existing.get(game.steam_game_id)
                item = (
                    GameItem.from_existing(game, prior.game_id)
                    if prior is not None
                    else GameItem.from_game(game)
                )
                batch.put_item(Item=item.to_ddb_record())
                # Keep the snapshot consistent so a game repeated in a later batch
                # within the same run isn't re-inserted under a new key.
                existing[game.steam_game_id] = ExistingGame(
                    game_id=item.game_id,
                    game_title=item.game_title,
                )

        return games
