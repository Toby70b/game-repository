import logging

from domain.game import Game
from ports import ImportGamesUseCase, GameSource, GameRepository

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100


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
        total_persisted = 0
        batch: list[Game] = []

        for game in self._source.fetch_games(last_appid=last_appid):
            total_fetched += 1
            if game.steam_game_id not in existing_ids:
                batch.append(game)

            if len(batch) >= _BATCH_SIZE:
                persisted = self._repo.persist_games(list(batch))
                total_persisted += len(persisted)
                logger.info("Flushed batch of %d games (%d persisted so far)", len(batch), total_persisted)
                batch.clear()

        # Flush any remaining games that didn't fill a full batch
        if batch:
            persisted = self._repo.persist_games(batch)
            total_persisted += len(persisted)

        summary = {
            "total games fetched from Steam": total_fetched,
            "total games written to persistence": total_persisted,
        }
        logger.info("Import complete: %s", summary)
        return summary
