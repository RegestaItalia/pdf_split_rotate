#!/usr/bin/env python3
"""
Script to rename folders named group_1, group_2, ... to group1, group2, ...
Works recursively on all subfolders of the target directory.
By default, it shows a preview of proposed changes. Use --apply to perform renaming.
"""
import os
import re
import argparse

def find_group_folders(root_folder):
    pattern = re.compile(r'^group_(\d+)$')
    changes = []
    # Walk bottom-up to avoid affecting os.walk iteration when renaming directories
    for dirpath, dirnames, _ in os.walk(root_folder, topdown=False):
        for dirname in dirnames:
            match = pattern.match(dirname)
            if match:
                num = match.group(1)
                old_path = os.path.join(dirpath, dirname)
                new_name = f'group{num}'
                new_path = os.path.join(dirpath, new_name)
                changes.append((old_path, new_path))
    return changes

def main():
    parser = argparse.ArgumentParser(
        description='Rename group_# folders to group# in a directory tree.'
    )
    parser.add_argument(
        'target',
        help='Path to the root folder to process'
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='If set, actually perform the renaming. Otherwise, only show a preview.'
    )
    args = parser.parse_args()

    changes = find_group_folders(args.target)
    if not changes:
        print('No folders matching pattern group_# were found.')
        return

    print('Preview of proposed changes:')
    for old, new in changes:
        print(f"{old} -> {new}")

    if not args.apply:
        print('\nNo changes applied. Re-run with --apply to perform renaming.')
        return

    print('\nApplying changes...')
    for old, new in changes:
        if os.path.exists(new):
            print(f"Skipping '{old}': target '{new}' already exists.")
        else:
            os.rename(old, new)
            print(f"Renamed '{old}' -> '{new}'")
    print('All done.')

if __name__ == '__main__':
    main()
