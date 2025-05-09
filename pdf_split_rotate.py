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
import io
from concurrent.futures import ProcessPoolExecutor
from dotenv import load_dotenv

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
    for i in range(RETRIES):
        try:
            with open(path, 'rb') as f:
                f.read(1)
            return
        except (PermissionError, IOError):
            logging.info(f"{path} not ready, retry {i + 1}/{RETRIES}")
            time.sleep(RETRY_DELAY)
    raise TimeoutError(f"{path} not ready after {RETRIES * RETRY_DELAY}s")

from pytesseract import TesseractError

def detect_orientation(pdf_document, source_path: str, page_no: int, initial_dpi=200, max_trials=3):
    dpi = initial_dpi
    last_rotate = 0
    last_conf = 0

    for trial in range(1, max_trials + 1):
        try:
            # rasterize page → PIL image
            pix = pdf_document[0].get_pixmap(dpi=dpi)
            png_bytes = pix.tobytes("png")   # ensure it's actual PNG data
            img = Image.open(io.BytesIO(png_bytes))

            # run OSD
            try:
                osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
                rotate = int(osd.get('rotate', 0) or 0)
                conf   = float(osd.get('orientation_conf', 0) or 0.0)
            except TesseractError as te:
                logging.warning(f"OSD failed for {source_path}, page {page_no+1}: {te}")
                rotate, conf = 0, 0.0

            logging.debug(f"Trial {trial}: DPI={dpi}, orientation={rotate}, confidence={conf}"
                          f" (File={source_path}, Page={page_no + 1})")

            if conf >= 2:
                if trial > 1:
                    logging.info(f"Orientation ({rotate}) stabilized at trial {trial}"
                                 f" (DPI={dpi}, confidence={conf}) {source_path}, page {page_no+1}")
                return rotate

            # too low confidence → bump DPI and retry
            last_rotate, last_conf = rotate, conf
            logging.warning(f"Low orientation confidence ({conf:.1f}) at DPI={dpi}"
                            f" for {source_path}, page {page_no + 1}; retrying with higher DPI.")
            dpi += 100

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
        logging.info(f"Progress: {done_count}/{total_count} PDFs processed ({pct:.1f}%)")

# The processing function
def process_pdf(pdf_path: str):
    with processed_lock:
        if pdf_path in processed_files:
            logging.info(f"{pdf_path} already processed, skipping.")
            return

    start = time.time()
    logging.info(f"Processing {pdf_path}")
    try:
        doc = fitz.open(pdf_path)
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        rel_dir = os.path.relpath(os.path.dirname(pdf_path), WATCH_FOLDER)
        first_under_root = os.path.normpath(rel_dir).lstrip(os.sep).split(os.sep)[0]
        target_dir = os.path.join(OUTPUT_FOLDER, first_under_root)
        os.makedirs(target_dir, exist_ok=True)

        for pno in range(doc.page_count):
            try:
                single = fitz.open()
                single.insert_pdf(doc, from_page=pno, to_page=pno)

                angle = detect_orientation(single, pdf_path, pno)
                logging.info(f"Page {pno + 1}: detected rotation {angle}° for {pdf_path}")

                out_fname = f"{'_'.join(os.path.normpath(rel_dir).strip(os.sep).split(os.sep)[1:])} - {base} - page_{pno + 1}.pdf"
                out_path  = os.path.join(target_dir, out_fname)

                if angle:
                    rotated = rotate_pdf(single, angle)
                    rotated.save(out_path)
                    rotated.close()
                else:
                    single.save(out_path)
                single.close()

                logging.info(f"Saved {out_path}")

            except Exception as e:
                # Log the error but keep going
                logging.error(f"Error processing page {pno+1} of {pdf_path}: {e}", exc_info=True)
                log_error(pdf_path, f"Page {pno+1} error: {e}")
                # Still save the *original* single-page PDF if you want:
                try:
                    backup_path = os.path.join(target_dir, f"page_{pno+1}_backup.pdf")
                    single.save(backup_path)
                    logging.info(f"Saved backup (unrotated) to {backup_path}")
                except Exception:
                    pass
                finally:
                    single.close()
                continue

        doc.close()
        append_processed_file(pdf_path)
        logging.info(f"Finished {pdf_path} in {time.time() - start:.2f}s")

    except Exception as e:
        logging.error(f"Error on {pdf_path}: {e}")
        log_error(pdf_path, str(e))

# Queue + executor
job_queue = queue.Queue()
executor = ProcessPoolExecutor(max_workers=MAX_WORKERS)

def queue_worker():
    while True:
        pdf_path = job_queue.get()
        job_queue.task_done()
        if pdf_path is None:
            break
        increment_total()
        future = executor.submit(process_pdf, pdf_path)
        future.add_done_callback(update_progress)

# Start single queue thread
t_queue = threading.Thread(target=queue_worker, daemon=True)
t_queue.start()

# Watchdog handler
class PDFHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith('.pdf'):
            return
        try:
            wait_until_file_is_ready(event.src_path)
            with processed_lock:
                if event.src_path in processed_files:
                    return
            job_queue.put(event.src_path)
            logging.info(f"Enqueued {event.src_path}")
        except Exception as e:
            log_error(event.src_path, str(e))

def scan_existing_pdfs(root: str):
    for dirpath, _, files in os.walk(root):
        for fname in files:
            if fname.lower().endswith('.pdf'):
                full = os.path.join(dirpath, fname)
                with processed_lock:
                    if full in processed_files:
                        continue
                wait_until_file_is_ready(full)
                job_queue.put(full)
                logging.info(f"Enqueued existing {full}")

if __name__ == "__main__":
    # Optional reset
    if os.getenv('RESET_PROGRESS', 'false').lower() == 'true':
        if os.path.exists(PROCESSED_FILE_PATH):
            os.remove(PROCESSED_FILE_PATH)
        processed_files.clear()
        logging.info("Reset processed files list")

    observer = Observer()
    observer.schedule(PDFHandler(), Path(WATCH_FOLDER), recursive=True)
    observer.start()
    logging.info(f"Watching {WATCH_FOLDER}")

    scan_existing_pdfs(WATCH_FOLDER)

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
