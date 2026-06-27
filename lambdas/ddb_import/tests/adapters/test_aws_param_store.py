from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from adapters.aws_param_store import AwsParamStore


def _store() -> AwsParamStore:
    # Bypass __init__ (no boto/env needed) and inject a stubbed SSM client.
    store = AwsParamStore.__new__(AwsParamStore)
    store._param_name = "/test/last-import"
    store._ssm = MagicMock()
    return store


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, "GetParameter")


class TestAwsParamStore:

    def test_get_returns_stored_timestamp(self):
        store = _store()
        store._ssm.get_parameter.return_value = {"Parameter": {"Value": "1719446400"}}

        assert store.get_last_import_timestamp() == 1719446400
        store._ssm.get_parameter.assert_called_once_with(Name="/test/last-import")

    def test_get_returns_none_when_param_missing(self):
        store = _store()
        store._ssm.get_parameter.side_effect = _client_error("ParameterNotFound")

        assert store.get_last_import_timestamp() is None

    def test_get_propagates_unexpected_errors(self):
        store = _store()
        store._ssm.get_parameter.side_effect = _client_error("AccessDeniedException")

        with pytest.raises(ClientError):
            store.get_last_import_timestamp()

    def test_set_writes_overwritable_string_param(self):
        store = _store()

        store.set_last_import_timestamp(1719446400)

        store._ssm.put_parameter.assert_called_once_with(
            Name="/test/last-import",
            Value="1719446400",
            Type="String",
            Overwrite=True,
        )

    def test_set_does_not_raise_on_success(self):
        store = _store()

        # A successful put must return normally — it should not re-raise.
        store.set_last_import_timestamp(1719446400)
