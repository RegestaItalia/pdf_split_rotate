"""Main service with hybrid concurrency and advanced network resilience."""

import os
import time
import queue
import logging
import threading
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from watchdog.observers import Observer

from src.config.settings import Config
from src.utils.logging_setup import LoggingSetup
from src.network.operations import NetworkOperations
from src.managers.file_manager import ProcessedFilesManager
from src.file_operations.checker import FileReadyChecker
from src.managers.group_manager import GroupManager
from src.core.processor import PDFProcessor
from src.managers.progress_tracker import ProgressTracker
from src.file_operations.handler import PDFFileHandler

if TYPE_CHECKING:
    pass


class PDFWatcherService:
    """Main service with hybrid concurrency and advanced network resilience."""
    
    def __init__(self):
        self.config = Config.load_from_env()
        self.logger = LoggingSetup(self.config)
        self.network_ops = NetworkOperations(self.config)
        
        # Initialize file manager and set network operations
        self.file_manager = ProcessedFilesManager(self.config)
        self.file_manager.set_network_ops(self.network_ops)
        
        self.file_checker = FileReadyChecker(self.config, self.network_ops)
        self.group_manager = GroupManager(self.config, self.network_ops)
        self.processor = PDFProcessor(
            self.config, self.logger, self.file_manager, 
            self.file_checker, self.group_manager, self.network_ops
        )
        self.progress_tracker = ProgressTracker(len(self.file_manager.processed_files))
        
        # Hybrid executor architecture for optimal performance
        self.job_queue = queue.Queue(maxsize=self.config.queue_max_size)
        
        # IO-bound operations (file handling) use ThreadPool
        self.io_executor = ThreadPoolExecutor(
            max_workers=self.config.io_thread_workers,
            thread_name_prefix="PDF-IO"
        )
        
        # CPU-bound operations (OCR) use ProcessPool when beneficial
        self.cpu_executor = ProcessPoolExecutor(
            max_workers=min(self.config.cpu_process_workers, self.config.max_workers)
        )
        
        self.queue_workers = []
        self.observer = None
        self.shutdown_event = threading.Event()
        self._stats = {
            'processed_count': 0,
            'error_count': 0,
            'start_time': time.time(),
            'peak_queue_size': 0
        }
    
    def _start_queue_workers(self):
        """Start multiple queue worker threads for better parallelization."""
        worker_count = min(self.config.max_workers, self.config.io_thread_workers)
        
        for i in range(worker_count):
            worker = threading.Thread(
                target=self._queue_worker,
                name=f"QueueWorker-{i}",
                daemon=True
            )
            worker.start()
            self.queue_workers.append(worker)
        
        logging.info(f"Started {worker_count} queue worker threads")
    
    def _queue_worker(self):
        """Enhanced worker thread with better error handling and backpressure."""
        worker_name = threading.current_thread().name
        
        while not self.shutdown_event.is_set():
            try:
                # Use timeout to allow periodic shutdown checks
                pdf_path = self.job_queue.get(timeout=1.0)
                
                if pdf_path is None:  # Shutdown signal
                    break
                
                # Update queue statistics
                current_queue_size = self.job_queue.qsize()
                self._stats['peak_queue_size'] = max(
                    self._stats['peak_queue_size'],
                    current_queue_size
                )
                
                # Process with timeout and error isolation
                self._process_with_isolation(pdf_path, worker_name)
                
            except queue.Empty:
                continue  # Normal timeout, check shutdown
            except Exception as e:
                logging.error(f"Unexpected error in {worker_name}: {e}")
                time.sleep(1)  # Brief pause to prevent tight error loops
    
    def _process_with_isolation(self, pdf_path: str, worker_name: str):
        """Process PDF with proper error isolation and resource management."""
        start_time = time.time()
        
        try:
            self.progress_tracker.increment_total()
            
            # Submit to IO executor with timeout
            future = self.io_executor.submit(self.processor.process_pdf, pdf_path)
            
            # Wait with timeout to prevent hanging
            timeout = max(300, self.config.network_timeout * 10)  # 5 min minimum
            future.result(timeout=timeout)
            
            self._stats['processed_count'] += 1
            processing_time = time.time() - start_time
            
            if processing_time > 60:  # Log slow processing
                logging.warning(f"Slow processing detected: {pdf_path} took {processing_time:.1f}s")
            
        except Exception as e:
            self._stats['error_count'] += 1
            error_msg = f"Processing failed in {worker_name} for {pdf_path}: {e}"
            logging.error(error_msg)
            self.logger.log_error(pdf_path, str(e))
            
        finally:
            self.progress_tracker.update_progress()
            self.job_queue.task_done()
    
    def _enqueue_pdf(self, pdf_path: str):
        """Enhanced PDF enqueueing with backpressure handling."""
        def enqueue_with_backpressure():
            try:
                # Check if queue is getting full
                current_size = self.job_queue.qsize()
                if current_size > self.config.queue_max_size * 0.8:
                    logging.warning(f"Queue near capacity ({current_size}/{self.config.queue_max_size}), "
                                  f"applying backpressure for {pdf_path}")
                    time.sleep(2)  # Brief delay to allow processing to catch up
                
                # Verify file is ready and not already processed
                self.file_checker.wait_until_ready(pdf_path)
                
                if not self.file_manager.is_processed(pdf_path):
                    # Try to enqueue with timeout to prevent blocking
                    self.job_queue.put(pdf_path, timeout=10)
                    logging.info(f"Enqueued {pdf_path} (queue size: {self.job_queue.qsize()})")
                else:
                    logging.debug(f"Skipping already processed file: {pdf_path}")
                    
            except queue.Full:
                logging.error(f"Queue full, dropping {pdf_path}")
                self.logger.log_error(pdf_path, "Queue full - file dropped")
            except Exception as e:
                logging.error(f"Error enqueueing {pdf_path}: {e}")
                self.logger.log_error(pdf_path, str(e))
        
        # Run enqueueing in separate thread to avoid blocking file watcher
        threading.Thread(
            target=enqueue_with_backpressure,
            name=f"Enqueue-{os.path.basename(pdf_path)}",
            daemon=True
        ).start()
    
    def scan_existing_pdfs(self):
        """Scan existing PDFs with batched processing and progress reporting."""
        logging.info("Scanning for existing PDFs...")
        
        pdfs_found = []
        scan_start = time.time()
        
        try:
            for dirpath, _, files in os.walk(self.config.watch_folder):
                for fname in files:
                    if fname.lower().endswith('.pdf'):
                        full_path = os.path.join(dirpath, fname)
                        if not self.file_manager.is_processed(full_path):
                            pdfs_found.append(full_path)
        except Exception as e:
            logging.error(f"Error scanning directory {self.config.watch_folder}: {e}")
            return
        
        scan_time = time.time() - scan_start
        logging.info(f"Found {len(pdfs_found)} unprocessed PDFs in {scan_time:.1f}s")
        
        if not pdfs_found:
            return
        
        # Process in batches to avoid overwhelming the queue
        batch_size = min(self.config.batch_size, self.config.queue_max_size // 4)
        
        for i in range(0, len(pdfs_found), batch_size):
            batch = pdfs_found[i:i + batch_size]
            
            # Submit batch to IO executor for enqueueing
            with ThreadPoolExecutor(max_workers=min(8, len(batch))) as batch_executor:
                enqueue_futures = [
                    batch_executor.submit(self._enqueue_existing_pdf, pdf_path)
                    for pdf_path in batch
                ]
                
                # Wait for batch to be enqueued
                for future in as_completed(enqueue_futures, timeout=60):
                    try:
                        future.result()
                    except Exception as e:
                        logging.warning(f"Error enqueueing file in batch: {e}")
            
            # Brief pause between batches to allow processing
            if i + batch_size < len(pdfs_found):
                time.sleep(1)
                logging.info(f"Enqueued batch {i//batch_size + 1} "
                           f"({min(i + batch_size, len(pdfs_found))}/{len(pdfs_found)} files)")
    
    def _enqueue_existing_pdf(self, pdf_path: str):
        """Enqueue a single existing PDF file."""
        try:
            self.job_queue.put(pdf_path, timeout=5)
            logging.debug(f"Enqueued existing {pdf_path}")
        except queue.Full:
            logging.warning(f"Queue full, will retry {pdf_path} later")
            # Could implement retry logic here
        except Exception as e:
            logging.error(f"Error enqueueing existing file {pdf_path}: {e}")
    
    def _log_periodic_stats(self):
        """Log periodic statistics about processing."""
        runtime = time.time() - self._stats['start_time']
        rate = self._stats['processed_count'] / max(runtime, 1)
        
        logging.info(
            f"Stats: {self._stats['processed_count']} processed, "
            f"{self._stats['error_count']} errors, "
            f"{rate:.1f} files/min, "
            f"queue: {self.job_queue.qsize()}, "
            f"peak queue: {self._stats['peak_queue_size']}"
        )
    
    def start(self):
        """Start the enhanced PDF watching service."""
        logging.info("Starting PDF processing service with enhanced resilience...")
        
        # Reset progress if configured
        if self.config.reset_progress:
            self.file_manager.reset()
        
        # Initialize customer groups with network resilience
        try:
            self.group_manager.initialize_customer_groups()
        except Exception as e:
            logging.error(f"Error initializing customer groups: {e}")
        
        # Start queue worker threads
        self._start_queue_workers()
        
        # Setup file system watcher
        self.observer = Observer()
        handler = PDFFileHandler(self)
        self.observer.schedule(handler, Path(self.config.watch_folder), recursive=True)
        self.observer.start()
        logging.info(f"Watching {self.config.watch_folder}")
        
        # Scan existing files
        self.scan_existing_pdfs()
        
        # Start periodic stats logging
        stats_thread = threading.Thread(
            target=self._periodic_stats_logger,
            daemon=True
        )
        stats_thread.start()
        
        # Keep running until interrupted
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Shutdown requested, terminating...")
            self.shutdown()
    
    def _periodic_stats_logger(self):
        """Log statistics periodically."""
        while not self.shutdown_event.wait(300):  # Every 5 minutes
            self._log_periodic_stats()
    
    def shutdown(self):
        """Enhanced graceful shutdown with proper resource cleanup."""
        logging.info("Initiating graceful shutdown...")
        
        # Set shutdown event
        self.shutdown_event.set()
        
        # Stop file system observer
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=10)
        
        # Signal queue workers to stop
        for _ in self.queue_workers:
            try:
                self.job_queue.put(None, timeout=1)
            except queue.Full:
                pass
        
        # Wait for queue workers to finish
        for worker in self.queue_workers:
            worker.join(timeout=10)
        
        # Wait for remaining jobs to complete
        try:
            logging.info("Waiting for remaining jobs to complete...")
            remaining_jobs = self.job_queue.qsize()
            if remaining_jobs > 0:
                logging.info(f"Waiting for {remaining_jobs} remaining jobs...")
                self.job_queue.join()
        except Exception as e:
            logging.warning(f"Error waiting for job completion: {e}")
        
        # Shutdown executors
        logging.info("Shutting down executors...")
        self.io_executor.shutdown(wait=True, cancel_futures=False)
        self.cpu_executor.shutdown(wait=True, cancel_futures=False)
        
        # Shutdown group manager
        self.group_manager.shutdown()
        
        # Final statistics
        self._log_periodic_stats()
        logging.info("Shutdown complete.")
