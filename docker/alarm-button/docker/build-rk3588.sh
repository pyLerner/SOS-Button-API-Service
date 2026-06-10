#!/usr/bin/env bash
set -euo pipefail

# RK3588 / Ubuntu friendly build path:
# disable BuildKit/buildx and use classic docker builder.
export DOCKER_BUILDKIT=0
export COMPOSE_DOCKER_CLI_BUILD=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
IMAGE_TAG="${IMAGE_TAG:-alarm-button-api:1}"

cd "${PROJECT_ROOT}"
docker build --no-cache -f docker/alarm-button/docker/Dockerfile -t "${IMAGE_TAG}" .

echo "Built ${IMAGE_TAG}"
echo "Export: docker save ${IMAGE_TAG} | gzip > alarm-button-1-\$(date +%Y%m%d).tar.gz"
