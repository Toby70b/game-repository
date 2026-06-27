from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from domain.game import Game
from game_import_service import GameImportService


def game(steam_id: str, title: str) -> Game:
    return Game(steam_game_id=steam_id, game_title=title)


def _store(last_timestamp="1000") -> MagicMock:
    store = MagicMock()
    store.get_last_import_timestamp.return_value = last_timestamp
    return store


class TestGameImportService:

    def _make_service(self, *, source=None, repo=None, timestamp_store=None):
        return GameImportService(
            source=source or MagicMock(),
            repo=repo or MagicMock(),
            timestamp_store=timestamp_store or _store(),
        )

    # ---- No games from source ----

    def test_no_games_returns_zero_counts(self):
        source = MagicMock()
        source.fetch_games.return_value = iter([])
        repo = MagicMock()
        repo.existing_titles.return_value = {}

        svc = self._make_service(source=source, repo=repo)
        result = svc.import_games()

        assert result["total games fetched from Steam"] == 0
        assert result["total games written to persistence"] == 0
        repo.upsert_games.assert_not_called()

    # ---- All games are new ----

    def test_new_games_are_written(self):
        games = [game("10", "Game A"), game("20", "Game B")]
        source = MagicMock()
        source.fetch_games.return_value = iter(games)
        repo = MagicMock()
        repo.existing_titles.return_value = {}
        repo.upsert_games.side_effect = lambda batch: batch

        svc = self._make_service(source=source, repo=repo)
        result = svc.import_games()

        assert result["total games fetched from Steam"] == 2
        assert result["total games written to persistence"] == 2
        repo.upsert_games.assert_called_once_with(games)

    # ---- Change detection lives in the service ----

    def test_unchanged_games_are_skipped(self):
        games = [game("10", "Game A"), game("20", "Game B")]
        source = MagicMock()
        source.fetch_games.return_value = iter(games)
        repo = MagicMock()
        repo.existing_titles.return_value = {"10": "Game A"}  # "10" unchanged, "20" new
        repo.upsert_games.side_effect = lambda batch: batch

        svc = self._make_service(source=source, repo=repo)
        result = svc.import_games()

        assert result["total games fetched from Steam"] == 2
        assert result["total games written to persistence"] == 1
        repo.upsert_games.assert_called_once_with([game("20", "Game B")])

    def test_changed_title_is_written(self):
        games = [game("10", "New Title")]
        source = MagicMock()
        source.fetch_games.return_value = iter(games)
        repo = MagicMock()
        repo.existing_titles.return_value = {"10": "Old Title"}
        repo.upsert_games.side_effect = lambda batch: batch

        svc = self._make_service(source=source, repo=repo)
        result = svc.import_games()

        assert result["total games fetched from Steam"] == 1
        assert result["total games written to persistence"] == 1
        repo.upsert_games.assert_called_once_with([game("10", "New Title")])

    def test_all_unchanged_writes_nothing(self):
        games = [game("10", "Game A"), game("20", "Game B")]
        source = MagicMock()
        source.fetch_games.return_value = iter(games)
        repo = MagicMock()
        repo.existing_titles.return_value = {"10": "Game A", "20": "Game B"}

        svc = self._make_service(source=source, repo=repo)
        result = svc.import_games()

        assert result["total games fetched from Steam"] == 2
        assert result["total games written to persistence"] == 0
        repo.upsert_games.assert_not_called()

    # ---- Batching ----

    def test_large_set_is_batched(self):
        """With _BATCH_SIZE=100, 250 new games should produce 3 upsert calls (100+100+50)."""
        games = [game(str(i), f"Game {i}") for i in range(250)]
        source = MagicMock()
        source.fetch_games.return_value = iter(games)
        repo = MagicMock()
        repo.existing_titles.return_value = {}
        repo.upsert_games.side_effect = lambda batch: batch

        svc = self._make_service(source=source, repo=repo)
        result = svc.import_games()

        assert result["total games fetched from Steam"] == 250
        assert result["total games written to persistence"] == 250
        assert repo.upsert_games.call_count == 3
        batch_sizes = [len(call.args[0]) for call in repo.upsert_games.call_args_list]
        assert batch_sizes == [100, 100, 50]

    # ---- Watermark (if_modified_since) ----

    def test_passes_stored_timestamp_as_modified_since(self):
        source = MagicMock()
        source.fetch_games.return_value = iter([])
        repo = MagicMock()
        repo.existing_titles.return_value = {}

        svc = self._make_service(source=source, repo=repo, timestamp_store=_store("1717200000"))
        svc.import_games()

        source.fetch_games.assert_called_once_with(modified_since="1717200000")

    def test_raises_and_skips_fetch_when_timestamp_missing(self):
        source = MagicMock()
        source.fetch_games.return_value = iter([])
        repo = MagicMock()
        repo.existing_titles.return_value = {}

        svc = self._make_service(source=source, repo=repo, timestamp_store=_store(last_timestamp=None))

        with pytest.raises(RuntimeError):
            svc.import_games()
        source.fetch_games.assert_not_called()

    def test_writes_start_of_run_day_watermark_on_success(self):
        source = MagicMock()
        source.fetch_games.return_value = iter([])
        repo = MagicMock()
        repo.existing_titles.return_value = {}
        store = _store("1000")

        svc = self._make_service(source=source, repo=repo, timestamp_store=store)

        fixed_now = datetime(2026, 6, 27, 14, 30, 0, tzinfo=timezone.utc)
        with patch("game_import_service.datetime") as mock_datetime:
            mock_datetime.now.return_value = fixed_now
            svc.import_games()

        # The new watermark should be midnight UTC of the run day, not the exact time.
        start_of_day = datetime(2026, 6, 27, 0, 0, 0, tzinfo=timezone.utc)
        expected = str(int(start_of_day.timestamp()))
        store.set_last_import_timestamp.assert_called_once_with(expected)

    def test_watermark_not_written_when_persistence_fails(self):
        source = MagicMock()
        source.fetch_games.return_value = iter([game("10", "Game A")])
        repo = MagicMock()
        repo.existing_titles.return_value = {}
        repo.upsert_games.side_effect = RuntimeError("ddb down")
        store = _store("1000")

        svc = self._make_service(source=source, repo=repo, timestamp_store=store)

        with pytest.raises(RuntimeError):
            svc.import_games()
        store.set_last_import_timestamp.assert_not_called()
