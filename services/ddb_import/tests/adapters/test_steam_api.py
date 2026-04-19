from unittest.mock import patch, MagicMock

from domain.game import Game
from adapters.steam_api import SteamApiAdapter


def _build_adapter(http_client):
    """Build a SteamApiAdapter with SSM stubbed out and a custom http client."""
    with patch("adapters.steam_api.boto3") as mock_boto:
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "fake-key"}}
        mock_boto.client.return_value = mock_ssm

        with patch.dict("os.environ", {"STEAM_API_KEY_PARAM": "/test/key"}):
            adapter = SteamApiAdapter()

    adapter._http = http_client
    return adapter


class TestSteamApiAdapter:

    def test_single_page_yields_games(self):
        http = MagicMock()
        http.get_app_list.return_value = {
            "response": {
                "apps": [
                    {"appid": 10, "name": "Game A"},
                    {"appid": 20, "name": "Game B"},
                ],
                "have_more_results": False,
            }
        }

        adapter = _build_adapter(http)
        games = list(adapter.fetch_games())

        assert games == [
            Game(steam_game_id="10", game_title="Game A"),
            Game(steam_game_id="20", game_title="Game B"),
        ]
        http.get_app_list.assert_called_once_with("fake-key", last_appid=None)

    def test_multi_page_pagination(self):
        http = MagicMock()
        http.get_app_list.side_effect = [
            {
                "response": {
                    "apps": [{"appid": 10, "name": "Game A"}],
                    "have_more_results": True,
                    "last_appid": 10,
                }
            },
            {
                "response": {
                    "apps": [{"appid": 20, "name": "Game B"}],
                    "have_more_results": False,
                }
            },
        ]

        adapter = _build_adapter(http)
        games = list(adapter.fetch_games())

        assert len(games) == 2
        assert http.get_app_list.call_count == 2
        http.get_app_list.assert_any_call("fake-key", last_appid=None)
        http.get_app_list.assert_any_call("fake-key", last_appid=10)

    def test_skips_apps_without_name(self):
        http = MagicMock()
        http.get_app_list.return_value = {
            "response": {
                "apps": [
                    {"appid": 10, "name": ""},
                    {"appid": 20, "name": "  "},
                    {"appid": 30, "name": "Valid"},
                ],
                "have_more_results": False,
            }
        }

        adapter = _build_adapter(http)
        games = list(adapter.fetch_games())

        assert games == [Game(steam_game_id="30", game_title="Valid")]

    def test_skips_apps_without_appid(self):
        http = MagicMock()
        http.get_app_list.return_value = {
            "response": {
                "apps": [
                    {"name": "No ID"},
                    {"appid": 10, "name": "Has ID"},
                ],
                "have_more_results": False,
            }
        }

        adapter = _build_adapter(http)
        games = list(adapter.fetch_games())

        assert games == [Game(steam_game_id="10", game_title="Has ID")]

    def test_passes_last_appid_cursor(self):
        http = MagicMock()
        http.get_app_list.return_value = {
            "response": {"apps": [], "have_more_results": False}
        }

        adapter = _build_adapter(http)
        list(adapter.fetch_games(last_appid=500))

        http.get_app_list.assert_called_once_with("fake-key", last_appid=500)

    def test_empty_response(self):
        http = MagicMock()
        http.get_app_list.return_value = {"response": {}}

        adapter = _build_adapter(http)
        games = list(adapter.fetch_games())

        assert games == []

