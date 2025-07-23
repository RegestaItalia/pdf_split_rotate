# Folder Cleanup Service - Testing Guide

This guide explains how to test the Folder Cleanup Service using the provided test files and utilities.

## Files Overview

- **`FolderCleanupService.ps1`** - Main cleanup service script
- **`GenerateTestFiles.ps1`** - Utility to generate test files for testing
- **`test_folders/`** - Contains test directories with sample files

## Test Folder Structure

```
test_folders/
├── full_cleanup_test/          # For testing full cleanup mode
│   ├── README.md              # Safe file (should not be deleted)
│   └── sample_file.txt        # Regular file (should be deleted)
└── timestamp_cleanup_test/     # For testing timestamp-based cleanup
    ├── old_document_20240601_report.pdf    # Old file (should be deleted)
    └── recent_backup_20250720_data.txt     # Recent file (should be kept)
```

## How to Test

### Step 1: Generate Test Files

Run the test file generator to create a comprehensive set of test files:

```powershell
# Generate all types of test files (recommended for first test)
.\GenerateTestFiles.ps1

# Or generate specific types:
.\GenerateTestFiles.ps1 -GenerateOld -FileCount 5       # Create 5 old files
.\GenerateTestFiles.ps1 -GenerateRecent -FileCount 5    # Create 5 recent files
.\GenerateTestFiles.ps1 -GenerateSafe                   # Create safe files
```

**What this creates:**
- **Old files** (31-90 days old) - Should be DELETED by timestamp cleanup
- **Recent files** (1-29 days old) - Should be KEPT by timestamp cleanup  
- **Files without timestamps** - Should be IGNORED by timestamp cleanup
- **Safe files** - Should NEVER be deleted by any cleanup mode


### Step 2: Test Configuration

Verify that the cleanup service can find your test folders and parse timestamps:

```powershell
.\FolderCleanupService.ps1 -TestConfig
```

This will:
- Test timestamp pattern recognition
- Check if configured folders exist
- Show you which files would be affected
- Warn about any configuration or mode errors

### Step 3: Run a Dry Run (Recommended)

Before actually deleting files, run a dry run to see exactly what would be deleted, kept, ignored, or protected. The dry run now provides a detailed summary at the end:

```powershell
.\FolderCleanupService.ps1 -DryRun
```

**Dry Run Output:**
- [DELETE] ... : Would be deleted
- [KEEP] ... : Would be kept (recent or protected)
- [IGNORE] ... : No timestamp, ignored (timestamp-based mode)
- [ERROR] ... : Any errors or unknown modes
- At the end, a summary of all actions is shown (to delete, to keep, ignored, protected, errors)

### Step 4: Run Test Cleanup

⚠️ **WARNING: This will actually delete files!**

```powershell
.\FolderCleanupService.ps1 -TestRun
```

This performs a real cleanup run on your test folders. The script is now more robust and will continue processing even if some files/folders cause errors. All actions and errors are logged.

### Step 5: Check Results

After running the test:

1. **Check the folders** to see which files were deleted/kept
2. **Check the logs** in `C:\Windows\Logs\FolderCleanupService\`
3. **Run the summary again**: `.\GenerateTestFiles.ps1` (shows current state)


## Expected Results

### Timestamp-Based Cleanup (`timestamp_cleanup_test/`)
- ✓ **Old files** (>30 days) → DELETED
- ✓ **Recent files** (<30 days) → KEPT
- ✓ **Files without timestamps** → IGNORED (kept)
- ✓ **Safe files** (README.md, important*, backup*, etc.) → KEPT
- ✓ **Errors**: Will be logged and shown in summary, but script continues

### Full Cleanup (`full_cleanup_test/`)
- ✓ **All regular files** → DELETED
- ✓ **Safe files** (README.md, important*, backup*, etc.) → KEPT
- ✓ **Errors**: Will be logged and shown in summary, but script continues


## Cleanup Test Environment

To reset the test environment:

```powershell
# Clean all test folders
.\GenerateTestFiles.ps1 -CleanTestFolders

# Then regenerate files for next test
.\GenerateTestFiles.ps1
```

## Customizing Tests

### Add More Test Folders

Edit `FolderCleanupService.ps1` and modify the `$FoldersToClean` array:

```powershell
$FoldersToClean = @(
    @{
        Path = "C:\Your\Test\Folder"
        Mode = "TimestampBased"  # or "Full"
        AgeThresholdDays = 7     # Custom age threshold
        LocalSafelist = @("keep_this.txt")
    }
)
```

### Test Different Timestamp Patterns

The generator creates files with these timestamp patterns:
- `file_20250723_data.txt` (yyyyMMdd)
- `file_20250723-143000_data.txt` (yyyyMMdd-HHmmss)
- `file_2025-07-23_data.txt` (yyyy-MM-dd)
- `file_20250723143000_data.txt` (yyyyMMddHHmmss)
- `file_20250723_143000_data.txt` (yyyyMMdd_HHmmss)

### Add Custom Safe Files

Edit the `$GlobalSafelist` in `FolderCleanupService.ps1`:

```powershell
$GlobalSafelist = @(
    "desktop.ini",
    "thumbs.db",
    "your_custom_safe_file.txt"
)
```

## Production Deployment

Once testing is complete:

1. Update `$FoldersToClean` with your real folder paths
2. Install as service: `.\FolderCleanupService.ps1 -Install`
3. Start service: `Start-Service FolderCleanupService`


## Troubleshooting

### Permission Issues
- Run PowerShell as Administrator
- Check folder permissions

### Files Not Being Deleted or Unexpected Errors
- Verify timestamp patterns match your files
- Check if files are in the safelist
- Review logs for error messages
- Check the summary and error counts in dry run or test run output

### Service Installation Issues
- Ensure PowerShell execution policy allows scripts
- Run as Administrator
- Check Windows Event Log for service errors
