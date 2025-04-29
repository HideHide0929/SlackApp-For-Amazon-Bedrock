#
# Receive a request from Slack and register it in AWS SQS
#
# environmental variables:
#     SLACK_SIGNING_SECRET : Slack app secret
#     SQS_QUEUE_URL : AWS SQS URL
#     BOT_USER_ID : Slack Bot User ID
#     REQUEST_ALLOWED_SEC : Request allowed time (seconds)
# 
import json
import os
import boto3
import hmac
import logging
import time
import hashlib

# Log Settings
logging.basicConfig(level=logging.INFO)

def lambda_handler(event, context):
    # Get Environmental Variables
    SQS_QUEUE_URL = os.getenv('SQS_QUEUE_URL')
    SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
    BOT_USER_ID = os.getenv('BOT_USER_ID')
    REQUEST_ALLOWED_SEC = os.getenv('REQUEST_ALLOWED_SEC')

    # Checking environment variables
    if not SQS_QUEUE_URL:
        return out_env_error("SQS_QUEUE_URL")
    if not SLACK_SIGNING_SECRET:
        return out_env_error("SLACK_SIGNING_SECRET")
    if not BOT_USER_ID:
        return out_env_error("BOT_USER_ID")
    if not REQUEST_ALLOWED_SEC:
        return out_env_error("REQUEST_ALLOWED_SEC")

    # Request Validation
    headers = event.get("headers", {})
    body = event.get("body", "")
    body_json = json.loads(body)

    logging.debug(f"Header: {headers}.")
    logging.debug(f"Body: {body}.")

    # Slack challenge request response
    if "challenge" in body_json:
        return {
            "statusCode": 200,
            "body": json.dumps({"challenge": body_json["challenge"]})
        }

    # Verify Slack signature
    if not verify_slack_request(headers, body, SLACK_SIGNING_SECRET, REQUEST_ALLOWED_SEC):
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "Forbidden: Invalid signature"})
        }

    # Prevent retries in Slack
    if "x-slack-retry-num" in headers:
        logging.debug("Ignoring duplicate Slack request")
        return {"statusCode": 200, "body": json.dumps({"message": "Ignoring duplicate request"})}

    # Ignore the bot's own posts
    if 'bot_id' in body_json["event"]:
        return {"statusCode": 200, "body": json.dumps({"message": "Rejected because it was a message sent by a bot."})}
    if body_json["event"].get('user') == BOT_USER_ID:
        return {"statusCode": 200, "body": json.dumps({"message": "Rejected because it was a message sent by a bot."})}

    # Send a message to SQS
    sqs = boto3.client('sqs')
    try:
        response = sqs.send_message(QueueUrl=SQS_QUEUE_URL,MessageBody=body)
        logging.info(f"Message ID: {response['MessageId']} is successfully sent.")
        return {
            'statusCode': 202,
            'body': body
        }
    except Exception as e:
        logging.exception("An unexpected error occurred")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f"Internal server error: {str(e)}"})
        }

def verify_slack_request(headers, body, secret, allow_sec):
    """
    Verify Slack request signature

    Args:
        headers: Slack Request Header
        body: Slack Request Body
        secret: Slack Signing Seret
        allow_sec: Request Allowed Sec
    Return:
        boolean: True: OK, False: NG
    """
    timestamp = headers.get("x-slack-request-timestamp")
    # Requests made before the time limit are rejected
    if abs(time.time() - int(timestamp)) > int(allow_sec):
        return False

    slack_signature = headers.get("x-slack-signature")
    basestring = f"v0:{timestamp}:{body}"
    computed_signature = "v0=" + hmac.new(
        secret.encode(),
        basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_signature, slack_signature)

def out_env_error(env_name):
    """
    Error output when environment variables are not set.

    Args:
        env_name: Environment variable name
    Return:
        dict: {'statusCode': 500,'body':<Error String>}
    """
    err_str = f"The environment variable is not set: {env_name}"
    logging.error(err_str)
    return {
        'statusCode': 500,
        'body': json.dumps({'error': err_str})
    }
