# FundMate

**Automated broker statement processor with LLM-powered data extraction**

## SYNOPSIS

```
python -m src.main BROKER_FOLDER --date DATE [OPTIONS]
```

## DESCRIPTION

FundMate is a production-ready financial data processor that extracts cash holdings and position data from broker statements. It supports both PDF and Excel formats, uses LLM for intelligent data extraction, and provides real-time asset valuation with market prices.

### Key Features

- **Multi-format support**: PDF statements (image-based) and Excel files (structured data)
- **LLM-powered extraction**: Intelligent parsing using Google Gemini API
- **Real-time pricing**: Live stock and option prices via Futu OpenD API (with akshare fallback)
- **Intelligent MMF handling**: Automatically detects and reclassifies Money Market Funds as cash
- **Multi-currency**: Automatic currency conversion with recalculated totals (USD, CNY, HKD)
- **Concurrent processing**: Parallel processing of multiple broker accounts (up to 10 threads)
- **Data persistence**: Structured output in Parquet and CSV formats

## Installation

1. 建议在仓库根目录执行一次 editable 安装，这样所有命令都可以使用标准 `src.*` 包路径：
   ```bash
   pip install -e .
   ```
2. 之后运行 CLI/脚本时使用 `python -m src.<module>`（例如 `python -m src.main ...`）；IDE、测试与 web 服务都会自动解析依赖，不再需要手工调整 `PYTHONPATH` 或在代码里写特殊导入逻辑。

## SUPPORTED BROKERS

### PDF-based Brokers
- **IB** (Interactive Brokers)
- **HUATAI** (华泰证券)
- **SDICS** (申万宏源)
- **TIGER** (老虎证券)
- **MOOMOO** (富途证券)
- **TFI** (天风国际)
- **CICC** (中金公司)
- **HTI** (海通国际)
- **LB** (Longbridge/长桥证券)
- **First Shanghai** (第一上海)

### Excel-based Brokers  
- **MS** (Morgan Stanley)
- **GS** (Goldman Sachs)

## OPTIONS

### Required Arguments

**BROKER_FOLDER**
  Path to directory containing broker statement files. Must follow the standard directory structure (see FILES section).

**--date DATE**
  Processing date in YYYY-MM-DD format. Used for price lookups and output organization.

### Optional Arguments

**--broker BROKER**
  Process only the specified broker. Valid values include IB, HUATAI, SDICS, TIGER, MOOMOO, TFI, CICC, HTI, MS, GS. If not specified, all detected brokers are processed.

**--output DIR**  
  Output directory for converted images. Default: `./out/pictures`

**-f, --force**
  Force re-conversion of PDFs even if images already exist. Useful for reprocessing after template changes.

**--max-workers N**
  Maximum number of concurrent processing threads. Default: 10. Increase for faster processing on multi-core systems.

### Trade Confirmation Mode

**--use-tc**
  Enable trade confirmation mode for incremental portfolio updates. This mode uses trade confirmation files to update portfolio from a base date to the target date, useful when broker statements are delayed or incorrect.

**--base-date DATE**
  Base date for trade confirmation mode (YYYY-MM-DD format). If not specified, automatically uses the latest available portfolio date. This should be the date of the last complete broker statement.

**--tc-folder PATH**
  Path to trade confirmation folder. Default: `data/archives/TradeConfirmation`. Trade confirmation files must follow the naming convention: `TC-{YYYY-MM-DD}-{original_name}.xlsx`

## DIRECTORY STRUCTURE

FundMate supports two directory structures:

### Archive Mode (Recommended)

Organized by broker with date in filename:

```
data/archives/
├── IB/
│   ├── IB_2025-02-28_U9018171.pdf
│   ├── IB_2025-06-30_U9018171.pdf
│   └── IB_2025-07-31_U9018171.pdf
├── HUATAI/
│   ├── HUATAI_2025-02-28_20250228.pdf
│   └── HUATAI_2025-06-30_202506.pdf
├── MS/             # Excel broker
│   ├── MS_2025-02-28_OptionDaily.XLS
│   └── MS_2025-06-30_OptionDaily.XLS
├── TradeConfirmation/  # Trade confirmation files
│   ├── TC-2025-07-21-Asia Internal Trade Confirmation - 20250721.xlsx
│   ├── TC-2025-07-21-US Trading Confirmation 0721_2025.xlsx
│   ├── TC-2025-07-22-US Trading Confirmation 0722_2025.xlsx
│   └── TC-2025-09-22-Internal Trade Confirmation - 20250922.xlsx
└── ...
```

**Naming Convention**: `{BROKER}_{YYYY-MM-DD}_{ACCOUNT_ID}.{ext}`

**Benefits**:
- Centralized management by broker, no date directory fragmentation
- Filename contains complete information for easy lookup
- Supports multiple accounts (distinguished by account identifier)

### Statement Mode (Legacy)

Date-based directory structure:

```
data/20250228_Statement/
├── IB/
│   └── statement.pdf
├── HUATAI/
│   └── account.pdf
├── MS/
│   └── options.xlsx
└── ...
```

**Note**: 
- Both modes can coexist, program auto-detects
- Archive mode: pass `data/archives` path
- Statement mode: pass `data/YYYYMMDD_Statement` path

## EXAMPLES

### Basic Usage

**Archive Mode** (Recommended):
```bash
# Process all brokers for a specific date
python -m src.main data/archives --date 2025-02-28

# Process specific broker only
python -m src.main data/archives --date 2025-02-28 --broker IB

# Force reprocessing with higher concurrency  
python -m src.main data/archives --date 2025-02-28 -f --max-workers 8
```

**Statement Mode** (Legacy):
```bash
# Process date-specific directory
python -m src.main data/20250228_Statement --date 2025-02-28

# Process specific broker only
python -m src.main data/20250228_Statement --date 2025-02-28 --broker IB
```

### Advanced Usage
```bash
# Custom output directory
python -m src.main ./data/statements --date 2025-02-28 --output ./custom/images

# Debug single broker with detailed logging
python -m src.main ./data/statements --date 2025-02-28 --broker HUATAI --max-workers 1
```

### Trade Confirmation Mode

Use trade confirmation files to update portfolio when broker statements are delayed or incorrect:

```bash
# Auto-detect base date and update to target date
python -m src.main data/archives --date 2025-07-22 --use-tc

# Specify base date explicitly
python -m src.main data/archives --date 2025-07-22 --use-tc --base-date 2025-07-18

# Custom trade confirmation folder
python -m src.main data/archives --date 2025-07-22 --use-tc \
  --base-date 2025-07-18 \
  --tc-folder /custom/path/to/TradeConfirmation
```

**How it works**:
1. Loads the base portfolio from the specified (or auto-detected) base date
2. Applies all trade confirmations between base date and target date
3. Updates prices to the target date
4. Saves the updated portfolio

**Prerequisites**:
- Base portfolio must exist (run normal mode first for the base date)
- Trade confirmation files must be preprocessed with standard naming: `TC-{YYYY-MM-DD}-{original_name}.xlsx`
- Use `src/scripts/rename_trade_confirmations.py` to preprocess files if needed

## TRADE CONFIRMATION FILE PREPROCESSING

Trade confirmation files from different sources may have inconsistent naming. Use the preprocessing script to standardize them:

```bash
# Preview changes (dry-run)
python src/scripts/rename_trade_confirmations.py

# Execute renaming
python src/scripts/rename_trade_confirmations.py --execute

# Custom folder
python src/scripts/rename_trade_confirmations.py --folder /path/to/tc/files --execute
```

**Expected Excel Format**:
Trade confirmation files must contain these columns:
- `Trade Date`: Transaction date
- `Stock Code`: Symbol (e.g., "9988 HK", "TSLA")
- `BUY/SELL`: Transaction direction (BUY, SELL, or BUYCOVER)
- `Quantity`: Number of shares
- `Avg. Price`: Average execution price
- `Amount (USD)`: USD amount (cash impact)
- `Broker`: Broker name
- `Currency`: Original currency
- `Market/Exchange` (optional): Market identifier

## OUTPUT

FundMate generates three types of output:

### 1. Asset Summary Report
Console output showing:
- Broker list with data sources (PDF/Excel)
- Cash totals by currency and USD equivalent
- Position values with pricing success rate
- Grand total across all accounts

### 2. Structured Data Files
Saved to `./out/result/DATE/`:
- `cash_summary_DATE.parquet` - Cash holdings by broker and currency
- `positions_DATE.parquet` - Position data with market values and pricing details
- `portfolio_details_DATE.csv` - Human-readable portfolio report with all positions
- `metadata_DATE.json` - Processing metadata and exchange rates

### 3. Processing Logs
Detailed logs in `./log/DATE/fundmate.log` including:
- PDF conversion status
- LLM extraction results
- Price lookup attempts
- Error conditions and retries

## ENVIRONMENT

### Required Dependencies
- Python 3.8+
- Google Gemini API key (for LLM-powered data extraction)
- Futu OpenD (for real-time price data)
- Internet connection (for API access and exchange rates)

### Python Packages
```
akshare>=1.17.0       # Market data fallback
futu-api>=9.4.0       # Primary price data source (Futu OpenD)
pandas>=2.0.0         # Data manipulation
pydantic>=2.0.0       # Data validation
loguru>=0.7.0         # Logging
pdf2image>=1.16.0     # PDF conversion
openpyxl>=3.1.0       # Excel parsing
python-dotenv>=1.0.0  # Environment variables
requests>=2.28.0      # HTTP client for API calls
Pillow>=9.0.0         # Image processing
```

### System Requirements
- 4GB+ RAM (for concurrent LLM processing)
- 2GB+ disk space (for image conversion)
- Multi-core CPU recommended for `--max-workers > 10`
- Futu OpenD running locally (default: 127.0.0.1:11111)

## ENVIRONMENT VARIABLES

### Required
- `LLM_API_KEY` - Google Gemini API key
- `LLM_BASE_URL` - Gemini API endpoint URL
- `EXCHANGE_API_KEY` - Exchange rate API key (exchangerate.host)

### Optional
- `LLM_MODEL` - LLM model name (default: `gemini-2.5-pro`)
- `FUNDMATE_PRICE_SOURCE` - Price source: `futu` or `akshare` (default: `futu`)
- `FUTU_HOST` - Futu OpenD host (default: `127.0.0.1`)
- `FUTU_PORT` - Futu OpenD port (default: `11111`)
- `FUTU_TIMEOUT` - Futu API timeout in seconds (default: `30`)
- `FUNDMATE_OUTPUT_DIR` - Output directory (default: `./out`)
- `FUNDMATE_LOG_DIR` - Log directory (default: `./log`)

### .env File Example
Create a `.env` file in the project root:
```bash
# LLM Configuration (Google Gemini)
LLM_API_KEY=your_gemini_api_key_here
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta
LLM_MODEL=gemini-2.5-pro

# Exchange Rate API
EXCHANGE_API_KEY=your_exchange_rate_key_here

# Price Data Source (Futu OpenD)
FUNDMATE_PRICE_SOURCE=futu
FUTU_HOST=127.0.0.1
FUTU_PORT=11111

# Output Directories
FUNDMATE_OUTPUT_DIR=./out
FUNDMATE_LOG_DIR=./log
```

## PREREQUISITES

### Futu OpenD Setup (Required for Price Data)

FundMate uses Futu OpenD API for real-time stock and option prices. You must have Futu OpenD running before processing statements.

**Installation:**
1. Download Futu OpenD from [Futu Open API](https://www.futunn.com/download/OpenAPI)
2. Install and start Futu OpenD:
   ```bash
   ./FutuOpenD -addr 127.0.0.1 -port 11111
   ```
3. Verify connection (FundMate will connect automatically to `FUTU_HOST:FUTU_PORT`)

**Note**: If Futu OpenD is not running, price fetching will fail and positions will use broker-provided prices only.

## LIMITATIONS

### Price Data Coverage
- **Stock prices**: Supports US, HK, and China A-share markets via Futu API (with akshare fallback)
- **Options**: 
  - ✅ **US options** (via Futu API, OCC format)
  - ✅ **HK options** (via Futu API, HKATS format)
  - ✅ **OTC options** (uses broker-provided prices)
- **Delisted stocks**: Automatically uses broker price when historical API data unavailable
- **Money Market Funds**: Automatically detected and reclassified as cash (e.g., "CSOP USD Money Market Fund")

### Broker-specific Notes
- **MS/GS Excel**: Position-only data (no cash holdings in Excel statements)
- **PDF quality**: LLM extraction accuracy depends on statement image quality
- **MOOMOO**: Processes both securities and funds tables; MMF auto-detected

### Known Issues
- Futu API requires local OpenD instance running
- Some CN A-share options may fallback to broker prices
- Historical prices limited by Futu API data availability

Report bugs with detailed logs from `./log/DATE/fundmate.log`.

## DATA ARCHIVING TOOL

### Archive Existing Statements

FundMate provides an archiving tool to convert traditional `*_Statement` directory structure to archive mode:

```bash
# Dry run (preview operations)
python scripts/archive_statements.py --dry-run

# Execute archiving (copy files to data/archives)
python scripts/archive_statements.py

# Custom paths
python scripts/archive_statements.py --data-dir /path/to/data --archive-dir /path/to/archives
```

**Archiving Tool Features**:
- Automatically scans all `data/*_Statement/` directories
- Copies files to `data/archives/{BROKER}/` organized by broker
- Renames to standard format: `{BROKER}_{YYYY-MM-DD}_{ACCOUNT_ID}.{ext}`
- Intelligently extracts account IDs (supports all broker formats)
- Generates detailed archiving report

**Note**: The archiving tool only copies files without deleting originals for safety.

## FILES

### Input Files
- `BROKER_FOLDER/BROKER/*.pdf` - Broker PDF statements
- `BROKER_FOLDER/BROKER/*.xlsx` - Excel option statements (MS/GS)

### Output Files  
- `./out/pictures/DATE/BROKER/` - Converted PNG images
- `./out/result/DATE/` - Structured data files
- `./log/DATE/fundmate.log` - Processing logs

### Configuration
- `src/prompt_templates.py` - LLM extraction prompts per broker
- `src/price_fetcher.py` - Market data source configuration
- `src/config.py` - Global settings and environment variables
- `.env` - Environment variable configuration (not in repo)

## VERSION

This documentation corresponds to FundMate v1.0 - Production release with Excel integration.
