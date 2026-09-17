"""Publishes scan job messages to the SQS scan queue."""

import json
import os

import boto3

QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")

_sqs = boto3.client("sqs")


def enqueue_scan(scan_id: str, image_name: str, user_id: str) -> str:
    """Send a scan job to SQS. Returns the SQS message ID."""
    message = {
        "scan_id": scan_id,
        "image_name": image_name,
        "user_id": user_id,
    }
    response = _sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(message),
    )
    return response["MessageId"]
