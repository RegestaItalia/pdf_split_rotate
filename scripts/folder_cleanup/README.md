# Folder Cleanup Utilities

This folder contains robust PowerShell scripts for automated folder cleanup and for generating test environments to validate cleanup logic. These tools are designed for regular maintenance and safe testing of document or archive folders.

---

## FolderCleanupService.ps1

### Overview
A configurable PowerShell script for automated folder cleanup. Supports both full and timestamp-based cleanup modes, with global and local safelists, logging, and Windows service integration.

### Features
- **Full cleanup**: Remove all files/folders except those in safelists.
- **Timestamp-based cleanup**: Remove only files/folders older than a threshold, based on timestamps in filenames.
- **Global and local safelists**: Protect important files/folders from deletion.
- **Configurable schedule**: Can run as a Windows service at regular intervals.
- **Comprehensive logging**: Logs actions, warnings, and errors to file and Windows Event Log.
- **Dry run and test modes**: Preview what would be deleted before running for real.

### Usage
1. **Configure the script**
   - Edit the CONFIGURATION SECTION at the top of the script to set folders, modes, safelists, and thresholds.
2. **Test configuration**
   - Run:
     ```powershell
     .\FolderCleanupService.ps1 -TestConfig
     ```
3. **Dry run (preview only)**
   - Run:
     ```powershell
     .\FolderCleanupService.ps1 -DryRun
     ```
4. **Test run (actually deletes!)**
   - Run:
     ```powershell
     .\FolderCleanupService.ps1 -TestRun
     ```
5. **Install as a Windows service**
   - Run:
     ```powershell
     .\FolderCleanupService.ps1 -Install
     Start-Service FolderCleanupService
     ```
6. **Uninstall the service**
   - Run:
     ```powershell
     .\FolderCleanupService.ps1 -Uninstall
     ```

### Parameters
- `-Install` : Install as a Windows service
- `-Uninstall` : Uninstall the service
- `-RunAsService` : (internal) Run in service mode
- `-TestRun` : Run cleanup once (deletes files!)
- `-TestConfig` : Test configuration and patterns
- `-DryRun` : Preview what would be deleted

### Logging
- Log files: `C:\Windows\Logs\FolderCleanupService` (configurable)
- Windows Event Log: Source = `FolderCleanupService`

### Troubleshooting
- Run PowerShell as Administrator for service install/uninstall.
- Check log files and Windows Event Log for errors.
- Adjust safelists and patterns as needed for your environment.

---

## GenerateTestFiles.ps1

### Overview
A PowerShell utility to generate test files and folders for validating the Folder Cleanup Service. It creates files with various timestamp patterns, safe files, and folders, and can also clean up the test environment.

### Features
- Generate old files (older than 30 days, should be deleted by timestamp cleanup)
- Generate recent files (newer than 30 days, should be kept)
- Generate files without timestamps (should be ignored by timestamp cleanup)
- Generate safe files and folders (should never be deleted)
- Clean all test folders for a fresh start
- Print a summary of the test environment

### Usage
1. **Generate all test files (recommended for first test):**
   ```powershell
   .\GenerateTestFiles.ps1
   ```
2. **Generate only old files:**
   ```powershell
   .\GenerateTestFiles.ps1 -GenerateOld -FileCount 5
   ```
3. **Generate only recent files:**
   ```powershell
   .\GenerateTestFiles.ps1 -GenerateRecent -FileCount 5
   ```
4. **Generate only safe files:**
   ```powershell
   .\GenerateTestFiles.ps1 -GenerateSafe
   ```
5. **Clean all test folders:**
   ```powershell
   .\GenerateTestFiles.ps1 -CleanTestFolders
   ```

### Parameters
- `-GenerateAll` : Generate all types of test files (default)
- `-GenerateOld` : Generate only old files
- `-GenerateRecent` : Generate only recent files
- `-GenerateSafe` : Generate only safe files
- `-CleanTestFolders` : Remove all files/folders in test directories
- `-FileCount` : Number of files to generate for each type (default: 10)

### Output
- Test files and folders are created in:
  - `test_folders/full_cleanup_test`
  - `test_folders/timestamp_cleanup_test`
- A summary of the test environment is printed at the end.

### Troubleshooting
- Run PowerShell as Administrator if you encounter permission errors.
- Check the script output for warnings about file creation or cleanup.
- Adjust test folder paths in the script if needed for your environment.

---

## Author
- RegestaItalia
- Last updated: July 2025
