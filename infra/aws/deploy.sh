#!/usr/bin/env bash
# Build, push and roll out ContentPulse to the AWS stack created by terraform/.
#
#   cd infra/aws/terraform && terraform init && terraform apply   # once
#   ../deploy.sh                                                  # every release
#
# Needs: aws CLI (logged in), docker, terraform. Runs from Git Bash on Windows too.
# Steps: build both images -> push to ECR -> run migrations as a one-off task
# (the release stops if they fail) -> roll the services -> wait until stable.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TF="$ROOT/infra/aws/terraform"
out() { terraform -chdir="$TF" output -raw "$1"; }

REGION="$(out region)"
CLUSTER="$(out cluster)"
API_REPO="$(out api_repository)"
WEB_REPO="$(out web_repository)"
TAG="$(out image_tag)"
RELEASE="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)"
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" MSYS_NO_PATHCONV=1

echo "==> Logging in to ECR"
aws ecr get-login-password | docker login --username AWS --password-stdin "${API_REPO%%/*}"

echo "==> Building images ($RELEASE)"
docker build --platform linux/amd64 -t "$API_REPO:$RELEASE" -t "$API_REPO:$TAG" "$ROOT/backend"
docker build --platform linux/amd64 -t "$WEB_REPO:$RELEASE" -t "$WEB_REPO:$TAG" "$ROOT/frontend"

echo "==> Pushing"
for image in "$API_REPO:$RELEASE" "$API_REPO:$TAG" "$WEB_REPO:$RELEASE" "$WEB_REPO:$TAG"; do
  docker push "$image"
done

echo "==> Running database migrations"
TASK_ARN="$(aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$(out migrate_task_definition)" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$(out private_subnets)],securityGroups=[$(out app_security_group)],assignPublicIp=DISABLED}" \
  --query 'tasks[0].taskArn' --output text)"
aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$TASK_ARN"
EXIT_CODE="$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK_ARN" \
  --query 'tasks[0].containers[0].exitCode' --output text)"
if [ "$EXIT_CODE" != "0" ]; then
  echo "Migrations failed (exit $EXIT_CODE). Logs: aws logs tail $(out log_group) --log-stream-name-prefix migrate" >&2
  exit 1
fi

echo "==> Rolling out"
SERVICES=(api worker beat web)
for service in "${SERVICES[@]}"; do
  aws ecs update-service --cluster "$CLUSTER" --service "$service" --force-new-deployment \
    --query 'service.serviceName' --output text
done
aws ecs wait services-stable --cluster "$CLUSTER" --services "${SERVICES[@]}"

echo "==> Deployed $RELEASE: $(out app_url)"
