#!/usr/bin/env bash
set -euo pipefail

exec conda run -n clocksimulator python -m pytest "$@"
