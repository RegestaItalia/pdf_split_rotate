#!/usr/bin/env python3
"""
File renaming utilities - replaces the original pdf_files_rename.py.

This module exports the same functions but uses the new modular structure.
"""

from src.utils.file_utils import (
    clean_name,
    resolve_collision,
    remove_substring,
    replace_substring,
    strip_whitespace,
    spaces_to_underscore,
    to_lowercase,
    remove_non_alphanumeric,
    remove_duplicate_underscores,
    strip_underscores,
    remove_dots_from_dir,
    rules
)

# Make all functions available at module level for backward compatibility
__all__ = [
    'clean_name',
    'resolve_collision',
    'remove_substring',
    'replace_substring',
    'strip_whitespace',
    'spaces_to_underscore',
    'to_lowercase',
    'remove_non_alphanumeric',
    'remove_duplicate_underscores',
    'strip_underscores',
    'remove_dots_from_dir',
    'rules'
]
