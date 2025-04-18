import os
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
import io
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from concurrent.futures import ProcessPoolExecutor
executor = ProcessPoolExecutor()

# Load paths from environment variables
WATCH_FOLDER = os.path.abspath(os.getenv('WATCH_FOLDER', './input'))
OUTPUT_FOLDER = os.path.abspath(os.getenv('OUTPUT_FOLDER', './output'))
PROCESSED_FILE_PATH = os.path.abspath(os.getenv('PROCESSED_FILE_PATH', './processed_files.txt'))
ERROR_LOG_PATH = os.path.abspath(os.getenv('ERROR_LOG_PATH', './error_log.txt'))

# Create necessary directories
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def reset_processed_files():
    """Reset the processed files tracking."""
    if os.path.exists(PROCESSED_FILE_PATH):
        os.remove(PROCESSED_FILE_PATH)
    logging.info("Processed files reset.")

def load_processed_files():
    """Load the list of processed files from the tracking file."""
    if os.path.exists(PROCESSED_FILE_PATH):
        with open(PROCESSED_FILE_PATH, 'r') as f:
            return set(f.read().splitlines())
    return set()

def log_error(file_path, error_message):
    """Log error messages for failed processing."""
    with open(ERROR_LOG_PATH, 'a') as f:
        f.write(f"{file_path} - ERROR: {error_message}\n")

def append_processed_file(file_path):
    """Append processed file path to the tracking file."""
    with open(PROCESSED_FILE_PATH, 'a') as f:
        f.write(f"{file_path}\n")

# Load the set of already processed files
processed_files = load_processed_files()

def wait_until_file_is_ready(file_path, retries=10, delay=1):
    """Wait until the file is available for reading."""
    for attempt in range(retries):
        try:
            with open(file_path, 'rb') as f:
                f.read(1)
            return
        except (PermissionError, IOError):
            logging.info(f"{file_path} - file not ready yet, retrying... ({attempt + 1}/{retries})")
            time.sleep(delay)
    raise TimeoutError(f"{file_path} - file not ready after {retries * delay} seconds")

class PDFHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith('.pdf'):
            return
        logging.info(f"{event.src_path} - new PDF detected: {event.src_path}")
        try:
            if event.src_path in processed_files:
                logging.info(f"{event.src_path} - already processed, skipping.")
                return
            wait_until_file_is_ready(event.src_path)
            executor.submit(process_pdf, event.src_path)
        except Exception as e:
            log_error(event.src_path, str(e))

def process_pdf(pdf_path):
    if pdf_path in processed_files:
        logging.info(f"{pdf_path} - already processed, skipping.")
        return

    start_time = time.time()
    logging.info(f"{pdf_path} - starting processing")
    
    try:
        doc = fitz.open(pdf_path)
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        relative_path = os.path.relpath(os.path.dirname(pdf_path), WATCH_FOLDER)
        target_folder = os.path.join(OUTPUT_FOLDER, relative_path, base_name)
        os.makedirs(target_folder, exist_ok=True)

        page_files = []
        for page_number in range(doc.page_count):
            page_start_time = time.time()
            single_page_doc = fitz.open()
            single_page_doc.insert_pdf(doc, from_page=page_number, to_page=page_number)
            page_pdf_path = os.path.join(target_folder, f"{base_name}_page_{page_number + 1}.pdf")

            # Detect orientation before saving
            angle = detect_orientation(single_page_doc)
            logging.info(f"{page_pdf_path} - detected {angle} degrees angle")

            # Rotate the page if needed (all done in memory)
            rotated_doc = rotate_pdf(single_page_doc, angle)

            # Save rotated page directly
            rotated_doc.save(page_pdf_path)
            rotated_doc.close()

            page_files.append(page_pdf_path)
            logging.info(f"{page_pdf_path} saved and processed. Page time: {time.time() - page_start_time:.2f} seconds")

        doc.close()
        append_processed_file(pdf_path)  # Mark this file as processed
        logging.info(f"{pdf_path} - processing completed. Total time: {time.time() - start_time:.2f} seconds")
    except Exception as e:
        log_error(pdf_path, str(e))

def detect_orientation(pdf_document):
    try:
        pix = pdf_document[0].get_pixmap(dpi=200)
        if pix.samples == b'':  # Check if the image has no content
            logging.warning(f"Page is empty, skipping orientation detection.")
            return 0
        
        img = Image.open(io.BytesIO(pix.tobytes()))
        osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
        logging.info(f"Orientation detected: {osd['rotate']} degrees")
        return osd['rotate']
    except Exception as e:
        logging.error(f"Error detecting orientation: {str(e)}")
        return 0  # Default to no rotation if error occurs

def rotate_pdf(page_doc, rotation_angle):
    try:
        if rotation_angle == 0:
            logging.info("No rotation needed")
            return page_doc  # No change needed, return original doc
        
        rotated_doc = fitz.open()
        for page in page_doc:
            mat = fitz.Matrix(1, 1).prerotate(rotation_angle)
            pix = page.get_pixmap(matrix=mat)
            img_page = rotated_doc.new_page(width=pix.width, height=pix.height)
            img_page.insert_image(img_page.rect, pixmap=pix)

        logging.info(f"Rotation applied with angle: {rotation_angle} degrees")
        return rotated_doc
    except Exception as e:
        logging.error(f"Error rotating PDF: {str(e)}")
        return page_doc  # In case of error, return original document

def scan_existing_pdfs(root_folder):
    """Scan existing PDFs in the watch folder and submit them for processing."""
    for dirpath, _, filenames in os.walk(root_folder):
        for filename in filenames:
            if filename.lower().endswith(".pdf"):
                full_path = os.path.join(dirpath, filename)
                if full_path in processed_files:
                    continue  # Skip already processed files
                logging.info(f"{full_path} - found existing PDF to process")
                try:
                    wait_until_file_is_ready(full_path)
                    executor.submit(process_pdf, full_path)
                except Exception as e:
                    log_error(full_path, str(e))

if __name__ == "__main__":
    # Optional: Reset progress on fresh start
    if os.getenv('RESET_PROGRESS', 'false').lower() == 'true':
        reset_processed_files()

    observer = Observer()
    observer.schedule(PDFHandler(), path=WATCH_FOLDER, recursive=True)
    observer.start()
    logging.info(f"{WATCH_FOLDER} - watching folder")

    # Scan existing files (non-blocking)
    scan_existing_pdfs(WATCH_FOLDER)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        executor.shutdown(wait=True)
    observer.join()
    logging.info("stopped folder observer")
