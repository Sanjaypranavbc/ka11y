#!/usr/bin/env bash
# LocalStack "ready" hook (mounted at /etc/localstack/init/ready.d/): creates
# the audit job queue and its dead-letter queue the way they must exist in AWS.
#
#   ka11y-audit-jobs-dlq   where a message lands after maxReceiveCount deliveries
#   ka11y-audit-jobs       the worker's queue; VisibilityTimeout 300 s (the worker
#                          heartbeats every 150 s), redrive to the DLQ after 3
#                          receives — the same number as WORKER_MAX_ATTEMPTS.
#
# Real AWS: create the two queues with the same RedrivePolicy (Terraform/CDK/
# console) and point SQS_QUEUE_URL at the main queue. Nothing in the code
# creates queues.
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-${AWS_REGION:-us-east-1}}"
QUEUE="${KA11Y_SQS_QUEUE_NAME:-ka11y-audit-jobs}"
DLQ="${QUEUE}-dlq"
MAX_RECEIVE="${KA11Y_SQS_MAX_RECEIVE_COUNT:-3}"
VISIBILITY="${SQS_VISIBILITY_TIMEOUT:-300}"

awslocal sqs create-queue --region "$REGION" --queue-name "$DLQ" \
  --attributes '{"MessageRetentionPeriod":"1209600"}' >/dev/null
DLQ_ARN="$(awslocal sqs get-queue-attributes --region "$REGION" \
  --queue-url "$(awslocal sqs get-queue-url --region "$REGION" --queue-name "$DLQ" --query QueueUrl --output text)" \
  --attribute-names QueueArn --query Attributes.QueueArn --output text)"

awslocal sqs create-queue --region "$REGION" --queue-name "$QUEUE" --attributes "$(cat <<JSON
{
  "VisibilityTimeout": "${VISIBILITY}",
  "ReceiveMessageWaitTimeSeconds": "20",
  "MessageRetentionPeriod": "345600",
  "RedrivePolicy": "{\"deadLetterTargetArn\":\"${DLQ_ARN}\",\"maxReceiveCount\":\"${MAX_RECEIVE}\"}"
}
JSON
)" >/dev/null

# Optional: an S3 bucket for artifacts when KA11Y_S3_BUCKET points at LocalStack.
if [ -n "${KA11Y_S3_BUCKET:-}" ]; then
  awslocal s3 mb "s3://${KA11Y_S3_BUCKET}" --region "$REGION" 2>/dev/null || true
fi

echo "[init-sqs] queues ready: $(awslocal sqs list-queues --region "$REGION" --query QueueUrls --output text)"
