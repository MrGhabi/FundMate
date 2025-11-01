# FundMate Upload Feature Demo

## Quick Start

### 1. Start the Web Application

```bash
# Make sure you're in the project root directory
cd /Users/seven/Project/FundMate-1

# Start Futu OpenD (required for price data)
./tools/futu/FutuOpenD -addr 127.0.0.1 -port 11111

# In another terminal, start the web app
python web_app.py
```

Open your browser and navigate to: `http://localhost:5000`

### 2. Navigate to Upload Page

Click the **"Upload"** link in the navigation menu.

### 3. Upload Your Files

**Example 1: Single PDF Upload**
```
Broker Name: IB
Statement Date: 2025-02-28
Files: IB_Statement_Feb2025.pdf
```

**Example 2: Multiple Files Upload**
```
Broker Name: MOOMOO
Statement Date: 2025-02-28
Files:
  - MOOMOO_Cash.pdf
  - MOOMOO_Positions.pdf
  - MOOMOO_Transactions.pdf
```

**Example 3: Excel File Upload (for MS/GS options)**
```
Broker Name: MS
Statement Date: 2025-02-28
Files: MS_Options_Statement.xlsx
```

### 4. Monitor Processing

After clicking "Process Statements", you'll see:

```
Processing Status:
[=========>          ] 50%
Extracting data with LLM...
```

### 5. View Results

Once complete, you'll be redirected to the dashboard showing:
- Total portfolio value
- Cash by currency
- Position details
- Historical comparison

## Real-World Use Case

### Scenario: Monthly Portfolio Update

**Goal**: Process statements from multiple brokers for month-end review

**Steps**:

1. **Collect Statements**:
   - Download PDF statements from IB, FUTU, MOOMOO
   - Download Excel option statements from MS
   - Organize by broker

2. **Upload IB Statements**:
   ```
   Broker: IB
   Date: 2025-02-28
   Files: IB_Statement_Feb.pdf
   Status: ✓ Completed in 2 minutes
   ```

3. **Upload FUTU Statements**:
   ```
   Broker: FUTU
   Date: 2025-02-28
   Files: FUTU_Statement_Feb.pdf
   Status: ✓ Completed in 1.5 minutes
   ```

4. **Upload MOOMOO Statements**:
   ```
   Broker: MOOMOO
   Date: 2025-02-28
   Files: MOOMOO_Statement_Feb.pdf
   Status: ✓ Completed in 2.5 minutes
   ```

5. **Review Combined Portfolio**:
   - Navigate to Dashboard
   - Select date: 2025-02-28
   - View consolidated data from all brokers

## Visual Walkthrough

### Upload Page Screenshot Guide

```
┌─────────────────────────────────────────────────┐
│  Upload Broker Statements                       │
├─────────────────────────────────────────────────┤
│                                                  │
│  Broker Name: [IB____________]                  │
│  ℹ️ Supported: IB, FUTU, MOOMOO, MS, GS...      │
│                                                  │
│  Statement Date: [2025-02-28__]                 │
│  ℹ️ Select the statement date                    │
│                                                  │
│  Files:                                          │
│  ┌─────────────────────────────────────────┐   │
│  │         📁                              │   │
│  │  Drag and drop files here               │   │
│  │  or click to browse                      │   │
│  │  PDF, XLSX, XLS (Max 50MB)              │   │
│  └─────────────────────────────────────────┘   │
│                                                  │
│  Selected Files:                                 │
│  ✓ IB_Statement.pdf (2.3 MB)     [Remove]       │
│                                                  │
│  [Process Statements]                            │
│                                                  │
│  Processing...                                   │
│  [=========>     ] 50%                          │
│  Extracting data with LLM...                    │
│                                                  │
│  Recent Jobs:                                    │
│  ✓ IB - 2025-02-28 (Completed)                  │
│  ⚙️ FUTU - 2025-02-28 (Processing)               │
└─────────────────────────────────────────────────┘
```

## API Usage Examples

### Upload via cURL

```bash
# Upload a single PDF file
curl -X POST http://localhost:5000/upload \
  -F "files=@/path/to/IB_Statement.pdf" \
  -F "broker=IB" \
  -F "date=2025-02-28"

# Response:
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "processing",
  "message": "Processing 1 file(s) for IB"
}
```

### Check Job Status

```bash
# Check processing status
curl http://localhost:5000/api/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Response:
{
  "status": "processing",
  "broker": "IB",
  "date": "2025-02-28",
  "progress": 50,
  "message": "Extracting data with LLM...",
  "created_at": "2025-02-28T10:30:00",
  "result": null,
  "error": null
}
```

### Upload via Python

```python
import requests

# Upload file
files = {'files': open('IB_Statement.pdf', 'rb')}
data = {'broker': 'IB', 'date': '2025-02-28'}

response = requests.post(
    'http://localhost:5000/upload',
    files=files,
    data=data
)

job_id = response.json()['job_id']
print(f"Job ID: {job_id}")

# Poll for status
import time
while True:
    status_response = requests.get(
        f'http://localhost:5000/api/jobs/{job_id}'
    )
    job_status = status_response.json()

    print(f"Progress: {job_status['progress']}% - {job_status['message']}")

    if job_status['status'] in ['completed', 'failed']:
        break

    time.sleep(2)

print(f"Final status: {job_status['status']}")
```

## Troubleshooting Examples

### Problem: "Processing failed: No LLM API key"

**Solution**:
```bash
# Create or update .env file
echo "LLM_API_KEY=your_gemini_api_key" >> .env
echo "LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta" >> .env

# Restart web app
python web_app.py
```

### Problem: "Failed to get price for AAPL"

**Solution**:
```bash
# Check if Futu OpenD is running
ps aux | grep FutuOpenD

# If not running, start it
cd tools/futu
./FutuOpenD -addr 127.0.0.1 -port 11111
```

### Problem: "Upload failed: File too large"

**Solution**:
```python
# In web_app.py, increase the limit
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

# Or split large PDFs into smaller files
```

## Performance Tips

### For Large Uploads

1. **Process one broker at a time** to avoid overwhelming the system
2. **Use smaller page ranges** if PDFs are very large
3. **Monitor system resources** during processing

### Optimization Settings

```python
# In web_app.py, adjust worker count
sys.argv = [
    'web_app',
    str(broker_folder),
    '--date', date,
    '--broker', broker,
    '--max-workers', '10'  # Increase for faster processing
]
```

## Common Workflows

### Workflow 1: Monthly Batch Processing

```bash
# Day 1: Upload all statements
- IB → Upload
- FUTU → Upload
- MOOMOO → Upload

# Day 1: Review results
- Dashboard → Check totals
- Positions → Verify holdings
- Cash → Confirm balances

# Day 2: Compare with previous month
- Compare → Select current vs. previous month
- Review changes and trends
```

### Workflow 2: Single Broker Quick Check

```bash
# Upload statement
Broker: IB
Date: Today
Files: Latest_Statement.pdf

# Wait for processing (2-3 minutes)

# View results immediately on dashboard
```

### Workflow 3: Historical Data Entry

```bash
# Upload statements chronologically
Date: 2025-01-31 → IB, FUTU, MOOMOO
Date: 2025-02-28 → IB, FUTU, MOOMOO
Date: 2025-03-31 → IB, FUTU, MOOMOO

# Use compare feature to track growth
```

## Testing the Feature

### Test Case 1: Valid Upload
```
Input:
- Broker: IB
- Date: 2025-02-28
- File: Valid PDF (2MB)

Expected: ✓ Success
Result: Data appears in dashboard
```

### Test Case 2: Invalid File Type
```
Input:
- Broker: IB
- Date: 2025-02-28
- File: document.docx

Expected: ✗ Error
Result: "File type not allowed"
```

### Test Case 3: Missing Broker
```
Input:
- Broker: (empty)
- Date: 2025-02-28
- File: Valid PDF

Expected: ✗ Error
Result: "Broker name is required"
```

## Next Steps

After successful upload:

1. **View Dashboard**: Check the processed data summary
2. **Review Positions**: Verify all holdings are captured correctly
3. **Check Prices**: Ensure market prices are up-to-date
4. **Compare Dates**: Track portfolio changes over time
5. **Export Data**: Download CSV for further analysis

## Support

If you encounter issues:

1. Check browser console for JavaScript errors
2. Review server logs in `log/` directory
3. Verify all prerequisites are met (Futu OpenD, API keys)
4. Test with a small sample file first
5. Refer to WEB_UPLOAD_GUIDE.md for detailed documentation
