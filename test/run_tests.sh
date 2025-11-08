#!/bin/bash
# Simple test runner script for FundMate

set -e

echo "FundMate Test Runner"
echo "===================="
echo ""

# Default: run all tests
echo "Running all tests..."
python -m pytest test/ -v

echo ""
echo "✅ Tests completed successfully!"

