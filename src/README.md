# PDF Split and Rotate Service - Refactored Structure

## Overview

This project has been refactored to follow SOLID principles and best practices. The monolithic files have been split into a modular structure for better maintainability, testability, and separation of concerns.

## Directory Structure

```
src/
├── __init__.py                    # Package initialization
├── main.py                       # Main entry point
├── config/
│   ├── __init__.py
│   └── settings.py              # Configuration management (Config class)
├── core/
│   ├── __init__.py
│   ├── service.py               # Main service orchestrator (PDFWatcherService)
│   └── processor.py             # PDF processing logic (PDFProcessor)
├── managers/
│   ├── __init__.py
│   ├── file_manager.py          # Processed files tracking (ProcessedFilesManager)
│   ├── group_manager.py         # Customer groups management (GroupManager)
│   └── progress_tracker.py     # Progress tracking (ProgressTracker)
├── network/
│   ├── __init__.py
│   ├── operations.py            # Network-safe file operations (NetworkOperations)
│   ├── resilience.py            # Circuit breaker and retry patterns
│   └── exceptions.py            # Network-related exceptions
├── pdf/
│   ├── __init__.py
│   ├── detector.py              # Orientation detection (OrientationDetector)
│   └── rotator.py               # PDF rotation (PDFRotator)
├── file_operations/
│   ├── __init__.py
│   ├── checker.py               # File readiness checking (FileReadyChecker)
│   ├── locking.py               # Advanced file locking (AdvancedFileLocking)
│   └── handler.py               # File system event handler (PDFFileHandler)
└── utils/
    ├── __init__.py
    ├── logging_setup.py         # Logging configuration (LoggingSetup)
    └── file_utils.py             # File naming utilities (clean_name, resolve_collision)
```

## Entry Points

### New Structure
- **`main.py`** - New main entry point that uses the refactored modules
- **`src/main.py`** - Internal main function

### Backward Compatibility
- **`file_utils.py`** - Exports all functions from the original `pdf_files_rename.py`

## Key Principles Applied

### Single Responsibility Principle (SRP)
- Each class has a single, well-defined responsibility
- `Config` only handles configuration
- `LoggingSetup` only handles logging setup
- `OrientationDetector` only handles PDF orientation detection
- etc.

### Open/Closed Principle (OCP)
- Classes are open for extension but closed for modification
- Network resilience patterns are implemented as decorators
- File operations can be extended without modifying core logic

### Liskov Substitution Principle (LSP)
- All network operations implement the same interface
- File operations are interchangeable

### Interface Segregation Principle (ISP)
- Interfaces are focused and specific
- Classes only depend on the methods they actually use

### Dependency Inversion Principle (DIP)
- High-level modules don't depend on low-level modules
- Dependencies are injected rather than hardcoded
- Abstract interfaces are used where appropriate

## Key Benefits

1. **Maintainability**: Code is organized into logical modules
2. **Testability**: Each class can be tested in isolation
3. **Reusability**: Components can be reused across different contexts
4. **Flexibility**: Easy to modify or extend individual components
5. **Debugging**: Easier to locate and fix issues in specific modules

## Migration Notes

### No Logic Changes
- All existing functionality has been preserved exactly as it was
- No business logic has been modified during the refactoring
- All network resilience, error handling, and processing logic remains identical

### Import Changes
- The original files still work but now import from the new structure
- New code should import from the appropriate `src/` modules
- `file_utils.py` provides backward compatibility for the naming functions

### Configuration
- All environment variables and configuration options remain the same
- The `Config` class in `src/config/settings.py` maintains the same interface

## Running the Application

### Using the new structure:
```bash
python main.py
```

### Using the original structure (still works):
```bash
python pdf_split_rotate.py
```

## Development

### Adding New Features
1. Identify the appropriate module based on responsibility
2. Create new classes following the same patterns
3. Inject dependencies through constructors
4. Use TYPE_CHECKING imports to avoid circular dependencies

### Testing
Each module can now be tested independently:
- Mock dependencies using the interfaces
- Test individual components in isolation
- Integration tests can focus on component interactions

## File Organization Rules

1. **No circular imports**: Use TYPE_CHECKING for type hints that would cause circles
2. **Clear interfaces**: Each module exports only what's needed
3. **Dependency injection**: Pass dependencies explicitly through constructors
4. **Single purpose**: Each file has one clear responsibility
