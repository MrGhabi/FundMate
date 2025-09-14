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
- **LLM-powered extraction**: Intelligent parsing of unstructured broker documents
- **Real-time pricing**: Live stock and option prices via akshare integration
- **Multi-currency**: Automatic currency conversion (USD, CNY, HKD)
- **Concurrent processing**: Parallel processing of multiple broker accounts
- **Data persistence**: Structured output in Parquet format

## SUPPORTED BROKERS

### PDF-based Brokers
- **IB** (Interactive Brokers)
- **HUATAI** 
- **SDICS**
- **TIGER** 
- **MOOMOO** 
- **TFI** 
- **CICC** 
- **HTI** 
- **First Shanghai** 

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
  Maximum number of concurrent processing threads. Default: 3. Increase for faster processing on multi-core systems.

## DIRECTORY STRUCTURE

FundMate expects a specific directory layout:

```
statements/
├── DATE/               # e.g., 2025-02-28/
│   ├── IB/
│   │   └── statement.pdf
│   ├── HUATAI/
│   │   └── account.pdf
│   ├── MS/             # Excel broker
│   │   └── options.xlsx
│   └── ...
```

For dated processing, the structure becomes:
```
statements/DATE/BROKER/files
```

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
- `cash_summary_DATE.parquet` - Cash holdings by broker
- `positions_DATE.parquet` - Position data with market values  
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
- OpenAI API key (for LLM processing)
- Internet connection (for price data and exchange rates)

### Python Packages
```
akshare>=1.11.0      # Chinese market data
openai>=1.0.0        # LLM processing  
pandas>=2.0.0        # Data manipulation
pydantic>=2.0.0      # Data validation
loguru>=0.7.0        # Logging
pdf2image>=1.16.0    # PDF conversion
```

### System Requirements
- 4GB+ RAM (for concurrent LLM processing)
- 2GB+ disk space (for image conversion)
- Multi-core CPU recommended for `--max-workers > 3`

## LIMITATIONS

### Price Data Coverage
- **Stock prices**: Supports US, HK, and China markets via akshare
- **Options**: Limited to Chinese domestic options; US/HK options show as unpriced
- **Delisted stocks**: Automatically detected and skipped (e.g., HK:04827)

### Broker-specific Notes
- **MOOMOO**: Requires PDF password "0592"
- **MS/GS Excel**: Position-only data (no cash holdings)
- **PDF quality**: OCR accuracy depends on statement image quality

Report bugs with detailed logs from `./log/DATE/fundmate.log`.

## FILES

### Input Files
- `BROKER_FOLDER/DATE/BROKER/*.pdf` - Broker PDF statements
- `BROKER_FOLDER/DATE/BROKER/*.xlsx` - Excel option statements (MS/GS)

### Output Files  
- `./out/pictures/DATE/BROKER/` - Converted PNG images
- `./out/result/DATE/` - Structured data files
- `./log/DATE/fundmate.log` - Processing logs

### Configuration
- `src/prompt_templates.py` - LLM extraction prompts per broker
- `src/price_fetcher.py` - Market data source configuration

## VERSION

This documentation corresponds to FundMate v1.0 - Production release with Excel integration.
