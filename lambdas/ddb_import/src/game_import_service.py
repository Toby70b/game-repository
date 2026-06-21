import logging

from domain.game import Game
from ports import ImportGamesUseCase, GameSource, GameRepository, LastImportTimestampStore
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100


class GameImportService(ImportGamesUseCase):

    def __init__(
            self,
            source: GameSource,
            repo: GameRepository,
            timestamp_store: LastImportTimestampStore,
    ) -> None:
        self._source = source
        self._repo = repo
        self._timestamp_store = timestamp_store

    def import_games(self) -> dict:
        existing = self._repo.existing_titles()

        last_appid = max((int(sid) for sid in existing), default=None)

        total_fetched = 0
        total_written = 0
        batch: list[Game] = []

        for game in self._source.fetch_games(last_appid=last_appid):
            total_fetched += 1

            if existing.get(game.steam_game_id) == game.game_title:
                continue
            batch.append(game)

            if len(batch) >= _BATCH_SIZE:
                written = self._repo.upsert_games(list(batch))
                total_written += len(written)
                logger.info("Flushed batch of %d games (%d written so far)", len(written), total_written)
                batch.clear()

        if batch:
            written = self._repo.upsert_games(batch)
            total_written += len(written)

        self.__update_last_modified_timestamp()

        summary = {
            "total games fetched from Steam": total_fetched,
            "total games written to persistence": total_written,
        }
        logger.info("Import complete: %s", summary)

        return summary

    def __update_last_modified_timestamp(self) -> None:
        new_timestamp = int(datetime.now(timezone.utc).timestamp())
        logger.info("Updating last modified timestamp param to %d", new_timestamp)
        self._timestamp_store.set_last_timestamp(new_timestamp)
