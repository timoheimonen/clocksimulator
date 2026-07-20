#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH= cd "$(dirname "$0")" && pwd -P)"
cd "$repository_root"

exec conda run --no-capture-output -n clocksimulator \
  env \
  -u PYTEST_ADDOPTS \
  -u PYTEST_PLUGINS \
  -u PYTEST_DISABLE_PLUGIN_AUTOLOAD \
  -u PYTHONOPTIMIZE \
  -u PYTHONPATH \
  -u PYTHONUSERBASE \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  PYTHONNOUSERSITE=1 \
  python -m pytest \
  -p pytest_playwright.pytest_playwright \
  -p pytest_randomly \
  "$@"
