param(
    [string]$ChunkDirectory = '.\artifacts\results\b3_accuracy_chunks_20260914_1024',
    [int]$StartChunk = 0,
    [int]$EndChunk = 15,
    [string]$Runner = '.\boards\hellozynq\b2_sw\run_b3_speed_benchmark.ps1',
    [switch]$AllowDirty
)

$ErrorActionPreference = 'Stop'
$chunkRoot = (Resolve-Path -LiteralPath $ChunkDirectory).Path
$runnerPath = (Resolve-Path -LiteralPath $Runner).Path
if ($StartChunk -lt 0 -or $EndChunk -lt $StartChunk) {
    throw 'invalid chunk range'
}

$records = @()
for ($chunk = $StartChunk; $chunk -le $EndChunk; ++$chunk) {
    $manifest = Join-Path $chunkRoot ('b3_accuracy_chunk_{0:D2}.json' -f $chunk)
    if (-not (Test-Path -LiteralPath $manifest)) {
        throw "missing chunk manifest: $manifest"
    }
    Write-Host ("B3_ACCURACY_SWEEP_CHUNK={0:D2} DENSE_BEGIN" -f $chunk)
    $denseParams = @{ Mode = 'dense'; Samples = 64; BenchmarkManifest = $manifest; CaptureLogits = $true }
    if ($AllowDirty) { $denseParams.AllowDirty = $true }
    $denseOutput = @(& $runnerPath @denseParams 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "dense run failed for chunk $chunk`n$($denseOutput -join "`n")"
    }
    $denseLine = $denseOutput | ForEach-Object { [string]$_ } | Where-Object { $_ -match '^B3_SPEED_BENCHMARK_SUMMARY=' } | Select-Object -Last 1
    if (-not $denseLine) { throw "dense summary marker missing for chunk $chunk" }
    $denseSummary = $denseLine -replace '^B3_SPEED_BENCHMARK_SUMMARY=', ''

    Write-Host ("B3_ACCURACY_SWEEP_CHUNK={0:D2} LIVE_BEGIN" -f $chunk)
    $liveParams = @{ Mode = 'live_eneuron'; Samples = 64; LiveMaskBatchK = 1; BenchmarkManifest = $manifest; CaptureLogits = $true }
    if ($AllowDirty) { $liveParams.AllowDirty = $true }
    $liveOutput = @(& $runnerPath @liveParams 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "live run failed for chunk $chunk`n$($liveOutput -join "`n")"
    }
    $liveLine = $liveOutput | ForEach-Object { [string]$_ } | Where-Object { $_ -match '^B3_SPEED_BENCHMARK_SUMMARY=' } | Select-Object -Last 1
    if (-not $liveLine) { throw "live summary marker missing for chunk $chunk" }
    $liveSummary = $liveLine -replace '^B3_SPEED_BENCHMARK_SUMMARY=', ''

    $records += [ordered]@{
        chunk = $chunk
        manifest = $manifest
        dense_summary = $denseSummary
        live_summary = $liveSummary
    }
    Write-Host ("B3_ACCURACY_SWEEP_CHUNK={0:D2} PASS" -f $chunk)
}

$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$output = Join-Path $chunkRoot ("b3_accuracy_sweep_runs_$stamp.json")
[ordered]@{
    schema = 'eneuron_b3_accuracy_sweep_v1'
    chunk_directory = $chunkRoot
    start_chunk = $StartChunk
    end_chunk = $EndChunk
    records = $records
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $output -Encoding utf8
Write-Host "B3_ACCURACY_SWEEP_MANIFEST=$output"
