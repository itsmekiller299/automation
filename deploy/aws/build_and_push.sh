#!/usr/bin/env bash
# Build and push the API and dashboard images to ECR (linux/amd64 for Fargate).
#
# Prerequisites: AWS credentials, Docker buildx, and the ECR repositories
# created by `terraform apply -target=aws_ecr_repository.repos`.
#
# Usage:
#   AWS_REGION=us-east-1 ./deploy/aws/build_and_push.sh
#   AWS_REGION=us-east-1 TAG=2026-10-31 ./deploy/aws/build_and_push.sh
#   INSTALL_ONNX=false ./deploy/aws/build_and_push.sh   # rules-only image
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ACCOUNT_ID="${ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
REGION="${AWS_REGION:-us-east-1}"
PROJECT="${PROJECT:-orbit}"
TAG="${TAG:-$(date -u +%Y%m%d%H%M%S)}"
INSTALL_ONNX="${INSTALL_ONNX:-true}"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
API_IMAGE="${REGISTRY}/${PROJECT}-api:${TAG}"
DASHBOARD_IMAGE="${REGISTRY}/${PROJECT}-dashboard:${TAG}"

echo "Account:  ${ACCOUNT_ID}"
echo "Region:   ${REGION}"
echo "API:      ${API_IMAGE}"
echo "Dashboard:${DASHBOARD_IMAGE}"

aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${REGISTRY}"

docker buildx build \
  --platform linux/amd64 \
  --build-arg "INSTALL_ONNX=${INSTALL_ONNX}" \
  -f "${ROOT}/backend/Dockerfile" \
  -t "${API_IMAGE}" \
  --push \
  "${ROOT}"

docker buildx build \
  --platform linux/amd64 \
  -f "${ROOT}/dashboard/Dockerfile" \
  -t "${DASHBOARD_IMAGE}" \
  --push \
  "${ROOT}/dashboard"

cat <<EOF

Images pushed. Apply the stack with:

  terraform -chdir="${ROOT}/deploy/aws" apply \\
    -var="api_image=${API_IMAGE}" \\
    -var="dashboard_image=${DASHBOARD_IMAGE}"

EOF
