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
        repo.retrieve_existing_steam_ids.return_value = set()

        svc = self._make_service(source=source, repo=repo)
        result = svc.import_games()

        assert result["total games fetched from Steam"] == 0
        assert result["total games written to persistence"] == 0
        repo.persist_games.assert_not_called()

    # ---- All games are new ----

    def test_new_games_are_persisted(self):
        games = [game("10", "Game A"), game("20", "Game B")]
        source = MagicMock()
        source.fetch_games.return_value = iter(games)
        repo = MagicMock()
        repo.retrieve_existing_steam_ids.return_value = set()
        repo.persist_games.side_effect = lambda batch: batch

        svc = self._make_service(source=source, repo=repo)
        result = svc.import_games()

        assert result["total games fetched from Steam"] == 2
        assert result["total games written to persistence"] == 2
        repo.persist_games.assert_called_once_with(games)

    # ---- Duplicate games are filtered ----

    def test_existing_games_are_skipped(self):
        games = [game("10", "Game A"), game("20", "Game B")]
        source = MagicMock()
        source.fetch_games.return_value = iter(games)
        repo = MagicMock()
        repo.retrieve_existing_steam_ids.return_value = {"10"}
        repo.persist_games.side_effect = lambda batch: batch

        svc = self._make_service(source=source, repo=repo)
        result = svc.import_games()

        assert result["total games fetched from Steam"] == 2
        assert result["total games written to persistence"] == 1
        repo.persist_games.assert_called_once_with([game("20", "Game B")])

    def test_all_duplicates_means_nothing_persisted(self):
        games = [game("10", "Game A"), game("20", "Game B")]
        source = MagicMock()
        source.fetch_games.return_value = iter(games)
        repo = MagicMock()
        repo.retrieve_existing_steam_ids.return_value = {"10", "20"}

        svc = self._make_service(source=source, repo=repo)
        result = svc.import_games()

        assert result["total games fetched from Steam"] == 2
        assert result["total games written to persistence"] == 0
        repo.persist_games.assert_not_called()

    # ---- Batching ----

    def test_large_set_is_batched(self):
        """With _BATCH_SIZE=100, 250 games should produce 3 persist calls (100+100+50)."""
        games = [game(str(i), f"Game {i}") for i in range(250)]
        source = MagicMock()
        source.fetch_games.return_value = iter(games)
        repo = MagicMock()
        repo.retrieve_existing_steam_ids.return_value = set()
        repo.persist_games.side_effect = lambda batch: batch

        svc = self._make_service(source=source, repo=repo)
        result = svc.import_games()

        assert result["total games fetched from Steam"] == 250
        assert result["total games written to persistence"] == 250
        assert repo.persist_games.call_count == 3
        # Verify batch sizes
        batch_sizes = [len(call.args[0]) for call in repo.persist_games.call_args_list]
        assert batch_sizes == [100, 100, 50]

    # ---- Cursor / last_appid ----

    def test_cursor_is_max_existing_id(self):
        source = MagicMock()
        source.fetch_games.return_value = iter([])
        repo = MagicMock()
        repo.retrieve_existing_steam_ids.return_value = {"5", "200", "30"}

        svc = self._make_service(source=source, repo=repo)
        svc.import_games()

        source.fetch_games.assert_called_once_with(last_appid=200)

    def test_cursor_is_none_when_no_existing(self):
        source = MagicMock()
        source.fetch_games.return_value = iter([])
        repo = MagicMock()
        repo.retrieve_existing_steam_ids.return_value = set()

        svc = self._make_service(source=source, repo=repo)
        svc.import_games()

        source.fetch_games.assert_called_once_with(last_appid=None)

