import json
from datetime import datetime, timezone
import os
import logging
import uuid

import boto3
from boto3.dynamodb.types import TypeDeserializer

sns = boto3.client("sns")
deserializer = TypeDeserializer()
TOPIC_ARN = os.environ.get("TOPIC_ARN")
if not TOPIC_ARN:
    raise EnvironmentError("Missing required environment variable: TOPIC_ARN")
NEW_GAME_ITEM_EVENT_SUBJECT = "new_game_item"
SNS_BATCH_SIZE_LIMIT = 10

logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)


def deserialize(dynamo_obj: dict) -> dict:
    return {k: deserializer.deserialize(v) for k, v in dynamo_obj.items()}


def create_game_event(record: dict) -> dict:
    event_id = record['eventID']
    event_name = record['eventName']
    current_timestamp = datetime.now(timezone.utc).isoformat()
    if "NewImage" not in record["dynamodb"]:
        raise ValueError(f"No NewImage found in record {event_id} — cannot process {event_name} event.")

    new_image = deserialize(record["dynamodb"]["NewImage"])

    game_event = {
        'event_id': event_id,
        'event_name': event_name,
        'event_timestamp': current_timestamp,
        'game_data' : new_image
    }
    return game_event

def lambda_handler(event, context):
    records = event['Records']
    logger.info('Received {} records from DynamoDB stream.'.format(len(records)))
    record_chunks = [records[i:i + SNS_BATCH_SIZE_LIMIT] for i in range(0, len(records), SNS_BATCH_SIZE_LIMIT)]
    logger.debug('Splitting records into {} chunks of size {}'.format(len(record_chunks), SNS_BATCH_SIZE_LIMIT))

    for chunk in record_chunks:
        new_game_item_event_publish_entries = []
        for record in chunk:
            logger.info(record['eventID'])
            logger.info(record['eventName'])
            logger.info("DynamoDB Record: " + json.dumps(record['dynamodb'], indent=2))

            try:
                game_event = create_game_event(record)
            except ValueError as e:
                # In the future, we can DLQ but skip for now...
                logger.warning(f"Error deserializing record {record['eventID']} it will not be published: {e}")
                continue

            logger.debug("Creating batch entry for game event: " + json.dumps(game_event, indent=2))

            game_event_publish_entry = {
                'Id': str(uuid.uuid4()),
                'Message': json.dumps(game_event),
                'Subject': NEW_GAME_ITEM_EVENT_SUBJECT
            }

            new_game_item_event_publish_entries.append(game_event_publish_entry)

        if new_game_item_event_publish_entries:
            response = sns.publish_batch(
                TopicArn=TOPIC_ARN,
                PublishBatchRequestEntries=new_game_item_event_publish_entries
            )
            failed = response.get("Failed", [])
            if failed:
                for failure in failed:
                    logger.error(
                        "Failed to publish event Id=%s — Code=%s Message=%s",
                        failure.get("Id"),
                        failure.get("Code"),
                        failure.get("Message"),
                    )
                raise RuntimeError(
                    f"{len(failed)} of {len(new_game_item_event_publish_entries)} events failed to publish to SNS."
                )
            logger.info('Successfully published batch of {} events to SNS'.format(len(new_game_item_event_publish_entries)))
        else:
            logger.info('No publishable events in this chunk — skipping SNS publish')
    logger.info('Successfully processed {} records.'.format(len(records)))
