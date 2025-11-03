#!/bin/bash
# Simple test runner script for FundMate

set -e

echo "FundMate Test Runner"
echo "===================="
echo ""

# Default: run fast tests only
TEST_MODE="${1:-fast}"

case "$TEST_MODE" in
    fast)
        echo "Running fast tests (unit tests only)..."
        python -m pytest test/unit/ -v
        ;;
    
    e2e)
        echo "Running end-to-end tests (requires API keys and Futu OpenD)..."
        python -m pytest test/e2e/ -v -s
        ;;
    
    all)
        echo "Running all tests..."
        python -m pytest test/ -v
        ;;
    
    all-fast)
        echo "Running all tests except slow ones..."
        python -m pytest test/ -v -m "not slow"
        ;;
    
    *)
        echo "Usage: $0 [fast|e2e|all|all-fast]"
        echo ""
        echo "  fast        - Run unit tests only (default, ~0.1s)"
        echo "  e2e         - Run end-to-end tests (~10-15min)"
        echo "  all         - Run all tests (~15min)"
        echo "  all-fast    - Run all except slow tests (~0.1s)"
        exit 1
        ;;
esac

echo ""
echo "Tests completed successfully!"

