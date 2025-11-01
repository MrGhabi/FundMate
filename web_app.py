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

from src.config import settings

app = Flask(__name__,
            template_folder='web/templates',
            static_folder='web/static')

# Configuration
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB max file size for ZIP files
app.config['UPLOAD_FOLDER'] = Path('./data/uploads')
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'xlsx', 'xls', 'zip'}

# Create upload directory
app.config['UPLOAD_FOLDER'].mkdir(parents=True, exist_ok=True)

# Processing job tracking
processing_jobs = {}
processing_lock = threading.Lock()

# Broker name patterns for automatic detection
BROKER_PATTERNS = {
    'IB': [r'ib[_\-\s]', r'interactive', r'ibkr'],
    'FUTU': [r'futu', r'富途'],
    'MOOMOO': [r'moomoo', r'moo[_\-\s]', r'富牛'],
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
                status_msg = f'Processed {len(processed_brokers)}/{total_brokers} broker(s). {len(failed_brokers)} failed: {", ".join([fb["broker"] for fb in failed_brokers])}'
            else:
                status_msg = f'Successfully processed all {len(processed_brokers)} broker(s) for {date}'

            update_job_status(
                job_id,
                'completed' if not failed_brokers else 'partial',
                status_msg,
                100,
                result=result
            )
        else:
            update_job_status(
                job_id,
                'failed',
                'Processing completed but no output generated',
                100,
                error=f'Failed brokers: {", ".join([fb["broker"] for fb in failed_brokers])}'
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


@app.route('/')
def index():
    """Dashboard - main overview page"""
    available_dates = get_available_dates()

    if not available_dates:
        return render_template('no_data.html')

    # Use the most recent date by default
    selected_date = request.args.get('date', available_dates[0])

    if selected_date not in available_dates:
        selected_date = available_dates[0]

    data = load_portfolio_data(selected_date)

    if not data:
        return render_template('error.html', error="Failed to load portfolio data")

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

    # Convert to records for template
    positions_list = positions_df.to_dict('records')

    return render_template('positions.html',
                         date=selected_date,
                         available_dates=available_dates,
                         positions=positions_list,
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
        cash_by_broker = cash_df.groupby(broker_col)['usd_total'].sum().to_dict()
    else:
        cash_by_broker = {}

    cash_list = cash_df.to_dict('records')

    return render_template('cash.html',
                         date=selected_date,
                         available_dates=available_dates,
                         cash_list=cash_list,
                         cash_by_currency=cash_by_currency,
                         accounts_by_currency=accounts_by_currency,
                         cash_by_broker=cash_by_broker,
                         metadata=data.get('metadata', {}))


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
                         comparison=comparison)


@app.route('/about')
def about():
    """About page"""
    return render_template('about.html')


@app.route('/upload')
def upload_page():
    """File upload page"""
    return render_template('upload.html')


@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle file uploads and initiate processing - supports batch upload with auto-detection"""
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400

    files = request.files.getlist('files')
    date = request.form.get('date')
    auto_detect = request.form.get('auto_detect', 'true').lower() == 'true'
    manual_broker = request.form.get('broker', '').upper() if not auto_detect else None

    # Validate inputs
    if not files or files[0].filename == '':
        return jsonify({'error': 'No files selected'}), 400

    if not date:
        return jsonify({'error': 'Date is required'}), 400

    # Validate date format
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    # Validate file extensions
    for file in files:
        if not allowed_file(file.filename):
            return jsonify({'error': f'File type not allowed: {file.filename}'}), 400

    # Create job ID
    job_id = str(uuid.uuid4())

    # Create temporary upload directory
    temp_dir = app.config['UPLOAD_FOLDER'] / 'temp' / job_id
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Save and process uploaded files
    all_files = []
    zip_files = []

    try:
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                filepath = temp_dir / filename
                file.save(str(filepath))

                # Check if it's a ZIP file
                if filename.lower().endswith('.zip'):
                    zip_files.append(filepath)
                else:
                    all_files.append(filepath)

        # Extract ZIP files
        for zip_path in zip_files:
            try:
                extracted = extract_zip_file(zip_path, temp_dir)
                all_files.extend(extracted)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400

        if not all_files:
            return jsonify({'error': 'No valid files found (after extracting ZIPs)'}), 400

        # Organize files by broker
        if auto_detect:
            broker_files, undetected = organize_files_by_broker(
                all_files, date, app.config['UPLOAD_FOLDER']
            )

            if undetected:
                undetected_names = [f.name for f in undetected]
                return jsonify({
                    'error': f'Could not detect broker for files: {", ".join(undetected_names)}. '
                             'Please rename files to include broker name or use manual mode.'
                }), 400

            if not broker_files:
                return jsonify({'error': 'No broker could be detected from filenames'}), 400

        else:
            # Manual mode - use provided broker name
            if not manual_broker:
                return jsonify({'error': 'Broker name is required when auto-detect is disabled'}), 400

            broker_dir = app.config['UPLOAD_FOLDER'] / manual_broker / date
            broker_dir.mkdir(parents=True, exist_ok=True)

            # Move all files to broker directory
            import shutil
            for file_path in all_files:
                new_path = broker_dir / file_path.name
                shutil.move(str(file_path), str(new_path))

            broker_files = {manual_broker: all_files}

        # Initialize job status
        with processing_lock:
            processing_jobs[job_id] = {
                'status': 'pending',
                'brokers': list(broker_files.keys()),
                'date': date,
                'broker_files': {broker: [str(f) for f in files] for broker, files in broker_files.items()},
                'progress': 0,
                'message': 'Job queued',
                'created_at': datetime.now().isoformat(),
                'result': None,
                'error': None,
                'auto_detect': auto_detect
            }

        # Start processing in background thread
        thread = threading.Thread(
            target=process_multiple_brokers,
            args=(job_id, broker_files, date, str(app.config['UPLOAD_FOLDER']))
        )
        thread.daemon = True
        thread.start()

        broker_list = ', '.join(broker_files.keys())
        total_files = sum(len(files) for files in broker_files.values())

        return jsonify({
            'job_id': job_id,
            'status': 'processing',
            'brokers': list(broker_files.keys()),
            'message': f'Processing {total_files} file(s) for {len(broker_files)} broker(s): {broker_list}'
        })

    except Exception as e:
        # Clean up temp directory on error
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500


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
                'date': job['date'],
                'status': job['status'],
                'created_at': job['created_at']
            }
            for job_id, job in processing_jobs.items()
        ]

    # Sort by created_at descending
    jobs_list.sort(key=lambda x: x['created_at'], reverse=True)

    return jsonify(jobs_list)


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
        'positions_change': summary1['total_positions_value_usd'] - summary2['total_positions_value_usd'],
        'position_count_change': summary1['position_count'] - summary2['position_count'],
        'summary1': summary1,
        'summary2': summary2
    }

    if summary2['total_portfolio_value_usd'] > 0:
        comparison['portfolio_change_pct'] = (
            (comparison['portfolio_change'] / summary2['total_portfolio_value_usd']) * 100
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
    # Create necessary directories
    Path('web/templates').mkdir(parents=True, exist_ok=True)
    Path('web/static/css').mkdir(parents=True, exist_ok=True)
    Path('web/static/js').mkdir(parents=True, exist_ok=True)

    app.run(debug=True, host='0.0.0.0', port=5000)
