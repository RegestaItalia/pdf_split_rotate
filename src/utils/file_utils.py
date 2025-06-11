"""File utilities for name cleaning and collision resolution."""

import re
from pathlib import Path
from typing import Callable, List, Tuple


# ─── Rule Definitions ─────────────────────────────────────────────────────────
def remove_substring(name: str, parent: str, substring: str = 'Documenti ') -> str:
    """Remove a specific substring from the name."""
    return name.replace(substring, '') if substring in name else name


def replace_substring(name: str, parent: str, substring: str = ' - ') -> str:
    """Replace a specific substring with an underscore."""
    return name.replace(substring, '_') if substring in name else name


def strip_whitespace(name: str, parent: str) -> str:
    """Strip leading and trailing whitespace."""
    return name.strip()


def spaces_to_underscore(name: str, parent: str) -> str:
    """Replace spaces with underscores."""
    return name.replace(' ', '_')


def to_lowercase(name: str, parent: str) -> str:
    """Convert name to lowercase."""
    return name.lower()


def remove_non_alphanumeric(name: str, parent: str) -> str:
    """Replace non-alphanumeric characters (except underscore and dot) with underscores."""
    base, sep, ext = name.rpartition('.')
    if sep and ext:
        cleaned_base = re.sub(r'[^A-Za-z0-9_]', '_', base)
        cleaned_ext = re.sub(r'[^A-Za-z0-9_]', '_', ext)
        return f"{cleaned_base}.{cleaned_ext}"
    return re.sub(r'[^A-Za-z0-9_]', '_', name)


def remove_duplicate_underscores(name: str, parent: str) -> str:
    """Replace multiple consecutive underscores with a single underscore."""
    return re.sub(r'_{2,}', '_', name)


def strip_underscores(name: str, parent: str) -> str:
    """Strip leading and trailing underscores."""
    return name.strip('_')


def remove_dots_from_dir(name: str, parent: str) -> str:
    """Replace dots with underscores (for directories only)."""
    return name.replace('.', '_')


# Each rule is a tuple: (function, applies_to), where applies_to is 'file', 'dir', or 'both'
Rule = Tuple[Callable[[str, str], str], str]
rules: List[Rule] = [
    (remove_substring, 'file'),
    (replace_substring, 'file'),
    (strip_whitespace, 'both'),
    (spaces_to_underscore, 'both'),
    (to_lowercase, 'both'),
    (remove_non_alphanumeric, 'both'),
    (remove_duplicate_underscores, 'both'),
    (strip_underscores, 'both'),
    (remove_dots_from_dir, 'dir'),
]


def clean_name(name: str, parent: str, kind: str) -> str:
    """
    Clean a file or directory name by applying a strict rule: remove all non-alphanumeric characters (except for the extension dot in files).
    :param name: The original file or directory name.
    :param parent: The parent directory path as a string.
    :param kind: Either 'file' or 'dir'.
    :return: The cleaned name.
    """
    if kind == 'file' and '.' in name:
        base, dot, ext = name.rpartition('.')
        cleaned = ''.join(c for c in base if c.isalnum()) + dot + ''.join(c for c in ext if c.isalnum())
    else:
        cleaned = ''.join(c for c in name if c.isalnum())
    return cleaned.lower()


def resolve_collision(dest: Path) -> Path:
    """
    If the destination path exists, append _1, _2, ... before the extension until unique.
    :param dest: The intended Path.
    :return: A Path that does not exist yet.
    """
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    i = 1
    while True:
        new_name = f"{stem}_{i}{suffix}"
        candidate = parent / new_name
        if not candidate.exists():
            return candidate
        i += 1
