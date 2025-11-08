# FundMate Test Suite

Complete test suite for FundMate broker statement processor. Tests use real 0228 and 0630 datasets (10+ brokers each).

## Quick Start

```bash
# Fast unit tests (recommended for development, ~0.1s)
./run_tests.sh fast

# E2E tests (~10min, needs full API setup)
./run_tests.sh e2e

# All tests
./run_tests.sh all
```

## Test Structure

```
test/
├── unit/                   # 37 tests, ~0.1s, no external deps
│   ├── test_utils.py       # Option detection, multiplier, MMF (28 tests)
│   └── test_exchange_rate.py # Caching mechanism (9 tests)
│
└── e2e/                    # 3 tests, ~10-15min, needs full API setup
    ├── expected_results.json # Expected totals (manually maintained)
    ├── test_0228_full.py   # Full pipeline for 0228 dataset
    ├── test_0630_full.py   # Full pipeline for 0630 dataset
    └── test_cross_broker.py # Cross-broker aggregation
```

**Statistics:** 9 files, ~800 lines, 40 tests total

## Common Commands

```bash
# Using run_tests.sh
./run_tests.sh fast         # Unit tests only
./run_tests.sh e2e          # End-to-end tests
./run_tests.sh all          # All tests
./run_tests.sh all-fast     # Skip slow tests

# Using pytest directly
pytest test/unit/ -v                    # All unit tests
pytest test/e2e/ -v -s                  # E2E tests with output
pytest test/ -m "not slow" -v           # Skip slow tests
pytest test/unit/test_utils.py -v      # Specific file

# Debugging
pytest test/unit/test_utils.py -v --tb=long -s  # Full traceback + prints
pytest --lf -v                                   # Last failed only
pytest test/unit/ -x                             # Stop on first failure
```

## What We Test

**Unit Tests (no external deps):**
- Option detection (CALL/PUT/OCC/HKATS formats)
- Option multiplier logic (100 vs 1 for OTC, broker override)
- Position value calculation (price × holding × multiplier)
- MMF detection for cash reclassification
- Exchange rate caching (JSON + memory cache)

**E2E Tests (real scenarios):**
- Simulate running `python src/main.py data/XXX_Statement --date YYYY-MM-DD`
- Process 10+ brokers with real PDF and Excel files
- Verify final CSV totals (cash + positions) against baseline
- Allow 5% variance for market price changes
- Verify cross-broker aggregation and batch pricing optimization

## What We Don't Test

PDF decryption, Excel parsing, account ID extraction, config loading, date validation - these are library functions or trivial logic.

## Prerequisites

**Unit tests:**
- Python 3.8+, pytest, FundMate dependencies

**E2E tests:**
- Above + `.env` configured (LLM_API_KEY, LLM_BASE_URL, EXCHANGE_API_KEY)
- Futu OpenD running locally
- Test data: `data/20250228_Statement/`, `data/20250630_Statement/`

## Troubleshooting

**Import errors:**
```bash
cd /path/to/FundMate
export PYTHONPATH=$PYTHONPATH:$(pwd)/src
pytest test/
```

**API timeout:**
- Check Futu OpenD running on 127.0.0.1:11111
- Verify `.env` has valid API keys
- Check network connection

**Missing test data:**
- Ensure `data/20250228_Statement/` and `data/20250630_Statement/` exist
- Check broker subdirectories have PDF/Excel files

**Skipped tests:**
Normal if prerequisites not met (e.g., need 2+ brokers for cross-broker test). Run full suite instead of individual tests.

## Test Results

```
============================= test session starts ==============================
collected 37 items

test/unit/test_exchange_rate.py ......... [24%]
test/unit/test_utils.py ............................ [100%]

============================== 37 passed in 0.10s ===============================

Tests completed successfully!
```

## Design Principles

Following Linus philosophy:
- **Simple** - Each test has single clear purpose
- **Robust** - Test what matters, not implementation details
- **Direct** - Minimal mocking, test real behavior
- **Practical** - Focus on user scenarios
- **Clean** - English comments, no emoji, no fluff

## Test Markers

- `@pytest.mark.slow` - Slow tests (processing, API calls)
- `@pytest.mark.e2e` - End-to-end tests
- No marker - Fast unit tests

Use: `pytest test/ -m "not slow"` to skip slow tests.

## Contributing

1. Place tests in appropriate directory (unit/e2e)
2. Use descriptive names and docstrings
3. Mark slow tests with `@pytest.mark.slow`
4. Keep tests independent (no shared state)
5. Use fixtures from `conftest.py`
