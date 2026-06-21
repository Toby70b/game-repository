from unittest.mock import MagicMock

from domain.game import Game
from game_import_service import GameImportService


def game(steam_id: str, title: str) -> Game:
    return Game(steam_game_id=steam_id, game_title=title)


class TestGameImportService:

    def _make_service(self, *, source=None, repo=None):
        return GameImportService(
            source=source or MagicMock(),
            repo=repo or MagicMock(),
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

    # ---- Cursor / last_appid ----

    def test_cursor_is_max_existing_id(self):
        source = MagicMock()
        source.fetch_games.return_value = iter([])
        repo = MagicMock()
        repo.existing_titles.return_value = {"5": "a", "200": "b", "30": "c"}

        svc = self._make_service(source=source, repo=repo)
        svc.import_games()

        source.fetch_games.assert_called_once_with(last_appid=200)

    def test_cursor_is_none_when_no_existing(self):
        source = MagicMock()
        source.fetch_games.return_value = iter([])
        repo = MagicMock()
        repo.existing_titles.return_value = {}

        svc = self._make_service(source=source, repo=repo)
        svc.import_games()

        source.fetch_games.assert_called_once_with(last_appid=None)
