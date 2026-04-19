from unittest.mock import patch, MagicMock
import json

from adapters.steam_http_client import SteamHttpClient


class TestSteamHttpClient:

    def test_builds_url_with_correct_params(self):
        response_body = json.dumps({
            "response": {"apps": [], "have_more_results": False}
        }).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("adapters.steam_http_client.urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            client = SteamHttpClient()
            client.get_app_list("my-api-key")

            url = mock_urlopen.call_args[0][0]
            assert "/IStoreService/GetAppList/v1/" in url
            assert "key=my-api-key" in url
            assert "include_dlc=false" in url
            assert "max_results=50000" in url

    def test_includes_last_appid_when_provided(self):
        response_body = json.dumps({
            "response": {"apps": [], "have_more_results": False}
        }).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("adapters.steam_http_client.urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            client = SteamHttpClient()
            client.get_app_list("key", last_appid=999)

            url = mock_urlopen.call_args[0][0]
            assert "last_appid=999" in url

    def test_omits_last_appid_when_none(self):
        response_body = json.dumps({
            "response": {"apps": [], "have_more_results": False}
        }).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("adapters.steam_http_client.urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            client = SteamHttpClient()
            client.get_app_list("key")

            url = mock_urlopen.call_args[0][0]
            assert "last_appid" not in url

    def test_returns_parsed_json(self):
        expected = {"response": {"apps": [{"appid": 1, "name": "X"}], "have_more_results": False}}
        response_body = json.dumps(expected).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("adapters.steam_http_client.urllib.request.urlopen", return_value=mock_response):
            client = SteamHttpClient()
            result = client.get_app_list("key")

        assert result == expected

