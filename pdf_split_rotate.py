import os
import time
import logging
import threading
import queue
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
MAX_WORKERS         = int(os.getenv('MAX_WORKERS', '4'))
RETRIES             = int(os.getenv('FILE_READY_RETRIES', '10'))
RETRY_DELAY         = float(os.getenv('FILE_READY_DELAY', '1'))

# Prepare output folder
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

def detect_orientation(pdf_document, initial_dpi=200, max_trials=3):
    dpi = initial_dpi
    last_rotate = 0
    last_conf = 0
    for trial in range(1, max_trials + 1):
        try:
            pix = pdf_document[0].get_pixmap(dpi=dpi)
            img = Image.open(io.BytesIO(pix.tobytes()))
            osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
            rotate = osd.get('rotate', 0)
            conf = osd.get('orientation_conf', 0)
            logging.debug(f"Trial {trial}: DPI={dpi}, orientation={rotate}, confidence={conf}")
            if conf >= 2:
                if trial > 1:
                    logging.info(f"Orientation stabilized at trial {trial} (DPI={dpi}) with confidence {conf}")
                return rotate
            logging.warning(f"Low orientation confidence ({conf}) at DPI={dpi}; retrying with higher DPI.")
            last_rotate, last_conf = rotate, conf
            dpi += 100
        except Exception as e:
            logging.error(f"Orientation detection failed on trial {trial} (DPI={dpi}): {e}")
            dpi += 100
    logging.warning(
        f"Max trials ({max_trials}) reached. "
        f"Returning last detected orientation {last_rotate} with confidence {last_conf}"
    )
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
        logging.error(f"Error rotating PDF: {e}")
        return page_doc

# === Progress counters ===
total_count = 0
done_count = 0
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
        target_dir = os.path.join(OUTPUT_FOLDER, first_under_root)#rel_dir, base)
        os.makedirs(target_dir, exist_ok=True)

        for pno in range(doc.page_count):
            single = fitz.open()
            single.insert_pdf(doc, from_page=pno, to_page=pno)
            angle = detect_orientation(single)
            logging.info(f"Page {pno + 1}: detected rotation {angle}°")
            out_path = os.path.join(target_dir, f"{'_'.join(os.path.normpath(rel_dir).strip(os.sep).split(os.sep)[1:])} - {base} - page_{pno + 1}.pdf")
            if angle:
                rotated = rotate_pdf(single, angle)
                rotated.save(out_path)
                rotated.close()
            else:
                single.save(out_path)
            single.close()
            logging.info(f"Saved {out_path}")

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
        # increment total before submitting
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
    observer.schedule(PDFHandler(), WATCH_FOLDER, recursive=True)
    observer.start()
    logging.info(f"Watching {WATCH_FOLDER}")

    scan_existing_pdfs(WATCH_FOLDER)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutdown requested, terminating...")

        # Stop watcher
        observer.stop()
        observer.join()

        # Signal queue thread to exit
        job_queue.put(None)
        t_queue.join()

        # Terminate any running workers
        for p in executor._processes.values():
            p.terminate()

        # Shutdown executor immediately
        executor.shutdown(wait=False, cancel_futures=True)

        logging.info("All done, exiting.")
