from abc import ABC, abstractmethod
from typing import Iterator
from domain.game import Game


# ---------------------------------------------------------------------------
# Inbound port (driven by the outside world e.g. a Lambda event)
# ---------------------------------------------------------------------------

class ImportGamesUseCase(ABC):
    """Inbound port: the single operation this application exposes."""

    @abstractmethod
    def import_games(self) -> dict:
        """Run a full import cycle. Returns a summary dict."""
        ...


# ---------------------------------------------------------------------------
# Outbound ports (the application drives these)
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
    def retrieve_existing_steam_ids(self) -> set[str]:
        """Return the set of all steam_game_ids already existing within the repository."""
        ...

    @abstractmethod
    def put_batch(self, games: list[Game]) -> int:
        """Write a batch of new games. Returns the number of items written."""
        ...

