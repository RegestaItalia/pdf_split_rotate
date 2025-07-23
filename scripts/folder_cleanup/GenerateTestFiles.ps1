#Requires -RunAsAdministrator

<#
.SYNOPSIS
    Test File Generator for Folder Cleanup Service
.DESCRIPTION
    Generates test files with various timestamp patterns and safe files for testing the cleanup service
.NOTES
    Use this to create test scenarios before running the actual cleanup service
#>

param(
    [switch]$GenerateAll,
    [switch]$GenerateOld,
    [switch]$GenerateRecent,
    [switch]$GenerateSafe,
    [switch]$CleanTestFolders,
    [int]$FileCount = 10
)

# Test folder paths
$TestFolders = @{
    FullCleanup = "c:\Users\giovanni.misso\Documents\pdf_split_rotate\scripts\folder_cleanup\test_folders\full_cleanup_test"
    TimestampCleanup = "c:\Users\giovanni.misso\Documents\pdf_split_rotate\scripts\folder_cleanup\test_folders\timestamp_cleanup_test"
}

# Sample file extensions
$FileExtensions = @(".txt", ".pdf", ".log", ".tmp", ".bak", ".csv", ".xml")

# Timestamp patterns (same as in main script)
$TimestampFormats = @(
    @{Pattern="_yyyyMMdd_"; Example="_20250723_"},
    @{Pattern="_yyyyMMdd-HHmmss_"; Example="_20250723-143000_"},
    @{Pattern="_yyyy-MM-dd_"; Example="_2025-07-23_"},
    @{Pattern="_yyyyMMddHHmmss_"; Example="_20250723143000_"},
    @{Pattern="_yyyyMMdd_HHmmss_"; Example="_20250723_143000_"}
)

# Safe file names (should never be deleted)
$SafeFiles = @(
    "README.md",
    "important_config.txt",
    "backup_settings.ini",
    "desktop.ini",
    "thumbs.db"
)

function Write-TestLog {
    param([string]$Message, [string]$Color = "White")
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Message" -ForegroundColor $Color
}

function New-TestFile {
    param(
        [string]$FilePath,
        [string]$Content = "This is a test file created for cleanup service testing."
    )
    
    try {
        # Ensure directory exists
        $directory = Split-Path $FilePath -Parent
        if (-not (Test-Path $directory)) {
            New-Item -Path $directory -ItemType Directory -Force | Out-Null
        }
        
        # Create file with content
        Set-Content -Path $FilePath -Value $Content -Encoding UTF8
        Write-TestLog "Created: $(Split-Path $FilePath -Leaf)" "Green"
    }
    catch {
        Write-TestLog "Failed to create $FilePath : $_" "Red"
    }
}

function Generate-OldFiles {
    param([string]$TargetFolder, [int]$Count)
    
    Write-TestLog "Generating $Count old files in $TargetFolder..." "Yellow"
    
    for ($i = 1; $i -le $Count; $i++) {
        # Generate dates between 31-90 days ago
        $daysAgo = Get-Random -Minimum 31 -Maximum 91
        $oldDate = (Get-Date).AddDays(-$daysAgo)
        
        # Pick random timestamp format
        $format = $TimestampFormats | Get-Random
        $extension = $FileExtensions | Get-Random
        
        # Generate timestamp string based on format
        $timestampString = switch ($format.Pattern) {
            "_yyyyMMdd_" { $oldDate.ToString("yyyyMMdd") }
            "_yyyyMMdd-HHmmss_" { $oldDate.ToString("yyyyMMdd-HHmmss") }
            "_yyyy-MM-dd_" { $oldDate.ToString("yyyy-MM-dd") }
            "_yyyyMMddHHmmss_" { $oldDate.ToString("yyyyMMddHHmmss") }
            "_yyyyMMdd_HHmmss_" { $oldDate.ToString("yyyyMMdd_HHmmss") }
        }
        
        $fileName = "old_file_${i}_${timestampString}_data${extension}"
        $filePath = Join-Path $TargetFolder $fileName
        
        $content = @"
Test file #$i
Created: $(Get-Date)
Simulated date: $oldDate
Days ago: $daysAgo
Format used: $($format.Pattern)
This file should be DELETED by timestamp-based cleanup (older than 30 days)
"@
        
        New-TestFile -FilePath $filePath -Content $content
        
        # Set file creation and modification time to the old date
        try {
            $file = Get-Item $filePath
            $file.CreationTime = $oldDate
            $file.LastWriteTime = $oldDate
        }
        catch {
            Write-TestLog "Warning: Could not set file dates for $fileName" "Yellow"
        }
    }
}

function Generate-RecentFiles {
    param([string]$TargetFolder, [int]$Count)
    
    Write-TestLog "Generating $Count recent files in $TargetFolder..." "Yellow"
    
    for ($i = 1; $i -le $Count; $i++) {
        # Generate dates between 1-29 days ago (should be kept)
        $daysAgo = Get-Random -Minimum 1 -Maximum 30
        $recentDate = (Get-Date).AddDays(-$daysAgo)
        
        # Pick random timestamp format
        $format = $TimestampFormats | Get-Random
        $extension = $FileExtensions | Get-Random
        
        # Generate timestamp string based on format
        $timestampString = switch ($format.Pattern) {
            "_yyyyMMdd_" { $recentDate.ToString("yyyyMMdd") }
            "_yyyyMMdd-HHmmss_" { $recentDate.ToString("yyyyMMdd-HHmmss") }
            "_yyyy-MM-dd_" { $recentDate.ToString("yyyy-MM-dd") }
            "_yyyyMMddHHmmss_" { $recentDate.ToString("yyyyMMddHHmmss") }
            "_yyyyMMdd_HHmmss_" { $recentDate.ToString("yyyyMMdd_HHmmss") }
        }
        
        $fileName = "recent_file_${i}_${timestampString}_data${extension}"
        $filePath = Join-Path $TargetFolder $fileName
        
        $content = @"
Test file #$i
Created: $(Get-Date)
Simulated date: $recentDate
Days ago: $daysAgo
Format used: $($format.Pattern)
This file should be KEPT by timestamp-based cleanup (newer than 30 days)
"@
        
        New-TestFile -FilePath $filePath -Content $content
        
        # Set file creation and modification time to the recent date
        try {
            $file = Get-Item $filePath
            $file.CreationTime = $recentDate
            $file.LastWriteTime = $recentDate
        }
        catch {
            Write-TestLog "Warning: Could not set file dates for $fileName" "Yellow"
        }
    }
}

function Generate-SafeFiles {
    param([string]$TargetFolder)
    
    Write-TestLog "Generating safe files in $TargetFolder..." "Yellow"
    
    foreach ($safeFile in $SafeFiles) {
        $filePath = Join-Path $TargetFolder $safeFile
        $content = @"
SAFE FILE - SHOULD NEVER BE DELETED
File: $safeFile
Created: $(Get-Date)
This file is protected by the global safelist and should never be deleted by the cleanup service.
"@
        New-TestFile -FilePath $filePath -Content $content
    }
    
    # Create a safe subfolder
    $safeFolder = Join-Path $TargetFolder "important_data"
    New-Item -Path $safeFolder -ItemType Directory -Force | Out-Null
    
    $safeSubFile = Join-Path $safeFolder "critical_file.txt"
    $content = @"
SAFE SUBFOLDER FILE
This file is in a folder that might be protected.
Created: $(Get-Date)
"@
    New-TestFile -FilePath $safeSubFile -Content $content
}

function Generate-FilesWithoutTimestamp {
    param([string]$TargetFolder, [int]$Count)
    
    Write-TestLog "Generating $Count files without timestamps in $TargetFolder..." "Yellow"
    
    for ($i = 1; $i -le $Count; $i++) {
        $extension = $FileExtensions | Get-Random
        $fileName = "no_timestamp_file_${i}${extension}"
        $filePath = Join-Path $TargetFolder $fileName
        
        $content = @"
Test file without timestamp #$i
Created: $(Get-Date)
This file has NO timestamp in the filename.
For timestamp-based cleanup, this file should be IGNORED (not deleted).
"@
        
        New-TestFile -FilePath $filePath -Content $content
    }
}

function Clean-TestFolders {
    Write-TestLog "Cleaning all test folders..." "Red"
    
    foreach ($folder in $TestFolders.Values) {
        if (Test-Path $folder) {
            try {
                Get-ChildItem -Path $folder -Force | Remove-Item -Recurse -Force
                Write-TestLog "Cleaned: $folder" "Green"
            }
            catch {
                Write-TestLog "Failed to clean $folder : $_" "Red"
            }
        }
    }
}

function Show-TestSummary {
    Write-TestLog "`n=== TEST FOLDER SUMMARY ===" "Cyan"
    
    foreach ($folderType in $TestFolders.Keys) {
        $folder = $TestFolders[$folderType]
        Write-TestLog "`n$folderType`: $folder" "White"
        
        if (Test-Path $folder) {
            $files = Get-ChildItem -Path $folder -Force
            Write-TestLog "  Total items: $($files.Count)" "Gray"
            
            # Categorize files
            $oldFiles = @()
            $recentFiles = @()
            $noTimestampFiles = @()
            $safeFiles = @()
            
            foreach ($file in $files) {
                if ($SafeFiles -contains $file.Name -or $file.Name -like "*important*" -or $file.Name -like "*backup*") {
                    $safeFiles += $file
                }
                elseif ($file.Name -match "_(\d{8})_|_(\d{8}-\d{6})_|_(\d{4}-\d{2}-\d{2})_|_(\d{14})_|_(\d{4}\d{2}\d{2}_\d{6})_") {
                    if ((Get-Date) - $file.LastWriteTime -gt [TimeSpan]::FromDays(30)) {
                        $oldFiles += $file
                    } else {
                        $recentFiles += $file
                    }
                }
                else {
                    $noTimestampFiles += $file
                }
            }
            
            Write-TestLog "    [OLD] Files older than 30 days: $($oldFiles.Count)" "Red"
            Write-TestLog "    [NEW] Recent files (under 30 days): $($recentFiles.Count)" "Green"
            Write-TestLog "    [???] No timestamp files: $($noTimestampFiles.Count)" "Yellow"
            Write-TestLog "    [SAFE] Protected files: $($safeFiles.Count)" "Blue"
        }
        else {
            Write-TestLog "  Folder does not exist" "Red"
        }
    }
}

# Main execution
if ($CleanTestFolders) {
    Clean-TestFolders
    exit
}

if ($GenerateAll -or (-not $GenerateOld -and -not $GenerateRecent -and -not $GenerateSafe)) {
    Write-TestLog "=== GENERATING ALL TEST FILES ===" "Cyan"
    
    # Generate files for timestamp-based cleanup testing
    Generate-OldFiles -TargetFolder $TestFolders.TimestampCleanup -Count $FileCount
    Generate-RecentFiles -TargetFolder $TestFolders.TimestampCleanup -Count $FileCount
    Generate-FilesWithoutTimestamp -TargetFolder $TestFolders.TimestampCleanup -Count 3
    Generate-SafeFiles -TargetFolder $TestFolders.TimestampCleanup
    
    # Generate files for full cleanup testing
    Generate-OldFiles -TargetFolder $TestFolders.FullCleanup -Count ($FileCount / 2)
    Generate-RecentFiles -TargetFolder $TestFolders.FullCleanup -Count ($FileCount / 2)
    Generate-FilesWithoutTimestamp -TargetFolder $TestFolders.FullCleanup -Count 2
    Generate-SafeFiles -TargetFolder $TestFolders.FullCleanup
}
else {
    if ($GenerateOld) {
        Generate-OldFiles -TargetFolder $TestFolders.TimestampCleanup -Count $FileCount
        Generate-OldFiles -TargetFolder $TestFolders.FullCleanup -Count $FileCount
    }
    
    if ($GenerateRecent) {
        Generate-RecentFiles -TargetFolder $TestFolders.TimestampCleanup -Count $FileCount
        Generate-RecentFiles -TargetFolder $TestFolders.FullCleanup -Count $FileCount
    }
    
    if ($GenerateSafe) {
        Generate-SafeFiles -TargetFolder $TestFolders.TimestampCleanup
        Generate-SafeFiles -TargetFolder $TestFolders.FullCleanup
    }
}

Show-TestSummary

Write-TestLog "`n=== NEXT STEPS ===" "Cyan"
Write-TestLog "1. Update FolderCleanupService.ps1 configuration to use these test folders" "White"
Write-TestLog "2. Run: .\FolderCleanupService.ps1 -TestConfig" "White"
Write-TestLog "3. Run: .\FolderCleanupService.ps1 -TestRun" "White"
Write-TestLog "4. Check the results and logs" "White"
Write-TestLog "`nTest folder paths:" "Yellow"
Write-TestLog "  Full cleanup: $($TestFolders.FullCleanup)" "Gray"
Write-TestLog "  Timestamp cleanup: $($TestFolders.TimestampCleanup)" "Gray"
