#!/usr/bin/env bash
# Simple helper script to run on the remote EC2 host (or locally via SSH) to pull
# the latest image from ECR and restart the service/container.

set -euo pipefail

REPO_URI="$1" # e.g. 123456789012.dkr.ecr.us-east-1.amazonaws.com/ece461-team17-phase2
IMAGE_TAG=${2:-latest}
CONTAINER_NAME=${3:-pieta_app}
PORT_MAP=${4:-8000:8000}

# Login to ECR (assumes awscli is configured on the host)
aws ecr get-login-password --region ${AWS_REGION:-us-east-1} | docker login --username AWS --password-stdin $(aws sts get-caller-identity --query Account --output text).dkr.ecr.${AWS_REGION:-us-east-1}.amazonaws.com

# Pull and restart
docker pull ${REPO_URI}:${IMAGE_TAG}
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  docker stop ${CONTAINER_NAME} || true
  docker rm ${CONTAINER_NAME} || true
fi

docker run -d --restart=unless-stopped --name ${CONTAINER_NAME} -p ${PORT_MAP} ${REPO_URI}:${IMAGE_TAG}

echo "Deployed ${REPO_URI}:${IMAGE_TAG} as ${CONTAINER_NAME}"