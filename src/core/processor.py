"""Main PDF processing logic with network resilience and memory management."""

import os
import time
import psutil
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

import fitz

from file_utils import clean_name, resolve_collision

if TYPE_CHECKING:
    from src.config.settings import Config
    from src.utils.logging_setup import LoggingSetup
    from src.managers.file_manager import ProcessedFilesManager
    from src.file_operations.checker import FileReadyChecker
    from src.managers.group_manager import GroupManager
    from src.network.operations import NetworkOperations


class PDFProcessor:
    """Main PDF processing logic with network resilience and memory management."""
    
    def __init__(self, config: 'Config', logger: 'LoggingSetup', file_manager: 'ProcessedFilesManager',
                 file_checker: 'FileReadyChecker', group_manager: 'GroupManager', network_ops: 'NetworkOperations'):
        self.config = config
        self.logger = logger
        self.file_manager = file_manager
        self.file_checker = file_checker
        self.group_manager = group_manager
        self.network_ops = network_ops
        
        # Import here to avoid circular imports
        from src.pdf.detector import OrientationDetector
        from src.pdf.rotator import PDFRotator
        
        self.orientation_detector = OrientationDetector()
        self.rotator = PDFRotator()
        self._memory_monitor = self._setup_memory_monitoring()
    
    def _setup_memory_monitoring(self):
        """Setup memory usage monitoring."""
        return {
            'peak_memory': 0,
            'current_files': 0,
            'last_check': time.time()
        }
    
    def _check_memory_usage(self) -> bool:
        """Check if memory usage is within limits."""
        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            
            self._memory_monitor['peak_memory'] = max(
                self._memory_monitor['peak_memory'], 
                memory_mb
            )
            
            if memory_mb > self.config.memory_limit_mb:
                logging.warning(f"Memory usage ({memory_mb:.1f}MB) exceeds limit ({self.config.memory_limit_mb}MB)")
                return False
            
            return True
        except Exception as e:
            logging.warning(f"Could not check memory usage: {e}")
            return True  # Assume OK if can't check
    
    def process_pdf(self, pdf_path: str):
        """Process a single PDF file with enhanced error handling and resource management."""
        if self.file_manager.is_processed(pdf_path):
            logging.info(f"{pdf_path} already processed, skipping.")
            return

        # Check memory before processing
        if not self._check_memory_usage():
            logging.warning(f"Delaying processing of {pdf_path} due to memory pressure")
            time.sleep(5)  # Brief delay to allow memory cleanup

        try:
            self.file_checker.wait_until_ready(pdf_path)
        except Exception as e:
            logging.error(f"File not ready for processing: {pdf_path}: {e}")
            self.logger.log_error(pdf_path, f"File not ready: {e}")
            return

        start_time = time.time()
        logging.info(f"Processing {pdf_path}")
        
        temp_files = []  # Track temporary files for cleanup
        
        try:
            self._memory_monitor['current_files'] += 1
            temp_files = self._process_pdf_pages(pdf_path)
            self.file_manager.mark_processed(pdf_path)
            
            processing_time = time.time() - start_time
            logging.info(f"Finished {pdf_path} in {processing_time:.2f}s")
            
            # Remove source file if configured
            if self.config.remove_source_file:
                try:
                    self.network_ops.safe_remove(pdf_path)
                    logging.info(f"Removed source file: {pdf_path}")
                except Exception as e:
                    logging.warning(f"Failed to remove source file {pdf_path}: {e}")
                    
        except Exception as e:
            logging.error(f"Error processing {pdf_path}: {e}", exc_info=True)
            self.logger.log_error(pdf_path, str(e))
            
        finally:
            self._memory_monitor['current_files'] -= 1
            
            # Cleanup any temporary files
            for temp_file in temp_files:
                try:
                    if self.network_ops.safe_path_exists(temp_file):
                        self.network_ops.safe_remove(temp_file)
                except Exception as e:
                    logging.warning(f"Failed to cleanup temp file {temp_file}: {e}")
    
    def _process_pdf_pages(self, pdf_path: str) -> List[str]:
        """Process all pages in a PDF document, returning list of temp files created."""
        temp_files = []
        doc = None
        
        try:
            # Load PDF with network resilience
            pdf_data = self.network_ops.safe_file_read(pdf_path)
            doc = fitz.open(stream=pdf_data)
            
            file_info = self._extract_file_info(pdf_path)
            
            for page_no in range(doc.page_count):
                try:
                    temp_file = self._process_single_page(doc, pdf_path, page_no, file_info)
                    if temp_file:
                        temp_files.append(temp_file)
                except Exception as e:
                    logging.error(f"Error processing page {page_no+1} of {pdf_path}: {e}")
                    continue
                    
        finally:
            if doc:
                doc.close()
        
        return temp_files
    
    def _extract_file_info(self, pdf_path: str) -> Dict[str, str]:
        """Extract customer and subfolder information from file path."""
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        rel_dir = os.path.relpath(os.path.dirname(pdf_path), self.config.watch_folder)
        rel_parts = os.path.normpath(rel_dir).split(os.sep)
        
        # Customer is always the first part
        customer_folder = rel_parts[0]
        # All subfolders under customer (may be empty)
        subfolders = rel_parts[1:] if len(rel_parts) > 1 else []
        
        # Clean customer folder name
        customer_clean = clean_name(customer_folder, self.config.output_folder, kind="dir")
        target_dir = os.path.join(self.config.output_folder, customer_clean)
        
        # Ensure target directory exists with network resilience
        self.network_ops.safe_makedirs(target_dir, exist_ok=True)
        
        return {
            'base': base,
            'customer_clean': customer_clean,
            'target_dir': target_dir,
            'subfolders': subfolders
        }
    
    def _process_single_page(self, doc, pdf_path: str, page_no: int, file_info: Dict[str, str]) -> Optional[str]:
        """Process a single page from the PDF."""
        single = fitz.open()
        temp_file = None
        
        try:
            single.insert_pdf(doc, from_page=page_no, to_page=page_no)
            
            # Detect orientation
            angle = self.orientation_detector.detect_orientation(single, pdf_path, page_no)
            logging.debug(f"Page {page_no + 1}: detected rotation {angle}° for {pdf_path}")
            
            # Get group directory with lock
            group_dir, lock_path = self.group_manager.get_next_group_dir_with_lock(
                file_info['target_dir']
            )
            
            try:
                with self.group_manager.file_locking.acquire_lock(lock_path):
                    # Generate output filename
                    output_path = self._generate_output_path(group_dir, file_info, page_no)
                    
                    # Create temporary file for atomic write
                    temp_file = f"{output_path}.tmp.{os.getpid()}.{threading.get_ident()}"
                    
                    # Rotate and save to temp file
                    if angle:
                        rotated = self.rotator.rotate_pdf(single, angle)
                        rotated.save(temp_file)
                        rotated.close()
                    else:
                        single.save(temp_file)
                    
                    # Atomic move from temp to final location
                    pdf_data = self.network_ops.safe_file_read(temp_file)
                    self.network_ops.safe_file_write(str(output_path), pdf_data)
                    
                    logging.info(f"Saved {output_path}")
                    
            except Exception as e:
                logging.error(f"Error saving page {page_no+1} of {pdf_path}: {e}")
                
                # Save backup if possible
                try:
                    backup_path = Path(file_info['target_dir']) / f"page{page_no+1}_backup.pdf"
                    single.save(str(backup_path))
                    logging.info(f"Saved backup (unrotated) to {backup_path}")
                except Exception:
                    pass
                raise
                
        finally:
            single.close()
        
        return temp_file
    
    def _generate_output_path(self, group_dir: str, file_info: Dict[str, str], page_no: int) -> Path:
        """Generate the output file path for a processed page."""
        group_name = os.path.basename(group_dir)
        group_clean = ''.join(c for c in group_name if c.isalnum())
        
        # Clean subfolder parts
        subfolder_clean = '_'.join(
            ''.join(c for c in part if c.isalnum()) 
            for part in file_info['subfolders']
        ) if file_info['subfolders'] else ''
        
        base_clean = ''.join(c for c in file_info['base'] if c.isalnum())
        
        # Build filename: customer+group, then separator, then rest
        customer_group = f"{file_info['customer_clean']}_{group_clean}{self.config.filename_separator}"
        
        if subfolder_clean:
            name_parts = [subfolder_clean, f"{base_clean}page{page_no+1}.pdf"]
        else:
            name_parts = [f"{base_clean}page{page_no+1}.pdf"]
            
        raw_filename = customer_group + '_'.join(name_parts)
        return resolve_collision(Path(group_dir) / raw_filename)
