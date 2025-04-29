# SlackApp-For-Amazon-Bedrock
## Introduction

Slack APPからAWS Bedrockを通じて生成AIチャットボットを作成するプログラムです。
AWS Lambdaサーピス上での稼働を想定しています。
Slackからは、Slack Bot Appのメンションをつけたメッセージ又は、Bot AppへのDMを生成AIへの入力のプロンプトとし、スレッドの返信として回答を返します。

### slack_app_ai_recv.py
Slackからのリクエストを受けて、AWS SQSにリクエストを登録する。

#### 権限
AWSマネジメントポリシーAWSLambdaBasicExecutionRoleのほかに以下のポリシーを追加する。

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "sqs:SendMessage"
            ],
            "Resource": "arn:aws:sqs:{region}:{account-id}:<your-sqs-queue-name>"
        }
    ]
}
```
### slack_app_ai_invoke.py
AWA SQSからキューを受信し、Amazon Bedrockサービス経由で生成AIへ問い合わせを行う。

#### 　権限
AWSマネジメントポリシーAWSLambdaBasicExecutionRoleのほかに以下のポリシーを追加する。
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "sqs:ReceiveMessage",
                "sqs:DeleteMessage",
                "sqs:GetQueueAttributes"
            ],
            "Resource": "arn:aws:sqs:{region}:{account-id}:<your-sqs-queue-name>"
        },
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem"
            ],
            "Resource": "arn:aws:dynamodb:<region>:<account-id>:table/<YOUR_DYNAMO_TABLE_NAME>"
        },
        {
            "Effect": "Allow",
            "Action": "bedrock:InvokeModel",
            "Resource": "*"
        }
    ]
}
```