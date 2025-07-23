# select_copy.ps1

## Overview

A PowerShell script to copy a predefined set of folders from the current directory to a destination (e.g., `D:\staging`). Only folders that actually exist in the source are copied; missing folders are skipped with a notification. Useful for collecting specific client or supplier folders in one place for further processing or archiving.

---

## Features
- Copies only folders present in the source directory
- Skips and notifies about missing folders
- Opens the destination folder in Windows Explorer at the end
- Handles folder names with spaces and special characters

---

## Usage

1. **Edit the folder list**
   - Modify the `$folderNames` array at the top of the script to include the folders you want to copy.

2. **Set the destination**
   - Change `$destinationRoot` if you want a different destination (default: `D:\staging`).

3. **Run the script**
   - Open PowerShell in the source directory (where the folders are located).
   - Run:
     ```powershell
     .\select_copy.ps1
     ```

4. **Result**
   - All found folders are copied to the destination.
   - The destination folder opens in Explorer when done.

---

## Parameters
- `$folderNames`: Array of folder names to copy
- `$destinationRoot`: Destination directory

---

## Troubleshooting
- Run PowerShell as Administrator if you get permission errors.
- Check for typos or special characters in folder names.
- Ensure the destination drive/folder is accessible and has enough space.

---

## Author
- RegestaItalia
- Last updated: July 2025
