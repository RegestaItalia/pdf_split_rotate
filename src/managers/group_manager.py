"""Customer groups and file organization with robust network-aware locking."""

import os
import logging
import threading
from typing import Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.settings import Config
    from src.network.operations import NetworkOperations
    from src.file_operations.locking import AdvancedFileLocking


class GroupManager:
    """Manages customer groups and file organization with robust network-aware locking."""
    
    def __init__(self, config: 'Config', network_ops: 'NetworkOperations'):
        self.config = config
        self.network_ops = network_ops
        # Import here to avoid circular imports
        from src.file_operations.locking import AdvancedFileLocking
        self.file_locking = AdvancedFileLocking(config, network_ops)
        self.customer_group_state: Dict[str, List[int]] = {}
        self.state_lock = threading.Lock()
    
    def initialize_customer_groups(self):
        """Initialize customer group state from existing output directory with network resilience."""
        try:
            if not self.network_ops.safe_path_exists(self.config.output_folder):
                self.network_ops.safe_makedirs(self.config.output_folder)
                return
            
            customer_dirs = self.network_ops.safe_listdir(self.config.output_folder)
            
            for customer_dir in customer_dirs:
                customer_path = os.path.join(self.config.output_folder, customer_dir)
                
                if not self.network_ops.safe_path_exists(customer_path):
                    continue
                
                try:
                    self._process_customer_directory(customer_dir, customer_path)
                except Exception as e:
                    logging.warning(f"Error processing customer directory {customer_dir}: {e}")
                    # Set default state for this customer
                    with self.state_lock:
                        self.customer_group_state[customer_dir] = [1, 0]
                        
        except Exception as e:
            logging.error(f"Error initializing customer groups: {e}")
    
    def _process_customer_directory(self, customer_dir: str, customer_path: str):
        """Process a single customer directory to determine group state."""
        try:
            entries = self.network_ops.safe_listdir(customer_path)
        except Exception as e:
            logging.warning(f"Could not list customer directory {customer_path}: {e}")
            return
        
        group_numbers = []
        group_counts = {}
        
        for entry in entries:
            if not entry.startswith('group_'):
                continue
                
            entry_path = os.path.join(customer_path, entry)
            try:
                if not self.network_ops.safe_path_exists(entry_path):
                    continue
                    
                group_num = int(entry.split('_')[1])
                group_numbers.append(group_num)
                
                # Count files in group directory
                try:
                    group_files = self.network_ops.safe_listdir(entry_path)
                    file_count = len([
                        f for f in group_files 
                        if not f.endswith('.lock') and not f.startswith('.')
                    ])
                    group_counts[group_num] = file_count
                except Exception as e:
                    logging.warning(f"Error counting files in {entry_path}: {e}")
                    group_counts[group_num] = 0
                    
            except (IndexError, ValueError, Exception) as e:
                logging.warning(f"Invalid group directory name {entry}: {e}")
                continue
        
        with self.state_lock:
            if group_numbers:
                max_group = max(group_numbers)
                count = group_counts.get(max_group, 0)
                self.customer_group_state[customer_dir] = [max_group, count]
            else:
                self.customer_group_state[customer_dir] = [1, 0]
    
    def get_next_group_dir_with_lock(self, target_dir: str) -> Tuple[str, str]:
        """Get the next available group directory with robust network-aware locking."""
        group_num = 1
        max_attempts = 100  # Prevent infinite loops
        
        for attempt in range(max_attempts):
            group_dir = os.path.join(target_dir, f'group_{group_num}')
            
            try:
                # Ensure group directory exists
                self.network_ops.safe_makedirs(group_dir, exist_ok=True)
                
                lock_path = os.path.join(group_dir, '.group.lock')
                
                # Try to acquire lock with timeout
                with self.file_locking.acquire_lock(lock_path, self.config.file_lock_timeout):
                    # Count files while holding the lock
                    try:
                        files = self.network_ops.safe_listdir(group_dir)
                        file_count = len([
                            f for f in files
                            if not f.endswith('.lock') and not f.startswith('.') 
                            and self._is_regular_file(os.path.join(group_dir, f))
                        ])
                    except Exception as e:
                        logging.warning(f"Error counting files in {group_dir}: {e}")
                        file_count = 0
                    
                    if file_count < self.config.max_files_per_group:
                        # Found available group, but keep the lock
                        return group_dir, lock_path
                    
                    # Group is full, try next one
                    logging.info(f"Group {group_num} is full ({file_count} files), trying next group")
                    
            except TimeoutError:
                logging.warning(f"Timeout acquiring lock for group {group_num}, trying next group")
            except Exception as e:
                logging.warning(f"Error processing group {group_num}: {e}, trying next group")
            
            group_num += 1
        
        raise RuntimeError(f"Could not find available group after {max_attempts} attempts")
    
    def _is_regular_file(self, path: str) -> bool:
        """Check if path is a regular file with network resilience."""
        try:
            return self.network_ops.safe_path_exists(path) and not os.path.isdir(path)
        except Exception:
            return False
    
    def shutdown(self):
        """Shutdown the group manager."""
        self.file_locking.shutdown()
