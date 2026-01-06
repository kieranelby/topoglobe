#!/bin/bash
# Run test suite

set -e

echo "Running unit tests..."
venv/bin/python3 -m pytest tests/ -v

echo ""
echo "✓ All tests passed!"
