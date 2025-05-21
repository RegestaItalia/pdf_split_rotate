# PDF Split, Rotate & Clean

## Overview
This project provides a robust Python script (`pdf_split_rotate.py`) to automatically process PDF files in a directory tree. It splits each PDF into single-page files, detects and corrects page orientation using OCR, and saves the results with clean, standardized filenames. The script is designed for batch processing of scanned or messy PDF archives, making them easier to manage and search.

### Key Features
- **Recursive directory watching**: Monitors a folder (and subfolders) for new or changed PDF files.
- **Batch processing**: On startup, processes all existing PDFs in the watch folder.
- **Page splitting**: Each PDF is split into single-page PDFs.
- **Automatic rotation**: Uses Tesseract OCR to detect and correct page orientation.
- **Filename cleaning**: Standardizes output filenames and folder names for consistency.
- **Parallel processing**: Utilizes multiple CPU cores for fast operation.
- **Progress tracking**: Keeps a log of processed files to avoid duplicates.
- **Error and warning logs**: All issues are logged for review.

## Requirements
- **Python 3.7+**
- **Poppler** (for `pdf2image`):
  - Windows: Download from [Poppler for Windows](http://blog.alivate.com.au/poppler-windows/)
  - Linux: `sudo apt install poppler-utils`
- **Tesseract OCR**:
  - Windows: [UB Mannheim builds](https://github.com/UB-Mannheim/tesseract/wiki)
  - Linux: `sudo apt install tesseract-ocr`
- **Ghostscript** (optional, for some PDF conversions)
- Python packages (see `requirements.txt`):
  - watchdog
  - PyMuPDF
  - pdf2image
  - pytesseract
  - Pillow
  - python-dotenv

## Installation
1. Install system dependencies (Poppler, Tesseract, Ghostscript if needed).
2. Install Python packages:
   ```powershell
   pip install -r requirements.txt
   ```
3. (Optional) Copy `.env.example` to `.env` and adjust settings as needed.

## Usage
1. Edit the `.env` file or set environment variables to configure:
   - `WATCH_FOLDER`: Folder to monitor for PDFs (default: `./input`)
   - `OUTPUT_FOLDER`: Where processed PDFs are saved (default: `./output`)
   - `PROCESSED_FILE_PATH`: Log of processed files (default: `./processed_files.txt`)
   - `ERROR_LOG_PATH`, `WARNINGS_LOG_PATH`: Log files
   - `MAX_WORKERS`: Number of parallel processes (default: 4)
2. Run the script:
   ```powershell
   python pdf_split_rotate.py
   ```
3. The script will process all PDFs in the watch folder and continue monitoring for new files.

## Output
- Each page of every PDF is saved as a separate, correctly rotated PDF in the output folder.
- Filenames and folder names are cleaned for consistency.
- Logs are written for errors, warnings, and processed files.

## Troubleshooting
- Ensure Poppler and Tesseract are installed and available in your system PATH.
- Check the log files for details on any errors or warnings.
- For large batches, increase `MAX_WORKERS` for faster processing (CPU dependent).

## License
MIT License. See `LICENSE.md` for details.
