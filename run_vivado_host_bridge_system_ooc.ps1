$ErrorActionPreference = 'Stop'

# 通过官方 loader 启动 Vivado，确保 DLL、Java 和器件数据库环境完整。
$vivado = 'G:\Xilinx\Vivado\2024.1\bin\vivado.bat'
$root = $PSScriptRoot
$reportDirectory = Join-Path $root 'vivado_host_bridge_reports'
$tcl = Join-Path $root 'vivado_host_bridge_system_ooc.tcl'
$log = Join-Path $reportDirectory 'vivado_run.log'
$rtlFiles = @(
    'digital_lif_engine.sv',
    'digital_snn_tile_4x2x2.sv',
    'digital_snn_host_bridge_controller.sv',
    'digital_snn_host_bridge.sv',
    'digital_snn_host_bridge_system.sv'
) | ForEach-Object { Join-Path $root $_ }
$requiredReports = @(
    'timing_summary_impl.rpt',
    'clock_interaction_impl.rpt',
    'cdc_impl.rpt',
    'cdc_classification.txt',
    'route_status_impl.rpt',
    'drc_impl.rpt',
    'methodology_impl.rpt',
    'utilization_hierarchical_impl.rpt',
    'power_impl.rpt',
    'signoff_summary.txt'
)

if (-not (Test-Path -LiteralPath $vivado -PathType Leaf)) {
    throw "Vivado loader 不存在：$vivado"
}
if (-not (Test-Path -LiteralPath $tcl -PathType Leaf)) {
    throw "Vivado Tcl 不存在：$tcl"
}
foreach ($rtl in $rtlFiles) {
    if (-not (Test-Path -LiteralPath $rtl -PathType Leaf)) {
        throw "RTL 文件不存在：$rtl"
    }
}

# 只允许清理由本任务拥有的固定报告目录，避免旧报告通过时间戳签核。
$resolvedRoot = [IO.Path]::GetFullPath($root).TrimEnd([IO.Path]::DirectorySeparatorChar)
$resolvedReportDirectory = [IO.Path]::GetFullPath($reportDirectory)
$expectedPrefix = $resolvedRoot + [IO.Path]::DirectorySeparatorChar
if (-not $resolvedReportDirectory.StartsWith($expectedPrefix, [StringComparison]::OrdinalIgnoreCase) -or
    [IO.Path]::GetFileName($resolvedReportDirectory) -ne 'vivado_host_bridge_reports') {
    throw "拒绝清理非预期报告目录：$resolvedReportDirectory"
}
if (Test-Path -LiteralPath $resolvedReportDirectory) {
    Remove-Item -LiteralPath $resolvedReportDirectory -Recurse -Force
}
New-Item -ItemType Directory -Path $resolvedReportDirectory | Out-Null

$newestRtlTimestamp = ($rtlFiles | Get-Item | Measure-Object -Property LastWriteTimeUtc -Maximum).Maximum
Write-Host 'ENeuron Host Bridge System: 启动 Vivado 2024.1 OOC 实现'
Write-Host "RTL 最新时间：$($newestRtlTimestamp.ToString('o'))"

$commandLine = '"' + $vivado + '" -mode batch -nolog -nojournal -notrace -source "' + $tcl + '"'
Push-Location $root
try {
    & $env:ComSpec /d /s /c $commandLine 2>&1 | Tee-Object -FilePath $log
    $vivadoExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($vivadoExitCode -ne 0) {
    throw "Vivado OOC 实现失败，退出码：$vivadoExitCode"
}

$missingReports = @()
$staleReports = @()
foreach ($reportName in $requiredReports) {
    $reportPath = Join-Path $resolvedReportDirectory $reportName
    if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) {
        $missingReports += $reportPath
        continue
    }
    if ((Get-Item -LiteralPath $reportPath).LastWriteTimeUtc -le $newestRtlTimestamp) {
        $staleReports += $reportPath
    }
}
if ($missingReports.Count -ne 0) {
    throw "缺少签核报告：$($missingReports -join ', ')"
}
if ($staleReports.Count -ne 0) {
    throw "报告时间戳不晚于相关 RTL：$($staleReports -join ', ')"
}

$summaryPath = Join-Path $resolvedReportDirectory 'signoff_summary.txt'
$summary = Get-Content -LiteralPath $summaryPath -Raw
if ($summary -notmatch '(?m)^RESULT=PASS\r?$') {
    throw "签核摘要未给出 RESULT=PASS：$summaryPath"
}

Write-Host 'ENeuron Host Bridge System: OOC 实现与硬门槛全部通过'
Get-Content -LiteralPath $summaryPath
