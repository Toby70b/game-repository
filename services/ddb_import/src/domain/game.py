from dataclasses import dataclass


@dataclass(frozen=True)
class Game:
    """Core domain model. Contains only what the domain cares about."""
    steam_game_id: str
    game_title: str

