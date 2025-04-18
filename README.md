
# **PDF Splitter and Orientation Corrector**

This Python project listens to a folder for newly added scanned PDF files. Upon detecting a new file, it splits the PDF into individual pages, performs OCR (Optical Character Recognition) to detect text orientation, and rotates each page to ensure that the text is aligned properly, similar to how it would appear in a regular book. The final output is saved as one PDF per page, with each page rotated for correct orientation.

## **Features**

- **Monitors a Folder**: Automatically detects new PDF files added to a specified directory.
- **Splits PDFs**: Each PDF is split into individual pages.
- **OCR-Based Orientation Detection**: Uses Tesseract OCR to detect the orientation of text.
- **Page Rotation**: Rotates pages as needed to ensure the text is properly oriented.
- **Efficient and Easy Setup**: With minimal dependencies, the solution is quick to deploy and configure.

---

## **Prerequisites**

Before running the project, make sure to install the required dependencies:

### 1. **Python Dependencies**:
You’ll need to install the following Python packages using `pip`:
```bash
pip install watchdog pymupdf pytesseract pdf2image
```

### 2. **External Dependencies**:

- **Tesseract OCR**: Tesseract is required for OCR-based text orientation detection. Download and install it based on your OS:
  - **Windows**: Download from [Tesseract for Windows](https://github.com/tesseract-ocr/tesseract) and follow the installation instructions. Ensure that `tesseract.exe` is in your system’s `PATH`.
  - **macOS**: Install via Homebrew: `brew install tesseract`
  - **Linux**: Install using `apt`: `sudo apt install tesseract-ocr`

- **Poppler** (for PDF to Image conversion):
  - **Windows**: Download from [Poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases) and add it to your `PATH`.
  - **macOS**: Install via Homebrew: `brew install poppler`
  - **Linux**: Install via `apt`: `sudo apt install poppler-utils`

---

## **Usage**

### 1. **Set Up the Folder to Monitor**:
Create a folder where PDFs will be placed. The script will automatically detect new PDFs added to this folder.

### 2. **Start the Script**:
Run the Python script to start monitoring the folder:
```bash
python pdf_orientation_corrector.py
```

Once started, the script will listen for new PDFs in the specified folder. When a new PDF is detected, it will:
- Split the PDF into individual pages.
- Perform OCR to detect text orientation.
- Rotate pages if needed.
- Save the rotated pages as separate PDF files.

### 3. **Example Folder Setup**:
1. **Input Folder**: Place the PDFs you want to process into `./pdf_folder/` (or any folder you choose).
2. **Output Folder**: The processed PDFs (with individual pages and correct orientations) will be saved to `./processed/`.

---

## **File Structure**

```
.
├── pdf_orientation_corrector.py       # Main Python script
├── requirements.txt                  # List of required Python dependencies
├── README.md                         # Project documentation
└── pdf_folder/                       # Folder for input PDFs
└── processed/                         # Folder for output PDFs
```

---

## **How It Works**

1. **Folder Monitoring**: The `watchdog` library monitors the specified folder (`./pdf_folder/`) for new PDF files.
2. **PDF Splitting**: When a new PDF is added, the script splits it into individual pages using `PyMuPDF`.
3. **OCR & Rotation**: The script then uses `pdf2image` to convert the first page into an image, which is processed by `pytesseract` to detect the text's orientation. Based on this, it determines if rotation is required.
4. **Output**: After rotation, the pages are saved into the `./processed/` folder as individual PDFs, each with the correct orientation.

---

## **Additional Configuration**

- **Tesseract Configuration**: You can customize Tesseract settings by modifying the `pytesseract` configuration, for example, adjusting the language or OCR parameters.
  
- **DPI for OCR**: You can adjust the DPI value for `pdf2image` in case you need better OCR accuracy (higher DPI means better quality images but may be slower).

---

## **Troubleshooting**

- **OCR Errors**: If Tesseract fails to detect text properly, consider increasing the DPI for image conversion or fine-tuning Tesseract's configuration.
- **Rotation Issues**: In some cases, Tesseract might not perfectly detect the correct rotation angle due to image quality. You can adjust the script to handle more specific cases based on your needs.

---

## **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
