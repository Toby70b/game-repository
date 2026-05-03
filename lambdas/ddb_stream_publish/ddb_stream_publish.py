import json
from datetime import datetime, timezone
import os
import boto3
import logging
from boto3.dynamodb.types import TypeDeserializer

sns = boto3.client("sns")
deserializer = TypeDeserializer()
TOPIC_ARN = os.environ["TOPIC_ARN"]

sns = boto3.client("sns")
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)


def deserialize(dynamo_obj: dict) -> dict:
    return {k: deserializer.deserialize(v) for k, v in dynamo_obj.items()}


def createGameEvent(record: dict) -> dict:
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
    for record in event['Records']:
        logger.info(record['eventID'])
        logger.info(record['eventName'])
        logger.info("DynamoDB Record: " + json.dumps(record['dynamodb'], indent=2))

        game_event = createGameEvent(record)

        logger.info("Publishing game event to SNS: " + json.dumps(game_event, indent=2))

        sns.publish(
            TopicArn=TOPIC_ARN,
            Message=json.dumps(game_event),
            Subject="new game event"
        )

        logger.info(f"Successfully published game event {game_event['event_id']} to SNS")
    logger.info('Successfully processed {} records.'.format(len(event['Records'])))
