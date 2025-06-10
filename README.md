# PDF Split, Rotate & Clean

## Overview
This project provides robust Python scripts for batch processing, cleaning, and analyzing PDF files in directory trees. The main script (`pdf_split_rotate.py`) automatically splits PDFs into single-page files, detects and corrects page orientation using OCR, and saves the results with standardized filenames. Additional utilities are included for renaming files/folders, counting PDF pages, and generating sample PDFs for testing.

---

## Features
- **Recursive directory watching**: Monitors a folder (and subfolders) for new or changed PDF files.
- **Batch processing**: Processes all existing PDFs in the watch folder on startup.
- **Page splitting**: Each PDF is split into single-page PDFs.
- **Automatic rotation**: Uses Tesseract OCR to detect and correct page orientation.
- **Filename and folder cleaning**: Standardizes output filenames and folder names for consistency using customizable rules.
- **Collision resolution**: Automatically renames files to avoid overwriting.
- **Parallel processing**: Utilizes multiple CPU cores for fast operation.
- **Progress tracking**: Keeps a log of processed files to avoid duplicates.
- **Error and warning logs**: All issues are logged for review.
- **PDF page counting**: Utility to count pages in PDFs and compare folder structures.
- **Sample PDF generator**: Utility to create randomized, rotated, and merged sample PDFs for testing.

---

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
  - tabulate (for `pdf_pages_count.py`)
  - PyPDF2 (for `pdf_pages_count.py` and `pdf_sample_generator.py`)

---

## Installation
1. Install system dependencies (Poppler, Tesseract, Ghostscript if needed).
2. Install Python packages:
   ```powershell
   pip install -r requirements.txt
   pip install tabulate PyPDF2  # For page counting and sample generation
   ```
3. (Optional) Copy `.env.template` to `.env` and adjust settings as needed.

---

## Usage

### 1. Main PDF Processor: `pdf_split_rotate.py`
- **Purpose:** Watches a folder for new PDFs, splits each into single-page files, auto-rotates, and cleans names.
- **Configuration:**
  - Edit `.env` or set environment variables:
    - `WATCH_FOLDER`, `OUTPUT_FOLDER`, `PROCESSED_FILE_PATH`, `ERROR_LOG_PATH`, `WARNINGS_LOG_PATH`, `MAX_WORKERS`, `RETRIES`, `RETRY_DELAY`, `FILENAME_SEPARATOR`, `RESET_PROGRESS`
- **Run:**
  ```powershell
  python pdf_split_rotate.py
  ```
- **What it does:**
  - Processes all PDFs in the watch folder and subfolders.
  - Splits each PDF into single-page PDFs.
  - Detects and corrects page orientation using Tesseract OCR.
  - Cleans and standardizes output filenames and folder names.
  - Logs processed files, errors, and warnings.

#### Example: Cleaning a Folder Name
```python
from pdf_files_rename import clean_name
cleaned = clean_name('Documenti 3Z Srl', '/output', kind='dir')
print(cleaned)  # Output: '3z_srl'
```

---

### 2. Filename/Folder Cleaner: `pdf_files_rename.py`
- **Purpose:** Recursively cleans file and folder names using a customizable set of rules.
- **Key Functions:**
  - `clean_name(name, parent, kind)`: Applies rules to clean a file or directory name.
  - `resolve_collision(dest)`: Ensures no filename collisions by appending a suffix if needed.

#### Example: Cleaning a File Name
```python
from pdf_files_rename import clean_name
cleaned = clean_name('Documenti - Fattura 2023.pdf', '/output', kind='file')
print(cleaned)  # Output: 'fattura_2023.pdf'
```

#### Example: Resolving Filename Collisions
```python
from pathlib import Path
from pdf_files_rename import resolve_collision
unique_path = resolve_collision(Path('/output/fattura_2023.pdf'))
print(unique_path)
```

---

### 3. PDF Page Counter: `pdf_pages_count.py`
- **Purpose:** Recursively counts all pages in every PDF under a folder, compares two folder trees, and logs results.
- **Run:**
  ```powershell
  python pdf_pages_count.py
  ```
- **What it does:**
  - Compares two root folders (edit `root1` and `root2` in the script).
  - Logs a table of which customer folders are present in each root.
  - Logs page counts for each customer in both roots.

#### Example: Count Pages in a Folder
```python
from pdf_pages_count import count_pdf_pages
pages = count_pdf_pages('D:/01_unzipped')
print(f"Total pages: {pages}")
```

---

### 4. Sample PDF Generator: `pdf_sample_generator.py`
- **Purpose:** Merges and randomly rotates pages from multiple PDFs to create a sample PDF for testing.
- **Run:**
  ```powershell
  python pdf_sample_generator.py
  ```
- **What it does:**
  - Selects random PDFs from a folder.
  - Merges and shuffles their pages.
  - Randomly rotates some pages.
  - Outputs a single sample PDF.

#### Example: Generate a Sample PDF
```python
from pdf_sample_generator import merge_and_rotate_pdfs, get_all_pdf_paths
pdfs = get_all_pdf_paths('samples/libra')
merged = merge_and_rotate_pdfs(pdfs, rotate_probability=0.8, page_cap=30)
with open('samples/test_pdf.pdf', 'wb') as f:
    f.write(merged)
```

---

## Output
- Each page of every PDF is saved as a separate, correctly rotated PDF in the output folder.
- Filenames and folder names are cleaned for consistency.
- Logs are written for errors, warnings, and processed files.

---

## Troubleshooting
- Ensure Poppler and Tesseract are installed and available in your system PATH.
- Check the log files for details on any errors or warnings.
- For large batches, increase `MAX_WORKERS` for faster processing (CPU dependent).

