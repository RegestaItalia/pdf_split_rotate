"""Configuration settings for the PDF processing service."""

import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Config:
    """Configuration settings loaded from environment variables."""
    watch_folder: str
    output_folder: str
    processed_file_path: str
    error_log_path: str
    warnings_log_path: str
    max_workers: int
    retries: int
    retry_delay: float
    filename_separator: str
    max_files_per_group: int
    remove_source_file: bool
    reset_progress: bool
    
    # Network resilience settings
    network_timeout: float
    network_retry_attempts: int
    network_retry_backoff: float
    network_retry_max_delay: float
    circuit_breaker_failure_threshold: int
    circuit_breaker_recovery_timeout: float
    
    # Advanced concurrency settings
    io_thread_workers: int
    cpu_process_workers: int
    queue_max_size: int
    memory_limit_mb: int
    
    # File operation settings
    file_lock_timeout: float
    file_lock_heartbeat_interval: float
    stale_lock_cleanup_interval: float
    batch_size: int

    @classmethod
    def load_from_env(cls) -> 'Config':
        """Load configuration from environment variables."""
        load_dotenv(override=True)
        return cls(
            watch_folder=os.path.abspath(os.getenv('WATCH_FOLDER', './input')),
            output_folder=os.path.abspath(os.getenv('OUTPUT_FOLDER', './output')),
            processed_file_path=os.path.abspath(os.getenv('PROCESSED_FILE_PATH', './processed_files.txt')),
            error_log_path=os.path.abspath(os.getenv('ERROR_LOG_PATH', './error_log.txt')),
            warnings_log_path=os.path.abspath(os.getenv('WARNINGS_LOG_PATH', './warnings_log.txt')),
            max_workers=int(os.getenv('MAX_WORKERS', '4')),
            retries=int(os.getenv('FILE_READY_RETRIES', '10')),
            retry_delay=float(os.getenv('FILE_READY_DELAY', '1')),
            filename_separator=os.getenv('FILENAME_SEPARATOR', '__EKR__'),
            max_files_per_group=int(os.getenv('MAX_FILES_PER_GROUP', '10000')),
            remove_source_file=os.getenv('REMOVE_SOURCE_FILE', 'false').lower() == 'true',
            reset_progress=os.getenv('RESET_PROGRESS', 'false').lower() == 'true',
            
            # Network resilience settings
            network_timeout=float(os.getenv('NETWORK_TIMEOUT', '30.0')),
            network_retry_attempts=int(os.getenv('NETWORK_RETRY_ATTEMPTS', '5')),
            network_retry_backoff=float(os.getenv('NETWORK_RETRY_BACKOFF', '2.0')),
            network_retry_max_delay=float(os.getenv('NETWORK_RETRY_MAX_DELAY', '60.0')),
            circuit_breaker_failure_threshold=int(os.getenv('CIRCUIT_BREAKER_FAILURE_THRESHOLD', '10')),
            circuit_breaker_recovery_timeout=float(os.getenv('CIRCUIT_BREAKER_RECOVERY_TIMEOUT', '300.0')),
            
            # Advanced concurrency settings
            io_thread_workers=int(os.getenv('IO_THREAD_WORKERS', str(min(32, (os.cpu_count() or 1) + 4)))),
            cpu_process_workers=int(os.getenv('CPU_PROCESS_WORKERS', str(os.cpu_count() or 1))),
            queue_max_size=int(os.getenv('QUEUE_MAX_SIZE', '1000')),
            memory_limit_mb=int(os.getenv('MEMORY_LIMIT_MB', '4096')),
            
            # File operation settings
            file_lock_timeout=float(os.getenv('FILE_LOCK_TIMEOUT', '60.0')),
            file_lock_heartbeat_interval=float(os.getenv('FILE_LOCK_HEARTBEAT_INTERVAL', '5.0')),
            stale_lock_cleanup_interval=float(os.getenv('STALE_LOCK_CLEANUP_INTERVAL', '300.0')),
            batch_size=int(os.getenv('BATCH_SIZE', '10'))
        )
