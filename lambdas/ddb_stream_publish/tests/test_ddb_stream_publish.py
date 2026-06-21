import json
import os
import pytest
from unittest.mock import MagicMock, patch

# Both env var and boto3.client must be in place before the module is imported,
# because TOPIC_ARN is read at module level and boto3.client("sns") is called
# at module level (Lambda best-practice: initialise clients outside the handler).
os.environ.setdefault("TOPIC_ARN", "arn:aws:sns:eu-west-2:123456789012:new-game-items")

with patch("boto3.client", return_value=MagicMock()):
    import ddb_stream_publish  # noqa: E402

TOPIC_ARN = os.environ["TOPIC_ARN"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def dynamo_image(**kwargs) -> dict:
    """Return a DynamoDB-typed image built from plain str->str pairs."""
    return {k: {"S": v} for k, v in kwargs.items()}


def make_insert_record(event_id: str = "evt-1", **image_fields) -> dict:
    return {
        "eventID": event_id,
        "eventName": "INSERT",
        "dynamodb": {
            "NewImage": dynamo_image(**image_fields),
        },
    }


def make_record_no_new_image(event_id: str = "evt-del", event_name: str = "REMOVE") -> dict:
    return {
        "eventID": event_id,
        "eventName": event_name,
        "dynamodb": {},
    }


# ---------------------------------------------------------------------------
# deserialize
# ---------------------------------------------------------------------------

class TestDeserialize:

    def test_string_fields_are_deserialized(self):
        result = ddb_stream_publish.deserialize(
            {"game_id": {"S": "abc-123"}, "game_title": {"S": "Portal"}}
        )
        assert result == {"game_id": "abc-123", "game_title": "Portal"}

    def test_empty_image_returns_empty_dict(self):
        assert ddb_stream_publish.deserialize({}) == {}


# ---------------------------------------------------------------------------
# createGameEvent
# ---------------------------------------------------------------------------

class TestCreateGameEvent:

    def test_returns_correct_structure_for_insert(self):
        record = make_insert_record("evt-1", game_id="abc-123", game_title="Portal")
        event = ddb_stream_publish.create_game_event(record)

        assert event["event_id"] == "evt-1"
        assert event["event_name"] == "INSERT"
        assert "event_timestamp" in event
        assert event["game_data"] == {"game_id": "abc-123", "game_title": "Portal"}

    def test_game_data_contains_all_image_fields(self):
        record = make_insert_record(
            "evt-2",
            game_id="def-456",
            game_title="Half-Life",
            steam_game_id="70",
        )
        event = ddb_stream_publish.create_game_event(record)

        assert event["game_data"]["steam_game_id"] == "70"

    def test_raises_value_error_when_no_new_image(self):
        record = make_record_no_new_image("evt-del", "REMOVE")
        with pytest.raises(ValueError, match="No NewImage found in record evt-del"):
            ddb_stream_publish.create_game_event(record)

    def test_raises_value_error_includes_event_name(self):
        record = make_record_no_new_image("evt-mod", "MODIFY")
        with pytest.raises(ValueError, match="MODIFY"):
            ddb_stream_publish.create_game_event(record)


# ---------------------------------------------------------------------------
# lambda_handler
# ---------------------------------------------------------------------------

class TestLambdaHandler:

    @pytest.fixture(autouse=True)
    def mock_sns(self, monkeypatch):
        """Replace the module-level sns client with a MagicMock for every test."""
        self.sns_client = MagicMock()
        self.sns_client.publish_batch.return_value = {"Successful": [], "Failed": []}
        monkeypatch.setattr(ddb_stream_publish, "sns", self.sns_client)

    # --- Happy path ---

    def test_single_insert_is_published(self):
        event = {"Records": [make_insert_record("evt-1", game_id="abc", game_title="Portal")]}
        ddb_stream_publish.lambda_handler(event, None)

        self.sns_client.publish_batch.assert_called_once()
        entries = self.sns_client.publish_batch.call_args.kwargs["PublishBatchRequestEntries"]
        assert len(entries) == 1
        assert entries[0]["Subject"] == "new_game_item"

    def test_topic_arn_is_passed_correctly(self):
        event = {"Records": [make_insert_record("evt-1", game_id="abc", game_title="Portal")]}
        ddb_stream_publish.lambda_handler(event, None)

        assert self.sns_client.publish_batch.call_args.kwargs["TopicArn"] == TOPIC_ARN

    def test_message_is_valid_json_with_expected_fields(self):
        event = {"Records": [make_insert_record("evt-1", game_id="abc", game_title="Portal")]}
        ddb_stream_publish.lambda_handler(event, None)

        entry = self.sns_client.publish_batch.call_args.kwargs["PublishBatchRequestEntries"][0]
        message = json.loads(entry["Message"])

        assert message["event_id"] == "evt-1"
        assert message["event_name"] == "INSERT"
        assert "event_timestamp" in message
        assert message["game_data"] == {"game_id": "abc", "game_title": "Portal"}

    def test_each_entry_has_unique_id(self):
        records = [
            make_insert_record("evt-1", game_id="a", game_title="Game A"),
            make_insert_record("evt-2", game_id="b", game_title="Game B"),
        ]
        event = {"Records": records}
        ddb_stream_publish.lambda_handler(event, None)

        entries = self.sns_client.publish_batch.call_args.kwargs["PublishBatchRequestEntries"]
        ids = [e["Id"] for e in entries]
        assert len(ids) == len(set(ids)), "Entry IDs should be unique"

    # --- Skipping ---

    def test_records_without_new_image_are_skipped(self):
        event = {"Records": [make_record_no_new_image("evt-del", "REMOVE")]}
        ddb_stream_publish.lambda_handler(event, None)

        self.sns_client.publish_batch.assert_not_called()

    def test_empty_records_list_does_not_call_publish(self):
        ddb_stream_publish.lambda_handler({"Records": []}, None)
        self.sns_client.publish_batch.assert_not_called()

    def test_mixed_records_only_valid_ones_are_published(self):
        records = [
            make_insert_record("evt-1", game_id="a", game_title="Game A"),
            make_record_no_new_image("evt-2", "REMOVE"),
            make_insert_record("evt-3", game_id="c", game_title="Game C"),
        ]
        ddb_stream_publish.lambda_handler({"Records": records}, None)

        entries = self.sns_client.publish_batch.call_args.kwargs["PublishBatchRequestEntries"]
        assert len(entries) == 2

    def test_all_records_skipped_means_no_publish(self):
        records = [
            make_record_no_new_image("evt-1", "REMOVE"),
            make_record_no_new_image("evt-2", "REMOVE"),
        ]
        ddb_stream_publish.lambda_handler({"Records": records}, None)
        self.sns_client.publish_batch.assert_not_called()

    # --- Chunking ---

    def test_exactly_10_records_produces_one_batch(self):
        records = [make_insert_record(f"evt-{i}", game_id=str(i), game_title=f"Game {i}") for i in range(10)]
        ddb_stream_publish.lambda_handler({"Records": records}, None)

        assert self.sns_client.publish_batch.call_count == 1
        entries = self.sns_client.publish_batch.call_args.kwargs["PublishBatchRequestEntries"]
        assert len(entries) == 10

    def test_11_records_produces_two_batches(self):
        records = [make_insert_record(f"evt-{i}", game_id=str(i), game_title=f"Game {i}") for i in range(11)]
        ddb_stream_publish.lambda_handler({"Records": records}, None)

        assert self.sns_client.publish_batch.call_count == 2
        batch_sizes = [
            len(c.kwargs["PublishBatchRequestEntries"])
            for c in self.sns_client.publish_batch.call_args_list
        ]
        assert batch_sizes == [10, 1]

    def test_25_records_produces_three_batches_of_10_10_5(self):
        records = [make_insert_record(f"evt-{i}", game_id=str(i), game_title=f"Game {i}") for i in range(25)]
        ddb_stream_publish.lambda_handler({"Records": records}, None)

        assert self.sns_client.publish_batch.call_count == 3
        batch_sizes = [
            len(c.kwargs["PublishBatchRequestEntries"])
            for c in self.sns_client.publish_batch.call_args_list
        ]
        assert batch_sizes == [10, 10, 5]

    # --- SNS partial failure ---

    def test_partial_sns_failure_raises_runtime_error(self):
        self.sns_client.publish_batch.return_value = {
            "Successful": [],
            "Failed": [{"Id": "some-id", "Code": "InternalError", "Message": "oops"}],
        }
        event = {"Records": [make_insert_record("evt-1", game_id="abc", game_title="Portal")]}

        with pytest.raises(RuntimeError, match="1 of 1 events failed to publish to SNS"):
            ddb_stream_publish.lambda_handler(event, None)

    def test_partial_failure_error_includes_counts(self):
        self.sns_client.publish_batch.return_value = {
            "Successful": [{"Id": "ok-id"}],
            "Failed": [
                {"Id": "bad-1", "Code": "InternalError", "Message": "oops"},
                {"Id": "bad-2", "Code": "InternalError", "Message": "oops again"},
            ],
        }
        records = [make_insert_record(f"evt-{i}", game_id=str(i), game_title=f"Game {i}") for i in range(3)]

        with pytest.raises(RuntimeError, match="2 of 3 events failed to publish to SNS"):
            ddb_stream_publish.lambda_handler({"Records": records}, None)

