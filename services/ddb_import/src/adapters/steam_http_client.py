import json
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
_MAX_RESULTS = 50000


class SteamHttpClient:
    """
    Responsible solely for building and sending requests to the Steam
    IStoreService/GetAppList endpoint. Returns the raw parsed JSON response.
    """

    def get_app_list(self, api_key: str, last_appid: int | None = None) -> dict:
        params: dict[str, str | int] = {
            "key": api_key,
            "include_dlc": "false",
            "include_software": "false",
            "include_videos": "false",
            "include_hardware": "false",
            "max_results": _MAX_RESULTS,
        }

        if last_appid is not None:
            params["last_appid"] = last_appid

        url = f"{_BASE_URL}?{urllib.parse.urlencode(params)}"

        # Don't log the api key
        redacted_url = url.replace(api_key, "***")
        logger.info("GET %s", redacted_url)

        with urllib.request.urlopen(url, timeout=30) as http_response:
            body = http_response.read()

        data = json.loads(body)
        payload = data.get("response", {})

        self.log_req_resp(redacted_url, payload)

        return data

    def log_req_resp(self, redacted_url: str, payload):
        logger.info(
            "GET %s — apps: %d, have_more_results: %s, last_appid: %s",
            redacted_url,
            len(payload.get("apps", [])),
            payload.get("have_more_results"),
            payload.get("last_appid"),
        )

