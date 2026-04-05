#!/usr/bin/env bash
set -e

echo "=== Running clocksimulator tests ==="
echo ""

python -m pytest tests/ -v --tb=short

echo ""
echo "=== Tests complete ==="
