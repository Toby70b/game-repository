from domain.game import Game
from service import GameImportService


def _run(source_games, existing_ids=None, batch_size=25):
    """Helper: build a service with fakes and run import_games."""
    from tests.conftest import FakeGameSource, FakeGameRepository
    source = FakeGameSource(source_games)
    repo = FakeGameRepository(existing_steam_ids=existing_ids or set())
    service = GameImportService(source=source, repo=repo, batch_size=batch_size)
    return service.import_games(), repo


class TestImportGames:

    def test_writes_new_games(self):
        games = [Game("1", "Half-Life"), Game("2", "Portal")]
        result, repo = _run(games)

        assert result["totalWritten"] == 2
        assert result["totalSkipped"] == 0
        assert result["totalFetched"] == 2
        assert len(repo.stored) == 2

    def test_skips_existing_games(self):
        games = [Game("1", "Half-Life"), Game("2", "Portal")]
        result, repo = _run(games, existing_ids={"1"})

        assert result["totalWritten"] == 1
        assert result["totalSkipped"] == 1
        assert repo.stored[0].steam_game_id == "2"

    def test_skips_all_when_all_exist(self):
        games = [Game("1", "Half-Life"), Game("2", "Portal")]
        result, repo = _run(games, existing_ids={"1", "2"})

        assert result["totalWritten"] == 0
        assert result["totalSkipped"] == 2
        assert repo.stored == []

    def test_empty_source(self):
        result, repo = _run([])

        assert result["totalFetched"] == 0
        assert result["totalWritten"] == 0
        assert result["statusCode"] == 200

    def test_batches_are_flushed(self):
        games = [Game(str(i), f"Game {i}") for i in range(10)]
        result, repo = _run(games, batch_size=3)

        # All 10 should be written regardless of batching
        assert result["totalWritten"] == 10
        assert len(repo.stored) == 10

    def test_returns_correct_status_code(self):
        result, _ = _run([Game("99", "Dota 2")])
        assert result["statusCode"] == 200

