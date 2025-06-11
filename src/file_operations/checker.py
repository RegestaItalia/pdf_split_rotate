"""File readiness checking with network resilience."""

import os
import time
import random
import logging
import subprocess
from typing import TYPE_CHECKING

from src.network.exceptions import NetworkException

if TYPE_CHECKING:
    from src.config.settings import Config
    from src.network.operations import NetworkOperations


class FileReadyChecker:
    """Handles checking if files are ready for processing with network resilience."""
    
    def __init__(self, config: 'Config', network_ops: 'NetworkOperations'):
        self.config = config
        self.network_ops = network_ops
    
    def wait_until_ready(self, path: str):
        """Wait until file is ready for processing with robust network handling."""
        last_size = -1
        stable_count = 0
        max_retries = self.config.retries * 3  # More retries for network shares
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        for i in range(max_retries):
            try:
                # Use network-safe file operations
                if not self.network_ops.safe_path_exists(path):
                    raise FileNotFoundError(f"File not found: {path}")
                
                size = self.network_ops.safe_file_size(path)
                
                if size == last_size and size > 0:
                    stable_count += 1
                else:
                    stable_count = 0
                last_size = size
                
                # Require file size to be stable for more checks on network shares
                stability_threshold = 3 if self._is_network_path(path) else 2
                if stable_count >= stability_threshold:
                    # Test file access with network resilience
                    try:
                        test_data = self.network_ops.safe_file_read(path)[:1]
                        if len(test_data) > 0 or size == 0:  # Empty files are OK
                            consecutive_errors = 0  # Reset error count on success
                            return
                    except Exception as e:
                        logging.warning(f"File access test failed for {path}: {e}")
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            raise IOError(f"Too many consecutive access failures for {path}")
                
                consecutive_errors = 0  # Reset on successful size check
                    
            except (PermissionError, IOError, FileNotFoundError, NetworkException) as e:
                consecutive_errors += 1
                logging.info(f"{path} not ready, retry {i + 1}/{max_retries}: {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    raise IOError(f"Too many consecutive errors accessing {path}: {e}")
            
            # Dynamic delay based on network conditions
            delay = self._calculate_adaptive_delay(i, consecutive_errors)
            time.sleep(delay)
        
        raise TimeoutError(f"{path} not ready after {max_retries * self.config.retry_delay}s")
    
    def _is_network_path(self, path: str) -> bool:
        """Detect if path is on a network share."""
        try:
            # Windows UNC path
            if path.startswith('\\\\'):
                return True
            
            # Check if drive is network mapped (Windows)
            if os.name == 'nt':
                drive = os.path.splitdrive(path)[0]
                if drive:
                    try:
                        result = subprocess.run(
                            ['net', 'use', drive], 
                            capture_output=True, 
                            text=True, 
                            timeout=5
                        )
                        return 'Remote' in result.stdout
                    except:
                        pass
            
            return False
        except Exception:
            return False  # Assume local if can't determine
    
    def _calculate_adaptive_delay(self, attempt: int, consecutive_errors: int) -> float:
        """Calculate adaptive delay based on attempt number and error rate."""
        base_delay = self.config.retry_delay
        
        # Exponential backoff with jitter
        delay = base_delay * (1.5 ** min(attempt, 10))
        
        # Additional delay for consecutive errors
        if consecutive_errors > 0:
            delay *= (1 + consecutive_errors * 0.5)
        
        # Add jitter (10-20% randomization)
        jitter = random.uniform(0.1, 0.2) * delay
        
        # Cap the maximum delay
        max_delay = self.config.network_retry_max_delay
        return min(delay + jitter, max_delay)
