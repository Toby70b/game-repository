from abc import ABC, abstractmethod
from typing import Iterator
from domain.game import Game


# ---------------------------------------------------------------------------
# Inbound port
# ---------------------------------------------------------------------------

class ImportGamesUseCase(ABC):
    """Inbound port: the single operation this application exposes."""

    @abstractmethod
    def import_games(self) -> dict:
        """Run a full import cycle. Returns a summary dict."""
        ...


# ---------------------------------------------------------------------------
# Outbound ports
# ---------------------------------------------------------------------------

class GameSource(ABC):
    """Outbound port: something that can provide a stream of games."""

    @abstractmethod
    def fetch_games(self, last_appid: int | None = None) -> Iterator[Game]:
        """Yield Game objects one at a time. Pass last_appid to resume from a specific offset."""
        ...


class GameRepository(ABC):
    """Outbound port: something that can persist games."""

    @abstractmethod
    def existing_titles(self) -> dict[str, str]:
        """Return a map of steam_game_id -> current game_title for every game
        already in the repository."""
        ...

    @abstractmethod
    def upsert_games(self, games: list[Game]) -> list[Game]:
        """Write the given games, reusing an existing primary key when the game is
        already present and minting one otherwise. The caller decides which games
        need writing. Returns the games written."""
        ...

