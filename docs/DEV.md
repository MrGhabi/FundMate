# FundMate Developer Guide

This document captures the implementation details that used to live in the top-level README. Use it as the authoritative reference when you need to understand how the system is wired, how to run advanced modes, and where to find supporting assets.

## 1. Architecture Overview

- **Base Mode** parses PDF/Excel broker statements into normalized `Position` objects plus cash buckets. Source code lives primarily in `src/broker_processor.py`, `src/excel_parser.py`, and `src/pdf_processor.py`.
- **Trade Confirmation (TC) Mode** reuses a persisted base portfolio, loads trade confirmation Excel files, and applies transactions incrementally via `src/trade_confirmation_processor.py`.
- **Position Model (`src/position.py`)**
  - Represents both stocks and options with auto-parsed option metadata.
  - Uses the parser registry in `src/option_parser.py` (US OCC, HKATS, HK numeric, OTC, long formats).
  - `Position.matches_option()` compares underlying/expiry/strike/OptionType for fuzzy lookups during TC reconciliation.
- **Pricing & Cash**
  - `BrokerStatementProcessor` and `TradeConfirmationProcessor` share the price-fetch pipeline (`src/price_fetcher.py`, `src/hk_option_price_helper.py`, `src/us_option_price_helper.py`).
  - Cash normalization relies on `src/exchange_rate_handler.py`; USD totals appear in both parquet summary and CSV exports.
- **Persistence**
  - `src/data_persistence.py` writes `cash_summary_*.parquet`, `positions_*.parquet`, and `portfolio_details_*.csv`, plus metadata/exchange rate cache.

## 2. Installation & Environment

```bash
pip install -e .
pip install -e .[web]  # required if you plan to run the Flask UI
```

Requirements:
- Python ≥ 3.10
- Google Gemini / OpenAI-compatible LLM key (PDF parsing)
- Futu OpenD running locally at `127.0.0.1:11111` (real-time pricing; akshare is a fallback but still needs internet)

Proxy note: some environments require unsetting `HTTP(S)_PROXY` for local services (Futu, Gemini gateway) while still keeping outbound access. Document the exact proxy workflow in your local `.env`.

## 3. Directory Layout

```
.
├── data/                 # Raw broker statements & trade confirmations
│   ├── archives/         # Recommended structure by broker
│   ├── *_Statement/      # Legacy date-based folders
│   └── uploads/          # Web UI upload temp
├── docs/DEV.md           # (this file)
├── log/                  # Processing logs (per date)
├── out/
│   ├── pictures/DATE/    # PDF-to-image conversion
│   └── result/DATE/      # cash/positions parquet + CSV + metadata
├── src/                  # Application source
│   └── webapp/           # Flask UI (templates/static packaged here)
├── temp/                 # Research notes, regression logs, baseline archives
└── test/
    ├── e2e/              # Full pipeline tests (require services)
    ├── fixtures/         # TC baselines, sample portfolios
    └── unit/             # Deterministic unit suites
```

## 4. CLI Usage (Base Mode)

Archive mode (recommended):
```bash
python -m src.main data/archives --date 2025-02-28
python -m src.main data/archives --date 2025-02-28 --broker IB
python -m src.main data/archives --date 2025-02-28 -f --max-workers 8
```

Statement mode (legacy date folders):
```bash
python -m src.main data/20250228_Statement --date 2025-02-28
python -m src.main data/20250228_Statement --date 2025-02-28 --broker IB
```

Key options:
- `--output DIR` – custom image output directory (default `./out/pictures`)
- `-f/--force` – reconvert PDFs even if images already exist
- `--max-workers N` – tune concurrency per hardware

## 5. Trade Confirmation Mode

Enable incremental updates when broker statements lag:

```bash
python -m src.main data/archives --date 2025-07-22 --use-tc
python -m src.main data/archives --date 2025-07-22 --use-tc --base-date 2025-07-18
python -m src.main data/archives --date 2025-07-22 --use-tc \
  --base-date 2025-07-18 \
  --tc-folder data/archives/TC
```

How it works:
1. Load the base portfolio snapshot (`positions_*.parquet`, `cash_summary_*.parquet`) for the base date.
2. Parse TC Excel files (Bloomberg suffix cleanup, broker prefix stripping, HK numeric resolution).
3. Apply BUY/SELL/short transactions, updating holdings and USD cash.
4. Fetch target-date prices, persist refreshed outputs, update summary rows.

Prerequisites & tooling:
- Base portfolio must exist (run base mode for the base date first).
- TC filenames should follow `TC-{YYYY-MM-DD}-{original_name}.xlsx`. Use `src/scripts/rename_trade_confirmations.py` to normalize disparate vendor names:
  ```bash
  python src/scripts/rename_trade_confirmations.py           # dry run
  python src/scripts/rename_trade_confirmations.py --execute
  ```
- `test/fixtures/tc_base/2025-07-18/` stores cached base results. Tests inject them via `base_results_override / base_exchange_rates_override` to avoid rerunning PDF+LLM.
- Regression assertions compare against `test/fixtures/tc_expected/portfolio_details_2025-07-22.csv`, ensuring `TOTAL_CASH` and `TOTAL_POSITIONS` stay stable.

## 6. Web UI

The Flask dashboard lives in `src.webapp`.

```
./run_web.sh 5000
python -m src.webapp.app
gunicorn -c gunicorn.conf.py src.webapp.app:app
```

The UI simply reads from `./out/result/<date>`; make sure at least one processing run (base or TC) has produced outputs before launching. All templates/static assets are packaged via `pyproject.toml` so relative paths are no longer an issue.

## 7. Outputs

`./out/result/DATE/` contains:
- `cash_summary_DATE.parquet`
- `positions_DATE.parquet`
- `portfolio_details_DATE.csv`
- `metadata_DATE.json`

`./log/DATE/fundmate.log` captures run-time diagnostics (PDF conversion, LLM extraction, price lookup status). Money Market Funds are reclassified as cash before persistence; summary rows include `[SUMMARY]/TOTAL_CASH`, `TOTAL_POSITIONS`, `GRAND_TOTAL` for downstream dashboards.

## 8. Environment Variables (.env)

```bash
LLM_API_KEY=...            # required
LLM_BASE_URL=...
LLM_MODEL=gemini-2.5-pro   # optional override
EXCHANGE_API_KEY=...       # optional if exchangerate.host is proxied
FUNDMATE_PRICE_SOURCE=futu | akshare
FUTU_HOST=127.0.0.1
FUTU_PORT=11111
FUNDMATE_OUTPUT_DIR=./out
FUNDMATE_LOG_DIR=./log
```

Store secrets in a local `.env`; keep an `.env.example` for onboarding.

## 9. Testing Strategy

```
sh test/run_tests.sh                                    # full regression (requires Gemini + Futu)
python -m pytest test/e2e/test_tc_mode.py -vv           # cached TC regression
python -m pytest test/unit/test_exchange_rate.py -vv    # deterministic unit suites
```

- `test/e2e/test_0228_full.py`, `test/e2e/test_0630_full.py`, `test/e2e/test_cross_broker.py` exercise full PDF/LLM pipelines for historical datasets.
- TC regression (`test/e2e/test_tc_mode.py`) injects baseline data to avoid heavy services but still validates transaction math and CSV outputs.
- Fixtures under `test/fixtures/tc_base/` and `test/fixtures/tc_expected/` are canonical references; update them only after verifying real broker data.

## 10. Data Archiving Tool

Convert `*_Statement` folders to archive mode:

```bash
python scripts/archive_statements.py --dry-run
python scripts/archive_statements.py --data-dir ./data --archive-dir ./data/archives
```

Features:
- Scans every `data/*_Statement/` directory.
- Copies files into `data/archives/{BROKER}/`, renaming to `{BROKER}_{YYYY-MM-DD}_{ACCOUNT_ID}.{ext}`.
- Extracts account IDs across broker formats and generates a summary report.

## 11. Known Limitations & Tips

- Futu OpenD must be reachable from the environment where you run FundMate; sandboxed environments may fail unless proxies are configured carefully.
- Some CN A-share options fall back to broker-provided prices when market APIs lack coverage.
- Keep `utils.is_money_market_fund` patterns up to date to avoid MMF positions leaking into `TOTAL_POSITIONS`.
- When adding new option parsers, register them in `ParserRegistry` to maintain deterministic auto-parsing and TC matching.

For a high-level onboarding narrative (goals, data flow, baseline philosophy), see `AGENTS.md`.
## 12. Broker Naming Convention

Archive directories and filenames follow a canonical naming scheme:

| Canonical Name   | Human-readable Broker | Notes                              |
| ---------------- | --------------------- | ---------------------------------- |
| `CICC`           | CICC                  |                                    |
| `FIRST_SHANGHAI` | First Shanghai        | Files named `FIRST_SHANGHAI_...`   |
| `GS`             | Goldman Sachs         |                                    |
| `HTI`            | HTI                   |                                    |
| `HUATAI`         | Huatai                |                                    |
| `IB`             | Interactive Brokers   |                                    |
| `LB`             | Longbridge            |                                    |
| `MOOMOO`         | Moomoo                |                                    |
| `MS`             | Morgan Stanley        |                                    |
| `SDICS`          | SDICS                 |                                    |
| `TFI`            | TFI                   |                                    |
| `TIGER`          | Tiger Brokers         |                                    |

File names must follow `CANONICAL_YYYY-MM-DD_ACCOUNT.ext` to ensure the archive scanner and processors detect them correctly. The `TC` folder stores trade-confirmation Excel files; if renamed, remember to adjust the `--tc-folder` argument accordingly.
