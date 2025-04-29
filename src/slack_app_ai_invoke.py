#
# Called from AWS SQS and runs generative AI on AWS Bedrock
# Use Dynamo DB to handle retransmissions in AWS SQS
#
# environmental variables:
#     BEDROCK_MODEL_ID : 利用するLLMモデル
#     SLACK_BOT_TOKEN : Slack app token
#     DYNAMO_DB_TABLE : Dynamo DB Table name
#     DYNAMO_DB_KEY_ITEM : Dynamo DB Key Item
#     DYNAMO_DB_TTL_ITEM : Dynamo DB TTL Item
#     DYNAMO_DB_TTL : date of expiry
# 
import os
import boto3
import urllib3
import logging
import json
import re
import time

# Log Settings
logging.basicConfig(level=logging.INFO)

http = urllib3.PoolManager()
bedrock = boto3.client("bedrock-runtime", region_name="ap-northeast-1")
dynamodb = boto3.client('dynamodb')
bedrock = boto3.client("bedrock-runtime", region_name="ap-northeast-1")

def lambda_handler(event, context):
    # Get Environmental Variables
    BEDROCK_MODEL_ID = os.getenv('BEDROCK_MODEL_ID')
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    DYNAMO_DB_TABLE = os.getenv('DYNAMO_DB_TABLE')
    DYNAMO_DB_KEY_ITEM = os.getenv('DYNAMO_DB_KEY_ITEM')
    DYNAMO_DB_TTL_ITEM = os.getenv('DYNAMO_DB_TTL_ITEM')
    DYNAMO_DB_TTL = os.getenv('DYNAMO_DB_TTL')

    # Checking environment variables
    if not BEDROCK_MODEL_ID:
        return out_env_error("BEDROCK_MODEL_ID")
    if not SLACK_BOT_TOKEN:
        return out_env_error("SLACK_BOT_TOKEN")
    if not DYNAMO_DB_TABLE:
        return out_env_error("DYNAMO_DB_TABLE")
    if not DYNAMO_DB_KEY_ITEM:
        return out_env_error("DYNAMO_DB_KEY_ITEM")
    if not DYNAMO_DB_TTL_ITEM:
        return out_env_error("DYNAMO_DB_TTL_ITEM")
    try:
        DYNAMO_DB_TTL = int(DYNAMO_DB_TTL)
    except ValueError:
        return out_env_error("DYNAMO_DB_TTL")

    # Pulling information from an AWS SQS queue
    slack_url = "https://slack.com/api/chat.postMessage"
    for record in event["Records"]:
        message_id = record["messageId"]
        if is_duplicate_message(message_id, DYNAMO_DB_TABLE, DYNAMO_DB_KEY_ITEM):
            logging.debug(f"Message duplicate: {message_id}")
            continue
        push_to_dynamoDB(message_id, DYNAMO_DB_TABLE, DYNAMO_DB_KEY_ITEM, DYNAMO_DB_TTL_ITEM, DYNAMO_DB_TTL)
        body = json.loads(record["body"])
        if "event" in body and "text" in body["event"]:
            exec_message(body,SLACK_BOT_TOKEN,slack_url,BEDROCK_MODEL_ID)
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Success."})
    }

def exec_message(body,slack_token,slack_url,model_id):
    """
    Process the message

    Args:
        body: Slack Request Body
        slack_token: Slack app token
        slack_url: Slack Chat Message Post API URL
    Return:
    
    """
    channel = body["event"]["channel"]
    thread_ts = body["event"].get("thread_ts", body["event"].get("ts"))
    user_id = body["event"].get("user")

    logging.debug(f"Channel:{channel},Thread TS:{thread_ts},User ID:{user_id}")

    # Get messages in a thread
    thread_messages = get_thread_messages(channel, thread_ts, slack_token)
    logging.debug(f"Thread Messages: {thread_messages}")

    # Prompt with thread content
    prompt = remove_mentions(thread_messages)
    logging.debug(f"Prompt: {prompt}")

    # Ask the generating AI (send all messages in the thread)
    ai_response = query_bedrock(prompt,model_id)
    logging.debug(f"AI Response: {ai_response}")

    logging.info(f"User ID: {user_id}, Prompt: {prompt}, AI Response: {ai_response}.")

    # Replying to a message in Slack
    res_body = json.dumps({
        "channel": channel,
        "text": f"AI Response:\n{ai_response}\nAI Response end.",
        "thread_ts": thread_ts  # Reply in thread
    })
    logging.info(f"Response Body: {res_body}")


    try:
        response = http.request(
            "POST", slack_url,
            headers={
                "Authorization": f"Bearer {slack_token}",
                "Content-Type": "application/json"
            },
            body=res_body
        )
        if response.status !=200:
            logging.error(f"Slack API Error: {response.data}")
    except Exception as e:
        logging.exception("Slack Send Error")

def get_thread_messages(channel, thread_ts, slack_token):
    """
    Get all messages in a thread
    Args:
        channel: Slack Channel ID
        thread_ts: Slack Thread ts
        slack_token: Slack app token
    Return:
        String: Slack meaasge in thread
    """
    slack_url = "https://slack.com/api/conversations.replies"
    response = http.request(
        "GET", slack_url,
        headers={
            "Authorization": f"Bearer {slack_token}",
            "Content-Type": "application/json"
        },
        fields={
            "channel": channel,
            "ts": thread_ts
        }
    )
    messages = json.loads(response.data.decode("utf-8")).get("messages", [])
    return "\n".join([msg.get("text", "") for msg in messages])

def remove_mentions(text):
    """
    Delete Slack mentions (<@USER_ID>)
    Args:
        text: Target Text
    Return: 
        String: Mention deleted text
    """
    return re.sub(r"<@[\w]+>", "", text).strip()

def query_bedrock(prompt,model_id):
    """
    Querying a generative AI using Amazon Bedrock.
    Sending all messages in a thread.

    Args:
        prompt: Prompts for generative AI
        model_id: AWS Bedrock Model ID
    Return: 
        String: Answers from generative AI
    """
    logging.info(f"Generating AI response for: {prompt}")
    messages = [
        {
            "role": "user",
            "content": [{"text": prompt}]
        }
    ]

    response = bedrock.converse(
        modelId = model_id,
        messages = messages
    )
    response_body = response["output"]["message"]["content"][0]["text"]
    return response_body

def is_duplicate_message(message_id,table_name,key_item):
    """
    Processed message determination
    Check the Dynamo DB and if the message ID passed as an argument exists, determine that the message has been processed.

    Args:
        table_name: Dynamo DB Table name
        key_item: Dynamo DB Key Item
    Return:
        Boolean True: Processed Messages, False: Unprocessed Messages
    """
    try:
        response = dynamodb.get_item(
            TableName=table_name,
            Key={key_item: {'S': message_id}}
        )
        return 'Item' in response
    except:
        return False        

def push_to_dynamoDB(message_id, table_name, table_key, table_ttl, ttl):
    """
    Marking a message as processed

    Args:
        message_id: Slack Message ID
        table_name: Dynamo DB Table name
        table_key: Dynamo DB Key Item
        table_ttl: Dynamo DB TTL Item
        ttl: date of expiry
    Return:
        Boolean True: Success
    
    """
    item = {
        f"{table_key}": {'S':message_id},
        f"{table_ttl}": {'N':str(int(time.time() + ttl))}
    }
    response = dynamodb.put_item(TableName = table_name,Item=item)
    return True

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
