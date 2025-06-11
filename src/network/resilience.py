"""Network resilience patterns: Circuit Breaker and Retry Handler."""

import time
import random
import socket
import logging
import threading
from typing import Callable
from functools import wraps

from src.network.exceptions import CircuitBreakerOpenError


class CircuitBreaker:
    """Circuit breaker pattern implementation for network operations."""
    
    def __init__(self, failure_threshold: int, recovery_timeout: float):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'closed'  # closed, open, half-open
        self.lock = threading.Lock()
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to apply circuit breaker to a function."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            with self.lock:
                if self.state == 'open':
                    if time.time() - self.last_failure_time < self.recovery_timeout:
                        raise CircuitBreakerOpenError("Circuit breaker is open")
                    else:
                        self.state = 'half-open'
                        logging.info("Circuit breaker transitioning to half-open")
            
            try:
                result = func(*args, **kwargs)
                with self.lock:
                    if self.state == 'half-open':
                        self.state = 'closed'
                        self.failure_count = 0
                        logging.info("Circuit breaker closed - operation successful")
                return result
            except Exception as e:
                with self.lock:
                    self.failure_count += 1
                    self.last_failure_time = time.time()
                    
                    if self.failure_count >= self.failure_threshold:
                        self.state = 'open'
                        logging.warning(f"Circuit breaker opened after {self.failure_count} failures")
                raise e
        
        return wrapper


class RetryHandler:
    """Handles retry logic with exponential backoff."""
    
    def __init__(self, max_attempts: int, base_delay: float, max_delay: float, backoff_factor: float = 2.0):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to add retry logic to a function."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(self.max_attempts):
                try:
                    return func(*args, **kwargs)
                except (OSError, IOError, TimeoutError, socket.error) as e:
                    last_exception = e
                    if attempt == self.max_attempts - 1:
                        break
                    
                    # Calculate delay with exponential backoff + jitter
                    delay = min(
                        self.base_delay * (self.backoff_factor ** attempt),
                        self.max_delay
                    )
                    jitter = random.uniform(0, delay * 0.1)  # Add 10% jitter
                    total_delay = delay + jitter
                    
                    logging.warning(f"Network operation failed (attempt {attempt + 1}/{self.max_attempts}): {e}. "
                                  f"Retrying in {total_delay:.2f}s")
                    time.sleep(total_delay)
                except Exception as e:
                    # Non-retryable exceptions
                    logging.error(f"Non-retryable error in network operation: {e}")
                    raise e
            
            raise last_exception
        
        return wrapper
