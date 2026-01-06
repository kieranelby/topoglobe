#!/usr/bin/env python3
"""
Simple wrapper script for integration tests.

This provides a user-friendly output format for manual testing.
For automated testing, use: pytest tests/test_integration.py
"""

import sys

import pytest


def main():
    """Run integration tests with user-friendly output."""
    print("\n=== Running Integration Tests ===\n")
    print("This will test the full data processing pipeline.")
    print("Data files (ETOPO1, MODIS) must be present in ./data/\n")

    # Run pytest on integration tests only
    exit_code = pytest.main([
        "tests/test_integration.py",
        "-v",
        "-m", "integration",
        "--tb=short",
    ])

    if exit_code == 0:
        print("\n✓ All integration tests PASSED!")
    else:
        print("\n✗ Some integration tests FAILED")
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
