import logging

from domain.game import Game
from ports import ImportGamesUseCase, GameSource, GameRepository

logger = logging.getLogger(__name__)


class GameImportService(ImportGamesUseCase):
    """
    Application service — implements the inbound port and orchestrates the
    outbound ports. Contains no knowledge of Lambda, HTTP, or DynamoDB.
    """

    def __init__(
        self,
        source: GameSource,
        repo: GameRepository,
        batch_size: int = 25,
    ) -> None:
        self._source = source
        self._repo = repo
        self._batch_size = batch_size

    def import_games(self) -> dict:
        existing_ids = self._repo.load_existing_steam_ids()

        total_fetched = 0
        total_skipped = 0
        total_written = 0
        pending: list[Game] = []

        for game in self._source.fetch_games():
            total_fetched += 1

            if game.steam_game_id in existing_ids:
                total_skipped += 1
                continue

            pending.append(game)

            if len(pending) >= self._batch_size:
                total_written += self._flush(pending)
                pending.clear()

        total_written += self._flush(pending)

        summary = {
            "statusCode": 200,
            "totalFetched": total_fetched,
            "totalSkipped": total_skipped,
            "totalWritten": total_written,
        }
        logger.info("Import complete: %s", summary)
        return summary

    def _flush(self, batch: list[Game]) -> int:
        if not batch:
            return 0
        written = self._repo.put_batch(batch)
        logger.info("Flushed batch of %d item(s) to DynamoDB", written)
        return written

