"""Management of processed files with network resilience."""

import os
import logging
import threading
from typing import Set, TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.settings import Config
    from src.network.operations import NetworkOperations


class ProcessedFilesManager:
    """Manages the tracking of processed files with network resilience."""
    
    def __init__(self, config: 'Config'):
        self.config = config
        self.processed_files: Set[str] = set()
        self.lock = threading.Lock()
        # Initialize network operations after all classes are defined
        self.network_ops = None
    
    def set_network_ops(self, network_ops: 'NetworkOperations'):
        """Set network operations instance after initialization."""
        self.network_ops = network_ops
        self.processed_files = self._load_processed_files()
    
    def _load_processed_files(self) -> Set[str]:
        """Load the set of already processed files."""
        if not self.network_ops:
            # Fallback to basic file operations during initialization
            if os.path.exists(self.config.processed_file_path):
                with open(self.config.processed_file_path, 'r') as f:
                    return set(f.read().splitlines())
            return set()
        
        try:
            if self.network_ops.safe_path_exists(self.config.processed_file_path):
                data = self.network_ops.safe_file_read(self.config.processed_file_path, 'r')
                if isinstance(data, bytes):
                    data = data.decode('utf-8')
                return set(data.splitlines())
        except Exception as e:
            logging.warning(f"Error loading processed files: {e}")
        
        return set()
    
    def is_processed(self, path: str) -> bool:
        """Check if a file has been processed."""
        with self.lock:
            return path in self.processed_files
    
    def mark_processed(self, path: str):
        """Mark a file as processed with network resilience."""
        try:
            if self.network_ops:
                # Append to file with network resilience
                existing_data = b""
                if self.network_ops.safe_path_exists(self.config.processed_file_path):
                    existing_data = self.network_ops.safe_file_read(self.config.processed_file_path)
                
                new_data = existing_data + f"{path}\n".encode('utf-8')
                self.network_ops.safe_file_write(self.config.processed_file_path, new_data)
            else:
                # Fallback to basic file operations
                with open(self.config.processed_file_path, 'a') as f:
                    f.write(path + "\n")
            
            with self.lock:
                self.processed_files.add(path)
                
        except Exception as e:
            logging.error(f"Error marking file as processed {path}: {e}")
    
    def reset(self):
        """Reset the processed files list."""
        try:
            if self.network_ops:
                if self.network_ops.safe_path_exists(self.config.processed_file_path):
                    self.network_ops.safe_remove(self.config.processed_file_path)
            else:
                if os.path.exists(self.config.processed_file_path):
                    os.remove(self.config.processed_file_path)
            
            with self.lock:
                self.processed_files.clear()
            
            logging.info("Reset processed files list")
            
        except Exception as e:
            logging.error(f"Error resetting processed files: {e}")
