# Folder Cleanup Utilities

This folder contains robust PowerShell scripts for automated folder cleanup and for generating test environments to validate cleanup logic. These tools are designed for regular maintenance and safe testing of document or archive folders.

---

## FolderCleanupService.ps1

### Overview
A configurable PowerShell script for automated folder cleanup using Windows Task Scheduler. Supports both full and timestamp-based cleanup modes, with global and local safelists, comprehensive logging, and reliable automation.

### Features
- **Timestamp-based cleanup**: Remove only files/folders older than a threshold, based on timestamps extracted from filenames (e.g., `ekr.pim-20250718T074751.380.log`)
- **Full cleanup**: Remove all files/folders except those in safelists
- **Folder size protection**: Skip cleanup if folder is below configurable size threshold
- **Global and local safelists**: Protect important files/folders from deletion
- **Task Scheduler integration**: Reliable automation via Windows Task Scheduler (runs as SYSTEM)
- **Comprehensive logging**: Logs actions, warnings, and errors to file and Windows Event Log
- **Dry run and test modes**: Preview what would be deleted before running for real
- **Configurable patterns**: Support multiple timestamp formats in filenames

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
5. **Install as a Scheduled Task**
   - Run:
     ```powershell
     .\FolderCleanupService.ps1 -InstallTask
     ```
6. **Uninstall the Scheduled Task**
   - Run:
     ```powershell
     .\FolderCleanupService.ps1 -UninstallTask
     ```

### Management Commands
After installation, manage the task with:
```powershell
# Check task status
Get-ScheduledTask -TaskName "FolderCleanupTask"

# Run task immediately
Start-ScheduledTask -TaskName "FolderCleanupTask"

# View task execution history
Get-ScheduledTaskInfo -TaskName "FolderCleanupTask"

# Stop running task
Stop-ScheduledTask -TaskName "FolderCleanupTask"
```

### Parameters
- `-InstallTask` : Install as a Windows Scheduled Task
- `-UninstallTask` : Uninstall the Scheduled Task
- `-RunCleanup` : (internal) Run cleanup process (used by scheduled task)
- `-TestRun` : Run cleanup once (deletes files!)
- `-TestConfig` : Test configuration and timestamp patterns
- `-DryRun` : Preview what would be deleted

### Configuration Options
The script includes comprehensive configuration options:
- **Task Schedule**: Configurable interval (default: 20 minutes)
- **Timestamp Patterns**: Support for multiple date/time formats in filenames
- **Folder Size Threshold**: Skip cleanup if folder is below specified size (MB)
- **Age Thresholds**: Different age limits per folder
- **Safelists**: Global and per-folder protection lists

### Supported Timestamp Formats
The script can extract timestamps from filenames with patterns like:
- `ekr.pim-20250718T074751.380.log` (ISO format with T separator)
- `backup_20250723-143000_final.txt` (date-time with dash)
- `log_2025-07-23_system.log` (date only)
- Custom patterns can be added in the configuration

### Example Configuration
The script includes a working example for EKRO log cleanup:
```powershell
$FoldersToClean = @(
    @{
        Path = "C:\Users\RegestaAdm\Documents\pdf_split_rotate-main\scripts\folder_cleanup\test_folders\timestamp_cleanup_test"
        Mode = "TimestampBased"
        AgeThresholdDays = 1/72  # 20 minutes for testing
        LocalSafelist = @("ekr.pim.log", "monitors")
    }
)
```

This configuration:
- Runs every 20 minutes
- Deletes files older than 20 minutes (for testing)
- Protects `ekr.pim.log` and `monitors` files/folders
- Only processes folders larger than 1 MB

### Logging
- Log files: `C:\Windows\Logs\FolderCleanupTask` (configurable)
- Windows Event Log: Source = `FolderCleanupTask`
- Automatic log rotation when files exceed size limit
- Daily log files with timestamp format: `FolderCleanup_YYYYMMDD.log`

### Troubleshooting
- Run PowerShell as Administrator for task install/uninstall
- Check log files and Windows Event Log for detailed error information
- Use `-TestConfig` to validate timestamp patterns and folder paths
- Use `-DryRun` to preview cleanup actions before running
- Verify folder paths exist and are accessible
- Check that timestamp patterns match your filename formats
- Adjust folder size thresholds if cleanup is being skipped unexpectedly

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
- Giovanni Misso / RegestaItalia
- Last updated: July 2025
- Version: 1.0 (Task Scheduler implementation)
