import logging

from domain.game import Game
from ports import ImportGamesUseCase, GameSource, GameRepository

logger = logging.getLogger(__name__)


class GameImportService(ImportGamesUseCase):

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
        existing_ids = self._repo.retrieve_existing_steam_ids()
        last_appid = max((int(sid) for sid in existing_ids), default=None)

        total_fetched = 0
        total_skipped = 0
        total_written = 0
        pending: list[Game] = []
        inserted_games: list[Game] = []

        for game in self._source.fetch_games(last_appid=last_appid):
            total_fetched += 1

            if game.steam_game_id in existing_ids:
                total_skipped += 1
                continue

            pending.append(game)

            if len(pending) >= self._batch_size:
                total_written += self.persist_games(pending, inserted_games)
                pending.clear()

        total_written += self.persist_games(pending, inserted_games)

        summary = {
            "total games fetched from Steam": total_fetched,
            "total games skipped due to already existing in persistence": total_skipped,
            "total games written to persistence": total_written,
        }
        logger.info("Import complete: %s", summary)
        return summary

    def persist_games(self, batch: list[Game], inserted_games: list[Game]) -> int:
        if not batch:
            return 0
        persisted = self._repo.persist_games(batch)
        inserted_games.extend(persisted)
        logger.info("Flushed batch of %d item(s) to DynamoDB", len(persisted))
        return len(persisted)
