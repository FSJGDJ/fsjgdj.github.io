---
title: '驱动程序时间线分析'
description: '通过脚本接收csv，记录虚拟机中驱动程序时间线'
pubDate: 2026-09-12
tags: ["Windows", "驱动", "分析"]
---

## 说明

把sysmon（事件ID 6），服务安装（事件ID 7045），以及drivertnery当前状态合并为统一时间线，并进行排序，html支持按驱动名称和事件类型筛选。
在脚本中统一时间格式和驱动路径，处理 %SystemRoot%、\SystemRoot、引号及大小写差异。

## 交互式报告查看

[👉 点击此处查看 Driver Timeline 交互式报告](/driver_timeline.html)

> 提示：如果无法直接预览，请右键链接选择“在新标签页打开”或下载 CSV 文件查看。

## 生成脚本

<details>
<summary>展开查看 PowerShell 脚本</summary>

```powershell
<#
.SYNOPSIS
    Build a unified driver timeline from Week 9 data sources.

.DESCRIPTION
    Processes EVTX/CSV logs, driverquery output, and Service Install events (7045).
    Normalizes paths, correlates events by Service Name/Image Path, and outputs
    a sorted CSV and an interactive HTML report.

.PARAMETER EvtxPath
    Path to the raw .evtx file containing Event ID 6.
.PARAMETER DriverQueryCsv
    Path to the driverquery CSV export.
.PARAMETER SysLog7045Csv
    Path to the CSV export of System Event ID 7045.
.PARAMETER OutputDir
    Directory to save the resulting CSV and HTML files.
#>

param(
    [string]$EVTXPath = ".\Week9_Raw.evtx",
    [string]$DriverQueryCsv = ".\Week9_DriverQuery.csv",
    [string]$SysLog7045Csv = ".\Week9_SysLog_7045.csv",
    [string]$OutputDir = ".\Output"
)

# Ensure output directory exists
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
}

Write-Host "[*] Starting Driver Timeline Generation for Week 9..." -ForegroundColor Cyan

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

function Normalize-Path {
    param([string]$RawPath)
    if ([string]::IsNullOrWhiteSpace($RawPath)) { return "" }
    
    # Remove quotes
    $clean = $RawPath.Replace('"', '').Replace("'", "").Trim()
    
    # Handle environment variables commonly found in driver paths
    $clean = $clean -replace '%SystemRoot%', $env:SystemRoot
    $clean = $clean -replace '%windir%', $env:SystemRoot
    $clean = $clean -replace '\\SystemRoot\\', "$($env:SystemRoot)\"
    
    # Normalize slashes
    $clean = $clean -replace '/', '\'
    
    # Lowercase for consistent matching
    return $clean.ToLower()
}

function Get-FileNameFromPath {
    param([string]$FullPath)
    if ([string]::IsNullOrWhiteSpace($FullPath)) { return "" }
    try {
        return (Split-Path $FullPath -Leaf).ToLower()
    } catch {
        return $FullPath.ToLower()
    }
}

function Calculate-SHA256 {
    param([string]$FilePath)
    if ([string]::IsNullOrWhiteSpace($FilePath) -or -not (Test-Path $FilePath)) {
        return "N/A"
    }
    try {
        $hash = Get-FileHash -Path $FilePath -Algorithm SHA256
        return $hash.Hash
    } catch {
        return "Error_Calc_Hash"
    }
}

function Check-Signature {
    param([string]$FilePath)
    if ([string]::IsNullOrWhiteSpace($FilePath) -or -not (Test-Path $FilePath)) {
        return "Unknown"
    }
    try {
        $sig = Get-AuthenticodeSignature -FilePath $FilePath
        if ($sig.Status -eq 'Valid') {
            return "Valid"
        } else {
            return "Invalid/Unsigned"
        }
    } catch {
        return "Check_Failed"
    }
}

# -----------------------------------------------------------------------------
# Step 1: Parse Data Sources
# -----------------------------------------------------------------------------

$TimelineObjects = @()

# --- Source A: Event ID 6 (Driver Load) from EVTX ---
Write-Host "[*] Processing Event ID 6 (Driver Load)..." -ForegroundColor Yellow
try {
    if (Test-Path $EVTXPath) {
        $ext = [System.IO.Path]::GetExtension($EVTXPath)
        if ($ext -eq '.evtx') {
            $events = Get-WinEvent -Path $EVTXPath | Where-Object { $_.Id -eq 6 }
        } else {
            # Assume CSV if not evtx
            $events = Import-Csv $EVTXPath | Where-Object { $_.Id -eq 6 }
        }

        foreach ($evt in $events) {
            # Adjust property names based on typical Get-WinEvent vs Import-Csv structures
            # Assuming standard XML mapping for ID 6: Image, Hash, etc.
            $imgPath = $evt.Properties['Image'].Value ?? $evt.Image
            $hashVal = $evt.Properties['SHA1Hash'].Value ?? $evt.SHA1Hash ?? "N/A" # Often SHA1 in ID 6, we'll note it
            
            # Note: Event ID 6 usually provides SHA1. We will recalculate SHA256 later if file exists.
            
            $obj = [PSCustomObject]@{
                EventTime       = $evt.TimeCreated ?? $evt.Date
                EventType       = "Driver_Load"
                ServiceName     = "N/A" # ID 6 doesn't always have service name directly, often just image
                ImagePath       = Normalize-Path $imgPath
                SHA256          = "" # Placeholder
                SignatureStatus = "" # Placeholder
                DriverState     = "Loaded"
                SourceEventId   = 6
                MatchType       = "Event_Log"
                RawHash         = $hashVal
            }
            $TimelineObjects += $obj
        }
    }
} catch {
    Write-Warning "Failed to process EVTX/CSV for ID 6: $_"
}

# --- Source B: Event ID 7045 (Service Install) ---
Write-Host "[*] Processing Event ID 7045 (Service Install)..." -ForegroundColor Yellow
try {
    if (Test-Path $SysLog7045Csv) {
        $svcEvents = Import-Csv $SysLog7045Csv
        
        foreach ($evt in $svcEvents) {
            # 7045 properties vary by export method. Looking for ServiceName, ImagePath
            $sName = $evt.ServiceName ?? $evt.'Service Name' ?? "Unknown"
            $iPath = $evt.ImagePath ?? $evt.'Image Path' ?? ""
            
            $obj = [PSCustomObject]@{
                EventTime       = $evt.TimeCreated ?? $evt.Date
                EventType       = "Service_Install"
                ServiceName     = $sName
                ImagePath       = Normalize-Path $iPath
                SHA256          = "" 
                SignatureStatus = ""
                DriverState     = "Installed"
                SourceEventId   = 7045
                MatchType       = "Event_Log"
                RawHash         = ""
            }
            $TimelineObjects += $obj
        }
    }
} catch {
    Write-Warning "Failed to process 7045 CSV: $_"
}

# --- Source C: DriverQuery (Current State) ---
Write-Host "[*] Processing DriverQuery CSV..." -ForegroundColor Yellow
try {
    if (Test-Path $DriverQueryCsv) {
        $drivers = Import-Csv $DriverQueryCsv
        
        foreach ($drv in $drivers) {
            # Columns usually: Module Name, Display Name, Type, Start Mode, State, Status, Accept Stop, Accept Pause, Paged Pool(bytes), Code Size(bytes), Page(s), Path, Group, Tag, Error Control, Started By, Service Account
            $sName = $drv.'Module Name' ?? $drv.ModuleName
            $iPath = $drv.Path ?? $drv.'Path'
            $state = $drv.State ?? $drv.'State'
            
            $obj = [PSCustomObject]@{
                EventTime       = Get-Date # Current time as snapshot
                EventType       = "Current_State"
                ServiceName     = $sName
                ImagePath       = Normalize-Path $iPath
                SHA256          = ""
                SignatureStatus = ""
                DriverState     = $state
                SourceEventId   = "DriverQuery"
                MatchType       = "Live_System"
                RawHash         = ""
            }
            $TimelineObjects += $obj
        }
    }
} catch {
    Write-Warning "Failed to process DriverQuery CSV: $_"
}

# -----------------------------------------------------------------------------
# Step 2: Enrichment (SHA256 & Signature) & Correlation
# -----------------------------------------------------------------------------

Write-Host "[*] Enriching data with SHA256 and Signature Status (This may take a moment)..." -ForegroundColor Yellow

$EnrichedTimeline = @()

foreach ($item in $TimelineObjects) {
    # Clone object to avoid reference issues
    $newItem = $item.PSObject.Copy()
    
    $path = $item.ImagePath
    
    if (-not [string]::IsNullOrWhiteSpace($path) -and $path -ne "n/a") {
        # Resolve full path if possible for hashing
        # If path is relative or just filename, try to find it in System32/drivers
        $fullPath = $path
        if (-not (Test-Path $fullPath)) {
            $potentialPath = Join-Path $env:SystemRoot "System32\drivers\$((Split-Path $path -Leaf))"
            if (Test-Path $potentialPath) {
                $fullPath = $potentialPath
            }
        }

        # Calculate SHA256
        $newItem.SHA256 = Calculate-SHA256 -FilePath $fullPath
        
        # Check Signature
        $newItem.SignatureStatus = Check-Signature -FilePath $fullPath
    } else {
        $newItem.SHA256 = "No_Path"
        $newItem.SignatureStatus = "No_Path"
    }
    
    # Remove helper property
    $newItem.PSObject.Properties.Remove('RawHash')
    
    $EnrichedTimeline += $newItem
}

# -----------------------------------------------------------------------------
# Step 3: Sort and Export CSV
# -----------------------------------------------------------------------------

Write-Host "[*] Sorting and exporting CSV..." -ForegroundColor Yellow

$SortedTimeline = $EnrichedTimeline | Sort-Object EventTime

$csvPath = Join-Path $OutputDir "driver_timeline.csv"
$SortedTimeline | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8

Write-Host "[+] CSV saved to: $csvPath" -ForegroundColor Green

# -----------------------------------------------------------------------------
# Step 4: Generate HTML Report
# -----------------------------------------------------------------------------

Write-Host "[*] Generating HTML Report..." -ForegroundColor Yellow

$htmlPath = Join-Path $OutputDir "driver_timeline.html"

$htmlHeader = @"
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Week 9 Driver Timeline</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f9; padding: 20px; }
        h1 { color: #333; }
        .controls { margin-bottom: 20px; padding: 15px; background: white; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        input, select { padding: 8px; margin-right: 10px; border: 1px solid #ddd; border-radius: 4px; }
        table { width: 100%; border-collapse: collapse; background: white; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #ddd; font-size: 14px; }
        th { background-color: #007bff; color: white; position: sticky; top: 0; }
        tr:hover { background-color: #f1f1f1; }
        .status-valid { color: green; font-weight: bold; }
        .status-invalid { color: red; font-weight: bold; }
        .type-load { background-color: #e3f2fd; }
        .type-install { background-color: #fff3e0; }
        .type-state { background-color: #e8f5e9; }
    </style>
</head>
<body>
    <h1>Week 9 Driver Unified Timeline</h1>
    
    <div class="controls">
        <label>Filter by Service Name:</label>
        <input type="text" id="filterName" placeholder="Enter service name..." onkeyup="filterTable()">
        
        <label>Filter by Event Type:</label>
        <select id="filterType" onchange="filterTable()">
            <option value="All">All Types</option>
            <option value="Driver_Load">Driver Load (ID 6)</option>
            <option value="Service_Install">Service Install (ID 7045)</option>
            <option value="Current_State">Current State (DriverQuery)</option>
        </select>
    </div>

    <table id="timelineTable">
        <thead>
            <tr>
                <th>Event Time</th>
                <th>Event Type</th>
                <th>Service Name</th>
                <th>Image Path</th>
                <th>SHA256</th>
                <th>Signature</th>
                <th>State</th>
                <th>Source ID</th>
            </tr>
        </thead>
        <tbody>
"@

$htmlFooter = @"
        </tbody>
    </table>

    <script>
        function filterTable() {
            var input, filter, select, typeFilter, table, tr, td, i, txtValue;
            input = document.getElementById("filterName");
            filter = input.value.toUpperCase();
            select = document.getElementById("filterType");
            typeFilter = select.value;
            
            table = document.getElementById("timelineTable");
            tr = table.getElementsByTagName("tr");

            for (i = 1; i < tr.length; i++) {
                tr[i].style.display = ""; // Reset
                tdName = tr[i].getElementsByTagName("td")[2]; // Service Name
                tdType = tr[i].getElementsByTagName("td")[1]; // Event Type
                
                if (tdName && tdType) {
                    txtValue = tdName.textContent || tdName.innerText;
                    typeValue = tdType.textContent || tdType.innerText;
                    
                    var nameMatch = txtValue.toUpperCase().indexOf(filter) > -1;
                    var typeMatch = (typeFilter === "All") || (typeValue.replace(/\s/g, '_') === typeFilter); // Simple mapping
                    
                    // Adjusting for exact match logic based on HTML content
                    if (!nameMatch || !typeMatch) {
                        tr[i].style.display = "none";
                    }
                }       
            }
        }
    </script>
</body>
</html>
"@

# Generate Table Rows
$tableRows = ""
foreach ($row in $SortedTimeline) {
    $sigClass = ""
    if ($row.SignatureStatus -eq "Valid") { $sigClass = "status-valid" }
    elseif ($row.SignatureStatus -like "*Invalid*" -or $row.SignatureStatus -like "*Unsigned*") { $sigClass = "status-invalid" }
    
    $typeClass = ""
    if ($row.EventType -eq "Driver_Load") { $typeClass = "type-load" }
    elseif ($row.EventType -eq "Service_Install") { $typeClass = "type-install" }
    elseif ($row.EventType -eq "Current_State") { $typeClass = "type-state" }

    # Escape HTML special chars in paths
    $safePath = $row.ImagePath -replace '<', '&lt;' -replace '>', '&gt;'
    
    $tableRows += @"
        <tr class="$typeClass">
            <td>$($row.EventTime)</td>
            <td>$($row.EventType)</td>
            <td>$($row.ServiceName)</td>
            <td title="$safePath">$($row.ImagePath.Substring(0, [Math]::Min(50, $row.ImagePath.Length)))...</td>
            <td style="font-family:monospace; font-size:12px;">$($row.SHA256.Substring(0, [Math]::Min(16, $row.SHA256.Length)))...</td>
            <td class="$sigClass">$($row.SignatureStatus)</td>
            <td>$($row.DriverState)</td>
            <td>$($row.SourceEventId)</td>
        </tr>
"@
}

$htmlContent = $htmlHeader + $tableRows + $htmlFooter
$htmlContent | Out-File -FilePath $htmlPath -Encoding UTF8

Write-Host "[+] HTML Report saved to: $htmlPath" -ForegroundColor Green
Write-Host "[*] Done." -ForegroundColor Cyan
```

</details>

## 附件

- [📥 时间线数据（CSV）](/driver_timeline.csv)
- [🔎 交互式时间线（HTML，可筛选）](/driver_timeline.html)

## 技术细节

使用 PowerShell 脚本统一处理了：
路径标准化（%SystemRoot%、大小写）
时间格式统一
SHA256 哈希计算
签名状态验证
