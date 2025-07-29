#Requires -RunAsAdministrator

<#
.SYNOPSIS
    Folder Cleanup Task - Configurable folder cleaning with timestamp-based and full cleanup modes
.DESCRIPTION
    This script can be deployed as a Windows Scheduled Task to automatically clean folders based on configuration.
    Supports two modes: full cleanup and timestamp-based cleanup with safelist protection.
    
    Features:
    - Timestamp-based cleanup with configurable patterns (e.g., ekr.pim-20250718T074751.380.log)
    - Time offset compensation for timezone differences in log timestamps
    - Folder size threshold protection
    - Emergency cleanup mode when disk space is low (bypasses folder size thresholds)
    - Global and local safelists
    - Reliable Task Scheduler automation (runs as SYSTEM)
    - Comprehensive logging to files and Windows Event Log
    - Dry run and test modes for safe validation
    
.PARAMETER InstallTask
    Install the script as a Windows Scheduled Task
.PARAMETER UninstallTask
    Uninstall the Windows Scheduled Task
.PARAMETER RunCleanup
    Run the cleanup process once (used internally by scheduled task)
.PARAMETER TestRun
    Run cleanup once for testing (WARNING: Will delete files!)
.PARAMETER TestConfig
    Test configuration and timestamp patterns without making changes
.PARAMETER DryRun
    Preview what would be deleted without actually deleting anything
    
.EXAMPLE
    .\FolderCleanupService.ps1 -InstallTask
    Installs the cleanup task to run every 20 minutes
    
.EXAMPLE
    .\FolderCleanupService.ps1 -TestConfig
    Tests the configuration and shows which timestamp patterns work
    
.EXAMPLE
    .\FolderCleanupService.ps1 -DryRun
    Shows what files would be deleted without actually deleting them
    
.NOTES
    Author: Giovanni Misso
    Date: 2025-07-28
    Version: 1.1
    Requires: PowerShell 5.1+, Administrator privileges for task installation
#>

param(
    [switch]$InstallTask,
    [switch]$UninstallTask,
    [switch]$RunCleanup,
    [switch]$TestRun,
    [switch]$TestConfig,
    [switch]$DryRun
)

# ==================== CONFIGURATION SECTION ====================
# Modify these variables to configure the task behavior

# Task Configuration
$TaskName = "FolderCleanupTask"
$TaskDisplayName = "Folder Cleanup Task"
$TaskDescription = "Automated folder cleanup with configurable rules and safelist protection"

# Cleanup Schedule (in minutes) - Default: 1440 minutes = 24 hours (daily)
$CleanupIntervalMinutes = 20

# Log Configuration
$LogPath = "C:\Windows\Logs\FolderCleanupTask"
$MaxLogSizeMB = 500
$MaxLogFiles = 100

# Timestamp Configuration
# Define multiple timestamp patterns that might appear in filenames
# Format: @{Pattern="regex_pattern"; Format="datetime_format"}
$TimestampPatterns = @(
    @{Pattern="-(\d{8}T\d{6})"; Format="yyyyMMddTHHmmss"}  # ekr.pim-20250718T074751.380.log
    # @{Pattern="_(\d{8}-\d{6})_"; Format="yyyyMMdd-HHmmss"}, # _20250723-143000_
    # @{Pattern="_(\d{4}-\d{2}-\d{2})_"; Format="yyyy-MM-dd"}, # _2025-07-23_
    # @{Pattern="_(\d{14})_"; Format="yyyyMMddHHmmss"},    # _20250723143000_
    # @{Pattern="_(\d{4}\d{2}\d{2}_\d{6})_"; Format="yyyyMMdd_HHmmss"} # _20250723_143000_
)

# Default age threshold for timestamp-based cleanup (in days)
$DefaultAgeThresholdDays = 30

# Minimum folder size threshold (in MB) - Skip cleanup if folder is smaller than this
# Set to 0 to disable size checking
$MinimumFolderSizeMB = 10*1024

# Low disk space emergency cleanup threshold (in MB) - Force cleanup if drive free space is below this
# When triggered, bypasses MinimumFolderSizeMB check to free up space
$LowDiskSpaceThresholdMB = 10240  # 10 GB

# Time offset compensation (in hours) - Adjust for timezone differences in log file timestamps
# If log files are timestamped 2 hours behind system time, set this to 2
$TimestampOffsetHours = 2

# Folder Configuration
# Each folder can have: Path, Mode, AgeThresholdDays, LocalSafelist
$FoldersToClean = @(
    @{
        Path = "C:\EKRO\ekro-libra\log"
        Mode = "TimestampBased"  # Options: "Full" or "TimestampBased"
        AgeThresholdDays = 1/72 # 1/72 is 20 min
        LocalSafelist = @("ekr.pim.log", "monitors")
    }
    # @{
    #     Path = "C:\Users\RegestaAdm\Documents\pdf_split_rotate-main\scripts\folder_cleanup\test_folders\full_cleanup_test" 
    #     Mode = "Full"
    #     AgeThresholdDays = 0  # Not used for Full mode
    #     LocalSafelist = @("config.ini")
    # }
    # Add more folders as needed
    # @{
    #     Path = "C:\Another\Folder"
    #     Mode = "TimestampBased"
    #     AgeThresholdDays = 7
    #     LocalSafelist = @()
    # }
)

# Global Safelist - These files/folders will NEVER be deleted from ANY folder
$GlobalSafelist = @(
    "ekr.pim.log",
    "monitors"
)

# ==================== END CONFIGURATION SECTION ====================

# Global variables
$LogFile = ""

function Write-TaskLog {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"
    
    try {
        # Ensure log directory exists
        if (-not (Test-Path $LogPath)) {
            New-Item -Path $LogPath -ItemType Directory -Force | Out-Null
        }
        
        # Create log file if it doesn't exist
        if (-not $LogFile) {
            $LogFile = Join-Path $LogPath "FolderCleanup_$(Get-Date -Format 'yyyyMMdd').log"
        }
        
        # Write to log file
        Add-Content -Path $LogFile -Value $logEntry -Encoding UTF8
        
        # Also write to event log
        try {
            $eventType = switch ($Level) {
                "ERROR" { "Error" }
                "WARN" { "Warning" }
                default { "Information" }
            }
            Write-EventLog -LogName Application -Source $TaskName -EntryType $eventType -EventId 1001 -Message $Message -ErrorAction SilentlyContinue
        }
        catch {
            # Event log writing is optional - don't fail if it doesn't work
        }
        
        # Rotate log if too large
        if ((Get-Item $LogFile -ErrorAction SilentlyContinue).Length -gt ($MaxLogSizeMB * 1MB)) {
            Rotate-LogFiles
        }
    }
    catch {
        Write-Host "Failed to write log: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Rotate-LogFiles {
    try {
        $logFiles = Get-ChildItem -Path $LogPath -Filter "FolderCleanup_*.log" | Sort-Object LastWriteTime -Descending
        
        if ($logFiles.Count -ge $MaxLogFiles) {
            $filesToDelete = $logFiles | Select-Object -Skip ($MaxLogFiles - 1)
            foreach ($file in $filesToDelete) {
                Remove-Item $file.FullName -Force
                Write-TaskLog "Rotated old log file: $($file.Name)"
            }
        }
    }
    catch {
        Write-TaskLog "Failed to rotate log files: $($_.Exception.Message)" "ERROR"
    }
}

function Test-SafelistProtection {
    param(
        [string]$ItemPath,
        [array]$LocalSafelist
    )
    
    $itemName = Split-Path $ItemPath -Leaf
    
    # Check global safelist
    foreach ($safeItem in $GlobalSafelist) {
        if ($itemName -like "*$safeItem*") {
            return $true
        }
    }
    
    # Check local safelist
    foreach ($safeItem in $LocalSafelist) {
        if ($itemName -like "*$safeItem*") {
            return $true
        }
    }
    
    return $false
}

function Get-FolderSizeMB {
    param([string]$FolderPath)
    
    try {
        if (-not (Test-Path $FolderPath)) {
            return 0
        }
        
        $folderSize = Get-ChildItem -Path $FolderPath -Recurse -Force -ErrorAction SilentlyContinue | 
                     Measure-Object -Property Length -Sum | 
                     Select-Object -ExpandProperty Sum
        
        if ($null -eq $folderSize) {
            return 0
        }
        
        return [math]::Round($folderSize / 1MB, 2)
    }
    catch {
        Write-TaskLog "Error calculating folder size for $FolderPath`: $($_.Exception.Message)" "WARN"
        return 0
    }
}

function Get-DiskFreeSpaceMB {
    param([string]$DriveLetter)
    
    try {
        # Ensure drive letter format (e.g., "C:" not "C:\")
        if ($DriveLetter.EndsWith('\')) {
            $DriveLetter = $DriveLetter.TrimEnd('\')
        }
        if (-not $DriveLetter.EndsWith(':')) {
            $DriveLetter += ':'
        }
        
        $drive = Get-WmiObject -Class Win32_LogicalDisk -Filter "DeviceID='$DriveLetter'" -ErrorAction SilentlyContinue
        if ($drive) {
            $freeSpaceGB = [math]::Round($drive.FreeSpace / 1MB, 2)
            return $freeSpaceGB
        } else {
            Write-TaskLog "Could not retrieve disk information for drive $DriveLetter" "WARN"
            return 0
        }
    }
    catch {
        Write-TaskLog "Error calculating free space for drive $DriveLetter`: $($_.Exception.Message)" "WARN"
        return 0
    }
}

function Get-TimestampFromFilename {
    param([string]$FileName)
    
    foreach ($pattern in $TimestampPatterns) {
        if ($FileName -match $pattern.Pattern) {
            try {
                $timestampString = $matches[1]
                $timestamp = [DateTime]::ParseExact($timestampString, $pattern.Format, $null)
                return $timestamp
            }
            catch {
                continue
            }
        }
    }
    
    return $null
}

function Clean-FolderFull {
    param(
        [string]$FolderPath,
        [array]$LocalSafelist
    )
    
    Write-TaskLog "Starting full cleanup of folder: $FolderPath"
    $deletedCount = 0
    $skippedCount = 0
    
    try {
        if (-not (Test-Path $FolderPath)) {
            Write-TaskLog "Folder does not exist: $FolderPath" "WARN"
            return
        }
        
        $items = Get-ChildItem -Path $FolderPath -Force
        
        foreach ($item in $items) {
            if (Test-SafelistProtection -ItemPath $item.FullName -LocalSafelist $LocalSafelist) {
                Write-TaskLog "Skipped safelist item: $($item.Name)"
                $skippedCount++
                continue
            }
            
            try {
                if ($item.PSIsContainer) {
                    Remove-Item -Path $item.FullName -Recurse -Force
                    Write-TaskLog "Deleted folder: $($item.Name)"
                } else {
                    Remove-Item -Path $item.FullName -Force
                    Write-TaskLog "Deleted file: $($item.Name)"
                }
                $deletedCount++
            }
            catch {
                Write-TaskLog "Failed to delete $($item.Name): $($_.Exception.Message)" "ERROR"
            }
        }
        
        Write-TaskLog "Full cleanup completed. Deleted: $deletedCount, Skipped: $skippedCount"
    }
    catch {
        Write-TaskLog "Error during full cleanup of $FolderPath`: $($_.Exception.Message)" "ERROR"
    }
}

function Clean-FolderTimestampBased {
    param(
        [string]$FolderPath,
        [int]$AgeThresholdDays,
        [array]$LocalSafelist
    )
    
    Write-TaskLog "Starting timestamp-based cleanup of folder: $FolderPath (Age threshold: $AgeThresholdDays days, Time offset: $TimestampOffsetHours hours)"
    $deletedCount = 0
    $skippedCount = 0
    $noTimestampCount = 0
    
    try {
        if (-not (Test-Path $FolderPath)) {
            Write-TaskLog "Folder does not exist: $FolderPath" "WARN"
            return
        }
        
        # Adjust cutoff time to account for timestamp offset
        $adjustedCurrentTime = (Get-Date).AddHours(-$TimestampOffsetHours)
        $cutoffDate = $adjustedCurrentTime.AddDays(-$AgeThresholdDays)
        Write-TaskLog "Current time: $(Get-Date), Adjusted time (minus $TimestampOffsetHours hours): $adjustedCurrentTime, Cutoff date: $cutoffDate"
        
        $items = Get-ChildItem -Path $FolderPath -Force
        
        foreach ($item in $items) {
            if (Test-SafelistProtection -ItemPath $item.FullName -LocalSafelist $LocalSafelist) {
                Write-TaskLog "Skipped safelist item: $($item.Name)"
                $skippedCount++
                continue
            }
            
            $timestamp = Get-TimestampFromFilename -FileName $item.Name
            
            if ($null -eq $timestamp) {
                Write-TaskLog "No timestamp found in filename: $($item.Name)"
                $noTimestampCount++
                continue
            }
            
            if ($timestamp -lt $cutoffDate) {
                try {
                    if ($item.PSIsContainer) {
                        Remove-Item -Path $item.FullName -Recurse -Force
                        Write-TaskLog "Deleted old folder: $($item.Name) (Date: $timestamp)"
                    } else {
                        Remove-Item -Path $item.FullName -Force
                        Write-TaskLog "Deleted old file: $($item.Name) (Date: $timestamp)"
                    }
                    $deletedCount++
                }
                catch {
                    Write-TaskLog "Failed to delete $($item.Name): $($_.Exception.Message)" "ERROR"
                }
            } else {
                Write-TaskLog "Kept recent item: $($item.Name) (Date: $timestamp)"
                $skippedCount++
            }
        }
        
        Write-TaskLog "Timestamp-based cleanup completed. Deleted: $deletedCount, Skipped: $skippedCount, No timestamp: $noTimestampCount"
    }
    catch {
        Write-TaskLog "Error during timestamp-based cleanup of $FolderPath`: $($_.Exception.Message)" "ERROR"
    }
}

function Start-CleanupProcess {
    Write-TaskLog "=== Starting cleanup process ==="
    $totalDeleted = 0
    $totalSkipped = 0
    $totalNoTimestamp = 0
    $totalErrors = 0
    
    foreach ($folderConfig in $FoldersToClean) {
        Write-TaskLog "Processing folder: $($folderConfig.Path)"
        
        try {
            # Check if folder exists
            if (-not (Test-Path $folderConfig.Path)) {
                Write-TaskLog "Folder does not exist: $($folderConfig.Path)" "WARN"
                $totalErrors++
                continue
            }
            
            # Check disk space for emergency cleanup
            $driveLetter = Split-Path $folderConfig.Path -Qualifier
            $freeSpaceMB = Get-DiskFreeSpaceMB -DriveLetter $driveLetter
            $emergencyCleanup = $false
            
            if ($LowDiskSpaceThresholdMB -gt 0 -and $freeSpaceMB -lt $LowDiskSpaceThresholdMB) {
                $emergencyCleanup = $true
                Write-TaskLog "EMERGENCY CLEANUP TRIGGERED - Low disk space on drive $driveLetter`: $freeSpaceMB MB < $LowDiskSpaceThresholdMB MB threshold" "WARN"
            }
            
            # Check folder size if threshold is set (unless emergency cleanup is triggered)
            if ($MinimumFolderSizeMB -gt 0 -and -not $emergencyCleanup) {
                $folderSizeMB = Get-FolderSizeMB -FolderPath $folderConfig.Path
                Write-TaskLog "Folder size: $folderSizeMB MB (Threshold: $MinimumFolderSizeMB MB) - Drive $driveLetter free space: $freeSpaceMB MB"
                
                if ($folderSizeMB -lt $MinimumFolderSizeMB) {
                    Write-TaskLog "Skipping cleanup - folder size ($folderSizeMB MB) is below threshold ($MinimumFolderSizeMB MB)"
                    continue
                }
            } elseif ($emergencyCleanup) {
                $folderSizeMB = Get-FolderSizeMB -FolderPath $folderConfig.Path
                Write-TaskLog "Emergency cleanup mode - bypassing folder size threshold. Folder size: $folderSizeMB MB, Drive $driveLetter free space: $freeSpaceMB MB"
            } else {
                Write-TaskLog "Drive $driveLetter free space: $freeSpaceMB MB (Low disk threshold: $LowDiskSpaceThresholdMB MB)"
            }
            
            # Proceed with cleanup
            switch ($folderConfig.Mode) {
                "Full" {
                    Clean-FolderFull -FolderPath $folderConfig.Path -LocalSafelist $folderConfig.LocalSafelist
                }
                "TimestampBased" {
                    $ageThreshold = if ($folderConfig.AgeThresholdDays -gt 0) { $folderConfig.AgeThresholdDays } else { $DefaultAgeThresholdDays }
                    Clean-FolderTimestampBased -FolderPath $folderConfig.Path -AgeThresholdDays $ageThreshold -LocalSafelist $folderConfig.LocalSafelist
                }
                default {
                    Write-TaskLog "Unknown cleanup mode: $($folderConfig.Mode) for folder $($folderConfig.Path)" "ERROR"
                    $totalErrors++
                }
            }
        } catch {
            Write-TaskLog "Error processing folder $($folderConfig.Path): $($_.Exception.Message)" "ERROR"
            $totalErrors++
        }
    }
    Write-TaskLog "=== Cleanup process completed ==="
}

function Install-ScheduledTask {
    try {
        Write-Host "Installing Scheduled Task: $TaskDisplayName..." -ForegroundColor Green
        
        # Create event log source
        try {
            if (-not ([System.Diagnostics.EventLog]::SourceExists($TaskName))) {
                New-EventLog -LogName Application -Source $TaskName
            }
        }
        catch {
            Write-Host "Note: Could not create event log source (this is optional)" -ForegroundColor Yellow
        }
        
        $scriptPath = $PSCommandPath
        if (-not $scriptPath) {
            $scriptPath = $MyInvocation.MyCommand.Path
        }
        if (-not $scriptPath) {
            throw "Could not determine script path for scheduled task"
        }
        
        # Create the action - Use a more explicit parameter format
        $action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -RunCleanup"
        
        # Create the trigger (runs every X minutes)
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $CleanupIntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 365)
        
        # Create the principal (run as SYSTEM)
        $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
        
        # Create the settings
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -DontStopOnIdleEnd
        
        # Register the task
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description $TaskDescription -Force
        
        Write-Host "Scheduled Task installed successfully!" -ForegroundColor Green
        Write-Host "Task Name: $TaskName" -ForegroundColor Yellow
        Write-Host "Runs every $CleanupIntervalMinutes minutes as SYSTEM user" -ForegroundColor Yellow
        Write-Host "Use 'Get-ScheduledTask -TaskName `"$TaskName`"' to check status" -ForegroundColor Yellow
    }
    catch {
        Write-Host "Failed to install scheduled task: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Uninstall-ScheduledTask {
    try {
        Write-Host "Uninstalling Scheduled Task: $TaskDisplayName..." -ForegroundColor Yellow
        
        # Check if task exists
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($task) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Host "Scheduled Task uninstalled successfully!" -ForegroundColor Green
        } else {
            Write-Host "Scheduled Task '$TaskName' not found." -ForegroundColor Yellow
        }
    }
    catch {
        Write-Host "Failed to uninstall scheduled task: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Test-Configuration {
    Write-Host "Testing configuration..." -ForegroundColor Cyan
    
    # Test timestamp patterns
    Write-Host ""
    Write-Host "Testing timestamp patterns:" -ForegroundColor Yellow
    $testFilenames = @(
        "document_20250723_report.pdf",
        "backup_20250723-143000_final.txt", 
        "log_2025-07-23_system.log",
        "data_20250723143000_export.csv",
        "temp_20250723_143000_file.tmp"
    )
    
    foreach ($filename in $testFilenames) {
        $timestamp = Get-TimestampFromFilename -FileName $filename
        if ($timestamp) {
            Write-Host "  [OK] $filename -> $timestamp" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] $filename -> No timestamp found" -ForegroundColor Red
        }
    }
    
    # Test folder paths
    Write-Host ""
    Write-Host "Testing folder configurations:" -ForegroundColor Yellow
    foreach ($folderConfig in $FoldersToClean) {
        $folderPath = $folderConfig.Path
        $folderMode = $folderConfig.Mode
        $exists = Test-Path $folderPath
        
        if ($exists) {
            $folderSizeMB = Get-FolderSizeMB -FolderPath $folderPath
            $driveLetter = Split-Path $folderPath -Qualifier
            $freeSpaceMB = Get-DiskFreeSpaceMB -DriveLetter $driveLetter
            
            $sizeStatus = if ($MinimumFolderSizeMB -gt 0 -and $folderSizeMB -lt $MinimumFolderSizeMB) { " (BELOW THRESHOLD)" } else { "" }
            $diskStatus = if ($LowDiskSpaceThresholdMB -gt 0 -and $freeSpaceMB -lt $LowDiskSpaceThresholdMB) { " (LOW DISK SPACE!)" } else { "" }
            
            Write-Host "  [EXISTS] $folderPath (Mode: $folderMode, Size: $folderSizeMB MB)$sizeStatus" -ForegroundColor $(if ($sizeStatus) { "Yellow" } else { "Green" })
            Write-Host "           Drive $driveLetter Free Space: $freeSpaceMB MB$diskStatus" -ForegroundColor $(if ($diskStatus) { "Red" } else { "Cyan" })
        } else {
            Write-Host "  [NOT FOUND] $folderPath (Mode: $folderMode)" -ForegroundColor Red
        }
    }
    
    if ($MinimumFolderSizeMB -gt 0) {
        Write-Host ""
        Write-Host "Minimum folder size threshold: $MinimumFolderSizeMB MB" -ForegroundColor Cyan
    }
    
    if ($LowDiskSpaceThresholdMB -gt 0) {
        Write-Host "Low disk space emergency threshold: $LowDiskSpaceThresholdMB MB" -ForegroundColor Cyan
    }
    
    if ($TimestampOffsetHours -gt 0) {
        Write-Host "Timestamp offset compensation: $TimestampOffsetHours hours" -ForegroundColor Cyan
        Write-Host "  (Log timestamps are assumed to be $TimestampOffsetHours hours behind system time)" -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "Configuration test completed!" -ForegroundColor Cyan
}

# Main script logic
if ($InstallTask) {
    Install-ScheduledTask
}
elseif ($UninstallTask) {
    Uninstall-ScheduledTask
}
elseif ($RunCleanup) {
    # Used by scheduled task - run cleanup once and exit
    Write-TaskLog "Running scheduled cleanup task"
    Start-CleanupProcess
    Write-TaskLog "Scheduled cleanup task completed"
}
elseif ($TestRun) {
    Write-Host "Running test cleanup (files will be deleted!)..." -ForegroundColor Yellow
    Start-CleanupProcess
}
elseif ($TestConfig) {
    Test-Configuration
}
elseif ($DryRun) {
    Write-Host "DRY RUN - No files will be deleted" -ForegroundColor Yellow
    $totalToDelete = 0
    $totalToKeep = 0
    $totalIgnored = 0
    $totalProtected = 0
    $totalErrors = 0
    $totalSkippedSize = 0
    $totalEmergencyCleanup = 0
    
    foreach ($folderConfig in $FoldersToClean) {
        Write-Host "`nFolder: $($folderConfig.Path)" -ForegroundColor White
        
        if (-not (Test-Path $folderConfig.Path)) {
            Write-Host "  [NOT FOUND]" -ForegroundColor Red
            $totalErrors++
            continue
        }
        
        # Check disk space for emergency cleanup
        $driveLetter = Split-Path $folderConfig.Path -Qualifier
        $freeSpaceMB = Get-DiskFreeSpaceMB -DriveLetter $driveLetter
        $emergencyCleanup = $false
        
        if ($LowDiskSpaceThresholdMB -gt 0 -and $freeSpaceMB -lt $LowDiskSpaceThresholdMB) {
            $emergencyCleanup = $true
            Write-Host "  [EMERGENCY] Low disk space on drive $driveLetter`: $freeSpaceMB MB < $LowDiskSpaceThresholdMB MB - FORCING CLEANUP" -ForegroundColor Red
            $totalEmergencyCleanup++
        }
        
        # Check folder size
        if ($MinimumFolderSizeMB -gt 0) {
            $folderSizeMB = Get-FolderSizeMB -FolderPath $folderConfig.Path
            Write-Host "  Folder size: $folderSizeMB MB (Threshold: $MinimumFolderSizeMB MB)" -ForegroundColor Cyan
            Write-Host "  Drive $driveLetter free space: $freeSpaceMB MB (Emergency threshold: $LowDiskSpaceThresholdMB MB)" -ForegroundColor Cyan
            
            if ($folderSizeMB -lt $MinimumFolderSizeMB -and -not $emergencyCleanup) {
                Write-Host "  [SKIP] Folder size below threshold - no cleanup needed" -ForegroundColor Yellow
                $totalSkippedSize++
                continue
            } elseif ($emergencyCleanup) {
                Write-Host "  [EMERGENCY MODE] Bypassing folder size threshold due to low disk space" -ForegroundColor Red
            }
        } else {
            Write-Host "  Drive $driveLetter free space: $freeSpaceMB MB (Emergency threshold: $LowDiskSpaceThresholdMB MB)" -ForegroundColor Cyan
        }
        
        $items = Get-ChildItem -Path $folderConfig.Path -Force -ErrorAction SilentlyContinue
        foreach ($item in $items) {
            try {
                $isProtected = Test-SafelistProtection -ItemPath $item.FullName -LocalSafelist $folderConfig.LocalSafelist
                if ($isProtected) {
                    Write-Host "  [KEEP] $($item.Name) (protected)" -ForegroundColor Blue
                    $totalProtected++
                } elseif ($folderConfig.Mode -eq "Full") {
                    Write-Host "  [DELETE] $($item.Name)" -ForegroundColor Red
                    $totalToDelete++
                } elseif ($folderConfig.Mode -eq "TimestampBased") {
                    $timestamp = Get-TimestampFromFilename -FileName $item.Name
                    if ($null -eq $timestamp) {
                        Write-Host "  [IGNORE] $($item.Name) (no timestamp)" -ForegroundColor Yellow
                        $totalIgnored++
                    } else {
                        # Adjust cutoff time to account for timestamp offset
                        $adjustedCurrentTime = (Get-Date).AddHours(-$TimestampOffsetHours)
                        $cutoffDate = $adjustedCurrentTime.AddDays(-$folderConfig.AgeThresholdDays)
                        if ($timestamp -lt $cutoffDate) {
                            Write-Host "  [DELETE] $($item.Name) (old: $timestamp, cutoff: $cutoffDate)" -ForegroundColor Red
                            $totalToDelete++
                        } else {
                            Write-Host "  [KEEP] $($item.Name) (recent: $timestamp, cutoff: $cutoffDate)" -ForegroundColor Green
                            $totalToKeep++
                        }
                    }
                } else {
                    Write-Host "  [ERROR] Unknown mode: $($folderConfig.Mode)" -ForegroundColor Red
                    $totalErrors++
                }
            } catch {
                Write-Host "  [ERROR] $($item.Name): $($_.Exception.Message)" -ForegroundColor Red
                $totalErrors++
            }
        }
    }
    Write-Host "`nDRY RUN SUMMARY:" -ForegroundColor Cyan
    Write-Host "  To Delete: $totalToDelete" -ForegroundColor Red
    Write-Host "  To Keep: $totalToKeep" -ForegroundColor Green
    Write-Host "  Ignored (no timestamp): $totalIgnored" -ForegroundColor Yellow
    Write-Host "  Protected: $totalProtected" -ForegroundColor Blue
    Write-Host "  Skipped (size threshold): $totalSkippedSize" -ForegroundColor Yellow
    Write-Host "  Emergency cleanup triggered: $totalEmergencyCleanup" -ForegroundColor Red
    Write-Host "  Errors: $totalErrors" -ForegroundColor Magenta
}
else {
    Write-Host @"
Folder Cleanup Task Management Script

Installation & Management:
  .\FolderCleanupService.ps1 -InstallTask    Install as Windows Scheduled Task
  .\FolderCleanupService.ps1 -UninstallTask  Uninstall the Scheduled Task

Testing & Configuration:
  .\FolderCleanupService.ps1 -TestConfig     Test the configuration without making changes
  .\FolderCleanupService.ps1 -DryRun         Show what would be deleted without deleting
  .\FolderCleanupService.ps1 -TestRun        Run cleanup once for testing (WARNING: Will delete files!)

After installation, manage with:
  Get-ScheduledTask -TaskName "$TaskName"                Check task status
  Start-ScheduledTask -TaskName "$TaskName"              Run task immediately
  Get-ScheduledTaskInfo -TaskName "$TaskName"            View task history
  Stop-ScheduledTask -TaskName "$TaskName"               Stop running task

Configuration:
  Edit the variables in the CONFIGURATION SECTION at the top of this script.
  
Logs:
  Task logs: $LogPath
  Windows Event Log: Application -> Source: $TaskName

Features:
  - Reliable PowerShell execution via Task Scheduler
  - Runs as SYSTEM with full privileges
  - Automatic retry and error handling
  - Configurable timestamp-based cleanup
  - Folder size threshold protection
  - Comprehensive safelist protection
  - Detailed logging and monitoring
"@ -ForegroundColor White
}
