# FundMate Web Client

A Flask-based web interface for viewing and analyzing FundMate portfolio data.

## Features

### Dashboard
- **Portfolio Overview**: Total portfolio value, cash holdings, and positions summary
- **Top 10 Positions**: Largest holdings by market value
- **Cash Breakdown**: Holdings by currency with percentage distribution
- **Multi-broker Support**: View aggregated data across all broker accounts

### Positions View
- **Detailed Position Listing**: All holdings with symbol, description, quantity, price, and value
- **Advanced Filtering**: Filter by broker or search by symbol/description
- **Sortable Columns**: Click column headers to sort data
- **Export to CSV**: Download positions data for external analysis

### Cash Holdings
- **Currency Summary**: Total cash by currency (USD, HKD, CNY)
- **Broker Breakdown**: Cash distribution across all brokers
- **Exchange Rates**: Current USD exchange rates used in calculations
- **Visual Charts**: Bar charts showing cash distribution

### Historical Comparison
- **Date-to-Date Analysis**: Compare portfolio performance between any two dates
- **Change Tracking**: See changes in portfolio value, cash, and positions
- **Percentage Gains**: Calculate returns over time
- **Side-by-Side View**: Detailed metric comparison tables

## Installation

### 1. Install Dependencies

Using pip:
```bash
pip install -r requirements-web.txt
```

Or using conda (after installing main FundMate environment):
```bash
conda activate FundMate
pip install Flask==3.0.0 gunicorn==21.2.0
```

### 2. Ensure Data is Processed

Before running the web app, you need to process your broker statements:

```bash
# Make sure Futu OpenD is running
./FutuOpenD -addr 127.0.0.1 -port 11111

# Process statements for a specific date
python src/main.py ./data/statements --date 2025-02-28
```

This will generate data files in `./out/result/YYYY-MM-DD/`

## Running the Application

### Development Mode

For local development with auto-reload:

```bash
python web_app.py
```

The app will start at: **http://localhost:5000**

### Production Mode

For production deployment using Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 web_app:app
```

Options:
- `-w 4`: Number of worker processes (adjust based on CPU cores)
- `-b 0.0.0.0:5000`: Bind to all network interfaces on port 5000
- `--timeout 120`: Request timeout in seconds

## Configuration

### Environment Variables

Create a `.env` file or set these environment variables:

```bash
# Flask Configuration
FLASK_SECRET_KEY=your-secret-key-here  # Change in production!

# FundMate Data Paths (optional, defaults shown)
OUTPUT_DIR=./out
LOG_DIR=./log

# Price Source
FUNDMATE_PRICE_SOURCE=futu  # or 'akshare'

# Futu OpenD Configuration
FUTU_HOST=127.0.0.1
FUTU_PORT=11111
```

### Port Configuration

To run on a different port:

```python
# Edit web_app.py, line at bottom:
app.run(debug=True, host='0.0.0.0', port=8080)  # Change 5000 to 8080
```

Or using Gunicorn:
```bash
gunicorn -w 4 -b 0.0.0.0:8080 web_app:app
```

## Usage Guide

### 1. Navigate to Dashboard

Open **http://localhost:5000** in your browser to see the main dashboard with portfolio summary.

### 2. Select Date

Use the date dropdown at the top to switch between different processing dates. Only dates with processed data will appear.

### 3. View Positions

Click **"Positions"** in the navigation to see detailed holdings:
- Use the broker filter to show positions from specific brokers
- Use the search box to find specific symbols or descriptions
- Click column headers to sort the table
- Click "Export to CSV" to download the data

### 4. View Cash Holdings

Click **"Cash"** to see cash breakdown:
- View total cash by currency
- See cash distribution across brokers
- Check current exchange rates

### 5. Compare Dates

Click **"Compare"** to analyze changes over time:
- Select two dates to compare
- View portfolio value change and percentage return
- See detailed breakdown of changes by metric

## API Endpoints

The web app also provides a REST API:

### Get Summary Data
```bash
GET /api/summary/<date>
```

Example:
```bash
curl http://localhost:5000/api/summary/2025-02-28
```

Returns JSON with portfolio summary including total values, position counts, and top holdings.

## Directory Structure

```
FundMate-1/
├── web_app.py              # Main Flask application
├── web/
│   ├── templates/          # Jinja2 HTML templates
│   │   ├── base.html       # Base template with navigation
│   │   ├── dashboard.html  # Dashboard page
│   │   ├── positions.html  # Positions view
│   │   ├── cash.html       # Cash holdings view
│   │   ├── compare.html    # Comparison view
│   │   ├── no_data.html    # Empty state page
│   │   └── error.html      # Error page
│   └── static/             # Static assets
│       ├── css/
│       │   └── style.css   # Main stylesheet
│       └── js/
│           └── main.js     # JavaScript utilities
└── requirements-web.txt    # Web dependencies
```

## Features in Detail

### Responsive Design
- Mobile-friendly interface
- Automatically adjusts layout for different screen sizes
- Print-optimized styles for reports

### Data Visualization
- Color-coded positive/negative changes
- Bar charts for cash distribution
- Badge system for broker/position types
- Sortable tables with hover effects

### User Experience
- Keyboard shortcuts (Ctrl/Cmd + K for search, Esc to clear)
- Loading indicators for long operations
- Toast notifications for user actions
- Smooth animations and transitions

### Performance
- Efficient data loading from Parquet files
- Client-side filtering and sorting
- Minimal API calls
- Cached static assets

## Troubleshooting

### No Data Available

If you see "No Portfolio Data Available":
1. Ensure you've run the main FundMate processor
2. Check that data exists in `./out/result/YYYY-MM-DD/`
3. Verify Parquet files are present (cash_summary_*.parquet, positions_*.parquet)

### Port Already in Use

If port 5000 is already in use:
```bash
# Find process using port 5000
lsof -i :5000

# Kill the process
kill -9 <PID>

# Or use a different port
python web_app.py  # Edit to use different port
```

### Import Errors

If you get import errors:
```bash
# Ensure you're in the correct conda environment
conda activate FundMate

# Install missing dependencies
pip install -r requirements-web.txt

# Verify Flask is installed
python -c "import flask; print(flask.__version__)"
```

### Data Not Loading

If data appears empty in the web app:
1. Check browser console for JavaScript errors
2. Verify data files exist: `ls -la ./out/result/2025-02-28/`
3. Check Flask logs in terminal for errors
4. Ensure paths in `src/config.py` are correct

## Production Deployment

### Using Nginx as Reverse Proxy

1. Install Nginx:
```bash
sudo apt install nginx  # Ubuntu/Debian
brew install nginx      # macOS
```

2. Configure Nginx (`/etc/nginx/sites-available/fundmate`):
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /static {
        alias /path/to/FundMate-1/web/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

3. Enable and restart:
```bash
sudo ln -s /etc/nginx/sites-available/fundmate /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Running as System Service

Create a systemd service file (`/etc/systemd/system/fundmate-web.service`):

```ini
[Unit]
Description=FundMate Web Application
After=network.target

[Service]
User=your-username
WorkingDirectory=/path/to/FundMate-1
Environment="PATH=/path/to/conda/envs/FundMate/bin"
ExecStart=/path/to/conda/envs/FundMate/bin/gunicorn -w 4 -b 127.0.0.1:5000 web_app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable fundmate-web
sudo systemctl start fundmate-web
sudo systemctl status fundmate-web
```

## Security Considerations

### For Production:

1. **Change the secret key**: Set a strong `FLASK_SECRET_KEY` in environment variables
2. **Use HTTPS**: Configure SSL/TLS certificates with Nginx or use a service like Let's Encrypt
3. **Restrict access**: Use firewall rules or authentication to limit who can access the app
4. **Regular updates**: Keep Flask and dependencies updated
5. **Environment isolation**: Never run in debug mode in production

### Access Control

The current version does not include authentication. For production use, consider adding:
- Flask-Login for user authentication
- Role-based access control (RBAC)
- API key authentication for API endpoints
- IP whitelisting

## Contributing

To extend the web client:

1. **Add new routes**: Edit `web_app.py` and add new Flask routes
2. **Create templates**: Add HTML files in `web/templates/`
3. **Add styles**: Edit `web/static/css/style.css`
4. **Add JavaScript**: Edit `web/static/js/main.js`

## Support

For issues related to the web client:
1. Check the Flask logs in the terminal
2. Check browser console for JavaScript errors
3. Verify data files are generated correctly by the main FundMate processor
4. Review the main CLAUDE.md for FundMate architecture details

## License

Same as FundMate main project.
