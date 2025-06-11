"""Progress tracking across multiple threads."""

import threading
import logging


class ProgressTracker:
    """Tracks processing progress across multiple threads."""
    
    def __init__(self, initial_processed_count: int = 0):
        self.total_count = initial_processed_count
        self.done_count = initial_processed_count
        self.total_lock = threading.Lock()
        self.done_lock = threading.Lock()
    
    def increment_total(self):
        """Increment the total count of files to process."""
        with self.total_lock:
            self.total_count += 1
    
    def update_progress(self, _future=None):
        """Update progress and log current status."""
        with self.done_lock:
            self.done_count += 1
            pct = (self.done_count / self.total_count * 100) if self.total_count else 0
            logging.info(f"Progress: {self.done_count}/{self.total_count} PDFs processed ({pct:.1f}%)")
