import logging

from domain.game import Game
from ports import ImportGamesUseCase, GameSource, GameRepository

logger = logging.getLogger(__name__)


class GameImportService(ImportGamesUseCase):

    def __init__(
            self,
            source: GameSource,
            repo: GameRepository,
    ) -> None:
        self._source = source
        self._repo = repo

    def import_games(self) -> dict:
        existing_ids = self._repo.retrieve_existing_steam_ids()
        last_appid = max((int(sid) for sid in existing_ids), default=None)

        total_fetched = 0
        new_games_to_persist: list[Game] = []

        for game in self._source.fetch_games(last_appid=last_appid):
            total_fetched += 1

            if game.steam_game_id not in existing_ids:
                new_games_to_persist.append(game)
            else:
                logger.warning(
                    "Game with Steam ID %s retrieved but has already been persisted. This might indicate an error "
                    "with the Steam API request, specifically with the last_appid param",
                    game.steam_game_id)

        persisted = self._repo.persist_games(new_games_to_persist)

        summary = {
            "total games fetched from Steam": total_fetched,
            "total games written to persistence": len(persisted),
        }
        logger.info("Import complete: %s", summary)
        return summary
