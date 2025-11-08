# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FundMate is a production-ready financial data processor that extracts cash holdings and position data from broker statements using LLM-powered data extraction. It processes both PDF statements (image-based) and Excel files (structured data) from 12+ different brokers, providing real-time asset valuation with market prices.

## Running the Application

### Basic Command
```bash
python src/main.py BROKER_FOLDER --date YYYY-MM-DD
```

### Common Development Commands
```bash
# Process all brokers for a specific date
python src/main.py ./data/statements --date 2025-02-28

# Process specific broker only
python src/main.py ./data/statements --date 2025-02-28 --broker IB

# Force reprocessing with higher concurrency
python src/main.py ./data/statements --date 2025-02-28 -f --max-workers 8

# Custom output directory
python src/main.py ./data/statements --date 2025-02-28 --output ./custom/images
```

### Prerequisites
1. **Futu OpenD** must be running for real-time price data:
   ```bash
   ./FutuOpenD -addr 127.0.0.1 -port 11111
   ```

2. **Environment variables** must be configured in `.env`:
   - `LLM_API_KEY` - Google Gemini API key
   - `LLM_BASE_URL` - Gemini API endpoint
   - `EXCHANGE_API_KEY` - Exchange rate API key

## Architecture Overview

### Core Processing Pipeline
1. **PDF Processing** (`pdf_processor.py`) - Handles PDF decryption, page filtering, and preparation
2. **LLM Extraction** (`llm_handler.py`) - Uses Google Gemini to extract structured data from PDFs
3. **Excel Parsing** (`excel_parser.py`) - Processes Excel option statements from MS/GS brokers
4. **Price Fetching** (`price_fetcher.py`) - Retrieves real-time market prices via Futu OpenD API
5. **Data Orchestration** (`broker_processor.py`) - Coordinates the entire workflow with concurrent processing

### Data Flow
```
Input PDFs/Excel → PDF Processing → LLM Extraction → Price Fetching → Cross-Broker Optimization → Output (Parquet/CSV)
```

### Key Design Principles
- **Concurrent Processing**: Uses ThreadPoolExecutor with configurable workers (default: 10) for parallel broker processing
- **Price Optimization**: Batch queries unique symbols across all brokers to minimize API calls
- **Intelligent Multipliers**: Handles options correctly - OTC options use 1x, standard options use 100x, broker-provided multipliers have highest priority
- **Multi-Currency Support**: Automatic conversion with recalculated totals (USD, CNY, HKD)

## Important Implementation Details

### Broker-Specific Processing
Each broker has unique PDF structure requiring custom prompts in `src/prompt_templates.py`. The `PROMPT_TEMPLATES` dictionary maps broker names to extraction instructions that guide the LLM on where to find cash and position data.

**Broker PDF configurations** are in `BROKER_CONFIG` dict in `pdf_processor.py`:
- Password protection (MOOMOO, LB)
- Page filtering rules (remove disclosure pages)
- Advanced filtering for complex statements (MOOMOO has special threshold-based filtering)

### Option Contract Handling
The system handles three types of options with different multiplier logic:

1. **Broker-provided multiplier** (Priority 1) - Trust broker's explicit multiplier field
2. **OTC options** - Always use 1x multiplier (identified by "OTC" in description)
3. **HK options** - Use 100x fallback (HKATS format: "CLI 250929 19.00 CALL")
4. **US options** - Use 100x standard multiplier (OCC format: "AMZN US 06/18/26 C300")

Helper functions in `utils.py`:
- `is_option_contract()` - Detects if position is an option
- `get_option_multiplier()` - Returns correct multiplier with priority logic
- `_identify_hk_option()` - Identifies HK options by HKATS code pattern

### Price Fetching Strategy
Located in `price_fetcher.py` with two-tier fallback:
1. **Primary**: Futu OpenD API (configurable via `FUNDMATE_PRICE_SOURCE=futu`)
2. **Fallback**: akshare library (set `FUNDMATE_PRICE_SOURCE=akshare`)

Price resolution priority:
1. Optimized API price (from cross-broker batch query)
2. Broker-provided price (from statement)
3. Failed pricing (position value = 0)

### Cross-Broker Optimization
The `_optimize_cross_broker_pricing()` method in `broker_processor.py`:
1. Aggregates unique symbols across all brokers
2. Batch queries prices once per unique symbol
3. Distributes optimized prices to all positions with that symbol
4. Recalculates position values with correct multipliers

This prevents redundant API calls when the same stock appears in multiple broker accounts.

### Money Market Fund Detection
The system automatically detects and reclassifies Money Market Funds as cash:
- Detection: `is_money_market_fund()` checks for "money market fund" in description
- Example: "CSOP USD Money Market Fund" is treated as cash, not a position
- This affects total cash calculations and position counts

### Concurrent Processing Model
Brokers are processed concurrently with `ThreadPoolExecutor`:
- Each PDF file becomes a separate task
- Tasks run in parallel up to `max_workers` limit
- Progress tracking shows completion status: `✅ [3/10] IB/U12345 processed`
- Failed tasks are logged but don't halt overall processing

## Configuration System

### Centralized Settings (`config.py`)
All configuration uses the singleton `settings` object:
```python
from config import settings

# Directory paths
settings.OUTPUT_DIR      # Default: './out'
settings.LOG_DIR         # Default: './log'
settings.pictures_dir    # Computed: './out/pictures'
settings.result_dir      # Computed: './out/result'

# Price source
settings.PRICE_SOURCE    # 'futu' or 'akshare'

# Futu API
settings.FUTU_HOST       # Default: '127.0.0.1'
settings.FUTU_PORT       # Default: 11111
settings.FUTU_TIMEOUT    # Default: 30 seconds
```

### LLM Configuration
Google Gemini API configured via environment variables:
- Model: `gemini-2.5-pro` (default)
- Temperature: 0 (deterministic extraction)
- Max tokens: 8192
- Retry logic: 5 attempts with automatic retry on failure

## Output Structure

### Generated Files
All outputs are organized by date in `./out/result/DATE/`:
- `cash_summary_DATE.parquet` - Cash holdings by broker and currency
- `positions_DATE.parquet` - Position data with market values
- `portfolio_details_DATE.csv` - Human-readable portfolio report
- `metadata_DATE.json` - Processing metadata and exchange rates

### Logging
Timestamped logs in `./log/DATE/fundmate_YYYYMMDD_HHMMSS.log` include:
- PDF processing status
- LLM extraction results
- Price lookup attempts and sources
- Error conditions and retry attempts
- Full traceback for debugging

## Common Development Patterns

### Adding a New Broker
1. Add broker to supported list in README.md
2. Create prompt template in `src/prompt_templates.py`:
   ```python
   "NEWBROKER": [{"type": "text", "text": "Extract instructions..."}]
   ```
3. Add PDF config in `pdf_processor.py` if needed:
   ```python
   'NEWBROKER': {'remove_last_pages': 1, 'min_pages': 2}
   ```
4. Test with sample PDF: `python src/main.py ./test_data --date 2025-02-28 --broker NEWBROKER`

### Modifying Price Fetching Logic
Price fetching is in `price_fetcher.py`:
- `get_stock_price()` - Main entry point for price queries
- `get_price_futu()` - Futu OpenD implementation
- `get_price_akshare()` - Akshare fallback
- Option pricing uses specialized helpers: `us_option_price_helper.py` and `hk_option_price_helper.py`

### Working with the LLM Handler
The LLM handler (`llm_handler.py`) processes both images and PDFs:
- `process_pdfs_with_prompt()` - For direct PDF processing (current method)
- `process_images_with_prompt()` - For pre-converted PNG images
- Response parsing handles both pure JSON and Markdown-wrapped JSON

### Exchange Rate Handling
Exchange rates are fetched once per date via `exchange_rate_handler.py`:
- Rates are from USD to target currency (CNY, HKD)
- Lazy loading: rates fetched on-demand and cached
- Fallback: if API fails, processing continues with broker prices only

## Key File Locations

- **Main entry point**: `src/main.py`
- **Core orchestration**: `src/broker_processor.py`
- **PDF processing**: `src/pdf_processor.py`
- **LLM extraction**: `src/llm_handler.py`
- **Price fetching**: `src/price_fetcher.py`
- **Excel parsing**: `src/excel_parser.py`
- **Configuration**: `src/config.py`
- **Broker prompts**: `src/prompt_templates.py`
- **Utilities**: `src/utils.py`

## Testing Notes

### Manual Testing Workflow
1. Prepare test data in `./data/statements/BROKER/` directory
2. Ensure Futu OpenD is running
3. Run with single broker: `python src/main.py ./data/statements --date 2025-02-28 --broker TESTBROKER --max-workers 1`
4. Check logs in `./log/DATE/fundmate_*.log`
5. Verify output in `./out/result/DATE/`

### Debugging Tips
- Use `--max-workers 1` to disable concurrency for easier debugging
- Check `./out/pdfs/DATE/BROKER/ACCOUNT/` for processed PDFs (cached)
- LLM extraction failures are logged with full API response
- Price lookup failures fall back to broker prices automatically
- Use `logger.debug()` statements - they appear in log files only, not console
