#!/usr/bin/env python3
"""
Main entry point for the PDF Split and Rotate Service.
"""

from src.core.service import PDFWatcherService


def main():
    """Main entry point."""
    service = PDFWatcherService()
    service.start()


if __name__ == "__main__":
    main()
