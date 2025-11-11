#!/bin/bash

# FundMate Web Application Launcher
# Usage: ./run_web.sh [port]

set -e

# Default port
PORT=${1:-5000}

echo "========================================="
echo "FundMate Web Application"
echo "========================================="
echo ""

# Check if Flask is installed
if ! python -c "import flask" 2>/dev/null; then
    echo "Error: Flask is not installed"
    echo "Please run: pip install -e .[web]"
    exit 1
fi

# Check if data directory exists
if [ ! -d "./out/result" ]; then
    echo "Warning: No result directory found at ./out/result"
    echo "Have you processed any broker statements yet?"
    echo ""
    echo "To process statements, run:"
    echo "  python -m src.main ./data/statements --date YYYY-MM-DD"
    echo ""
fi

# Check if Futu OpenD is running (optional check)
if ! nc -z 127.0.0.1 11111 2>/dev/null; then
    echo "Note: Futu OpenD does not appear to be running on port 11111"
    echo "This is only needed for processing new data, not for viewing existing data."
    echo ""
fi

echo "Starting FundMate Web Application on port $PORT..."
echo ""
echo "Access the application at: http://localhost:$PORT"
echo ""
echo "Press Ctrl+C to stop the server"
echo "========================================="
echo ""

# Start the Flask app inside the package
FLASK_ENV=development python -c "
from src.webapp.app import app
app.run(host='0.0.0.0', port=$PORT, debug=True)
"
