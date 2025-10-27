"""
FundMate Web Application
A Flask-based web interface for viewing and analyzing financial portfolio data
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
import pandas as pd
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import json

from src.config import settings

app = Flask(__name__,
            template_folder='web/templates',
            static_folder='web/static')

# Configuration
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size


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
    if 'cny' in cash_df.columns:
        total_cny = cash_df['cny'].sum()
        if total_cny > 0:
            cash_by_currency['CNY'] = total_cny

    if 'hkd' in cash_df.columns:
        total_hkd = cash_df['hkd'].sum()
        if total_hkd > 0:
            cash_by_currency['HKD'] = total_hkd

    if 'usd' in cash_df.columns:
        total_usd = cash_df['usd'].sum()
        if total_usd > 0:
            cash_by_currency['USD'] = total_usd

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


@app.route('/api/summary/<date>')
def api_summary(date):
    """API endpoint for summary data"""
    data = load_portfolio_data(date)

    if not data:
        return jsonify({'error': 'Data not found'}), 404

    summary = calculate_summary(data)

    return jsonify(summary)


def calculate_summary(data: Dict) -> Dict:
    """Calculate portfolio summary statistics"""
    summary = {
        'total_cash_usd': 0,
        'total_positions_value_usd': 0,
        'total_portfolio_value_usd': 0,
        'broker_count': 0,
        'position_count': 0,
        'cash_by_currency': {},
        'top_positions': []
    }

    # Cash summary - adapted for actual data structure
    if 'cash' in data:
        cash_df = data['cash']

        # Use broker_name column (actual column name in data)
        broker_col = 'broker_name' if 'broker_name' in cash_df.columns else 'broker'
        summary['broker_count'] = cash_df[broker_col].nunique()

        # Sum cash by currency from separate columns
        if 'cny' in cash_df.columns:
            total_cny = cash_df['cny'].sum()
            if total_cny > 0:
                summary['cash_by_currency']['CNY'] = float(total_cny)

        if 'hkd' in cash_df.columns:
            total_hkd = cash_df['hkd'].sum()
            if total_hkd > 0:
                summary['cash_by_currency']['HKD'] = float(total_hkd)

        if 'usd' in cash_df.columns:
            total_usd = cash_df['usd'].sum()
            if total_usd > 0:
                summary['cash_by_currency']['USD'] = float(total_usd)

        # If usd_total column exists, use it directly
        if 'usd_total' in cash_df.columns:
            summary['total_cash_usd'] = float(cash_df['usd_total'].sum())

    # Positions summary - adapted for actual data structure
    if 'positions' in data:
        positions_df = data['positions']
        summary['position_count'] = len(positions_df)

        # Since positions data structure is simple (just stock_code and holding),
        # we can't calculate market values without additional processing
        # Just track the count for now
        broker_col = 'broker_name' if 'broker_name' in positions_df.columns else 'broker'
        if broker_col in positions_df.columns:
            # Update broker count if positions have more brokers than cash
            summary['broker_count'] = max(
                summary['broker_count'],
                positions_df[broker_col].nunique()
            )

    summary['total_portfolio_value_usd'] = (
        summary['total_cash_usd'] + summary['total_positions_value_usd']
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
