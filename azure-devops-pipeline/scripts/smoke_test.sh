#!/usr/bin/env bash
# Post-deployment smoke test used by every DeployXxx stage in azure-pipelines.yml.
# Polls the deployed app's health endpoint and fails the pipeline if it
# doesn't return HTTP 200 within the retry window.

set -euo pipefail

TARGET_URL="${1:?Usage: smoke_test.sh <base-url>}"
HEALTH_PATH="${2:-/health}"
MAX_ATTEMPTS=10
SLEEP_SECONDS=6

url="${TARGET_URL%/}${HEALTH_PATH}"
echo "Smoke testing ${url}"

for attempt in $(seq 1 "${MAX_ATTEMPTS}"); do
  status=$(curl -s -o /dev/null -w '%{http_code}' "${url}" || echo "000")

  if [[ "${status}" == "200" ]]; then
    echo "Attempt ${attempt}/${MAX_ATTEMPTS}: OK (HTTP ${status})"
    exit 0
  fi

  echo "Attempt ${attempt}/${MAX_ATTEMPTS}: HTTP ${status}, retrying in ${SLEEP_SECONDS}s..."
  sleep "${SLEEP_SECONDS}"
done

echo "Smoke test failed: ${url} never returned HTTP 200 after ${MAX_ATTEMPTS} attempts" >&2
exit 1
