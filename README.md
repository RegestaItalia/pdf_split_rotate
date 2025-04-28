# PDF Watcher and Processor

## Overview
This Python script monitors a specified directory (and its subdirectories) for PDF files and automatically processes them by splitting each PDF into individual pages, detecting page orientation using Tesseract OCR, rotating pages if necessary, and saving each page as a separate one-page PDF.

Key features:
- **Real-time directory watching**: Automatically detects newly added PDF files.
- **Existing file scan**: Processes existing PDFs in the watch folder on startup.
- **Orientation detection**: Uses Tesseract OCR to determine rotation angles.
- **Automatic rotation**: Rotates pages to upright orientation.
- **Concurrent processing**: Employs a process pool executor for parallel processing.
- **Tracking**: Maintains a list of processed files to avoid reprocessing.
- **Error logging**: Logs any processing errors to a dedicated file.

## Requirements

### Software
- Python **3.7+**
- **Poppler** utilities (for `pdf2image`):
  - Linux: `poppler-utils`
  - Windows: Download binaries from [Poppler for Windows](http://blog.alivate.com.au/poppler-windows/)
- **Tesseract OCR** engine:
  - Linux: `tesseract-ocr`
  - Windows: Installer from [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
- Ghostscript (optional, can improve PDF handling performance)

### Python Packages
All Python dependencies are listed in `requirements.txt`:
```text
watchdog
PyMuPDF
pdf2image
pytesseract
Pillow
python-dotenv
```

Install them via:
```bash
pip install -r requirements.txt
```

## Installation Guide

### Linux (Ubuntu / Debian)
1. Update package list:
    ```bash
    sudo apt update
    ```
2. Install system dependencies:
    ```bash
    sudo apt install -y poppler-utils tesseract-ocr libtesseract-dev ghostscript
    ```
3. Clone the repository and install Python dependencies:
    ```bash
    git clone <your-repo-url>
    cd <your-repo-name>
    pip install -r requirements.txt
    ```

### Windows
1. Install Python 3.7+ from the [official website](https://www.python.org/downloads/).
2. Download and install **Poppler for Windows**:
   - Unzip and add the `bin/` directory to your PATH.
3. Download and install **Tesseract OCR** from the [UB Mannheim builds](https://github.com/UB-Mannheim/tesseract/wiki).
4. (Optional) Install Ghostscript and add to PATH.
5. Clone the repository and install Python dependencies:
    ```powershell
    git clone <your-repo-url>
    cd <your-repo-name>
    pip install -r requirements.txt
    ```

## Configuration

Below is the example `.env` file located in the project root:

```ini
# Directory paths
WATCH_FOLDER = ./input
OUTPUT_FOLDER = ./output
PROCESSED_FILE_PATH = ./logs/processed_files.txt
ERROR_LOG_PATH = ./logs/error_log.txt

# Conf params
MAX_WORKERS = 12
RETRIES = 5
RETRY_DELAY = 1

# Flag to reset processed files tracking (optional)
RESET_PROGRESS = false
```

If not provided, default values (shown above) will be used.

## Usage

Run the script directly:
```bash
python pdf_split_rotate.py
```

- The script will start watching the `WATCH_FOLDER`.
- New and existing PDF files will be enqueued and processed.
- Processed pages will be saved under `OUTPUT_FOLDER` in subdirectories mirroring the input structure.
- Processing logs will appear in the console.
- Errors are logged to `ERROR_LOG_PATH`.

To reset the processed files list and reprocess all PDFs, set the environment variable:
```bash
export RESET_PROGRESS=true
python pdf_split_rotate.py
```

## Logging

- **Console logs**: Informational messages about file processing.
- **Error log**: Detailed errors in `logs/error_log.txt`.

## Contributing

Contributions, bug reports, and feature requests are welcome. Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License. Feel free to use and modify.
