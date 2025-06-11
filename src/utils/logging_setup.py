"""Logging configuration and utilities."""

import os
import time
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.settings import Config


class LoggingSetup:
    """Handles logging configuration and error logging utilities."""
    
    def __init__(self, config: 'Config'):
        self.config = config
        self._setup_logging()
    
    def _setup_logging(self):
        """Initialize logging configuration."""
        # Ensure log directories exist
        os.makedirs(self.config.output_folder, exist_ok=True)
        open(self.config.warnings_log_path, 'a').close()
        
        # Basic logging setup
        logging.basicConfig(
            level=logging.INFO, 
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # Add warnings file handler
        warnings_handler = logging.FileHandler(self.config.warnings_log_path)
        warnings_handler.setLevel(logging.WARNING)
        warnings_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(warnings_handler)
    
    def log_error(self, path: str, msg: str):
        """Log error to dedicated error file."""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(self.config.error_log_path, 'a') as f:
            f.write(f"{timestamp} - {path} - {msg}\n")
