"""Advanced file locking system with heartbeat and stale lock detection."""

import os
import time
import psutil
import logging
import threading
from typing import Dict, Any
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.settings import Config
    from src.network.operations import NetworkOperations


class AdvancedFileLocking:
    """Advanced file locking system with heartbeat and stale lock detection."""
    
    def __init__(self, config: 'Config', network_ops: 'NetworkOperations'):
        self.config = config
        self.network_ops = network_ops
        self.active_locks: Dict[str, Dict[str, Any]] = {}
        self.lock_registry_lock = threading.Lock()
        self.heartbeat_thread = None
        self.cleanup_thread = None
        self.shutdown_event = threading.Event()
        self._start_maintenance_threads()
    
    def _start_maintenance_threads(self):
        """Start heartbeat and cleanup maintenance threads."""
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_worker, 
            daemon=True
        )
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_worker, 
            daemon=True
        )
        self.heartbeat_thread.start()
        self.cleanup_thread.start()
    
    def _heartbeat_worker(self):
        """Maintain heartbeat for active locks."""
        while not self.shutdown_event.wait(self.config.file_lock_heartbeat_interval):
            try:
                with self.lock_registry_lock:
                    for lock_path, lock_info in list(self.active_locks.items()):
                        try:
                            # Update heartbeat timestamp in lock file
                            heartbeat_data = f"{os.getpid()}:{threading.get_ident()}:{time.time()}"
                            self.network_ops.safe_file_write(lock_path, heartbeat_data.encode())
                        except Exception as e:
                            logging.warning(f"Failed to update heartbeat for lock {lock_path}: {e}")
                            # Remove from active locks if can't maintain heartbeat
                            del self.active_locks[lock_path]
            except Exception as e:
                logging.error(f"Error in heartbeat worker: {e}")
    
    def _cleanup_worker(self):
        """Clean up stale locks."""
        while not self.shutdown_event.wait(self.config.stale_lock_cleanup_interval):
            try:
                self._cleanup_stale_locks()
            except Exception as e:
                logging.error(f"Error in lock cleanup worker: {e}")
    
    def _cleanup_stale_locks(self):
        """Remove stale lock files."""
        # This would scan for .lock files and check if they're stale
        # Implementation depends on your specific lock file patterns
        pass
    
    @contextmanager
    def acquire_lock(self, lock_path: str, timeout: float = None):
        """Acquire a file lock with heartbeat maintenance."""
        timeout = timeout or self.config.file_lock_timeout
        start_time = time.time()
        lock_acquired = False
        
        try:
            # Try to acquire lock
            while True:
                try:
                    # Create lock file with process/thread info
                    lock_data = f"{os.getpid()}:{threading.get_ident()}:{time.time()}"
                    
                    # Try exclusive creation
                    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    try:
                        os.write(fd, lock_data.encode())
                    finally:
                        os.close(fd)
                    
                    lock_acquired = True
                    break
                    
                except FileExistsError:
                    if time.time() - start_time > timeout:
                        raise TimeoutError(f"Timeout acquiring lock: {lock_path}")
                    
                    # Check if existing lock is stale
                    if self._is_lock_stale(lock_path):
                        try:
                            os.remove(lock_path)
                            logging.info(f"Removed stale lock: {lock_path}")
                            continue
                        except FileNotFoundError:
                            continue
                    
                    time.sleep(0.1)
            
            # Register lock for heartbeat
            with self.lock_registry_lock:
                self.active_locks[lock_path] = {
                    'acquired_at': time.time(),
                    'pid': os.getpid(),
                    'thread_id': threading.get_ident()
                }
            
            yield lock_path
            
        finally:
            if lock_acquired:
                # Remove from active locks
                with self.lock_registry_lock:
                    self.active_locks.pop(lock_path, None)
                
                # Remove lock file
                try:
                    os.remove(lock_path)
                except FileNotFoundError:
                    pass
    
    def _is_lock_stale(self, lock_path: str) -> bool:
        """Check if a lock file is stale."""
        try:
            with open(lock_path, 'r') as f:
                lock_data = f.read().strip()
            
            if ':' not in lock_data:
                return True  # Invalid lock format
            
            parts = lock_data.split(':')
            if len(parts) < 3:
                return True
            
            try:
                lock_pid = int(parts[0])
                lock_time = float(parts[2])
            except ValueError:
                return True
            
            # Check if process still exists
            try:
                process = psutil.Process(lock_pid)
                if not process.is_running():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return True
            
            # Check if lock is too old
            if time.time() - lock_time > self.config.file_lock_timeout * 2:
                return True
            
            return False
            
        except Exception:
            return True  # Assume stale if can't read
    
    def shutdown(self):
        """Shutdown the locking system."""
        self.shutdown_event.set()
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=5)
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)
