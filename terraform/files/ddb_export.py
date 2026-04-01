import boto3
import gzip
import json
import os

TABLE_NAME = os.environ["TABLE_NAME"]
EXPORT_BUCKET_NAME = os.environ["EXPORT_BUCKET_NAME"]
EXPORT_KEY = os.environ["EXPORT_KEY"]

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

    print(f"Exported {len(items)} items to s3://{EXPORT_BUCKET_NAME}/{EXPORT_KEY}")
    return {"statusCode": 200, "itemCount": len(items)}
