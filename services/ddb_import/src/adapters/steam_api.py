import urllib.request
import urllib.error
import json
import logging
from typing import Iterator

from domain.game import Game
from ports import GameSource

logger = logging.getLogger(__name__)

# Public Steam API — no auth required.
# Returns {"applist": {"apps": [{"appid": 123, "name": "..."}, ...]}}
STEAM_APP_LIST_URL = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"


class SteamApiAdapter(GameSource):
    """Outbound adapter: fetches the full Steam catalogue and yields Game objects."""

    def __init__(self, url: str = STEAM_APP_LIST_URL) -> None:
        self._url = url

    def fetch_games(self) -> Iterator[Game]:
        logger.info("Fetching Steam app list from %s", self._url)

        with urllib.request.urlopen(self._url, timeout=30) as response:
            raw = response.read()

        data = json.loads(raw)
        apps: list[dict] = data["applist"]["apps"]

        logger.info("Received %d apps from Steam", len(apps))

        for app in apps:
            app_id = app.get("appid")
            name = (app.get("name") or "").strip()

            # Skip entries with no usable name
            if not app_id or not name:
                continue

            yield Game(steam_game_id=str(app_id), title=name)

