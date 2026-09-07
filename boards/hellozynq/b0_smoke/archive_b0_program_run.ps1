param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$RunLabel
)

$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir '..\..\..')).Path
$buildDir = Join-Path $scriptDir 'build'
$bitstreamPath = Join-Path $buildDir 'hello_zynq_b0_smoke.bit'
$buildManifestPath = Join-Path $buildDir 'build_manifest.json'
$programResultPath = Join-Path $buildDir 'program_result.txt'
$programLogPath = Join-Path $buildDir 'program_run.log'
$evidenceRoot = Join-Path $repoRoot 'artifacts\logs\hellozynq_b0'
$runDir = Join-Path $evidenceRoot $RunLabel

$requiredPaths = @(
    $bitstreamPath,
    $buildManifestPath,
    $programResultPath,
    $programLogPath
)
foreach ($path in $requiredPaths) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing B0 program evidence input: $path"
    }
}
if (Test-Path -LiteralPath $runDir) {
    throw "B0 evidence run already exists and will not be overwritten: $runDir"
}

$buildManifest = Get-Content -Raw -LiteralPath $buildManifestPath | ConvertFrom-Json
$bitstreamSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $bitstreamPath).Hash.ToLowerInvariant()
if ($bitstreamSha256 -ne $buildManifest.bitstream_sha256) {
    throw "Bitstream hash mismatch: expected $($buildManifest.bitstream_sha256), got $bitstreamSha256"
}
if (-not (Select-String -LiteralPath $programResultPath -SimpleMatch 'B0_PROGRAM_COMMAND=PASS' -Quiet)) {
    throw 'Program result does not contain B0_PROGRAM_COMMAND=PASS'
}
if (-not (Select-String -LiteralPath $programLogPath -SimpleMatch 'B0_PROGRAM_PASS' -Quiet)) {
    throw 'Program log does not contain B0_PROGRAM_PASS'
}

$archiveGitStatus = (& git -C $repoRoot status --porcelain=v1) -join "`n"
New-Item -ItemType Directory -Path $runDir | Out-Null
$archivedResultPath = Join-Path $runDir 'program_result.txt'
$archivedLogPath = Join-Path $runDir 'program_run.txt'
$archivedBuildManifestPath = Join-Path $runDir 'build_manifest.json'
Copy-Item -LiteralPath $programResultPath -Destination $archivedResultPath
Copy-Item -LiteralPath $programLogPath -Destination $archivedLogPath
Copy-Item -LiteralPath $buildManifestPath -Destination $archivedBuildManifestPath

$archiveManifest = [ordered]@{
    schema_version = 1
    run_label = $RunLabel
    archived_at_utc = [DateTime]::UtcNow.ToString('o')
    archive_git_head = (& git -C $repoRoot rev-parse HEAD).Trim()
    archive_worktree_clean = [string]::IsNullOrWhiteSpace($archiveGitStatus)
    archive_script_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $PSCommandPath).Hash.ToLowerInvariant()
    build_git_head = $buildManifest.git_head
    bitstream_sha256 = $bitstreamSha256
    program_result_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivedResultPath).Hash.ToLowerInvariant()
    program_log_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivedLogPath).Hash.ToLowerInvariant()
    build_manifest_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivedBuildManifestPath).Hash.ToLowerInvariant()
    observation_status = 'PENDING'
}
$archiveManifestPath = Join-Path $runDir 'archive_manifest.json'
$archiveManifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $archiveManifestPath -Encoding UTF8

Write-Host "B0_PROGRAM_ARCHIVE_PASS run_dir=$runDir"
Write-Host "B0_PROGRAM_ARCHIVE_BITSTREAM_SHA256=$bitstreamSha256"
