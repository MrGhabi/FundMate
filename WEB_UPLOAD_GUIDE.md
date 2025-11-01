# FundMate Web Upload Feature Guide

## Overview

The FundMate web application now includes a file upload feature that allows users to upload broker statements (PDF or Excel files) directly through the web interface and process them automatically.

## Features

### 1. File Upload Interface
- **Drag-and-drop** file upload zone
- **Multiple file selection** support
- **File validation**: Only PDF, XLSX, and XLS files are accepted
- **Maximum file size**: 50MB per upload
- **Visual feedback** for file selection and upload status

### 2. Processing Configuration
- **Broker Name**: Specify which broker the statement is from
  - Supported: IB, FUTU, MOOMOO, MS, GS, SC, HSBC, CS, LB, SOFI, UBS, WB
- **Statement Date**: Select the date the statement applies to (YYYY-MM-DD format)

### 3. Background Processing
- Files are processed in a **background thread**
- **Real-time progress tracking** with percentage and status messages
- **Job history** showing recent processing tasks
- Automatic **dashboard redirect** upon successful completion

### 4. Job Status Tracking
- Visual progress bar showing processing stages:
  - Starting processing... (10%)
  - Processing broker statements... (30%)
  - Extracting data with LLM... (50%)
  - Finalizing results... (90%)
  - Completed (100%)
- Error handling with detailed error messages
- Job history with status indicators (completed, failed, processing)

## How to Use

### Starting the Web Application

```bash
python web_app.py
```

The application will be available at `http://localhost:5000`

### Uploading Files

1. Navigate to the **Upload** page from the navigation menu
2. Enter the **Broker Name** (e.g., "IB", "MOOMOO")
3. Select the **Statement Date** using the date picker
4. **Upload files** by either:
   - Dragging and dropping files into the upload zone
   - Clicking the upload zone to browse for files
5. Review the selected files in the file list
6. Click **Process Statements** to start processing

### Monitoring Progress

Once you submit files:
- A progress bar will appear showing the current processing stage
- Status messages update in real-time
- The page will automatically redirect to the dashboard when complete
- If processing fails, an error message will be displayed

### Viewing Results

After successful processing:
- You'll be automatically redirected to the Dashboard
- The new data will be available for the specified date
- You can view:
  - Portfolio summary
  - Cash holdings by broker and currency
  - Position details with market prices
  - Historical comparisons

## API Endpoints

### Upload Files
```
POST /upload
Content-Type: multipart/form-data

Parameters:
- files: File[] (required) - Array of PDF/Excel files
- broker: string (required) - Broker name
- date: string (required) - Date in YYYY-MM-DD format

Response:
{
  "job_id": "uuid",
  "status": "processing",
  "message": "Processing N file(s) for BROKER"
}
```

### Get Job Status
```
GET /api/jobs/{job_id}

Response:
{
  "status": "processing|completed|failed",
  "broker": "IB",
  "date": "2025-02-28",
  "progress": 50,
  "message": "Processing broker statements...",
  "created_at": "2025-02-28T10:30:00",
  "result": {...},
  "error": null
}
```

### List All Jobs
```
GET /api/jobs

Response:
[
  {
    "job_id": "uuid",
    "broker": "IB",
    "date": "2025-02-28",
    "status": "completed",
    "created_at": "2025-02-28T10:30:00"
  },
  ...
]
```

## File Organization

Uploaded files are organized in the following structure:

```
data/
└── uploads/
    └── {BROKER}/
        └── {DATE}/
            ├── statement1.pdf
            ├── statement2.pdf
            └── ...
```

Processed results are saved to:

```
out/
└── result/
    └── {DATE}/
        ├── cash_summary_{DATE}.parquet
        ├── positions_{DATE}.parquet
        ├── portfolio_details_{DATE}.csv
        └── metadata_{DATE}.json
```

## Technical Details

### Processing Flow

1. **File Upload**:
   - Files are saved to `data/uploads/{BROKER}/{DATE}/`
   - A unique job ID is generated
   - Job status is initialized as "pending"

2. **Background Processing**:
   - A daemon thread is spawned to handle processing
   - The main processing pipeline from `src/main.py` is invoked
   - Job status is updated throughout the process

3. **Status Updates**:
   - Job status is stored in memory (`processing_jobs` dict)
   - Thread-safe updates using `processing_lock`
   - Client polls `/api/jobs/{job_id}` every 2 seconds

4. **Completion**:
   - Successful: Results saved to output directory
   - Failed: Error details stored in job status
   - Job history updated for user review

### Security Considerations

- **File type validation**: Only PDF, XLSX, XLS allowed
- **File size limit**: 50MB maximum
- **Filename sanitization**: Uses `secure_filename()` from werkzeug
- **Secret key**: Set `FLASK_SECRET_KEY` environment variable in production
- **Input validation**: Broker name and date format validated

### Performance

- **Concurrent processing**: Up to 5 workers per job (configurable)
- **Non-blocking uploads**: Processing happens in background threads
- **Memory efficient**: Temporary files are stored on disk
- **Job cleanup**: Consider implementing job history cleanup for long-running deployments

## Prerequisites

Before using the upload feature, ensure:

1. **Futu OpenD is running** (for price data):
   ```bash
   ./FutuOpenD -addr 127.0.0.1 -port 11111
   ```

2. **Environment variables are set** in `.env`:
   - `LLM_API_KEY` - Google Gemini API key
   - `LLM_BASE_URL` - Gemini API endpoint
   - `EXCHANGE_API_KEY` - Exchange rate API key

3. **Required directories exist**:
   - `data/uploads/` - Created automatically
   - `out/result/` - Created automatically
   - `log/` - Created automatically

## Troubleshooting

### Upload Fails
- Check file format (must be PDF, XLSX, or XLS)
- Verify file size is under 50MB
- Ensure broker name is valid
- Check date format is YYYY-MM-DD

### Processing Fails
- Verify Futu OpenD is running
- Check LLM API credentials in `.env`
- Review logs in `log/` directory
- Check job error details in the job history

### Results Not Appearing
- Wait for processing to complete (check progress bar)
- Refresh the dashboard page
- Check if the date selector shows the new date
- Review job status for errors

## Future Enhancements

Potential improvements:
- [ ] Multiple broker uploads in one session
- [ ] Persistent job storage (database)
- [ ] Email notifications on completion
- [ ] Downloadable processing logs
- [ ] Batch upload with folder selection
- [ ] Resume failed jobs
- [ ] Job cancellation feature
- [ ] WebSocket for real-time updates (instead of polling)

## Support

For issues or questions:
1. Check the logs in `log/` directory
2. Review job error messages in the upload page
3. Refer to the main CLAUDE.md documentation
4. Check broker-specific requirements in README.md
