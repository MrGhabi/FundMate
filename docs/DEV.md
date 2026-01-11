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
│   ├── pdfs/BROKER/      # decrypted/filtered PDFs cached per broker
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
# 未通过 `pip install -e .` 安装时，需加 `PYTHONPATH=src` 避免 ModuleNotFoundError：
# PYTHONPATH=src python -m src.main data/archives --date 2025-02-28
```

Statement mode (legacy date folders):
```bash
python -m src.main data/20250228_Statement --date 2025-02-28
python -m src.main data/20250228_Statement --date 2025-02-28 --broker IB
```

Key options:
- `-f/--force` – re-process PDFs even if processed files already exist
- `--max-workers N` – tune concurrency per hardware

## 5. Trade Confirmation Mode

Enable incremental updates when broker statements lag:

```bash
python -m src.main data/archives --date 2025-07-22 --use-tc
python -m src.main data/archives --date 2025-07-22 --use-tc \
  --tc-folder data/archives/TC
# 同理，未执行可编辑安装时请加前缀：
# PYTHONPATH=src python -m src.main data/archives --date 2025-07-22 --use-tc
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

Upload 页面布局（Upload tab）：
- 顶部块：Run calculation date + Run Calculation 按钮，包含 pipeline 进度条和汇总表（状态/错误列），job status banner 也在此块内。
- 中部块：Upload Broker Statements（拖拽/选择文件、上传进度条、Metadata Detection 表）。
- 底部块：Job History，默认折叠，点击“Show Job History”后加载展示最近的运行记录（上传/计算皆有）。
- 探针：默认启用 `PIPELINE_PROBE_ENABLE=1`（见 `run_web.sh`），可显式导出 `PIPELINE_PROBE_ENABLE=0` 关闭。
- Job history 持久化：终态任务（completed/failed）会写入 `temp/job_history.jsonl`，`/api/jobs` 会合并内存中的进行中任务与持久化历史。
- Job History 卡片内每条记录前有类型标记（Upload / Calculate），对应 job_type（metadata_only / pipeline_run）。
- 点击 Job History 卡片可重放结果：Upload 会重现 Metadata Detection 表；Calculate 会重现 Pipeline 表（依赖探针数据）。
- 若历史记录缺少 probe 数据（未启用探针的旧跑），点击时会提示无法重放该次的 pipeline summary。
- Upload 卡片标题使用首个上传文件名（prefer 上传文件名列表；缺失则退化为首个检测文件名或“Upload”）；Calculate 卡片标题使用运行日期。
- Pipeline 完成后会读取 parquet 汇总并回填 per-broker USD（cash/positions/total），并合并 probe 收集的文件列表以便表格展示。

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

### 10.1 Metadata-based preprocessing (RAR/ZIP uploads)

For ad-hoc bundles (RAR/ZIP) that are already grouped by broker/date, use the metadata tools under `src/metadata`:

```bash
# 1) Extract the archive into a temp directory (avoid deleting originals).
unrar x temp/20250807\ Statement.rar temp/20250807_statement_extract

# 2) Generate JSONL metadata (PDF via LLM, Excel via structured parsers).
python -m src.metadata.detector temp/20250807_statement_extract --output temp/metadata_20250807.jsonl

# 3) Organize into data/archives with hash-based dedupe (SHA-256 per broker).
python -m src.metadata.organizer temp/metadata_20250807.jsonl --output data/archives
```

- Naming & dedupe:
  - Canonical filename: `{BROKER}_{YYYY-MM-DD}_{ORIGINAL_NAME}.{ext}`. The trailing segment preserves the user’s original filename for traceability; organizer dedupes by `BROKER + hash + statement_date`, not by that trailing segment.
  - TC files stay under `data/archives/TC/` and should keep `TC-YYYY-MM-DD-*.xlsx` naming; do not let organizer flatten or rename them into broker roots.
- Hash dedupe: organizer computes SHA-256 per broker/date; identical content is skipped, hash conflicts are reported.
- Collision handling: when the same broker/date/account produces multiple files (e.g., GSPB Position + Cash), organizer appends `_position`, `_cash`, or `_vN` rather than overwriting.

**DBS 现金 CSV（测试周期）**
- 格式必须严格为 5 行：
  1) `Name of the Bank:,DBS`
  2) `Date,MM/DD/YYYY`
  3) `USD,<number>`
  4) `HKD,<number>`
  5) `CNY,<number>`
- `.env` 的 `FUNDMATE_ARCHIVE_DIR` 预计指向 `temp/archives`，组织后命名 `DBS_<date>_UNKNOWN.csv`。
- 仅现金、无持仓；日期以 CSV 内容为准（归档文件名不参与判定）。
- 汇率要求：HKD/CNY 缺当日汇率将直接报错，避免现金被低估。

- Excel routing: filename hints (`ms|morgan|gs|goldman|tenfund|optiondaily|trade confirmation`) pick a parser, then the extractor will fall back to try all parsers before giving up, so content is still inspected when filenames are non-standard. For TC, rely on **table shape** (headers such as `Trade Date`, `BUY/SELL`, `Avg. Price`, `Amount (USD)`, `Broker`, `Currency`) rather than only the filename; filenames containing GS/MS/GSPB can otherwise be misrouted.
- TC Excel: tagged as broker `TC` with date inferred from filename or sheet content; account may remain `UNKNOWN` unless the sheet carries it. Keep TC files in `data/archives/TC/` to avoid organizer renaming them into broker roots.
- PDF decryption: metadata detector auto-decrypts PDFs using `pdf_processor.BROKER_CONFIG` passwords (writes a temp decrypted copy for LLM), so encrypted PDFs won’t be mis-identified as separate accounts. Keep encrypted originals if needed for audit, but store readable copies in `data/archives`.
- TC file dedupe: TC parsing now SHA-256 de-duplicates identical TC-*.xlsx files and warns when skipping duplicates, preventing double application of the same trades.
- Archive hygiene: if both encrypted and decrypted versions of the same account/date exist, keep the readable version in `data/archives` and move the encrypted duplicate to `temp/null/` to avoid multi-account duplication.

## 11. Known Limitations & Tips

- Futu OpenD must be reachable from the environment where you run FundMate; sandboxed environments may fail unless proxies are configured carefully.
- Some CN A-share options fall back to broker-provided prices when market APIs lack coverage.
- Keep `utils.is_money_market_fund` patterns up to date to avoid MMF positions leaking into `TOTAL_POSITIONS`.
- When adding new option parsers, register them in `ParserRegistry` to maintain deterministic auto-parsing and TC matching.

For a high-level onboarding narrative (goals, data flow, baseline philosophy), see `AGENTS.md`.
## 12. Broker Naming Convention

Archive directories and filenames follow a canonical naming scheme:

| Canonical Name   | Human-readable Broker         | Notes                                    |
| ---------------- | ----------------------------- | ---------------------------------------- |
| `CICC`           | CICC                          | China International Capital Corporation  |
| `CIS`            | China Industrial Securities   | 兴证                                      |
| `CS`             | Credit Suisse                 | 瑞信                                      |
| `DBS`            | DBS Bank                      | Cash-only CSV format supported           |
| `FIRST_SHANGHAI` | First Shanghai                | Files named `FIRST_SHANGHAI_...`         |
| `GS`             | Goldman Sachs                 | 高盛                                      |
| `GSPB`           | Goldman Sachs Prime Brokerage | Position + Cash Excel auto-merged        |
| `HSBC`           | HSBC                          | 汇丰                                      |
| `HTI`            | Huatai International          | 华泰国际                                   |
| `HUATAI`         | Huatai                        | 华泰                                      |
| `IB`             | Interactive Brokers           | IBKR                                     |
| `LB`             | Longbridge                    | 长桥                                      |
| `MOOMOO`         | Moomoo / Futu                 | 富途/富牛                                  |
| `MS`             | Morgan Stanley                | 摩根士丹利                                 |
| `SC`             | Standard Chartered            | 渣打                                      |
| `SDICS`          | SDICS                         |                                          |
| `SOFI`           | SoFi                          |                                          |
| `TENFUND`        | TenFund                       |                                          |
| `TFI`            | Tianfeng International        | 天风国际                                   |
| `TIGER`          | Tiger Brokers                 |                                          |
| `UBS`            | UBS                           | 瑞银                                      |
| `WB`             | Webull                        | 微牛                                      |

File names must follow `CANONICAL_YYYY-MM-DD_ACCOUNT.ext` to ensure the archive scanner and processors detect them correctly. The `TC` folder stores trade-confirmation Excel files; if renamed, remember to adjust the `--tc-folder` argument accordingly.
