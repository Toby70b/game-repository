from unittest.mock import MagicMock

from domain.game import Game
from adapters.dynamodb_repo import GameItem, ExistingGame, DynamoDbGameRepository


class TestGameItem:

    def test_from_game_maps_fields(self):
        g = Game(steam_game_id="42", game_title="Portal")
        item = GameItem.from_game(g)

        assert item.steam_game_id == "42"
        assert item.game_title == "Portal"
        assert item.game_id  # UUID should be generated

    def test_from_game_generates_unique_ids(self):
        g = Game(steam_game_id="42", game_title="Portal")
        item_a = GameItem.from_game(g)
        item_b = GameItem.from_game(g)

        assert item_a.game_id != item_b.game_id

    def test_from_existing_reuses_primary_key(self):
        g = Game(steam_game_id="42", game_title="Portal 2")
        item = GameItem.from_existing(g, game_id="existing-pk")

        assert item.game_id == "existing-pk"
        assert item.steam_game_id == "42"
        assert item.game_title == "Portal 2"

    def test_to_ddb_record_returns_dict(self):
        g = Game(steam_game_id="42", game_title="Portal")
        item = GameItem.from_game(g)
        d = item.to_ddb_record()

        assert d == {
            "game_id": item.game_id,
            "steam_game_id": "42",
            "game_title": "Portal",
        }


class TestUpsertGames:
    """upsert_games is purely 'resolve the key, then write' — given games, it reuses
    an existing primary key or mints one. No change-detection lives here."""

    def _repo_with_existing(self, existing: dict[str, ExistingGame]) -> DynamoDbGameRepository:
        # Bypass __init__ (no boto/env needed) and inject the table snapshot.
        repo = DynamoDbGameRepository.__new__(DynamoDbGameRepository)
        repo._existing_games = dict(existing)
        repo._table = MagicMock()
        self._batch = MagicMock()
        repo._table.batch_writer.return_value.__enter__.return_value = self._batch
        repo._table.batch_writer.return_value.__exit__.return_value = False
        return repo

    def _written_items(self) -> list[dict]:
        return [call.kwargs["Item"] for call in self._batch.put_item.call_args_list]

    def test_existing_game_reuses_primary_key(self):
        repo = self._repo_with_existing({"42": ExistingGame("pk-42", "Portal")})

        repo.upsert_games([Game("42", "Portal 2")])

        items = self._written_items()
        assert len(items) == 1
        assert items[0]["game_id"] == "pk-42"      # reused -> overwrite, not duplicate
        assert items[0]["game_title"] == "Portal 2"

    def test_new_game_mints_primary_key(self):
        repo = self._repo_with_existing({})

        repo.upsert_games([Game("99", "New Game")])

        items = self._written_items()
        assert len(items) == 1
        assert items[0]["steam_game_id"] == "99"
        assert items[0]["game_id"]  # minted, non-empty

    def test_game_repeated_across_batches_keeps_one_primary_key(self):
        repo = self._repo_with_existing({})

        repo.upsert_games([Game("99", "New Game")])
        first_id = self._written_items()[0]["game_id"]
        # A later batch in the same run sees it via the updated cache.
        repo.upsert_games([Game("99", "New Game Renamed")])
        second_id = self._written_items()[-1]["game_id"]

        assert second_id == first_id  # same PK reused, no duplicate row
