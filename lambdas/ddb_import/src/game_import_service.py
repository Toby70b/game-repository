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
        existing = self._repo.existing_titles()
        last_appid = max((int(sid) for sid in existing), default=None)

        total_fetched = 0
        total_written = 0
        batch: list[Game] = []

        for game in self._source.fetch_games(last_appid=last_appid):
            total_fetched += 1

            # Write only games that are new or whose title has changed.
            if existing.get(game.steam_game_id) == game.game_title:
                continue
            batch.append(game)

            if len(batch) >= _BATCH_SIZE:
                written = self._repo.upsert_games(list(batch))
                total_written += len(written)
                logger.info("Flushed batch of %d games (%d written so far)", len(written), total_written)
                batch.clear()

        # Flush any remaining games that didn't fill a full batch
        if batch:
            written = self._repo.upsert_games(batch)
            total_written += len(written)

        summary = {
            "total games fetched from Steam": total_fetched,
            "total games written to persistence": total_written,
        }
        logger.info("Import complete: %s", summary)
        return summary
