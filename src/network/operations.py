"""Network-aware file operations with resilience patterns."""

import os
import time
import socket
import threading
from typing import List
from contextlib import contextmanager
from typing import TYPE_CHECKING

from src.network.resilience import CircuitBreaker, RetryHandler

if TYPE_CHECKING:
    from src.config.settings import Config


class NetworkOperations:
    """Network-aware file operations with resilience patterns."""
    
    def __init__(self, config: 'Config'):
        self.config = config
        self.circuit_breaker = CircuitBreaker(
            config.circuit_breaker_failure_threshold,
            config.circuit_breaker_recovery_timeout
        )
        self.retry_handler = RetryHandler(
            config.network_retry_attempts,
            config.network_retry_backoff,
            config.network_retry_max_delay
        )
    
    @property
    def robust_file_operation(self):
        """Combined decorator for circuit breaker + retry."""
        return lambda func: self.circuit_breaker(self.retry_handler(func))
    
    @contextmanager
    def timeout_context(self, timeout: float = None):
        """Context manager for network operation timeouts."""
        timeout = timeout or self.config.network_timeout
        
        original_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(timeout)
            yield
        finally:
            socket.setdefaulttimeout(original_timeout)
    
    def safe_file_read(self, path: str, mode: str = 'rb') -> bytes:
        """Network-safe file reading with resilience."""
        @self.robust_file_operation
        def _read_file():
            with self.timeout_context():
                with open(path, mode) as f:
                    return f.read()
        
        return _read_file()
    
    def safe_file_write(self, path: str, data: bytes, mode: str = 'wb'):
        """Network-safe file writing with resilience."""
        @self.robust_file_operation
        def _write_file():
            with self.timeout_context():
                # Write to temp file first, then atomic rename
                temp_path = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
                try:
                    with open(temp_path, mode) as f:
                        f.write(data)
                        f.flush()
                        os.fsync(f.fileno())
                    
                    # Atomic rename
                    if os.path.exists(path):
                        backup_path = f"{path}.backup.{int(time.time())}"
                        os.rename(path, backup_path)
                    os.rename(temp_path, path)
                    
                except Exception:
                    # Cleanup temp file on error
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    raise
        
        return _write_file()
    
    def safe_makedirs(self, path: str, exist_ok: bool = True):
        """Network-safe directory creation."""
        @self.robust_file_operation
        def _makedirs():
            with self.timeout_context():
                os.makedirs(path, exist_ok=exist_ok)
        
        return _makedirs()
    
    def safe_listdir(self, path: str) -> List[str]:
        """Network-safe directory listing."""
        @self.robust_file_operation
        def _listdir():
            with self.timeout_context():
                return os.listdir(path)
        
        return _listdir()
    
    def safe_path_exists(self, path: str) -> bool:
        """Network-safe path existence check."""
        @self.robust_file_operation
        def _exists():
            with self.timeout_context():
                return os.path.exists(path)
        
        return _exists()
    
    def safe_file_size(self, path: str) -> int:
        """Network-safe file size check."""
        @self.robust_file_operation
        def _get_size():
            with self.timeout_context():
                return os.path.getsize(path)
        
        return _get_size()
    
    def safe_remove(self, path: str):
        """Network-safe file removal."""
        @self.robust_file_operation
        def _remove():
            with self.timeout_context():
                os.remove(path)
        
        return _remove()
