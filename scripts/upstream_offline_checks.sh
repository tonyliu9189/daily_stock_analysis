#!/usr/bin/env bash
set -euo pipefail

python scripts/check_ai_assets.py
bash "${RUNNER_TEMP}/fork-ci-gate.sh" syntax
bash "${RUNNER_TEMP}/fork-ci-gate.sh" flake8
python -m pytest -q -o addopts= --timeout=120 \
  --junitxml="${RUNNER_TEMP}/fork-tests.xml" \
  tests/test_tw_market_review.py tests/test_tw_market_stats.py \
  tests/test_taiwan_infographic.py tests/test_share_image.py \
  tests/test_infographic_delivery.py tests/test_pipeline_notification_image_routing.py \
  tests/test_notification_sender.py tests/test_upstream_update.py
python "${RUNNER_TEMP}/fork-updater.py" verify-junit --directory "${RUNNER_TEMP}/fork-tests.xml"
bash "${RUNNER_TEMP}/fork-ci-gate.sh" offline-tests
