
# PDF Split & Utilities

## Overview
This repository provides a suite of Python scripts for batch processing, cleaning, and analyzing PDF files and related directory structures. The tools are designed for robust, automated workflows in document management and archiving.

---

## Python Scripts

### 1. `pdf_split_rotate.py` — Main PDF Processor

Watches a folder for new PDF/image files, splits PDFs into single pages, auto-rotates pages using OCR, and saves results with standardized names. Supports parallel processing, error logging, and processed-file tracking.

**Key Features:**
- Recursive directory watching and batch processing
- Splits PDFs and multi-page images into single-page PDFs
- Detects and corrects page orientation (Tesseract OCR)
- Cleans and standardizes output filenames/folders
- Parallel processing with progress tracking
- Robust error and warning logging

**Sphinx-style Example:**
```python
from pdf_files_rename import clean_name
cleaned = clean_name('Documenti 3Z Srl', '/output', kind='dir')
print(cleaned)  # '3zsrl'
```

**Run:**
```bash
python pdf_split_rotate.py
```

---

### 2. `pdf_files_rename.py` — Filename/Folder Cleaner

Recursively cleans file and folder names using customizable rules. Ensures names are safe, consistent, and collision-free.

**Main Functions:**

.. autofunction:: clean_name

.. autofunction:: resolve_collision

**Example:**
```python
from pdf_files_rename import clean_name, resolve_collision
name = clean_name('Documenti - Fattura 2023.pdf', '/output', kind='file')
unique_path = resolve_collision(Path('/output/fattura_2023.pdf'))
```

---

### 3. `pdf_pages_count.py` — PDF Page Counter & Folder Comparator

Recursively counts all pages in every PDF under a folder, compares two folder trees, and logs results. Useful for verifying batch splits and folder consistency.

**Sphinx-style Example:**
```python
from pdf_pages_count import count_pdf_pages
pages = count_pdf_pages('D:/01_unzipped')
print(f"Total pages: {pages}")
```

---

### 4. `pdf_sample_generator.py` — Sample PDF Generator

Merges and randomly rotates pages from multiple PDFs to create a sample PDF for testing or demonstration.

**Sphinx-style Example:**
```python
from pdf_sample_generator import merge_and_rotate_pdfs, get_all_pdf_paths
pdfs = get_all_pdf_paths('samples/libra')
merged = merge_and_rotate_pdfs(pdfs, rotate_probability=0.8, page_cap=30)
with open('samples/test_pdf.pdf', 'wb') as f:
    f.write(merged)
```

---

### 5. `pdf_group_rename.py` — Group Folder Renamer

Renames folders like `group_1`, `group_2`, ... to `group1`, `group2`, ... recursively. Preview changes before applying.

---

### 6. `list_non_pdf_files.py` — List Non-PDF Files

Lists all non-PDF files in a directory tree. Useful for data hygiene and migration checks.

---

### 7. `pdf_pages_count_check.py` — PDF Page Count Checker

Checks and logs the number of pages in PDFs, with tabular output and logging.

---

## Requirements

- Python 3.7+
- Poppler (for `pdf2image`)
- Tesseract OCR
- Ghostscript (optional)
- See `requirements.txt` for Python packages

## Installation

1. Install system dependencies (Poppler, Tesseract, Ghostscript if needed)
2. Install Python packages:
   ```bash
   pip install -r requirements.txt
   ```
3. (Optional) Copy `.env.template` to `.env` and adjust settings

## Usage Notes

- Configure environment variables in `.env` or via the shell for advanced options (see code comments)
- All logs and outputs are written to the `logs/` and `output/` folders

## Troubleshooting

- Ensure Poppler and Tesseract are installed and in your system PATH
- Check log files for error details
- For large batches, increase `MAX_WORKERS` (CPU dependent)

---

## License
See LICENSE file.
  - Outputs a single sample PDF.

