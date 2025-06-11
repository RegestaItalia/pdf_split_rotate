"""File system event handler for new PDF files."""

from watchdog.events import FileSystemEventHandler
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.service import PDFWatcherService


class PDFFileHandler(FileSystemEventHandler):
    """File system event handler for new PDF files."""
    
    def __init__(self, service: 'PDFWatcherService'):
        self.service = service
    
    def on_created(self, event):
        """Handle new file creation events."""
        if event.is_directory or not event.src_path.lower().endswith('.pdf'):
            return
        self.service._enqueue_pdf(event.src_path)
