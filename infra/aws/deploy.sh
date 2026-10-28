#!/usr/bin/env bash
# Build, push and roll out ContentPulse to the AWS stack created by terraform/.
#
#   cd infra/aws/terraform && terraform init && terraform apply   # once
#   ../deploy.sh                                                  # every release
#
# Needs: aws CLI (logged in), docker, terraform. Runs from Git Bash on Windows too.
# Steps: build both images under an immutable release tag -> push to ECR ->
# run migrations as a one-off task from that image (the release stops here if
# they fail, and nothing running has changed) -> point the services at the
# release tag -> wait until stable.
#
# Images are only ever addressed by their release tag (the ECR repositories are
# immutable), so a rollback is a different tag, never a re-pushed one:
#   terraform apply -var image_tag=<previous release>
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TF="$ROOT/infra/aws/terraform"
out() { terraform -chdir="$TF" output -raw "$1"; }

REGION="$(out region)"
CLUSTER="$(out cluster)"
API_REPO="$(out api_repository)"
WEB_REPO="$(out web_repository)"
API_NAME="${API_REPO#*/}"
WEB_NAME="${WEB_REPO#*/}"

# One tag per build. A dirty tree gets a timestamp so the tag never claims
# commit contents it doesn't have.
RELEASE="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)"
if [ -n "$(git -C "$ROOT" status --porcelain 2>/dev/null)" ]; then
  RELEASE="$RELEASE-$(date +%Y%m%d%H%M%S)"
fi
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" MSYS_NO_PATHCONV=1

tag_exists() { # repository name, tag
  aws ecr describe-images --repository-name "$1" --image-ids "imageTag=$2" >/dev/null 2>&1
}

echo "==> Logging in to ECR"
aws ecr get-login-password | docker login --username AWS --password-stdin "${API_REPO%%/*}"

echo "==> Building and pushing images ($RELEASE)"
if tag_exists "$API_NAME" "$RELEASE"; then
  echo "    api:$RELEASE is already in ECR; reusing it"
else
  docker build --platform linux/amd64 -t "$API_REPO:$RELEASE" "$ROOT/backend"
  docker push "$API_REPO:$RELEASE"
fi
if tag_exists "$WEB_NAME" "$RELEASE"; then
  echo "    web:$RELEASE is already in ECR; reusing it"
else
  docker build --platform linux/amd64 -t "$WEB_REPO:$RELEASE" "$ROOT/frontend"
  docker push "$WEB_REPO:$RELEASE"
fi

# The containers read every key in `secret_keys` from the app secret, and ECS will
# not start a task whose secret lacks one. Terraform never rewrites that secret
# (your edits are yours), so keys added in a newer release are added here, empty
# ("not configured") and nothing else is touched.
echo "==> Checking the app secret has every key"
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "python is needed to check the app secret (add the keys from 'terraform output secret_keys' by hand otherwise)." >&2
  exit 1
fi
SECRET_ARN="$(out app_secret_arn)"
CURRENT="$(aws secretsmanager get-secret-value --secret-id "$SECRET_ARN" --query SecretString --output text)"
MERGED="$(KEYS="$(out secret_keys)" CURRENT="$CURRENT" "$PY" -c '
import json, os
current = json.loads(os.environ["CURRENT"])
missing = [k for k in os.environ["KEYS"].split() if k not in current]
if missing:
    print(json.dumps({**{k: "" for k in missing}, **current}))
')"
if [ -n "$MERGED" ]; then
  aws secretsmanager put-secret-value --secret-id "$SECRET_ARN" --secret-string "$MERGED" >/dev/null
  echo "    added missing keys (empty)"
fi

# Only the migration task moves to the new image here; the running services are
# untouched until the migration has succeeded.
echo "==> Running database migrations"
terraform -chdir="$TF" apply -auto-approve -input=false \
  -var "image_tag=$RELEASE" -target=aws_ecs_task_definition.migrate
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
  echo "Migrations failed (exit $EXIT_CODE); the services still run the previous release." >&2
  echo "Logs: aws logs tail $(out log_group) --log-stream-name-prefix migrate" >&2
  exit 1
fi

echo "==> Rolling out"
SERVICES=(api worker beat web)
terraform -chdir="$TF" apply -auto-approve -input=false \
  -var "image_tag=$RELEASE" \
  -target='aws_ecs_service.backend' -target=aws_ecs_service.web
aws ecs wait services-stable --cluster "$CLUSTER" --services "${SERVICES[@]}"

# Remember the running release so a later plain `terraform apply` keeps it.
printf 'image_tag = "%s"\n' "$RELEASE" > "$TF/release.auto.tfvars"

echo "==> Deployed $RELEASE: $(out app_url)"
