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
        total_skipped = 0
        pending: list[Game] = []

        for game in self._source.fetch_games(last_appid=last_appid):
            total_fetched += 1

            if game.steam_game_id in existing_ids:
                total_skipped += 1
                continue

            pending.append(game)

        persisted = self._repo.persist_games(pending)

        summary = {
            "total games fetched from Steam": total_fetched,
            "total games skipped due to already existing in persistence": total_skipped,
            "total games written to persistence": len(persisted),
        }
        logger.info("Import complete: %s", summary)
        return summary
