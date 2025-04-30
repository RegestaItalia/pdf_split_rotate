#!/usr/bin/env python3
"""
Simple script to recursively clean file and folder names.

CONFIGURE:
  ROOT_DIR    – the path you want to process
  SAMPLE_SIZE – how many random items to preview
  APPLY       – set to True to actually rename after preview

Run with:
    python clean_names.py
"""
import os
import random
from pathlib import Path

# ─── CONFIGURATION ─────────────────────────────────────────────────────────────
ROOT_DIR    = Path("/path/to/your/root")  # ← change this to your target folder
SAMPLE_SIZE = 10                          # ← number of random items to preview
APPLY       = False                       # ← set to True to perform renames
# ───────────────────────────────────────────────────────────────────────────────

# ─── Rule definitions ──────────────────────────────────────────────────────────
def remove_substring(name: str, parent: str, substring='Documenti ') -> str:
    if substring in name:
        return name.replace(substring, '')
    return name

def replace_substring(name: str, parent: str, substring=' - ') -> str:
    if substring in name:
        return name.replace(substring, '')
    return name

def strip_whitespace(name: str, parent: str) -> str:
    """Remove leading/trailing whitespace."""
    return name.strip()

def spaces_to_underscore(name: str, parent: str) -> str:
    """Convert spaces to underscores."""
    return name.replace(' ', '_')

def to_lowercase(name: str, parent: str) -> str:
    """Lowercase everything."""
    return name.lower()

def prefix_parent_folder(name: str, parent: str) -> str:
    """Prepend the immediate parent folder name (if any)."""
    parent_name = Path(parent).name
    return f"{parent_name}_{name}" if parent_name else name

# rules: list of (function, apply_to) tuples.
# apply_to: "both", "file", or "dir"
rules = [
    (remove_substring,     "file"),
    (strip_whitespace,     "both"),
    (spaces_to_underscore, "both"),
    (to_lowercase,         "both"),
    (prefix_parent_folder, "dir"),    # only apply folder-prefix to directories
]

def clean_name(name: str, parent: str, kind: str) -> str:
    """
    Apply all rules in order to `name`, but only those where
    apply_to is "both" or matches `kind` ("file" or "dir").
    """
    for func, apply_to in rules:
        if apply_to == "both" or apply_to == kind:
            name = func(name, parent)
    return name

# ─── File‐tree traversal ────────────────────────────────────────────────────────
def collect_items(root: Path):
    """
    Walk the directory tree under `root` and collect
    tuples of (Path, 'file' or 'dir').
    """
    items = []
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        for d in dirnames:
            items.append((base / d, 'dir'))
        for f in filenames:
            items.append((base / f, 'file'))
    return items

# ─── Preview & Apply ───────────────────────────────────────────────────────────
def preview_changes(items, sample_size=10):
    """Print a random sample of proposed renames."""
    sample = random.sample(items, min(sample_size, len(items)))
    print(f"\nPreviewing {len(sample)} random changes:")
    for path, kind in sample:
        new_name = clean_name(path.name, str(path.parent), kind)
        print(f"  [{kind}] {path} → {path.parent / new_name}")
    print()

def apply_changes(items):
    """
    Rename directories (deepest first) then files.
    """
    dirs = [(p, k) for p, k in items if k == 'dir']
    dirs.sort(key=lambda x: len(str(x[0]).split(os.sep)), reverse=True)
    files = [(p, k) for p, k in items if k == 'file']

    for path, kind in dirs + files:
        new_name = clean_name(path.name, str(path.parent), kind)
        new_path = path.parent / new_name
        if path != new_path:
            try:
                path.rename(new_path)
                print(f"Renamed: {path} → {new_path}")
            except Exception as e:
                print(f"Error renaming {path}: {e}")

# ─── Main execution ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if not ROOT_DIR.is_dir():
        print(f"ERROR: {ROOT_DIR} is not a directory")
        exit(1)

    items = collect_items(ROOT_DIR)
    preview_changes(items, SAMPLE_SIZE)

    if APPLY:
        confirm = input("Proceed to rename all items? [y/N]: ").strip().lower()
        if confirm == 'y':
            apply_changes(items)
            print("\nDone.")
        else:
            print("Aborted—no changes made.")
    else:
        print("APPLY is False, so no changes were made. Set APPLY = True to rename.")
