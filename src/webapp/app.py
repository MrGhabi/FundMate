"""
FundMate Web Application
A Flask-based web interface for viewing and analyzing financial portfolio data
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
import pandas as pd
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import threading
import uuid
from werkzeug.utils import secure_filename
import zipfile
import re
import math
import shutil

try:
    import rarfile
except ImportError:  # pragma: no cover
    rarfile = None

from src.config import settings
from src.metadata.detector import StatementMetadataDetector, iter_files
from src.metadata.organizer import MetadataRecord, organize_files

PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = PACKAGE_ROOT / 'templates'
STATIC_DIR = PACKAGE_ROOT / 'static'
ARCHIVE_DIR = Path('./data/archives')

app = Flask(
    __name__,
    template_folder=str(TEMPLATE_DIR),
    static_folder=str(STATIC_DIR),
)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB max file size for ZIP files
app.config['UPLOAD_FOLDER'] = Path('./temp/uploads')  # Keep all validation in temp
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'xlsx', 'xls', 'zip', 'rar'}
METADATA_LLM_ENABLED = os.getenv('ENABLE_METADATA_LLM', 'true').lower() == 'true'

# Create upload directory (temp-only for validation)
app.config['UPLOAD_FOLDER'].mkdir(parents=True, exist_ok=True)

# Processing job tracking
processing_jobs = {}
processing_lock = threading.Lock()

# Broker name patterns for automatic detection
BROKER_PATTERNS = {
    'IB': [r'ib[_\-\s]', r'interactive', r'ibkr'],
    'FUTU': [r'futu', r'富途'],
    'MOOMOO': [r'moomoo', r'moo[_\-\s]', r'富牛'],
    'CICC': [r'cicc'],
    'First Shanghai': [r'first[\s_\-]*shanghai', r'fssec'],
    'HTI': [r'\bhti\b', r'huatai[\s_\-]*international'],
    'HUATAI': [r'huatai', r'htsc'],
    'SDICS': [r'\bsdics\b'],
    'TFI': [r'\btfi\b', r'tianfeng'],
    'TIGER': [r'tiger'],
    'TenFund': [r'ten[\s_\-]*fund', r'tenfund'],
    'MS': [r'morgan[_\-\s]stanley', r'^ms[_\-\s]', r'摩根士丹利'],
    'GS': [r'goldman[_\-\s]sachs', r'^gs[_\-\s]', r'高盛'],
    'SC': [r'standard[_\-\s]chartered', r'^sc[_\-\s]', r'渣打'],
    'HSBC': [r'hsbc', r'汇丰'],
    'CS': [r'credit[_\-\s]suisse', r'^cs[_\-\s]', r'瑞信'],
    'LB': [r'longbridge', r'^lb[_\-\s]', r'长桥'],
    'SOFI': [r'sofi'],
    'UBS': [r'ubs', r'瑞银'],
    'WB': [r'webull', r'^wb[_\-\s]', r'微牛'],
}


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


SKIP_PARTS = {'__MACOSX'}
SKIP_NAMES = {'.DS_Store'}


def _safe_target_path(base_dir: Path, member_name: str) -> Path:
    """Prevent path traversal when extracting archives."""
    target_path = (base_dir / member_name).resolve()
    base_resolved = base_dir.resolve()
    if not str(target_path).startswith(str(base_resolved)):
        raise ValueError(f"Unsafe path detected in archive entry: {member_name}")
    return target_path


def _should_skip_member(name: str) -> bool:
    path_obj = Path(name)
    if any(part in SKIP_PARTS for part in path_obj.parts):
        return True
    if path_obj.name in SKIP_NAMES or path_obj.name.startswith('._'):
        return True
    return False


def extract_archive(archive_path: Path, extract_to: Path) -> list[Path]:
    """
    Extract ZIP/RAR archive safely into extract_to.
    Returns list of extracted file paths (allowed extensions only).
    """
    extracted_files: list[Path] = []
    extract_to.mkdir(parents=True, exist_ok=True)
    suffix = archive_path.suffix.lower()

    if suffix == '.zip':
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            for info in zip_ref.infolist():
                if info.is_dir():
                    continue
                if _should_skip_member(info.filename):
                    continue
                target = _safe_target_path(extract_to, info.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zip_ref.open(info) as src, open(target, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                if target.is_file() and allowed_file(target.name):
                    extracted_files.append(target)
        return extracted_files

    if suffix == '.rar':
        if rarfile is None:
            raise ValueError("RAR support requires 'rarfile' package to be installed")
        if rarfile.UNRAR_TOOL is None:
            # Try to default to system unrar if available
            rarfile.UNRAR_TOOL = shutil.which('unrar')
        with rarfile.RarFile(archive_path) as rar_ref:
            for info in rar_ref.infolist():
                if info.isdir():
                    continue
                if _should_skip_member(info.filename):
                    continue
                target = _safe_target_path(extract_to, info.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with rar_ref.open(info) as src, open(target, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                if target.is_file() and allowed_file(target.name):
                    extracted_files.append(target)
        return extracted_files

    raise ValueError(f"Unsupported archive type: {archive_path.suffix}")


def detect_broker_from_filename(filename: str) -> Optional[str]:
    """
    Automatically detect broker name from filename using pattern matching

    Args:
        filename: Name of the file to analyze

    Returns:
        Detected broker name (uppercase) or None if not detected
    """
    filename_lower = filename.lower()

    for broker, patterns in BROKER_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, filename_lower, re.IGNORECASE):
                return broker

    return None


def extract_zip_file(zip_path: Path, extract_to: Path) -> List[Path]:
    """
    Extract ZIP file and return list of extracted files

    Args:
        zip_path: Path to ZIP file
        extract_to: Directory to extract to

    Returns:
        List of paths to extracted files
    """
    extracted_files = []

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Get list of files in ZIP
            zip_files = zip_ref.namelist()

            for file_info in zip_files:
                # Skip directories and hidden files
                if file_info.endswith('/') or file_info.startswith('__MACOSX') or '/.DS_Store' in file_info:
                    continue

                # Extract file
                zip_ref.extract(file_info, extract_to)
                extracted_path = extract_to / file_info

                # Check if extracted file is allowed type
                if extracted_path.is_file() and allowed_file(extracted_path.name):
                    extracted_files.append(extracted_path)

        return extracted_files

    except zipfile.BadZipFile:
        raise ValueError(f"Invalid ZIP file: {zip_path.name}")
    except Exception as e:
        raise ValueError(f"Failed to extract ZIP file: {str(e)}")


def organize_files_by_broker(files: List[Path], date: str, base_dir: Path) -> Dict[str, List[Path]]:
    """
    Organize files by detected broker and move to appropriate directories

    Args:
        files: List of file paths to organize
        date: Statement date
        base_dir: Base upload directory

    Returns:
        Dictionary mapping broker names to list of file paths
    """
    broker_files = {}
    undetected_files = []

    for file_path in files:
        # Try to detect broker from filename
        broker = detect_broker_from_filename(file_path.name)

        if broker:
            if broker not in broker_files:
                broker_files[broker] = []

            # Create broker-specific directory
            broker_dir = base_dir / broker / date
            broker_dir.mkdir(parents=True, exist_ok=True)

            # Move file to broker directory
            new_path = broker_dir / file_path.name
            if file_path != new_path:
                import shutil
                shutil.move(str(file_path), str(new_path))
                file_path = new_path

            broker_files[broker].append(file_path)
        else:
            undetected_files.append(file_path)

    return broker_files, undetected_files


def update_job_status(job_id: str, status: str, message: str = None,
                     progress: int = None, error: str = None, result: dict = None):
    """Update processing job status"""
    with processing_lock:
        if job_id in processing_jobs:
            processing_jobs[job_id]['status'] = status
            if message:
                processing_jobs[job_id]['message'] = message
            if progress is not None:
                processing_jobs[job_id]['progress'] = progress
            if error:
                processing_jobs[job_id]['error'] = error
            if result:
                processing_jobs[job_id]['result'] = result


def process_multiple_brokers(job_id: str, broker_files: Dict[str, List[Path]], date: str, upload_base_dir: str):
    """
    Process statements from multiple brokers in background thread
    This function runs the main FundMate processing pipeline for all detected brokers
    """
    try:
        total_brokers = len(broker_files)
        processed_brokers = []
        failed_brokers = []

        update_job_status(job_id, 'processing', f'Starting batch processing for {total_brokers} broker(s)...', 5)

        # Import main processing module
        from src.main import main as process_main
        import sys

        # Process each broker sequentially
        for idx, (broker, files) in enumerate(broker_files.items(), 1):
            try:
                # Calculate progress based on broker index
                base_progress = int((idx - 1) / total_brokers * 90)
                broker_progress_range = int(90 / total_brokers)

                update_job_status(
                    job_id,
                    'processing',
                    f'Processing {broker} ({idx}/{total_brokers}) - {len(files)} file(s)...',
                    base_progress + 10
                )

                # Prepare arguments for main processor
                broker_folder = Path(upload_base_dir)

                # Call the main processing function
                old_argv = sys.argv
                try:
                    sys.argv = [
                        'web_app',
                        str(broker_folder),
                        '--date', date,
                        '--broker', broker,
                        '--max-workers', '5'
                    ]

                    update_job_status(
                        job_id,
                        'processing',
                        f'Extracting data for {broker} with LLM...',
                        base_progress + int(broker_progress_range * 0.5)
                    )

                    # Run the processing
                    process_main()

                    update_job_status(
                        job_id,
                        'processing',
                        f'Completed {broker} ({idx}/{total_brokers})...',
                        base_progress + broker_progress_range
                    )

                    processed_brokers.append(broker)

                finally:
                    sys.argv = old_argv

            except Exception as e:
                import traceback
                error_msg = str(e)
                failed_brokers.append({'broker': broker, 'error': error_msg})
                update_job_status(
                    job_id,
                    'processing',
                    f'Failed to process {broker}: {error_msg}. Continuing with others...',
                    base_progress + broker_progress_range
                )

        # Check if output was generated
        result_dir = Path(settings.result_dir) / date

        if result_dir.exists() and processed_brokers:
            result = {
                'date': date,
                'brokers': processed_brokers,
                'failed_brokers': failed_brokers,
                'output_dir': str(result_dir),
                'total_processed': len(processed_brokers),
                'total_failed': len(failed_brokers)
            }

            if failed_brokers:
                failed_list = ', '.join([fb.get('broker', '') for fb in failed_brokers])
                status_msg = f"Processed {len(processed_brokers)}/{total_brokers} broker(s). {len(failed_brokers)} failed: {failed_list}"
            else:
                status_msg = f"Successfully processed all {len(processed_brokers)} broker(s) for {date}"

            update_job_status(
                job_id,
                'completed' if not failed_brokers else 'partial',
                status_msg,
                100,
                result=result
            )
        else:
            failed_list = ', '.join([fb.get('broker', '') for fb in failed_brokers])
            update_job_status(
                job_id,
                'failed',
                'Processing completed but no output generated',
                100,
                error=f"Failed brokers: {failed_list}"
            )

    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback_str = traceback.format_exc()
        update_job_status(
            job_id,
            'failed',
            f'Batch processing failed: {error_msg}',
            100,
            error=traceback_str
        )


def get_available_dates() -> List[str]:
    """Get list of available dates with processed data"""
    result_dir = Path(settings.result_dir)
    if not result_dir.exists():
        return []

    dates = []
    for date_dir in sorted(result_dir.iterdir(), reverse=True):
        if date_dir.is_dir():
            # Verify it has the required files
            parquet_file = date_dir / f"cash_summary_{date_dir.name}.parquet"
            if parquet_file.exists():
                dates.append(date_dir.name)
    return dates


def load_portfolio_data(date: str) -> Dict:
    """Load portfolio data for a specific date"""
    date_dir = Path(settings.result_dir) / date

    if not date_dir.exists():
        return None

    data = {}

    # Load cash summary
    cash_file = date_dir / f"cash_summary_{date}.parquet"
    if cash_file.exists():
        data['cash'] = pd.read_parquet(cash_file)

    # Load positions
    positions_file = date_dir / f"positions_{date}.parquet"
    if positions_file.exists():
        data['positions'] = pd.read_parquet(positions_file)

    # Load metadata
    metadata_file = date_dir / f"metadata_{date}.json"
    if metadata_file.exists():
        with open(metadata_file, 'r') as f:
            data['metadata'] = json.load(f)

    return data


def run_date_pipeline(job_id: str, date: str, use_tc: bool = True):
    """Run main pipeline for a given date in background (optionally with TC)"""
    try:
        from src.main import main as process_main
        import sys

        update_job_status(
            job_id,
            'processing',
            f"Starting pipeline for {date} ({'with TC' if use_tc else 'base only'})",
            10
        )

        old_argv = sys.argv
        try:
            argv = [
                'web_app_date_run',
                str(ARCHIVE_DIR),
                '--date', date,
            ]
            if use_tc:
                argv.append('--use-tc')
            sys.argv = argv

            process_main()

            update_job_status(
                job_id,
                'processing',
                f"Finished pipeline for {date}, validating output...",
                90
            )
        finally:
            sys.argv = old_argv

        result_dir = Path(settings.result_dir) / date
        if result_dir.exists():
            update_job_status(
                job_id,
                'completed',
                f"Success: generated output for {date}",
                100,
                result={'date': date, 'output_dir': str(result_dir)}
            )
        else:
            update_job_status(
                job_id,
                'failed',
                f"Pipeline finished but no output found for {date}",
                100,
                error='Missing output directory'
            )
    except Exception as e:
        import traceback
        update_job_status(
            job_id,
            'failed',
            f"Pipeline failed: {e}",
            100,
            error=traceback.format_exc()
        )


@app.route('/')
def index():
    """Dashboard - main overview page"""
    available_dates = get_available_dates()

    # Allow free date selection; fall back to most recent available for display
    requested_date = request.args.get('date')
    selected_date = requested_date or (available_dates[0] if available_dates else datetime.now().strftime('%Y-%m-%d'))

    data = load_portfolio_data(selected_date)

    if not data:
        return render_template('no_data.html', selected_date=selected_date, available_dates=available_dates)

    # Calculate summary statistics
    summary = calculate_summary(data)

    return render_template('dashboard.html',
                         date=selected_date,
                         available_dates=available_dates,
                         summary=summary,
                         data=data)


@app.route('/positions')
def positions():
    """Detailed positions view"""
    available_dates = get_available_dates()

    if not available_dates:
        return render_template('no_data.html')

    selected_date = request.args.get('date', available_dates[0])
    broker_filter = request.args.get('broker', 'all')

    data = load_portfolio_data(selected_date)

    if not data or 'positions' not in data:
        return render_template('error.html', error="No positions data available")

    positions_df = data['positions'].copy()

    # Use broker_name column (actual column name in data)
    broker_col = 'broker_name' if 'broker_name' in positions_df.columns else 'broker'

    # Apply broker filter
    if broker_filter != 'all':
        positions_df = positions_df[positions_df[broker_col] == broker_filter]

    # Get unique brokers for filter dropdown
    brokers = sorted(data['positions'][broker_col].unique().tolist())

    # Normalize numeric fields
    positions_df['holding_num'] = pd.to_numeric(positions_df['holding'], errors='coerce').fillna(0)
    if 'position_value_usd' in positions_df.columns:
        positions_df['value_num'] = pd.to_numeric(positions_df['position_value_usd'], errors='coerce').fillna(0)
    else:
        positions_df['value_num'] = 0

    def _sig_round(value: float, sig: int = 3) -> float:
        if value is None:
            return None
        if value == 0:
            return 0.0
        magnitude = int(math.floor(math.log10(abs(value))))
        decimals = max(sig - 1 - magnitude, 0)
        return round(value, decimals)

    def _group_key(row) -> str:
        stock_code = (row.get('stock_code') or '') if isinstance(row, dict) else row.stock_code
        raw_desc = (row.get('raw_description') or '') if isinstance(row, dict) else row.raw_description
        upper_code = stock_code.upper() if isinstance(stock_code, str) else ''
        # Use raw_description as key for options/derivatives to avoid mis-merge
        if raw_desc and ('OPTION' in upper_code or 'OPTION' in raw_desc.upper()):
            return raw_desc
        return stock_code or raw_desc or 'UNKNOWN'

    positions_df['group_key'] = positions_df.apply(_group_key, axis=1)

    aggregated_positions = []
    for key, grp in positions_df.groupby('group_key'):
        grp_sorted = grp.sort_values(by='value_num', ascending=False)
        symbol = grp_sorted['stock_code'].dropna().iloc[0] if 'stock_code' in grp_sorted.columns else key
        description = grp_sorted['raw_description'].dropna().iloc[0] if 'raw_description' in grp_sorted.columns else ''
        total_holding = float(grp_sorted['holding_num'].sum())
        total_value = float(grp_sorted['value_num'].sum()) if 'position_value_usd' in grp_sorted.columns else None
        children = []
        best_price = None
        best_price_currency = None
        best_source = None
        for _, row in grp_sorted.iterrows():
            child_price = row.get('final_price')
            child_currency = row.get('optimized_price_currency') or row.get('broker_price_currency')
            child_source = row.get('final_price_source')
            children.append({
                'broker_name': row.get(broker_col, ''),
                'account_id': row.get('account_id', ''),
                'holding': float(row.get('holding_num', 0)),
                'final_price': child_price,
                'price_currency': child_currency,
                'final_price_source': child_source,
                'position_value_usd': row.get('position_value_usd'),
                'date': row.get('date')
            })
            # Prefer Futu price; otherwise first available price
            if child_price is not None:
                if best_source is None:
                    best_price = _sig_round(float(child_price), 3)
                    best_price_currency = child_currency
                    best_source = child_source
                elif best_source != 'Futu' and child_source == 'Futu':
                    best_price = _sig_round(float(child_price), 3)
                    best_price_currency = child_currency
                    best_source = child_source

        aggregated_positions.append({
            'key': key,
            'symbol': symbol or key,
            'description': description or key,
            'total_holding': total_holding,
            'total_value_usd': total_value,
            'broker_count': int(grp_sorted[broker_col].nunique()),
            # Aggregate row price: prefer Futu price if exists; else first available; no averaging
            'display_price': best_price,
            'display_price_currency': best_price_currency,
            'price_source': best_source,
            'children': children
        })

    # Sort aggregated list by total_value descending
    aggregated_positions.sort(key=lambda x: x['total_value_usd'] if x['total_value_usd'] is not None else 0, reverse=True)

    return render_template('positions.html',
                         date=selected_date,
                         available_dates=available_dates,
                         positions=positions_df.to_dict('records'),
                         aggregated_positions=aggregated_positions,
                         brokers=brokers,
                         selected_broker=broker_filter)


@app.route('/cash')
def cash():
    """Cash holdings view"""
    available_dates = get_available_dates()

    if not available_dates:
        return render_template('no_data.html')

    selected_date = request.args.get('date', available_dates[0])

    data = load_portfolio_data(selected_date)

    if not data or 'cash' not in data:
        return render_template('error.html', error="No cash data available")

    cash_df = data['cash'].copy()

    # Calculate totals by currency (from separate CNY/HKD/USD columns)
    cash_by_currency = {}
    accounts_by_currency = {}

    def _track_currency(column: str, code: str) -> None:
        if column in cash_df.columns:
            totals = cash_df[column].fillna(0)
            total_amount = float(totals.sum())
            if total_amount > 0:
                cash_by_currency[code] = total_amount
                accounts_by_currency[code] = int((totals.abs() > 0).sum())

    for column, code in [('cny', 'CNY'), ('hkd', 'HKD'), ('usd', 'USD')]:
        _track_currency(column, code)

    # Calculate totals by broker (use usd_total column)
    broker_col = 'broker_name' if 'broker_name' in cash_df.columns else 'broker'
    if 'usd_total' in cash_df.columns:
        cash_by_broker = (
            cash_df.groupby(broker_col)['usd_total']
            .sum()
            .sort_values(ascending=False)
            .to_dict()
        )
        # Drop zero/NaN brokers
        cash_by_broker = {k: float(v) for k, v in cash_by_broker.items() if v and v != float('nan')}
    else:
        cash_by_broker = {}

    # Clean NaNs and prepare records
    cash_list = cash_df.to_dict('records')
    cleaned_list = []
    for rec in cash_list:
        for key in ['cny', 'hkd', 'usd', 'usd_total']:
            val = rec.get(key)
            if val is None:
                continue
            try:
                if isinstance(val, str):
                    if val.lower() == 'nan':
                        rec[key] = None
                        continue
                    try:
                        num_val = float(val)
                        if num_val == 0 or math.isnan(num_val) or math.isinf(num_val):
                            rec[key] = None
                        else:
                            rec[key] = num_val
                        continue
                    except Exception:
                        rec[key] = None
                        continue
                if isinstance(val, (int, float)):
                    if val == 0 or math.isnan(val) or math.isinf(val):
                        rec[key] = None
                        continue
            except Exception:
                rec[key] = None

        if any(rec.get(k) not in (None, 0) for k in ['cny', 'hkd', 'usd', 'usd_total']):
            cleaned_list.append(rec)

    cash_list = cleaned_list

    metadata = data.get('metadata', {}) if isinstance(data, dict) else {}

    # Prepare exchange rates for display (USD base → other currency)
    exchange_rates_usd_base = {}
    if metadata and isinstance(metadata, dict):
        raw_rates = metadata.get('exchange_rates', {}) or {}
        for cur, rate in raw_rates.items():
            if not rate or cur is None:
                continue
            cur_code = str(cur).upper()
            if cur_code == 'USD':
                continue
            try:
                exchange_rates_usd_base[cur_code] = round(1 / float(rate), 4)
            except Exception:
                continue

    return render_template('cash.html',
                         date=selected_date,
                         available_dates=available_dates,
                         cash_list=cash_list,
                         cash_by_currency=cash_by_currency,
                         accounts_by_currency=accounts_by_currency,
                         cash_by_broker=cash_by_broker,
                         metadata=metadata,
                         exchange_rates_usd_base=exchange_rates_usd_base)


@app.route('/compare')
def compare():
    """Historical comparison view"""
    available_dates = get_available_dates()

    if len(available_dates) < 2:
        return render_template('error.html',
                             error="Need at least 2 dates for comparison")

    date1 = request.args.get('date1', available_dates[0] if len(available_dates) > 0 else None)
    date2 = request.args.get('date2', available_dates[1] if len(available_dates) > 1 else None)

    data1 = load_portfolio_data(date1)
    data2 = load_portfolio_data(date2)

    if not data1 or not data2:
        return render_template('error.html', error="Failed to load comparison data")

    comparison = calculate_comparison(data1, data2, date1, date2)

    return render_template('compare.html',
                         date1=date1,
                         date2=date2,
                         available_dates=available_dates,
                         comparison=comparison,
                         hide_date_selector=True)


@app.route('/about')
def about():
    """About page"""
    return render_template('about.html', hide_date_selector=True)


@app.route('/upload')
def upload_page():
    """File upload page"""
    return render_template('upload.html')


@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle file uploads: save → safe extract → metadata detect → organize (temp-only).

    Now uses background job + progress updates for real-time UI feedback.
    """
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400

    files = request.files.getlist('files')
    date = request.form.get('date') or None

    if not files or files[0].filename == '':
        return jsonify({'error': 'No files selected'}), 400

    # Validate file extensions (upload-time gate, archives allowed here)
    for file in files:
        if not allowed_file(file.filename):
            return jsonify({'error': f'File type not allowed: {file.filename}'}), 400

    job_id = str(uuid.uuid4())
    base_dir = app.config['UPLOAD_FOLDER'] / job_id
    incoming_dir = base_dir / 'incoming'
    raw_dir = base_dir / 'raw'
    organized_dir = base_dir / 'organized'
    unclassified_dir = base_dir / 'unclassified'
    for d in [incoming_dir, raw_dir, organized_dir, unclassified_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Try initialize LLM handler for PDF metadata; report if unavailable.
    llm_handler = None
    llm_error = None
    if METADATA_LLM_ENABLED:
        try:
            from src.llm_handler import LLMHandler
            llm_handler = LLMHandler()
        except Exception as exc:  # pragma: no cover - environment dependent
            llm_handler = None
            llm_error = str(exc)
    else:
        llm_error = "LLM metadata detection disabled via ENABLE_METADATA_LLM"

    detector = StatementMetadataDetector(llm_handler=llm_handler)
    saved_archives: list[Path] = []
    saved_regular: list[Path] = []

    def _run_metadata_job():
        try:
            with processing_lock:
                processing_jobs[job_id].update({
                    'status': 'processing',
                    'progress': 10,
                    'message': 'Extracting uploads...',
                })

            extracted_paths: list[Path] = []

            # Extract archives
            for archive_path in saved_archives:
                extracted_paths.extend(extract_archive(archive_path, raw_dir))

            # Copy regular files into raw_dir
            for file_path in saved_regular:
                target = raw_dir / file_path.name
                shutil.copy2(file_path, target)
                extracted_paths.append(target)

            candidate_files = iter_files(raw_dir)
            if not candidate_files:
                raise ValueError('No valid files found after extraction')

            total = len(candidate_files)
            detection_results = []
            recognized_records: list[MetadataRecord] = []
            unclassified_files: list[Path] = []
            error_count = 0

            for idx, path in enumerate(candidate_files, 1):
                try:
                    if path.suffix.lower() == '.pdf' and llm_handler is None:
                        raise RuntimeError(f"LLM handler unavailable for PDF metadata: {llm_error}")
                    md = detector.detect_file(path)
                except Exception as e:
                    detection_results.append({
                        'file': str(path),
                        'status': 'error',
                        'error': str(e),
                        'broker': None,
                        'account_id': None,
                        'statement_date': None,
                        'source': None,
                    })
                    unclassified_files.append(path)
                    error_count += 1
                else:
                    if md and md.broker_name and md.statement_date:
                        recognized_records.append(
                            MetadataRecord(
                                file=Path(md.file),
                                broker_name=md.broker_name,
                                account_id=md.account_id,
                                statement_date=md.statement_date,
                            )
                        )
                        detection_results.append({
                            'file': str(path),
                            'status': 'recognized',
                            'broker': md.broker_name,
                            'account_id': md.account_id,
                            'statement_date': md.statement_date,
                            'source': md.source,
                        })
                    else:
                        detection_results.append({
                            'file': str(path),
                            'status': 'unclassified',
                            'broker': md.broker_name if md else None,
                            'account_id': md.account_id if md else None,
                            'statement_date': md.statement_date if md else None,
                            'source': md.source if md else None,
                        })
                        unclassified_files.append(path)

                # Progress update
                with processing_lock:
                    processing_jobs[job_id]['progress'] = 10 + int(idx / total * 80)
                    processing_jobs[job_id]['message'] = f"Detecting metadata {idx}/{total}: {path.name}"

            # Organize recognized files into canonical names under temp/organized
            if recognized_records:
                organize_files(recognized_records, organized_dir, dry_run=False)

            # Move unclassified files into a dedicated folder for user review
            for path in unclassified_files:
                target = _safe_target_path(unclassified_dir, path.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                if path != target:
                    shutil.move(str(path), target)

            message = (
                f"Metadata detection finished. Recognized: {len(recognized_records)}, "
                f"Unclassified: {len(unclassified_files)}, Errors: {error_count}"
            )

            result_payload = {
                'organized_dir': str(organized_dir),
                'unclassified_dir': str(unclassified_dir),
                'recognized_count': len(recognized_records),
                'unclassified_count': len(unclassified_files),
                'detection_results': detection_results,
                'llm_error': llm_error,
                'error_count': error_count,
            }

            with processing_lock:
                processing_jobs[job_id].update({
                    'status': 'completed',
                    'message': message,
                    'progress': 100,
                    'result': result_payload,
                    'error': None,
                })

        except Exception as e:
            with processing_lock:
                processing_jobs[job_id].update({
                    'status': 'failed',
                    'error': str(e),
                    'message': f'Failed: {e}',
                    'progress': 100,
                })

    # Save uploads synchronously before background job (avoid closed file handles)
    try:
        for file in files:
            if not file or not file.filename:
                continue
            filename = secure_filename(file.filename)
            incoming_path = incoming_dir / filename
            file.save(str(incoming_path))
            if incoming_path.suffix.lower() in {'.zip', '.rar'}:
                saved_archives.append(incoming_path)
            else:
                saved_regular.append(incoming_path)
    except Exception as e:
        if base_dir.exists():
            shutil.rmtree(base_dir)
        return jsonify({'error': f'Failed to save uploads: {e}'}), 500

    # Initialize job before kicking off background detection
    with processing_lock:
        processing_jobs[job_id] = {
            'status': 'processing',
            'date': date,
            'created_at': datetime.now().isoformat(),
            'message': 'Queued',
            'result': None,
            'error': None,
            'job_type': 'metadata_only',
            'progress': 10,
        }

    # Start background thread
    thread = threading.Thread(target=_run_metadata_job, daemon=True)
    thread.start()

    return jsonify({
        'job_id': job_id,
        'status': 'processing',
        'message': 'Queued metadata detection',
        'progress': 5,
    })


@app.route('/api/jobs/<job_id>')
def get_job_status(job_id):
    """Get processing job status"""
    with processing_lock:
        job = processing_jobs.get(job_id)

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    return jsonify(job)


@app.route('/api/jobs')
def list_jobs():
    """List all processing jobs"""
    with processing_lock:
        jobs_list = [
            {
                'job_id': job_id,
                'broker': job.get('broker'),  # For old single-broker jobs
                'brokers': job.get('brokers'),  # For new multi-broker jobs
                'date': job.get('date'),
                'status': job.get('status'),
                'created_at': job.get('created_at'),
                'result': job.get('result'),
                'message': job.get('message')
            }
            for job_id, job in processing_jobs.items()
        ]

    # Sort by created_at descending
    jobs_list.sort(key=lambda x: x['created_at'], reverse=True)

    return jsonify(jobs_list)


@app.route('/api/date-status')
def api_date_status():
    """Check if data exists for a date"""
    date = request.args.get('date')
    if not date:
        return jsonify({'error': 'date required'}), 400
    date_dir = Path(settings.result_dir) / date
    exists = date_dir.exists() and (date_dir / f"cash_summary_{date}.parquet").exists()
    return jsonify({'date': date, 'exists': exists})


@app.route('/api/run-date', methods=['POST'])
def api_run_date():
    """Trigger pipeline for a date (with TC by default)"""
    date = request.args.get('date') or request.form.get('date')
    use_tc = (request.args.get('use_tc', 'true').lower() == 'true') or (request.form.get('use_tc', 'true').lower() == 'true')
    if not date:
        return jsonify({'error': 'date required'}), 400
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    job_id = str(uuid.uuid4())
    with processing_lock:
        processing_jobs[job_id] = {
            'status': 'pending',
            'date': date,
            'created_at': datetime.now().isoformat(),
            'message': 'Queued',
            'result': None,
            'error': None,
            'job_type': 'run_date',
            'use_tc': use_tc
        }

    thread = threading.Thread(target=run_date_pipeline, args=(job_id, date, use_tc))
    thread.daemon = True
    thread.start()

    return jsonify({'job_id': job_id, 'date': date, 'use_tc': use_tc, 'status': 'processing'})


@app.route('/api/summary/<date>')
def api_summary(date):
    """API endpoint for summary data"""
    data = load_portfolio_data(date)

    if not data:
        return jsonify({'error': 'Data not found'}), 404

    summary = calculate_summary(data)

    return jsonify(summary)


def calculate_summary(data: Dict) -> Dict:
    """Calculate portfolio summary statistics."""
    summary = {
        'total_cash_usd': 0.0,
        'total_positions_value_usd': 0.0,
        'total_portfolio_value_usd': 0.0,
        'broker_count': 0,
        'position_count': 0,
        'cash_by_currency': {},
        'top_positions': [],
        'cash_allocation_pct': 0.0,
        'positions_allocation_pct': 0.0
    }

    # Prepare exchange rates for optional currency conversion
    metadata = data.get('metadata', {}) if isinstance(data, dict) else {}
    exchange_rates = {}
    if isinstance(metadata, dict):
        exchange_rates = {
            (cur or '').upper(): rate
            for cur, rate in metadata.get('exchange_rates', {}).items()
            if rate not in (None, 0)
        }
    exchange_rates.setdefault('USD', 1.0)

    def convert_to_usd(amount: float, currency: Optional[str]) -> float:
        """Best-effort conversion helper that tolerates legacy rate formats."""
        if amount in (None, float('nan')):
            return 0.0
        currency_code = (currency or 'USD').upper()
        if currency_code == 'USD':
            return float(amount)

        rate = exchange_rates.get(currency_code)
        if rate is None or rate == 0:
            return float(amount)

        # Legacy datasets stored currency-per-USD (e.g. 7.85); detect and invert when needed.
        if rate > 1.0 and currency_code not in {'KWD', 'BHD', 'OMR', 'JOD', 'KYD', 'GIP'}:
            return float(amount) / rate

        return float(amount) * rate

    # Cash summary
    cash_df = data.get('cash')
    if cash_df is not None and not cash_df.empty:
        broker_col = 'broker_name' if 'broker_name' in cash_df.columns else 'broker'
        if broker_col in cash_df.columns:
            summary['broker_count'] = int(cash_df[broker_col].nunique())

        for currency_col, currency_code in [('cny', 'CNY'), ('hkd', 'HKD'), ('usd', 'USD')]:
            if currency_col in cash_df.columns:
                total_amount = float(cash_df[currency_col].fillna(0).sum())
                if total_amount:
                    summary['cash_by_currency'][currency_code] = total_amount

        if 'usd_total' in cash_df.columns:
            summary['total_cash_usd'] = float(cash_df['usd_total'].fillna(0).sum())

    # Positions summary
    positions_df = data.get('positions')
    if positions_df is not None and not positions_df.empty:
        positions_df = positions_df.copy()
        summary['position_count'] = len(positions_df)

        broker_col = 'broker_name' if 'broker_name' in positions_df.columns else 'broker'
        if broker_col in positions_df.columns:
            summary['broker_count'] = max(
                summary['broker_count'],
                int(positions_df[broker_col].nunique())
            )

        # Determine position USD values
        if 'position_value_usd' in positions_df.columns:
            positions_df['position_value_usd'] = pd.to_numeric(
                positions_df['position_value_usd'], errors='coerce'
            ).fillna(0.0)
        else:
            def compute_row_value(row):
                price = row.get('final_price') if 'final_price' in row else None
                price_currency = row.get('optimized_price_currency')
                if price is None and 'broker_price' in row:
                    price = row.get('broker_price')
                    price_currency = price_currency or row.get('broker_price_currency')

                if price is None:
                    return 0.0

                holding = row.get('holding', 0)
                multiplier = row.get('multiplier', 1)

                try:
                    holding_val = float(str(holding).replace(',', ''))
                except (ValueError, AttributeError):
                    holding_val = 0.0

                try:
                    price_val = float(price)
                except (ValueError, TypeError):
                    price_val = 0.0

                try:
                    multiplier_val = float(multiplier) if multiplier not in (None, '') else 1.0
                except (ValueError, TypeError):
                    multiplier_val = 1.0

                raw_value = holding_val * price_val * multiplier_val
                return convert_to_usd(raw_value, price_currency)

            positions_df['position_value_usd'] = positions_df.apply(compute_row_value, axis=1)

        summary['total_positions_value_usd'] = float(positions_df['position_value_usd'].sum())

        # Build top positions list
        if summary['total_positions_value_usd'] > 0:
            top_df = positions_df[
                positions_df['position_value_usd'] > 0
            ].copy()
            if not top_df.empty:
                top_df.sort_values('position_value_usd', ascending=False, inplace=True)
                top_df = top_df.head(10)
                total_portfolio_value = summary['total_positions_value_usd'] + summary['total_cash_usd']
                summary['top_positions'] = [
                    {
                        'symbol': row.get('stock_code') or row.get('symbol') or '',
                        'description': row.get('raw_description') or row.get('description') or '',
                        'broker': row.get('broker_name') or row.get('broker') or 'Unknown',
                        'quantity': row.get('holding', 0),
                        'market_value': float(row['position_value_usd']),
                        'portfolio_pct': (
                            (float(row['position_value_usd']) / total_portfolio_value * 100)
                            if total_portfolio_value else 0.0
                        )
                    }
                    for _, row in top_df.iterrows()
                ]

    summary['total_portfolio_value_usd'] = (
        summary['total_cash_usd'] + summary['total_positions_value_usd']
    )

    if summary['total_portfolio_value_usd'] > 0:
        summary['cash_allocation_pct'] = (
            summary['total_cash_usd'] / summary['total_portfolio_value_usd'] * 100
        )
        summary['positions_allocation_pct'] = (
            summary['total_positions_value_usd'] / summary['total_portfolio_value_usd'] * 100
        )

    return summary


def calculate_comparison(data1: Dict, data2: Dict, date1: str, date2: str) -> Dict:
    """Calculate comparison between two dates"""
    summary1 = calculate_summary(data1)
    summary2 = calculate_summary(data2)

    comparison = {
        'date1': date1,
        'date2': date2,
        'portfolio_change': summary1['total_portfolio_value_usd'] - summary2['total_portfolio_value_usd'],
        'portfolio_change_pct': 0,
        'cash_change': summary1['total_cash_usd'] - summary2['total_cash_usd'],
        'cash_change_pct': 0,
        'positions_change': summary1['total_positions_value_usd'] - summary2['total_positions_value_usd'],
        'positions_change_pct': 0,
        'position_count_change': summary1['position_count'] - summary2['position_count'],
        'summary1': summary1,
        'summary2': summary2
    }

    if summary2['total_portfolio_value_usd'] > 0:
        comparison['portfolio_change_pct'] = (
            (comparison['portfolio_change'] / summary2['total_portfolio_value_usd']) * 100
        )
    if summary2['total_cash_usd'] > 0:
        comparison['cash_change_pct'] = (
            (comparison['cash_change'] / summary2['total_cash_usd']) * 100
        )
    if summary2['total_positions_value_usd'] > 0:
        comparison['positions_change_pct'] = (
            (comparison['positions_change'] / summary2['total_positions_value_usd']) * 100
        )

    return comparison


@app.template_filter('format_currency')
def format_currency_filter(value, currency='USD'):
    """Format number as currency"""
    if value is None:
        return 'N/A'

    currency_symbols = {
        'USD': '$',
        'HKD': 'HK$',
        'CNY': '¥'
    }

    symbol = currency_symbols.get(currency, currency + ' ')

    return f"{symbol}{value:,.2f}"


@app.template_filter('format_number')
def format_number_filter(value):
    """Format number with thousands separator"""
    if value is None:
        return 'N/A'

    return f"{value:,.2f}"


@app.template_filter('format_percent')
def format_percent_filter(value):
    """Format number as percentage"""
    if value is None:
        return 'N/A'

    return f"{value:.2f}%"


if __name__ == '__main__':
    # Create necessary directories within the package for local development
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / 'css').mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / 'js').mkdir(parents=True, exist_ok=True)

    app.run(debug=True, host='0.0.0.0', port=5000)
