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
    def fetch_games(self, modified_since: int | None = None) -> Iterator[Game]:
        """Yield Game objects one at a time. Pass modified_since (a unix timestamp)
        to fetch only games created or changed since then."""
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


class LastImportTimestampStore(ABC):
    """Outbound port: used to manage the last import timestamp."""

    @abstractmethod
    def get_last_import_timestamp(self) -> int | None:
        """Return the last import timestamp as a unix timestamp, or None if unset."""
        ...

    @abstractmethod
    def set_last_import_timestamp(self, timestamp: int) -> None:
        """Persist the last import timestamp (a unix timestamp)."""
        ...
