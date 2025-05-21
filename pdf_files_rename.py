#!/usr/bin/env python3
"""
Robust script to recursively clean file and folder names.

CONFIGURATION:
  ROOT_DIR – Path to the target folder
  APPLY    – If False, only preview changes; if True, preview then confirm before renaming
"""
import os
import re
from pathlib import Path

# ─── CONFIGURATION ─────────────────────────────────────────────────────────────
ROOT_DIR = Path("D:/03_checked")  # ← change this to your target folder
APPLY    = True                    # ← set to True to enable renaming after preview
# ───────────────────────────────────────────────────────────────────────────────

# ─── Rule definitions ──────────────────────────────────────────────────────────
def remove_substring(name: str, parent: str, substring='Documenti ') -> str:
    return name.replace(substring, '') if substring in name else name

def replace_substring(name: str, parent: str, substring=' - ') -> str:
    return name.replace(substring, '_') if substring in name else name

def strip_whitespace(name: str, parent: str) -> str:
    return name.strip()

def spaces_to_underscore(name: str, parent: str) -> str:
    return name.replace(' ', '_')

def to_lowercase(name: str, parent: str) -> str:
    return name.lower()

# Uncomment if you want parent prefixing for directories
# def prefix_parent_folder(name: str, parent: str) -> str:
#     parent_name = Path(parent).name
#     return f"{parent_name}_{name}" if parent_name else name

def remove_non_alphanumeric(name: str, parent: str) -> str:
    base, sep, ext = name.rpartition('.')
    if sep and ext:
        cleaned_base = re.sub(r'[^A-Za-z0-9_]', '_', base)
        cleaned_ext  = re.sub(r'[^A-Za-z0-9_]', '_', ext)
        return f"{cleaned_base}.{cleaned_ext}"
    return re.sub(r'[^A-Za-z0-9_]', '_', name)

def remove_duplicate_underscores(name: str, parent: str) -> str:
    return re.sub(r'_{2,}', '_', name)

def strip_underscores(name: str, parent: str) -> str:
    return name.strip('_')

def remove_dots_from_dir(name: str, parent: str) -> str:
    return name.replace('.', '_')

# List of (function, apply_to) tuples: "both", "file", or "dir"
rules = [
    (remove_substring,       "file"),
    (replace_substring,      "file"),
    (strip_whitespace,       "both"),
    (spaces_to_underscore,   "both"),
    (to_lowercase,           "both"),
    # (prefix_parent_folder,   "dir"),
    (remove_non_alphanumeric,"both"),
    (remove_duplicate_underscores, "both"),
    (strip_underscores,      "both"),
    (remove_dots_from_dir,   "dir"),  # <-- add this rule for directories only
]

def clean_name(name: str, parent: str, kind: str) -> str:
    for func, apply_to in rules:
        if apply_to == 'both' or apply_to == kind:
            name = func(name, parent)
    return name

# ─── Collision resolution ───────────────────────────────────────────────────────
def resolve_collision(dest: Path) -> Path:
    """
    If `dest` already exists, append _1, _2, ... before the extension until unique.
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

# ─── Preview & Apply ───────────────────────────────────────────────────────────
def collect_and_rename(root: Path, dry_run: bool = True):
    """
    Traverse bottom-up: rename files first, then directories.
    If `dry_run` is True, only print proposed changes.
    """
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        base = Path(dirpath)
        # Rename files
        for fname in filenames:
            src = base / fname
            new_name = clean_name(fname, str(base), 'file')
            if new_name != fname:
                dest = resolve_collision(base / new_name)
                if dry_run:
                    print(f"[DRY RUN] File:\n{src}\n{dest}")
                else:
                    src.rename(dest)
                    print(f"Renamed file:\n{src}\n{dest}")
        # Rename directories
        for dname in dirnames:
            src = base / dname
            new_name = clean_name(dname, str(base), 'dir')
            if new_name != dname:
                dest = resolve_collision(base / new_name)
                if dry_run:
                    print(f"[DRY RUN] Dir:\n{src}\n{dest}")
                else:
                    src.rename(dest)
                    print(f"Renamed dir:\n{src}\n{dest}")