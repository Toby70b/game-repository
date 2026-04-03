import pytest
from domain.game import Game
from ports import GameSource, GameRepository
from typing import Iterator


class FakeGameSource(GameSource):
    """In-memory game source for testing."""

    def __init__(self, games: list[Game]) -> None:
        self._games = games

    def fetch_games(self) -> Iterator[Game]:
        yield from self._games


class FakeGameRepository(GameRepository):
    """In-memory repository for testing."""

    def __init__(self, existing_steam_ids: set[str] | None = None) -> None:
        self._existing = existing_steam_ids or set()
        self.stored: list[Game] = []

    def load_existing_steam_ids(self) -> set[str]:
        return set(self._existing)

    def put_batch(self, games: list[Game]) -> int:
        self.stored.extend(games)
        return len(games)


@pytest.fixture
def make_game():
    def _factory(steam_id: str = "1", title: str = "Test Game") -> Game:
        return Game(steam_game_id=steam_id, title=title)
    return _factory


@pytest.fixture
def fake_source():
    def _factory(games: list[Game]) -> FakeGameSource:
        return FakeGameSource(games)
    return _factory


@pytest.fixture
def fake_repo():
    def _factory(existing: set[str] | None = None) -> FakeGameRepository:
        return FakeGameRepository(existing_steam_ids=existing)
    return _factory

