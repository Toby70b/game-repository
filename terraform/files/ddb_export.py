import boto3
import gzip
import json
import logging
import os

TABLE_NAME = os.environ["TABLE_NAME"]
EXPORT_BUCKET_NAME = os.environ["EXPORT_BUCKET_NAME"]
EXPORT_KEY = os.environ["EXPORT_KEY"]

logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)

ddb = boto3.client("dynamodb")
s3 = boto3.client("s3")


def handler(event, context):
    items = []
    paginator = ddb.get_paginator("scan")

    for page in paginator.paginate(TableName=TABLE_NAME):
        items.extend(page["Items"])

    # One DynamoDB JSON item per line (NDJSON)
    ndjson = "\n".join(json.dumps({"Item": item}) for item in items)
    compressed = gzip.compress(ndjson.encode("utf-8"))

    s3.put_object(
        Bucket=EXPORT_BUCKET_NAME,
        Key=EXPORT_KEY,
        Body=compressed,
        ContentEncoding="gzip",
        ContentType="application/json",
    )

    logger.info("Exported %d items to s3://%s/%s", len(items), EXPORT_BUCKET_NAME, EXPORT_KEY)
    return {"itemCount": len(items)}
