#Requires -RunAsAdministrator

<#
.SYNOPSIS
    Folder Cleanup Service - Configurable folder cleaning with timestamp-based and full cleanup modes
.DESCRIPTION
    This script can be deployed as a Windows service to automatically clean folders based on configuration.
    Supports two modes: full cleanup and timestamp-based cleanup with safelist protection.
.NOTES
    Author: Giovanni Misso
    Date: 2025-07-23
    Version: 1.0
#>

param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$RunAsService,
    [switch]$TestRun,
    [switch]$TestConfig,
    [switch]$DryRun
)

# ==================== CONFIGURATION SECTION ====================
# Modify these variables to configure the service behavior

# Service Configuration
$ServiceName = "FolderCleanupService"
$ServiceDisplayName = "Folder Cleanup Service"
$ServiceDescription = "Automated folder cleanup with configurable rules and safelist protection"

# Cleanup Schedule (in minutes) - Default: 1440 minutes = 24 hours (daily)
$CleanupIntervalMinutes = 1

# Log Configuration
$LogPath = "C:\Windows\Logs\FolderCleanupService"
$MaxLogSizeMB = 50
$MaxLogFiles = 10

# Timestamp Configuration
# Define multiple timestamp patterns that might appear in filenames
# Format: @{Pattern="regex_pattern"; Format="datetime_format"}
$TimestampPatterns = @(
    @{Pattern="_(\d{8})_"; Format="yyyyMMdd"},           # _20250723_
    @{Pattern="_(\d{8}-\d{6})_"; Format="yyyyMMdd-HHmmss"}, # _20250723-143000_
    @{Pattern="_(\d{4}-\d{2}-\d{2})_"; Format="yyyy-MM-dd"}, # _2025-07-23_
    @{Pattern="_(\d{14})_"; Format="yyyyMMddHHmmss"},    # _20250723143000_
    @{Pattern="_(\d{4}\d{2}\d{2}_\d{6})_"; Format="yyyyMMdd_HHmmss"} # _20250723_143000_
)

# Default age threshold for timestamp-based cleanup (in days)
$DefaultAgeThresholdDays = 30

# Folder Configuration
# Each folder can have: Path, Mode, AgeThresholdDays, LocalSafelist
$FoldersToClean = @(
    @{
        Path = "C:\Users\giovanni.misso\Documents\pdf_split_rotate\scripts\folder_cleanup\test_folders\timestamp_cleanup_test"
        Mode = "TimestampBased"  # Options: "Full" or "TimestampBased"
        AgeThresholdDays = 30
        LocalSafelist = @("important.txt", "keep_this_folder")
    },
    @{
        Path = "C:\Users\giovanni.misso\Documents\pdf_split_rotate\scripts\folder_cleanup\test_folders\full_cleanup_test" 
        Mode = "Full"
        AgeThresholdDays = 0  # Not used for Full mode
        LocalSafelist = @("config.ini")
    }
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
    "desktop.ini",
    "thumbs.db",
    ".gitkeep",
    "README.md",
    "readme.txt",
    "important",
    "backup"
)

# ==================== END CONFIGURATION SECTION ====================

# Global variables
$LogFile = ""
$ServiceRunning = $false

function Write-ServiceLog {
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
        
        # Also write to event log if running as service
        if ($ServiceRunning) {
            $eventType = switch ($Level) {
                "ERROR" { "Error" }
                "WARN" { "Warning" }
                default { "Information" }
            }
            Write-EventLog -LogName Application -Source $ServiceName -EntryType $eventType -EventId 1001 -Message $Message
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
                Write-ServiceLog "Rotated old log file: $($file.Name)"
            }
        }
    }
    catch {
        Write-ServiceLog "Failed to rotate log files: $($_.Exception.Message)" "ERROR"
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
    
    Write-ServiceLog "Starting full cleanup of folder: $FolderPath"
    $deletedCount = 0
    $skippedCount = 0
    
    try {
        if (-not (Test-Path $FolderPath)) {
            Write-ServiceLog "Folder does not exist: $FolderPath" "WARN"
            return
        }
        
        $items = Get-ChildItem -Path $FolderPath -Force
        
        foreach ($item in $items) {
            if (Test-SafelistProtection -ItemPath $item.FullName -LocalSafelist $LocalSafelist) {
                Write-ServiceLog "Skipped safelist item: $($item.Name)"
                $skippedCount++
                continue
            }
            
            try {
                if ($item.PSIsContainer) {
                    Remove-Item -Path $item.FullName -Recurse -Force
                    Write-ServiceLog "Deleted folder: $($item.Name)"
                } else {
                    Remove-Item -Path $item.FullName -Force
                    Write-ServiceLog "Deleted file: $($item.Name)"
                }
                $deletedCount++
            }
            catch {
                Write-ServiceLog "Failed to delete $($item.Name): $($_.Exception.Message)" "ERROR"
            }
        }
        
        Write-ServiceLog "Full cleanup completed. Deleted: $deletedCount, Skipped: $skippedCount"
    }
    catch {
        Write-ServiceLog "Error during full cleanup of $FolderPath`: $($_.Exception.Message)" "ERROR"
    }
}

function Clean-FolderTimestampBased {
    param(
        [string]$FolderPath,
        [int]$AgeThresholdDays,
        [array]$LocalSafelist
    )
    
    Write-ServiceLog "Starting timestamp-based cleanup of folder: $FolderPath (Age threshold: $AgeThresholdDays days)"
    $deletedCount = 0
    $skippedCount = 0
    $noTimestampCount = 0
    
    try {
        if (-not (Test-Path $FolderPath)) {
            Write-ServiceLog "Folder does not exist: $FolderPath" "WARN"
            return
        }
        
        $cutoffDate = (Get-Date).AddDays(-$AgeThresholdDays)
        $items = Get-ChildItem -Path $FolderPath -Force
        
        foreach ($item in $items) {
            if (Test-SafelistProtection -ItemPath $item.FullName -LocalSafelist $LocalSafelist) {
                Write-ServiceLog "Skipped safelist item: $($item.Name)"
                $skippedCount++
                continue
            }
            
            $timestamp = Get-TimestampFromFilename -FileName $item.Name
            
            if ($null -eq $timestamp) {
                Write-ServiceLog "No timestamp found in filename: $($item.Name)"
                $noTimestampCount++
                continue
            }
            
            if ($timestamp -lt $cutoffDate) {
                try {
                    if ($item.PSIsContainer) {
                        Remove-Item -Path $item.FullName -Recurse -Force
                        Write-ServiceLog "Deleted old folder: $($item.Name) (Date: $timestamp)"
                    } else {
                        Remove-Item -Path $item.FullName -Force
                        Write-ServiceLog "Deleted old file: $($item.Name) (Date: $timestamp)"
                    }
                    $deletedCount++
                }
                catch {
                    Write-ServiceLog "Failed to delete $($item.Name): $($_.Exception.Message)" "ERROR"
                }
            } else {
                Write-ServiceLog "Kept recent item: $($item.Name) (Date: $timestamp)"
                $skippedCount++
            }
        }
        
        Write-ServiceLog "Timestamp-based cleanup completed. Deleted: $deletedCount, Skipped: $skippedCount, No timestamp: $noTimestampCount"
    }
    catch {
        Write-ServiceLog "Error during timestamp-based cleanup of $FolderPath`: $($_.Exception.Message)" "ERROR"
    }
}

function Start-CleanupProcess {
    Write-ServiceLog "=== Starting cleanup process ==="
    $totalDeleted = 0
    $totalSkipped = 0
    $totalNoTimestamp = 0
    $totalErrors = 0
    foreach ($folderConfig in $FoldersToClean) {
        Write-ServiceLog "Processing folder: $($folderConfig.Path)"
        try {
            switch ($folderConfig.Mode) {
                "Full" {
                    Clean-FolderFull -FolderPath $folderConfig.Path -LocalSafelist $folderConfig.LocalSafelist
                }
                "TimestampBased" {
                    $ageThreshold = if ($folderConfig.AgeThresholdDays -gt 0) { $folderConfig.AgeThresholdDays } else { $DefaultAgeThresholdDays }
                    Clean-FolderTimestampBased -FolderPath $folderConfig.Path -AgeThresholdDays $ageThreshold -LocalSafelist $folderConfig.LocalSafelist
                }
                default {
                    Write-ServiceLog "Unknown cleanup mode: $($folderConfig.Mode) for folder $($folderConfig.Path)" "ERROR"
                    $totalErrors++
                }
            }
        } catch {
            Write-ServiceLog "Error processing folder $($folderConfig.Path): $($_.Exception.Message)" "ERROR"
            $totalErrors++
        }
    }
    Write-ServiceLog "=== Cleanup process completed ==="
    # Optionally, print a summary here if you want to aggregate stats
}

function Install-Service {
    try {
        Write-Host "Installing $ServiceDisplayName..." -ForegroundColor Green
        
        # Create event log source
        if (-not ([System.Diagnostics.EventLog]::SourceExists($ServiceName))) {
            New-EventLog -LogName Application -Source $ServiceName
        }
        
        $servicePath = $MyInvocation.MyCommand.Path
        $arguments = "-ExecutionPolicy Bypass -File `"$servicePath`" -RunAsService"
        
        New-Service -Name $ServiceName -BinaryPathName "powershell.exe $arguments" -DisplayName $ServiceDisplayName -Description $ServiceDescription -StartupType Automatic
        
        Write-Host "Service installed successfully!" -ForegroundColor Green
        Write-Host "Use 'Start-Service $ServiceName' to start the service." -ForegroundColor Yellow
    }
    catch {
        Write-Host "Failed to install service: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Uninstall-Service {
    try {
        Write-Host "Uninstalling $ServiceDisplayName..." -ForegroundColor Yellow
        
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        
        # Use sc.exe for compatibility with PowerShell 5.1
        $result = & sc.exe delete $ServiceName
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Service uninstalled successfully!" -ForegroundColor Green
        } else {
            Write-Host "Failed to uninstall service: $result" -ForegroundColor Red
        }
    }
    catch {
        Write-Host "Failed to uninstall service: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Start-ServiceMode {
    $script:ServiceRunning = $true
    Write-ServiceLog "Service starting..."
    
    try {
        while ($true) {
            Start-CleanupProcess
            
            Write-ServiceLog "Next cleanup scheduled in $CleanupIntervalMinutes minutes"
            Start-Sleep -Seconds ($CleanupIntervalMinutes * 60)
        }
    }
    catch {
        Write-ServiceLog "Service error: $($_.Exception.Message)" "ERROR"
    }
    finally {
        Write-ServiceLog "Service stopping..."
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
            Write-Host "  [EXISTS] $folderPath (Mode: $folderMode)" -ForegroundColor Green
        } else {
            Write-Host "  [NOT FOUND] $folderPath (Mode: $folderMode)" -ForegroundColor Red
        }
    }
    
    Write-Host ""
    Write-Host "Configuration test completed!" -ForegroundColor Cyan
}

# Main script logic
if ($Install) {
    Install-Service
}
elseif ($Uninstall) {
    Uninstall-Service
}
elseif ($RunAsService) {
    Start-ServiceMode
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
    foreach ($folderConfig in $FoldersToClean) {
        Write-Host "`nFolder: $($folderConfig.Path)" -ForegroundColor White
        if (-not (Test-Path $folderConfig.Path)) {
            Write-Host "  [NOT FOUND]" -ForegroundColor Red
            $totalErrors++
            continue
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
                        $cutoffDate = (Get-Date).AddDays(-$folderConfig.AgeThresholdDays)
                        if ($timestamp -lt $cutoffDate) {
                            Write-Host "  [DELETE] $($item.Name) (old: $timestamp)" -ForegroundColor Red
                            $totalToDelete++
                        } else {
                            Write-Host "  [KEEP] $($item.Name) (recent: $timestamp)" -ForegroundColor Green
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
    Write-Host "  Errors: $totalErrors" -ForegroundColor Magenta
}
else {
    Write-Host @"
Folder Cleanup Service Management Script

Usage:
  .\FolderCleanupService.ps1 -Install      Install the Windows service
  .\FolderCleanupService.ps1 -Uninstall    Uninstall the Windows service  
  .\FolderCleanupService.ps1 -TestConfig   Test the configuration without making changes
  .\FolderCleanupService.ps1 -DryRun       Show what would be deleted without deleting
  .\FolderCleanupService.ps1 -TestRun      Run cleanup once for testing (WARNING: Will delete files!)

After installation:
  Start-Service $ServiceName              Start the service
  Stop-Service $ServiceName               Stop the service
  Get-Service $ServiceName                Check service status

Configuration:
  Edit the variables in the CONFIGURATION SECTION at the top of this script.
  
Logs:
  Service logs: $LogPath
  Windows Event Log: Application -> Source: $ServiceName
"@ -ForegroundColor White
}
