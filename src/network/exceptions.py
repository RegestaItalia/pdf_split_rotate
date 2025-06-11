"""Network-related exceptions."""


class NetworkException(Exception):
    """Base exception for network-related errors."""
    pass


class CircuitBreakerOpenError(NetworkException):
    """Raised when circuit breaker is open."""
    pass
