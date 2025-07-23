import os
from pathlib import Path
import time
import logging
import threading
import queue
import traceback
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
Image.MAX_IMAGE_PIXELS = 178956970 * 3

import io
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dotenv import load_dotenv
from pdf_files_rename import clean_name
from collections import defaultdict

# Load environment variables
load_dotenv(override=True)
WATCH_FOLDER        = os.path.abspath(os.getenv('WATCH_FOLDER', './input'))
OUTPUT_FOLDER       = os.path.abspath(os.getenv('OUTPUT_FOLDER', './output'))
PROCESSED_FILE_PATH = os.path.abspath(os.getenv('PROCESSED_FILE_PATH', './processed_files.txt'))
ERROR_LOG_PATH      = os.path.abspath(os.getenv('ERROR_LOG_PATH', './error_log.txt'))
WARNINGS_LOG_PATH   = os.path.abspath(os.getenv('WARNINGS_LOG_PATH', './warnings_log.txt'))
MAX_WORKERS         = int(os.getenv('MAX_WORKERS', '4'))
RETRIES             = int(os.getenv('FILE_READY_RETRIES', '10'))
RETRY_DELAY         = float(os.getenv('FILE_READY_DELAY', '1'))
FILENAME_SEPARATOR  = os.getenv('FILENAME_SEPARATOR', '__EKR__')
MAX_FILES_PER_GROUP = int(os.getenv('MAX_FILES_PER_GROUP', '10000'))
REMOVE_SOURCE_FILE = os.getenv('REMOVE_SOURCE_FILE', 'false').lower() == 'true'

# Load supported file extensions from environment
process_extensions_str = os.getenv('PROCESS_EXTENSIONS', '.pdf,.tif,.tiff,.png,.jpg,.jpeg')
PROCESS_EXTENSIONS = tuple(ext.strip().lower() for ext in process_extensions_str.split(',') if ext.strip())

# Separate PDF and image extensions for routing
PDF_EXTENSIONS = ('.pdf',)
IMAGE_EXTENSIONS = tuple(ext for ext in PROCESS_EXTENSIONS if ext not in PDF_EXTENSIONS)

# Prepare output folder and logs
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
# Ensure warnings log exists
open(WARNINGS_LOG_PATH, 'a').close()

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# Handler for warnings
warnings_handler = logging.FileHandler(WARNINGS_LOG_PATH)
warnings_handler.setLevel(logging.WARNING)
warnings_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(warnings_handler)

# Load processed-files set
def load_processed_files():
    if os.path.exists(PROCESSED_FILE_PATH):
        with open(PROCESSED_FILE_PATH, 'r') as f:
            return set(f.read().splitlines())
    return set()

processed_files = load_processed_files()
processed_lock = threading.Lock()

def append_processed_file(path: str):
    with open(PROCESSED_FILE_PATH, 'a') as f:
        f.write(path + "\n")
    with processed_lock:
        processed_files.add(path)

def log_error(path: str, msg: str):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(ERROR_LOG_PATH, 'a') as f:
        f.write(f"{ts} - {path} - {msg}\n")

def wait_until_file_is_ready(path: str):
    last_size = -1
    stable_count = 0
    for i in range(RETRIES * 2):  # allow more retries for large files
        try:
            size = os.path.getsize(path)
            if size == last_size and size > 0:
                stable_count += 1
            else:
                stable_count = 0
            last_size = size
            # Require file size to be stable for 2 consecutive checks
            if stable_count >= 2:
                with open(path, 'rb') as f:
                    f.read(1)
                return
        except (PermissionError, IOError, FileNotFoundError):
            logging.info(f"{path} not ready, retry {i + 1}/{RETRIES * 2}")
        time.sleep(RETRY_DELAY)
    raise TimeoutError(f"{path} not ready after {(RETRIES * 2) * RETRY_DELAY}s")

from pytesseract import TesseractError

def detect_orientation_from_image(img: Image.Image, source_path: str, page_no: int, initial_dpi=200, max_trials=3):
    """Detect orientation from a PIL Image using OCR"""
    last_rotate = 0
    last_conf = 0

    for trial in range(1, max_trials + 1):
        try:
            # If we're on a retry, upscale the image to simulate higher DPI
            current_img = img
            if trial > 1:
                scale_factor = 1 + (trial - 1) * 0.5  # 1.0, 1.5, 2.0 for trials 1, 2, 3
                new_width = int(img.width * scale_factor)
                new_height = int(img.height * scale_factor)
                current_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # run OSD
            try:
                osd = pytesseract.image_to_osd(current_img, output_type=pytesseract.Output.DICT)
                rotate = int(osd.get('rotate', 0) or 0)
                conf   = float(osd.get('orientation_conf', 0) or 0.0)
            except TesseractError as te:
                logging.warning(f"OSD failed for {source_path}, page {page_no+1}: {te}")
                rotate, conf = 0, 0.0

            effective_dpi = initial_dpi * (1 + (trial - 1) * 0.5)
            logging.debug(f"Trial {trial}: effective_DPI={effective_dpi:.0f}, orientation={rotate}, confidence={conf}"
                          f" (File={source_path}, Page={page_no + 1})")

            if conf >= 2:
                if trial > 1:
                    logging.info(f"Orientation ({rotate}) stabilized at trial {trial}"
                                 f" (effective_DPI={effective_dpi:.0f}, confidence={conf}) {source_path}, page {page_no+1}")
                return rotate

            # too low confidence → retry with upscaled image
            last_rotate, last_conf = rotate, conf
            logging.warning(f"Low orientation confidence ({conf:.1f}) at effective_DPI={effective_dpi:.0f}"
                            f" for {source_path}, page {page_no + 1}; retrying with higher resolution.")

        except Exception as e:
            effective_dpi = initial_dpi * (1 + (trial - 1) * 0.5)
            err_msg = (f"Orientation detection failed on trial {trial} "
                       f"(effective_DPI={effective_dpi:.0f}) for {source_path}, page {page_no + 1}: {e}")
            logging.error(err_msg, exc_info=True)
            log_error(source_path, err_msg)

    logging.warning(f"Max trials reached for {source_path}, page {page_no+1}. "
                    f"Returning last {last_rotate}° @ confidence {last_conf}")
    return last_rotate

def detect_orientation(pdf_document, source_path: str, page_no: int, initial_dpi=200, max_trials=3):
    """Detect orientation from PDF document by converting to image first"""
    dpi = initial_dpi
    last_rotate = 0
    last_conf = 0

    for trial in range(1, max_trials + 1):
        try:
            # rasterize page → PIL image
            pix = pdf_document[0].get_pixmap(dpi=dpi)
            png_bytes = pix.tobytes("png")   # ensure it's actual PNG data
            img = Image.open(io.BytesIO(png_bytes))

            # Use the shared image-based detection
            return detect_orientation_from_image(img, source_path, page_no, dpi, 1)  # Single trial since we control DPI here

        except Exception as e:
            err_msg = (f"Orientation detection failed on trial {trial} "
                       f"(DPI={dpi}) for {source_path}, page {page_no + 1}: {e}")
            logging.error(err_msg, exc_info=True)
            log_error(source_path, err_msg)
            dpi += 100

    logging.warning(f"Max trials reached for {source_path}, page {page_no+1}. "
                    f"Returning last {last_rotate}° @ confidence {last_conf}")
    return last_rotate

def rotate_pdf(page_doc, rotation_angle):
    if rotation_angle == 0:
        return page_doc
    try:
        rotated = fitz.open()
        for page in page_doc:
            mat = fitz.Matrix(1, 1).prerotate(rotation_angle)
            pix = page.get_pixmap(matrix=mat)
            new_page = rotated.new_page(width=pix.width, height=pix.height)
            new_page.insert_image(new_page.rect, pixmap=pix)
        return rotated
    except Exception as e:
        error_msg = f"Error rotating PDF: {e}"
        logging.error(error_msg)
        return page_doc

# === Progress counters ===
total_count = len(processed_files)
done_count   = len(processed_files)
total_lock = threading.Lock()
done_lock = threading.Lock()

def increment_total():
    global total_count
    with total_lock:
        total_count += 1

def update_progress(_future):
    global done_count, total_count
    with done_lock:
        done_count += 1
        pct = (done_count / total_count * 100) if total_count else 0
        logging.info(f"Progress: {done_count}/{total_count} files processed ({pct:.1f}%)")

# Track per-customer group state: customer -> (group_number, count_in_group)
customer_group_state = {}

def initialize_customer_groups():
    for customer_dir in os.listdir(OUTPUT_FOLDER):
        customer_path = os.path.join(OUTPUT_FOLDER, customer_dir)
        if not os.path.isdir(customer_path):
            continue
        group_numbers = []
        group_counts = {}
        for entry in os.listdir(customer_path):
            entry_path = os.path.join(customer_path, entry)
            if entry.startswith('group') and os.path.isdir(entry_path):
                try:
                    group_num = int(entry.replace('group', ''))
                except Exception:
                    continue
                group_numbers.append(group_num)
                group_counts[group_num] = len([f for f in os.listdir(entry_path) if os.path.isfile(os.path.join(entry_path, f))])
        if group_numbers:
            max_group = max(group_numbers)
            count = group_counts[max_group]
            customer_group_state[customer_dir] = [max_group, count]
        else:
            customer_group_state[customer_dir] = [1, 0]

def get_next_group_dir(target_dir, max_files_per_group):
    group_num = 1
    while True:
        group_dir = os.path.join(target_dir, f'group{group_num}')
        os.makedirs(group_dir, exist_ok=True)
        num_files = len([f for f in os.listdir(group_dir) if os.path.isfile(os.path.join(group_dir, f))])
        if num_files < max_files_per_group:
            return group_dir
        group_num += 1

import time

def get_next_group_dir_with_lock(target_dir, max_files_per_group, lock_timeout=10):
    group_num = 1
    while True:
        group_dir = os.path.join(target_dir, f'group{group_num}')
        os.makedirs(group_dir, exist_ok=True)
        lock_path = os.path.join(group_dir, '.group.lock')
        start_time = time.time()
        # Try to acquire lock
        lock_acquired = False
        try:
            while True:
                try:
                    # Try to create the lock file exclusively
                    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.close(fd)
                    lock_acquired = True
                    break  # Lock acquired
                except FileExistsError:
                    # Lock file exists, wait and retry
                    if time.time() - start_time > lock_timeout:
                        raise TimeoutError(f"Timeout waiting for lock on {group_dir}")
                    time.sleep(0.05)
            num_files = len([
                f for f in os.listdir(group_dir)
                if os.path.isfile(os.path.join(group_dir, f)) and not f.endswith('.lock')
            ])
            if num_files < max_files_per_group:
                return group_dir, lock_path
        finally:
            # Only remove the lock if we acquired it and are NOT returning this group
            if lock_acquired and (num_files >= max_files_per_group):
                try:
                    os.remove(lock_path)
                except FileNotFoundError:
                    pass
        group_num += 1

# The processing function
def process_image(image_path: str):
    """Process image files (including multi-page TIFFs) - convert to rotated PDFs"""
    with processed_lock:
        if image_path in processed_files:
            logging.info(f"{image_path} already processed, skipping.")
            return

    try:
        wait_until_file_is_ready(image_path)
    except Exception as e:
        logging.error(f"File not ready for processing: {image_path}: {e}")
        log_error(image_path, f"File not ready: {e}")
        return

    start = time.time()
    logging.info(f"Processing {image_path}")
    try:
        # Open image and check if it's multi-page (TIFF)
        with Image.open(image_path) as img:
            is_multipage = hasattr(img, 'n_frames') and img.n_frames > 1
            total_pages = img.n_frames if is_multipage else 1
            
            base = os.path.splitext(os.path.basename(image_path))[0]
            # Get relative path from WATCH_FOLDER to image's parent
            rel_dir = os.path.relpath(os.path.dirname(image_path), WATCH_FOLDER)
            # Split into parts
            rel_parts = os.path.normpath(rel_dir).split(os.sep)
            # Customer is always the first part
            customer_folder = rel_parts[0]
            # All subfolders under customer (may be empty)
            subfolders = rel_parts[1:] if len(rel_parts) > 1 else []
            # Clean customer folder name and use for both folder and filename prefix
            customer_clean = clean_name(customer_folder, OUTPUT_FOLDER, kind="dir")
            target_dir = os.path.join(OUTPUT_FOLDER, customer_clean)
            os.makedirs(target_dir, exist_ok=True)

            for page_idx in range(total_pages):
                try:
                    # For multi-page images, seek to the specific frame
                    if is_multipage:
                        img.seek(page_idx)
                        logging.info(f"Processing page {page_idx+1}/{total_pages} from {image_path}")
                    
                    # Convert image to RGB if needed (for PDF compatibility)
                    page_img = img.convert('RGB')
                    
                    # Detect orientation
                    angle = detect_orientation_from_image(page_img, image_path, page_idx)
                    logging.info(f"Page {page_idx + 1}: detected rotation {angle}° for {image_path}")
                    
                    # Rotate image if needed
                    if angle != 0:
                        # PIL rotates counter-clockwise, but our angle is clockwise, so negate
                        page_img = page_img.rotate(-angle, expand=True)
                        logging.info(f"Rotated image by {angle}° for {image_path} page {page_idx+1}")
                    
                    # --- GROUP LOGIC WITH LOCK ---
                    group_dir, lock_path = get_next_group_dir_with_lock(target_dir, MAX_FILES_PER_GROUP)
                    group_name = os.path.basename(group_dir)
                    group_clean = ''.join(c for c in group_name if c.isalnum())

                    subfolder_clean = '_'.join(''.join(c for c in part if c.isalnum()) for part in subfolders) if subfolders else ''
                    base_clean = ''.join(c for c in base if c.isalnum())
                    customer_group = f"{customer_clean}_{group_clean}{FILENAME_SEPARATOR}"
                    
                    if total_pages > 1:
                        # Multi-page file: include page number
                        if subfolder_clean:
                            name_parts = [subfolder_clean, f"{base_clean}page-{page_idx+1}.pdf"]
                        else:
                            name_parts = [f"{base_clean}page-{page_idx+1}.pdf"]
                    else:
                        # Single page: no page number
                        if subfolder_clean:
                            name_parts = [subfolder_clean, f"{base_clean}.pdf"]
                        else:
                            name_parts = [f"{base_clean}.pdf"]
                    
                    raw_out_fname = customer_group + '_'.join(name_parts)
                    out_path = Path(group_dir) / raw_out_fname

                    # Convert to PDF and save
                    saved = False
                    if not out_path.exists():
                        page_img.save(str(out_path), "PDF", resolution=200.0)
                        logging.info(f"Saved {'rotated' if angle else 'unrotated'} page {page_idx+1} to {out_path}")
                        saved = True
                    else:
                        logging.warning(f"Page {page_idx+1} not saved, file already exists: {out_path}")

                    # Release lock
                    if os.path.exists(lock_path):
                        os.remove(lock_path)

                    if saved:
                        logging.info(f"Saved {out_path}")

                except Exception as e:
                    msg = str(e)
                    if 'Permission denied' in msg or 'Timeout' in msg or 'lock' in msg:
                        logging.info(f"Transient error processing page {page_idx+1} of {image_path}: {e}")
                    else:
                        logging.error(f"Error processing page {page_idx+1} of {image_path}: {e}", exc_info=True)
                        log_error(image_path, f"Page {page_idx+1} error: {e}")
                    
                    # Try to save unrotated version on error
                    try:
                        if is_multipage:
                            img.seek(page_idx)
                        page_img = img.convert('RGB')
                        
                        group_dir, lock_path = get_next_group_dir_with_lock(target_dir, MAX_FILES_PER_GROUP)
                        group_name = os.path.basename(group_dir)
                        group_clean = ''.join(c for c in group_name if c.isalnum())
                        subfolder_clean = '_'.join(''.join(c for c in part if c.isalnum()) for part in subfolders) if subfolders else ''
                        base_clean = ''.join(c for c in base if c.isalnum())
                        customer_group = f"{customer_clean}_{group_clean}{FILENAME_SEPARATOR}"
                        
                        if total_pages > 1:
                            if subfolder_clean:
                                name_parts = [subfolder_clean, f"{base_clean}page-{page_idx+1}.pdf"]
                            else:
                                name_parts = [f"{base_clean}page-{page_idx+1}.pdf"]
                        else:
                            if subfolder_clean:
                                name_parts = [subfolder_clean, f"{base_clean}.pdf"]
                            else:
                                name_parts = [f"{base_clean}.pdf"]
                        
                        raw_out_fname = customer_group + '_'.join(name_parts)
                        out_path = Path(group_dir) / raw_out_fname
                        
                        if not out_path.exists():
                            page_img.save(str(out_path), "PDF", resolution=200.0)
                            logging.info(f"Saved (unrotated, error) {out_path}")
                        else:
                            logging.warning(f"(Unrotated, error) page {page_idx+1} not saved, file already exists: {out_path}")
                        
                        if os.path.exists(lock_path):
                            os.remove(lock_path)
                    except Exception as e2:
                        logging.error(f"Failed to save unrotated page {page_idx+1} of {image_path} after error: {e2}")
                    continue

        append_processed_file(image_path)
        logging.info(f"Finished {image_path} in {time.time() - start:.2f}s")
        
        # Remove source file after successful processing (configurable)
        if REMOVE_SOURCE_FILE:
            try:
                os.remove(image_path)
                logging.info(f"Removed source file: {image_path}")
            except Exception as e:
                logging.warning(f"Failed to remove source file {image_path}: {e}")

    except Exception as e:
        logging.error(f"Error on {image_path}: {e}")
        log_error(image_path, str(e))

def process_pdf(pdf_path: str):
    with processed_lock:
        if pdf_path in processed_files:
            logging.info(f"{pdf_path} already processed, skipping.")
            return

    try:
        wait_until_file_is_ready(pdf_path)
    except Exception as e:
        logging.error(f"File not ready for processing: {pdf_path}: {e}")
        log_error(pdf_path, f"File not ready: {e}")
        return

    start = time.time()
    logging.info(f"Processing {pdf_path}")
    try:
        doc = fitz.open(pdf_path)
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        # Get relative path from WATCH_FOLDER to PDF's parent
        rel_dir = os.path.relpath(os.path.dirname(pdf_path), WATCH_FOLDER)
        # Split into parts
        rel_parts = os.path.normpath(rel_dir).split(os.sep)
        # Customer is always the first part
        customer_folder = rel_parts[0]
        # All subfolders under customer (may be empty)
        subfolders = rel_parts[1:] if len(rel_parts) > 1 else []
        # Clean customer folder name and use for both folder and filename prefix
        customer_clean = clean_name(customer_folder, OUTPUT_FOLDER, kind="dir")
        target_dir = os.path.join(OUTPUT_FOLDER, customer_clean)
        os.makedirs(target_dir, exist_ok=True)

        for pno in range(doc.page_count):
            single = fitz.open()
            try:
                logging.info(f"Attempting to extract page {pno+1} from {pdf_path} (doc.page_count={doc.page_count})")
                fallback_used = False
                try:
                    single.insert_pdf(doc, from_page=pno, to_page=pno)
                except IndexError as ie:
                    logging.warning(f"insert_pdf failed for {pdf_path} page {pno+1} (doc.page_count={doc.page_count}): {ie}. Fallback to image-based PDF.")
                    # Fallback: render page to image and create PDF in memory
                    try:
                        page = doc.load_page(pno)
                        pix = page.get_pixmap(dpi=200)
                        img_bytes = pix.tobytes("png")
                        img = Image.open(io.BytesIO(img_bytes))
                        fallback_pdf = fitz.open()
                        rect = fitz.Rect(0, 0, img.width, img.height)
                        pdf_page = fallback_pdf.new_page(width=img.width, height=img.height)
                        pdf_page.insert_image(rect, stream=img_bytes)
                        single.close()
                        single = fallback_pdf
                        fallback_used = True
                        logging.info(f"Fallback PDF created for {pdf_path} page {pno+1} (image-based)")
                    except Exception as fallback_e:
                        logging.error(f"Fallback failed for {pdf_path} page {pno+1}: {fallback_e}")
                        log_error(pdf_path, f"Page {pno+1} error: Fallback failed after insert_pdf IndexError: {fallback_e}")
                        single.close()
                        continue
                logging.info(f"After insert: single has {single.page_count} pages (expected 1)")
                if single.page_count == 0:
                    logging.warning(f"insert_pdf produced empty doc for {pdf_path} page {pno+1} (doc.page_count={doc.page_count}). Fallback to image-based PDF.")
                    # Fallback: render page to image and create PDF in memory
                    try:
                        page = doc.load_page(pno)
                        pix = page.get_pixmap(dpi=200)
                        img_bytes = pix.tobytes("png")
                        img = Image.open(io.BytesIO(img_bytes))
                        fallback_pdf = fitz.open()
                        rect = fitz.Rect(0, 0, img.width, img.height)
                        pdf_page = fallback_pdf.new_page(width=img.width, height=img.height)
                        pdf_page.insert_image(rect, stream=img_bytes)
                        single.close()
                        single = fallback_pdf
                        fallback_used = True
                        logging.info(f"Fallback PDF created for {pdf_path} page {pno+1} (image-based)")
                    except Exception as fallback_e:
                        logging.error(f"Fallback failed for {pdf_path} page {pno+1}: {fallback_e}")
                        log_error(pdf_path, f"Page {pno+1} error: Fallback failed after empty doc: {fallback_e}")
                        single.close()
                        continue
                angle = detect_orientation(single, pdf_path, pno)
                if fallback_used:
                    logging.info(f"Page {pno + 1}: detected rotation {angle}° for {pdf_path} (fallback image-based PDF)")
                else:
                    logging.info(f"Page {pno + 1}: detected rotation {angle}° for {pdf_path}")

                # --- GROUP LOGIC WITH LOCK ---
                group_dir, lock_path = get_next_group_dir_with_lock(target_dir, MAX_FILES_PER_GROUP)
                group_name = os.path.basename(group_dir)
                group_clean = ''.join(c for c in group_name if c.isalnum())

                subfolder_clean = '_'.join(''.join(c for c in part if c.isalnum()) for part in subfolders) if subfolders else ''
                base_clean = ''.join(c for c in base if c.isalnum())
                customer_group = f"{customer_clean}_{group_clean}{FILENAME_SEPARATOR}"
                if subfolder_clean:
                    name_parts = [subfolder_clean, f"{base_clean}page-{pno+1}.pdf"]
                else:
                    name_parts = [f"{base_clean}page-{pno+1}.pdf"]
                raw_out_fname = customer_group + '_'.join(name_parts)
                out_path = Path(group_dir) / raw_out_fname

                saved = False
                if angle:
                    rotated = rotate_pdf(single, angle)
                    if not out_path.exists():
                        rotated.save(str(out_path))
                        logging.info(f"Saved rotated page {pno+1} to {out_path}")
                        saved = True
                    else:
                        logging.warning(f"Rotated page {pno+1} not saved, file already exists: {out_path}")
                    rotated.close()
                else:
                    if not out_path.exists():
                        single.save(str(out_path))
                        logging.info(f"Saved unrotated page {pno+1} to {out_path}")
                        saved = True
                    else:
                        logging.warning(f"Unrotated page {pno+1} not saved, file already exists: {out_path}")
                single.close()

                if os.path.exists(lock_path):
                    os.remove(lock_path)

                if saved:
                    logging.info(f"Saved {out_path}")

            except Exception as e:
                msg = str(e)
                if 'Permission denied' in msg or 'Timeout' in msg or 'lock' in msg:
                    logging.info(f"Transient error processing page {pno+1} of {pdf_path}: {e}")
                else:
                    logging.error(f"Error processing page {pno+1} of {pdf_path}: {e}", exc_info=True)
                    log_error(pdf_path, f"Page {pno+1} error: {e}")
                try:
                    group_dir, lock_path = get_next_group_dir_with_lock(target_dir, MAX_FILES_PER_GROUP)
                    group_name = os.path.basename(group_dir)
                    group_clean = ''.join(c for c in group_name if c.isalnum())
                    subfolder_clean = '_'.join(''.join(c for c in part if c.isalnum()) for part in subfolders) if subfolders else ''
                    base_clean = ''.join(c for c in base if c.isalnum())
                    customer_group = f"{customer_clean}_{group_clean}{FILENAME_SEPARATOR}"
                    if subfolder_clean:
                        name_parts = [subfolder_clean, f"{base_clean}page-{pno+1}.pdf"]
                    else:
                        name_parts = [f"{base_clean}page-{pno+1}.pdf"]
                    raw_out_fname = customer_group + '_'.join(name_parts)
                    out_path = Path(group_dir) / raw_out_fname
                    if not out_path.exists():
                        single.save(str(out_path))
                        logging.info(f"Saved (unrotated, error) {out_path}")
                    else:
                        logging.warning(f"(Unrotated, error) page {pno+1} not saved, file already exists: {out_path}")
                    if os.path.exists(lock_path):
                        os.remove(lock_path)
                except Exception as e2:
                    logging.error(f"Failed to save unrotated page {pno+1} of {pdf_path} after error: {e2}")
                finally:
                    single.close()
                continue

        doc.close()
        append_processed_file(pdf_path)
        logging.info(f"Finished {pdf_path} in {time.time() - start:.2f}s")
        # Remove source file after successful processing and logging (configurable)
        if REMOVE_SOURCE_FILE:
            try:
                os.remove(pdf_path)
                logging.info(f"Removed source file: {pdf_path}")
            except Exception as e:
                logging.warning(f"Failed to remove source file {pdf_path}: {e}")

    except Exception as e:
        logging.error(f"Error on {pdf_path}: {e}")
        log_error(pdf_path, str(e))

# Queue + executor
job_queue = queue.Queue()
executor = ProcessPoolExecutor(max_workers=MAX_WORKERS)

def is_image_file(file_path: str) -> bool:
    """Check if file is a supported image format"""
    return file_path.lower().endswith(IMAGE_EXTENSIONS)

def is_pdf_file(file_path: str) -> bool:
    """Check if file is a PDF"""
    return file_path.lower().endswith(PDF_EXTENSIONS)

def is_supported_file(file_path: str) -> bool:
    """Check if file is any supported format"""
    return file_path.lower().endswith(PROCESS_EXTENSIONS)

def queue_worker():
    while True:
        file_path = job_queue.get()
        job_queue.task_done()
        if file_path is None:
            break
        increment_total()
        
        # Route to appropriate processor based on file type
        if is_pdf_file(file_path):
            future = executor.submit(process_pdf, file_path)
        elif is_image_file(file_path):
            future = executor.submit(process_image, file_path)
        else:
            # File not in supported extensions, skip silently
            logging.debug(f"Skipping unsupported file type: {file_path}")
            continue
            
        future.add_done_callback(update_progress)

# Start single queue thread
t_queue = threading.Thread(target=queue_worker, daemon=True)
t_queue.start()

# Watchdog handler
class FileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = event.src_path
        if not is_supported_file(file_path):
            return
            
        def enqueue_if_needed():
            try:
                wait_until_file_is_ready(file_path)
                with processed_lock:
                    if file_path in processed_files:
                        return
                job_queue.put(file_path)
                file_type = "PDF" if is_pdf_file(file_path) else "image"
                logging.info(f"Enqueued {file_type}: {file_path}")
            except Exception as e:
                log_error(file_path, str(e))
        threading.Thread(target=enqueue_if_needed, daemon=True).start()

def scan_existing_files(root: str):
    """Scan for existing supported files to process"""
    files_to_enqueue = []
    for dirpath, _, files in os.walk(root):
        for fname in files:
            full_path = os.path.join(dirpath, fname)
            if is_supported_file(full_path):
                with processed_lock:
                    if full_path in processed_files:
                        continue
                files_to_enqueue.append(full_path)
    
    def enqueue_file(file_path):
        job_queue.put(file_path)
        file_type = "PDF" if is_pdf_file(file_path) else "image"
        logging.info(f"Enqueued existing {file_type}: {file_path}")
    
    # Parallelize enqueueing
    pool = ThreadPoolExecutor(max_workers=8)
    for f in files_to_enqueue:
        pool.submit(enqueue_file, f)
    pool.shutdown(wait=True)

if __name__ == "__main__":
    # Optional reset
    if os.getenv('RESET_PROGRESS', 'false').lower() == 'true':
        if os.path.exists(PROCESSED_FILE_PATH):
            os.remove(PROCESSED_FILE_PATH)
        processed_files.clear()
        logging.info("Reset processed files list")

    initialize_customer_groups()

    # Log the configured extensions
    logging.info(f"Configured to process extensions: {', '.join(PROCESS_EXTENSIONS)}")
    if PDF_EXTENSIONS:
        logging.info(f"PDF extensions: {', '.join(PDF_EXTENSIONS)}")
    if IMAGE_EXTENSIONS:
        logging.info(f"Image extensions: {', '.join(IMAGE_EXTENSIONS)}")

    observer = Observer()
    observer.schedule(FileHandler(), Path(WATCH_FOLDER), recursive=True)
    observer.start()
    logging.info(f"Watching {WATCH_FOLDER} for supported file types")

    scan_existing_files(WATCH_FOLDER)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutdown requested, terminating...")

        observer.stop()
        observer.join()

        job_queue.put(None)
        t_queue.join()

        for p in executor._processes.values():
            p.terminate()
        executor.shutdown(wait=False, cancel_futures=True)

        logging.info("All done, exiting.")
