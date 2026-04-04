import logging
import os
from typing import Iterator

import boto3

from adapters.steam_http_client import SteamHttpClient
from domain.game import Game
from ports import GameSource

logger = logging.getLogger(__name__)


class SteamApiAdapter(GameSource):
    """
    Outbound adapter: retrieves the Steam API key from SSM, delegates HTTP
    requests to SteamHttpClient, and maps responses to Game objects.
    """

    def __init__(self) -> None:
        param_name = os.environ["STEAM_API_KEY_PARAM"]
        ssm = boto3.client("ssm")
        self._api_key = self.retrieve_api_key(param_name, ssm)
        self._http = SteamHttpClient()

    def retrieve_api_key(self, param_name: str, ssm) -> str:
        try:
            response = ssm.get_parameter(Name=param_name, WithDecryption=True)
            api_key = response["Parameter"]["Value"]
            return api_key
        except Exception as e:
            logger.error(f"Failed to retrieve Steam API key from SSM parameter '{param_name}': {e}")
            raise RuntimeError(f"Could not retrieve Steam API key from SSM parameter '{param_name}'") from e

    def fetch_games(self, last_appid: int | None = None) -> Iterator[Game]:
        cursor = last_appid
        page = 0
        have_more_results = True


        while have_more_results:
            page += 1
            data = self._http.get_app_list(self._api_key, last_appid=cursor)
            response = data.get("response", {})
            apps: list[dict] = response.get("apps", [])

            logger.info("Page %d: received %d apps from Steam", page, len(apps))

            for app in apps:
                app_id = app.get("appid")
                name = (app.get("name") or "").strip()

                if not app_id or not name:
                    continue

                yield Game(steam_game_id=str(app_id), title=name)

            if not response.get("have_more_results"):
                have_more_results = False
            cursor = response.get("last_appid")
