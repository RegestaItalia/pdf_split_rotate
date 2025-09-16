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
import math
import numpy as np
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logging.warning("OpenCV not available. Fine-grained angle detection will be disabled.")
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

# Fine-grained angle detection settings
ENABLE_FINE_DETECTION = os.getenv('ENABLE_FINE_DETECTION', 'true').lower() == 'true' and OPENCV_AVAILABLE
FINE_ANGLE_THRESHOLD = float(os.getenv('FINE_ANGLE_THRESHOLD', '1.0'))  # Minimum angle to apply fine correction
MAX_FINE_ANGLE = float(os.getenv('MAX_FINE_ANGLE', '10.0'))  # Maximum fine angle to detect

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

def detect_fine_angle(img: Image.Image, source_path: str, page_no: int) -> float:
    """
    Detect fine-grained rotation angle using OpenCV line detection.
    Returns angle in degrees (positive = clockwise rotation needed).
    """
    if not OPENCV_AVAILABLE:
        return 0.0
    
    try:
        # Convert PIL Image to OpenCV format
        img_array = np.array(img)
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array
        
        # Resize if image is too large for processing
        height, width = gray.shape
        if height > 2000 or width > 2000:
            scale = min(2000/height, 2000/width)
            new_height, new_width = int(height * scale), int(width * scale)
            gray = cv2.resize(gray, (new_width, new_height))
        
        # Edge detection with moderate settings
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        # Hough line detection with moderate threshold
        lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=100)
        
        if lines is None or len(lines) < 3:
            logging.debug(f"Insufficient lines detected ({lines.shape[0] if lines is not None else 0}) for fine angle detection: {source_path}, page {page_no+1}")
            return 0.0
        
        # Calculate angles of detected lines
        angles = []
        line_count = min(50, len(lines))  # Check up to 50 lines
        
        for i in range(line_count):
            rho, theta = lines[i][0]
            # Convert to degrees and normalize to [-90, 90]
            angle = np.degrees(theta) - 90
            
            # Focus on nearly horizontal lines (the most common in text documents)
            if abs(angle) <= MAX_FINE_ANGLE:  # Within our fine detection range
                angles.append(angle)
            # Also consider near-vertical lines converted to horizontal equivalent
            elif abs(abs(angle) - 90) <= MAX_FINE_ANGLE:
                if angle > 0:
                    converted_angle = angle - 90
                else:
                    converted_angle = angle + 90
                if abs(converted_angle) <= MAX_FINE_ANGLE:
                    angles.append(converted_angle)
        
        logging.debug(f"Found {len(angles)} valid angles from {line_count} lines for {source_path}, page {page_no+1}")
        
        if len(angles) < 3:
            logging.debug(f"Insufficient valid angles ({len(angles)}) for fine detection: {source_path}, page {page_no+1}")
            return 0.0
        
        # Use median to reduce noise
        median_angle = np.median(angles)
        
        logging.debug(f"Median angle calculated: {median_angle:.3f}° from {len(angles)} angles for {source_path}, page {page_no+1}")
        
        # Only return if angle is significant enough
        if abs(median_angle) >= FINE_ANGLE_THRESHOLD:
            logging.info(f"Fine angle detected: {median_angle:.2f}° for {source_path}, page {page_no+1}")
            return float(median_angle)
        else:
            logging.debug(f"Fine angle {median_angle:.2f}° below threshold {FINE_ANGLE_THRESHOLD}° for {source_path}, page {page_no+1}")
        
        return 0.0
        
    except Exception as e:
        logging.warning(f"Fine angle detection failed for {source_path}, page {page_no+1}: {e}")
        return 0.0

def detect_orientation_enhanced(img: Image.Image, source_path: str, page_no: int, initial_dpi=200, max_trials=3):
    """Enhanced orientation detection combining OCR and fine-grained detection"""
    # First, detect major orientation using existing OCR method
    coarse_angle = detect_orientation_from_image(img, source_path, page_no, initial_dpi, max_trials)
    
    # Apply coarse rotation if needed to get the image roughly upright for fine detection
    working_img = img
    if coarse_angle != 0:
        working_img = img.rotate(coarse_angle, expand=True)
        logging.debug(f"Applied coarse rotation of {coarse_angle}° before fine detection")
    
    # Detect fine angle on the coarse-corrected image
    fine_angle = 0.0
    if ENABLE_FINE_DETECTION:
        fine_angle = detect_fine_angle(working_img, source_path, page_no)
    
    # The total correction needed is the coarse correction plus fine adjustment
    # Note: coarse_angle is already the correction needed (not the detected rotation)
    total_angle = coarse_angle + fine_angle
    
    if fine_angle != 0:
        logging.info(f"Combined angle detection: coarse={coarse_angle}°, fine={fine_angle:.2f}°, total={total_angle:.2f}° for {source_path}, page {page_no+1}")
    else:
        logging.info(f"Angle detection: {coarse_angle}° (no fine correction) for {source_path}, page {page_no+1}")
    
    return total_angle

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
                detected_rotation = int(osd.get('rotate', 0) or 0)
                conf   = float(osd.get('orientation_conf', 0) or 0.0)
                
                # Convert detected rotation to correction angle
                # OCR returns how much text appears rotated clockwise
                # We need to apply the opposite rotation to correct it
                correction_angle = -detected_rotation
                
            except TesseractError as te:
                logging.warning(f"OSD failed for {source_path}, page {page_no+1}: {te}")
                correction_angle, conf = 0, 0.0

            effective_dpi = initial_dpi * (1 + (trial - 1) * 0.5)
            logging.debug(f"Trial {trial}: effective_DPI={effective_dpi:.0f}, detected={detected_rotation if 'detected_rotation' in locals() else 0}°, correction={correction_angle}°, confidence={conf}"
                          f" (File={source_path}, Page={page_no + 1})")

            if conf >= 2:
                if trial > 1:
                    logging.info(f"Orientation detection stabilized: detected={detected_rotation if 'detected_rotation' in locals() else 0}°, correction={correction_angle}° at trial {trial}"
                                 f" (effective_DPI={effective_dpi:.0f}, confidence={conf}) {source_path}, page {page_no+1}")
                return correction_angle

            # too low confidence → retry with upscaled image
            last_rotate, last_conf = correction_angle, conf
            logging.warning(f"Low orientation confidence ({conf:.1f}) at effective_DPI={effective_dpi:.0f}"
                            f" for {source_path}, page {page_no + 1}; retrying with higher resolution.")

        except Exception as e:
            effective_dpi = initial_dpi * (1 + (trial - 1) * 0.5)
            err_msg = (f"Orientation detection failed on trial {trial} "
                       f"(effective_DPI={effective_dpi:.0f}) for {source_path}, page {page_no + 1}: {e}")
            logging.error(err_msg, exc_info=True)
            log_error(source_path, err_msg)

    logging.warning(f"Max trials reached for {source_path}, page {page_no+1}. "
                    f"Returning last correction {last_rotate}° @ confidence {last_conf}")
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

            # Use the enhanced detection method
            return detect_orientation_enhanced(img, source_path, page_no, dpi, 1)  # Single trial since we control DPI here

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
    """Enhanced PDF rotation supporting arbitrary angles with content preservation"""
    if abs(rotation_angle) < 0.1:  # Threshold for negligible angles
        return page_doc
    
    try:
        rotated = fitz.open()
        for page in page_doc:
            # Get original page dimensions
            rect = page.rect
            
            # For arbitrary angles, we need to render to image and back to prevent content loss
            if abs(rotation_angle % 90) > 0.1:  # Non-90-degree rotation
                # High DPI for quality preservation
                dpi = 300
                mat = fitz.Matrix(dpi/72, dpi/72)  # Scale matrix for high DPI
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to PIL Image for rotation
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                
                # Rotate with expansion to prevent cropping
                rotated_img = img.rotate(rotation_angle, expand=True, fillcolor='white')
                
                # Save rotated image back to PDF
                img_bytes_rotated = io.BytesIO()
                rotated_img.save(img_bytes_rotated, format='PNG', dpi=(dpi, dpi))
                img_bytes_rotated.seek(0)
                
                # Create new page with rotated image
                new_page = rotated.new_page(width=rotated_img.width * 72/dpi, height=rotated_img.height * 72/dpi)
                new_page.insert_image(new_page.rect, stream=img_bytes_rotated.getvalue())
                
                logging.debug(f"Applied arbitrary rotation {rotation_angle:.2f}° using image-based method")
            else:
                # For 90-degree multiples, use native PDF rotation for better quality
                mat = fitz.Matrix(1, 1).prerotate(rotation_angle)
                pix = page.get_pixmap(matrix=mat)
                new_page = rotated.new_page(width=pix.width, height=pix.height)
                new_page.insert_image(new_page.rect, pixmap=pix)
                
                logging.debug(f"Applied 90-degree rotation {rotation_angle}° using native PDF method")
        
        return rotated
        
    except Exception as e:
        error_msg = f"Error rotating PDF by {rotation_angle}°: {e}"
        logging.error(error_msg)
        return page_doc

def rotate_image_arbitrary(img: Image.Image, angle: float) -> Image.Image:
    """Rotate PIL Image by arbitrary angle with content preservation"""
    if abs(angle) < 0.1:
        return img
    
    try:
        # Apply the detected angle directly - PIL positive = counterclockwise (which is correct!)
        rotated = img.rotate(angle, expand=True, fillcolor='white')
        logging.debug(f"Applied PIL rotation of {angle:.2f}° (counterclockwise) for correction")
        return rotated
    except Exception as e:
        logging.error(f"Failed to rotate image by {angle:.2f}°: {e}")
        return img

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

def get_next_group_dir_with_lock(target_dir, max_files_per_group, lock_timeout=15):
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
                        logging.warning(f"Lock timeout on {group_dir}, trying next group")
                        break  # Try next group instead of raising error
                    time.sleep(0.05)
            
            if lock_acquired:
                num_files = len([
                    f for f in os.listdir(group_dir)
                    if os.path.isfile(os.path.join(group_dir, f)) and not f.endswith('.lock')
                ])
                if num_files < max_files_per_group:
                    return group_dir, lock_path
                else:
                    # Group is full, release lock and try next
                    try:
                        os.remove(lock_path)
                    except FileNotFoundError:
                        pass
                    lock_acquired = False
        except Exception as e:
            logging.warning(f"Lock error on {group_dir}: {e}, trying next group")
            if lock_acquired:
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
            
            # Track if any errors occurred during processing
            has_errors = False
            
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
                    
                    # Detect orientation using enhanced method
                    angle = detect_orientation_enhanced(page_img, image_path, page_idx)
                    logging.info(f"Page {page_idx + 1}: detected rotation {angle:.2f}° for {image_path}")
                    
                    # Rotate image if needed
                    if abs(angle) >= 0.1:
                        page_img = rotate_image_arbitrary(page_img, angle)
                        logging.info(f"Rotated image by {angle:.2f}° for {image_path} page {page_idx+1}")
                    
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
                        page_img.save(str(out_path), "PDF", resolution=300.0)  # Higher DPI for quality
                        rotation_desc = f"rotated {angle:.2f}°" if abs(angle) >= 0.1 else "unrotated"
                        logging.info(f"Saved {rotation_desc} page {page_idx+1} to {out_path}")
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
                        has_errors = True
                    
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
                            page_img.save(str(out_path), "PDF", resolution=300.0)
                            logging.warning(f"Saved (unrotated, ERROR FALLBACK) {out_path}")
                            log_error(image_path, f"Page {page_idx+1}: Saved unrotated due to processing error")
                        else:
                            logging.warning(f"(Unrotated, error) page {page_idx+1} not saved, file already exists: {out_path}")
                        
                        if os.path.exists(lock_path):
                            os.remove(lock_path)
                    except Exception as e2:
                        logging.error(f"Failed to save unrotated page {page_idx+1} of {image_path} after error: {e2}")
                        log_error(image_path, f"Page {page_idx+1}: Failed to save fallback unrotated file: {e2}")
                        has_errors = True
                    continue

        # Only mark as processed if no errors occurred
        if not has_errors:
            append_processed_file(image_path)
            logging.info(f"Finished {image_path} in {time.time() - start:.2f}s")
        else:
            logging.error(f"Completed {image_path} with errors in {time.time() - start:.2f}s - NOT marking as processed")
            log_error(image_path, "File completed with errors - will be retried on next run")
        
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
        
        # Track if any errors occurred during processing
        has_errors = False
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
                    logging.info(f"Page {pno + 1}: detected rotation {angle:.2f}° for {pdf_path} (fallback image-based PDF)")
                else:
                    logging.info(f"Page {pno + 1}: detected rotation {angle:.2f}° for {pdf_path}")

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
                if abs(angle) >= 0.1:  # Use threshold for meaningful rotation
                    rotated = rotate_pdf(single, angle)
                    if not out_path.exists():
                        rotated.save(str(out_path))
                        logging.info(f"Saved rotated ({angle:.2f}°) page {pno+1} to {out_path}")
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
                    has_errors = True
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
                        logging.warning(f"Saved (unrotated, ERROR FALLBACK) {out_path}")
                        log_error(pdf_path, f"Page {pno+1}: Saved unrotated due to processing error")
                    else:
                        logging.warning(f"(Unrotated, error) page {pno+1} not saved, file already exists: {out_path}")
                    if os.path.exists(lock_path):
                        os.remove(lock_path)
                except Exception as e2:
                    logging.error(f"Failed to save unrotated page {pno+1} of {pdf_path} after error: {e2}")
                    log_error(pdf_path, f"Page {pno+1}: Failed to save fallback unrotated file: {e2}")
                    has_errors = True
                finally:
                    single.close()
                continue

        doc.close()
        
        # Only mark as processed if no errors occurred
        if not has_errors:
            append_processed_file(pdf_path)
            logging.info(f"Finished {pdf_path} in {time.time() - start:.2f}s")
        else:
            logging.error(f"Completed {pdf_path} with errors in {time.time() - start:.2f}s - NOT marking as processed")
            log_error(pdf_path, "File completed with errors - will be retried on next run")
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
