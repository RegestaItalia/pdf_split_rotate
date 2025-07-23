# count_them_all.ps1

## Overview

This PowerShell script automates the process of listing and counting files in a set of folders, typically used for batch PDF or document processing projects. It is designed to:
- Extract the names of all first-level folders in a specified directory and save them to a text file.
- For each folder listed in an input file, check for the existence of the folder, find the first subfolder, count the number of files in that subfolder, and write the results to an output file.
- Handle missing folders and missing subfolders with clear error messages in the output.

---

## Usage

1. **Set the main folder path**
   - Edit the `$folderPath` variable to point to the directory you want to analyze (e.g., `W:\03_processati`).

2. **Extract first-level folder names**
   - The script will list all first-level folders and save their names to a file (e.g., `folders.txt`).

3. **Prepare the input file**
   - Edit or generate `folders_to_count.txt` with the list of folder names you want to process.

4. **Run the script**
   - Execute the script in PowerShell:
     ```powershell
     .\count_them_all.ps1
     ```

5. **Check the output**
   - Results are written to `folders_with_count.txt`, showing the number of files in the first subfolder of each listed folder, or an error message if not found.

---

## Parameters & Files

- `$folderPath`: Path to the main directory to scan.
- `folders_to_count.txt`: Input file with folder names (one per line).
- `folders_with_count.txt`: Output file with results.
- The script also generates `folders.txt` with all first-level folder names.

---

## Output Example

```
CustomerA 123
CustomerB 98
CustomerC - No subfolder found
CustomerD - Directory not found
```

---

## Troubleshooting

- Ensure all paths are correct and accessible from your user account.
- If you get permission errors, run PowerShell as Administrator.
- If a folder is missing or has no subfolders, the script will note this in the output.

---

## Script Logic (Summary)

1. List all first-level folders in `$folderPath` and save to `folders.txt`.
2. For each folder in `folders_to_count.txt`:
   - Check if the folder exists in `$folderPath`.
   - If it exists, find the first subfolder and count its files.
   - Write the folder name and file count (or error) to `folders_with_count.txt`.

---

## Author
- RegestaItalia
- Last updated: July 2025
