#!/bin/bash
# Run code quality checks

set -e

echo "Running ruff linter..."
venv/bin/python3 -m ruff check .

echo ""
echo "Running mypy type checker..."
venv/bin/python3 -m mypy globe_generator/*.py *.py

echo ""
echo "✓ All checks passed!"
