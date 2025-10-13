# FundMate

**Automated broker statement processor with LLM-powered data extraction**

## SYNOPSIS

```
python src/main.py BROKER_FOLDER --date DATE [OPTIONS]
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

## DIRECTORY STRUCTURE

FundMate expects broker statements organized by broker:

```
statements/
├── IB/
│   └── statement.pdf
├── HUATAI/
│   └── account.pdf
├── LB/
│   └── account.pdf
├── MS/             # Excel broker
│   └── options.xlsx
└── ...
```

**Note**: Date is specified via `--date` parameter, not through directory structure.

## EXAMPLES

### Basic Usage
```bash
# Process all brokers for a specific date
python src/main.py ./data/statements --date 2025-02-28

# Process specific broker only
python src/main.py ./data/statements --date 2025-02-28 --broker IB

# Force reprocessing with higher concurrency  
python src/main.py ./data/statements --date 2025-02-28 -f --max-workers 8
```

### Advanced Usage
```bash
# Custom output directory
python src/main.py ./data/statements --date 2025-02-28 --output ./custom/images

# Debug single broker with detailed logging
python src/main.py ./data/statements --date 2025-02-28 --broker HUATAI --max-workers 1
```

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
