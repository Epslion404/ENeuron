param(
    [string]$XsctPath = 'G:\Xilinx\Vitis\2024.1\bin\xsct.bat',
    [switch]$B3Dense,
    [switch]$B3FullOpen,
    [switch]$B3Bypass,
    [switch]$B3StaticMixed,
    [switch]$B3CalibratedStatic,
    [switch]$B3LiveEneuron,
    [switch]$B3EpochOverlap,
    [switch]$B3SpeedBenchmark,
    [switch]$B3AccuracyBenchmark,
    [int]$B3LiveMaskBatchK = 1,
    [string]$B3BenchmarkManifest = '',
    [string]$B3QatManifest = '',
    [int]$B3BenchmarkSampleCount = 0,
    [string]$HardwareBuildDir = '',
    [string]$BuildTag = 'direct'
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..\..')).Path
if ($BuildTag -notmatch '^[A-Za-z0-9._-]+$') { throw "Invalid BuildTag: $BuildTag" }
$HardwareBuildDir = if ([string]::IsNullOrWhiteSpace($HardwareBuildDir)) {
    Join-Path $repoRoot 'boards\hellozynq\b2_hw\build'
} else {
    (Resolve-Path -LiteralPath $HardwareBuildDir).Path
}

# 复用已验证的 BSP/链接布局，再单独编译 packet smoke 应用。
& (Join-Path $scriptRoot 'run_b2_sw_build.ps1') -XsctPath $XsctPath -HardwareBuildDir $HardwareBuildDir -BuildTag $BuildTag

$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
$gitStatus = @(& git -C $repoRoot status --porcelain --untracked-files=no)
$gitTrackedWorktreeClean = $gitStatus.Count -eq 0
$buildRoot = Join-Path $scriptRoot (Join-Path 'build' (Join-Path $gitHead $BuildTag))
$bspRoot = Join-Path $buildRoot 'bsp'
$appRoot = Join-Path $buildRoot 'app'
$outRoot = Join-Path $buildRoot 'out'
$bitstream = Join-Path $HardwareBuildDir 'hello_zynq_b2.bit'
$hardwareManifestPath = Join-Path $HardwareBuildDir 'build_manifest.json'
$hardwareManifest = Get-Content -LiteralPath $hardwareManifestPath -Raw | ConvertFrom-Json
$hardwareBuildManifestSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $hardwareManifestPath).Hash.ToLowerInvariant()
$hardwareGitHead = [string]$hardwareManifest.git_head
$hardwareGitWorktreeClean = [bool]$hardwareManifest.git_worktree_clean
$hardwareSignoffPass = [string]$hardwareManifest.signoff.B2_SIGNOFF_PASS -eq '1'
$xsa = Join-Path $buildRoot 'hello_zynq_b2.xsa'
$goldenManifestPath = if ([string]::IsNullOrWhiteSpace($B3QatManifest)) {
    Join-Path $repoRoot 'tools\repro\b3_fixed_vector_manifest.json'
} else {
    (Resolve-Path -LiteralPath $B3QatManifest).Path
}
$multiInputManifestDefault = Join-Path $repoRoot 'tools\repro\b3_multi_input_manifest.json'
$calibratedMaskPath = Join-Path $repoRoot 'tools\repro\b3_calibrated_2of4_mask.json'
$packetSourcePath = Join-Path $scriptRoot 'src\packet_main.c'
$makePath = 'G:\Xilinx\Vitis\2024.1\gnuwin\bin\make.exe'
$toolBin = 'G:\Xilinx\Vitis\2024.1\gnu\aarch32\nt\gcc-arm-none-eabi\bin'
$gccPath = Join-Path $toolBin 'arm-none-eabi-gcc.exe'

foreach ($path in @($bitstream, $xsa, $goldenManifestPath, $makePath, $gccPath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required file not found: $path" }
}
$golden = Get-Content -LiteralPath $goldenManifestPath -Raw | ConvertFrom-Json
$goldenIsQat = $golden.schema -eq 'eneuron_b3_qat_model_v1'
if ($goldenIsQat) {
    if ($golden.model.word_count -ne 634 -or @($golden.samples).Count -lt 1) {
        throw 'QAT manifest model/sample contract mismatch'
    }
    if (-not $B3Dense -and -not $B3SpeedBenchmark) {
        throw 'QAT manifest currently supports B3Dense only'
    }
} elseif ($golden.schema -ne 'eneuron_b3_fixed_vector_v1' -or
          $golden.target.part -ne 'xc7z020clg484-2' -or
          $golden.target.protocol -ne 'ENB2_PACKET_NPU_V1' -or
          $golden.model.word_count -ne 634) {
    throw 'B3 golden manifest target/schema/model contract mismatch'
}
$goldenSample = @($golden.samples)[0]
if ($null -eq $goldenSample -or @($goldenSample.input_beats).Count -ne 8) {
    throw 'B3 golden manifest must contain one sample with eight input beats'
}
$goldenDenseMaskWords = if ($goldenIsQat) {
    @((0..17 | ForEach-Object { '0xFFFFFFFF' }) + '0x0000FFFF')
} else {
    @($goldenSample.modes.b3_dense.mask_words_data)
}
if ($goldenDenseMaskWords.Count -ne 19) {
    throw 'B3 dense mask must contain 19 words'
}
$benchmarkManifestPath = $null
$benchmark = $null
$benchmarkSamples = @()
if ($B3SpeedBenchmark) {
    $benchmarkManifestPath = if ([string]::IsNullOrWhiteSpace($B3BenchmarkManifest) -and $goldenIsQat) {
        $goldenManifestPath
    } elseif ([string]::IsNullOrWhiteSpace($B3BenchmarkManifest)) {
        $multiInputManifestDefault
    } else {
        (Resolve-Path -LiteralPath $B3BenchmarkManifest).Path
    }
    if (-not (Test-Path -LiteralPath $benchmarkManifestPath)) {
        throw "B3 benchmark manifest not found: $benchmarkManifestPath"
    }
    $benchmark = Get-Content -LiteralPath $benchmarkManifestPath -Raw | ConvertFrom-Json
    if ($benchmark.schema -ne 'eneuron_b3_multi_input_v1' -and
        $benchmark.schema -ne 'eneuron_b3_qat_model_v1') {
        throw 'B3 speed benchmark requires multi-input or QAT manifest v1'
    }
    $allBenchmarkSamples = @($benchmark.samples)
    $requestedCount = if ($B3BenchmarkSampleCount -gt 0) { $B3BenchmarkSampleCount } else { $allBenchmarkSamples.Count }
    if ($requestedCount -lt 1 -or $requestedCount -gt $allBenchmarkSamples.Count) {
        throw "B3 benchmark sample count out of range: $requestedCount / $($allBenchmarkSamples.Count)"
    }
    $benchmarkSamples = @($allBenchmarkSamples | Select-Object -First $requestedCount)
    if ($benchmark.schema -eq 'eneuron_b3_qat_model_v1') {
        if (-not $goldenIsQat -or -not $B3Dense) {
            throw 'QAT benchmark requires matching QAT manifest and B3Dense mode'
        }
        $benchmarkUniqueInputCount = @($benchmarkSamples | ForEach-Object { [string]$_.input_sha256 } | Sort-Object -Unique).Count
        if ($benchmarkUniqueInputCount -ne $benchmarkSamples.Count) {
            throw 'QAT benchmark inputs must be unique'
        }
    } else {
        if ([int]$benchmark.unique_input_count -lt $benchmarkSamples.Count) {
            throw 'B3 benchmark manifest unique input count is too small'
        }
        $benchmarkUniqueInputCount = @($benchmarkSamples | ForEach-Object { [string]$_.input_sha256 } | Sort-Object -Unique).Count
        if ($benchmarkUniqueInputCount -ne $benchmarkSamples.Count) {
            throw 'B3 benchmark samples must be unique'
        }
    }
    if ($B3LiveEneuron -and $B3LiveMaskBatchK -ne 1) {
        throw 'multi-input live benchmark requires B3_LIVE_MASK_BATCH_K=1'
    }
    if ($B3StaticMixed) {
        throw 'static mixed mode is not supported by the multi-input benchmark manifest'
    }
    if ($B3CalibratedStatic) {
        foreach ($sample in $benchmarkSamples) {
            if ($null -eq $sample.calibrated_static_logits) {
                throw 'calibrated static benchmark requires calibrated_static_logits per sample'
            }
        }
    }
} else {
    $benchmarkSamples = @([pscustomobject]@{
        sample_id = Convert-ManifestUInt32 $goldenSample.sample_id
        input_crc = if ($goldenIsQat) { Convert-ManifestUInt32 $goldenSample.input_crc } else { 0 }
        input_beats = @($goldenSample.input_beats)
        dense_logits = if ($goldenIsQat) { @($goldenSample.dense_logits) } else { @($goldenSample.modes.b3_dense.expected_logits) }
        live_logits = if ($goldenIsQat) { @($goldenSample.dense_logits) } else { @($goldenSample.modes.b3_live_eneuron.expected_logits) }
    })
    $benchmarkUniqueInputCount = 1
}
if ($B3AccuracyBenchmark -and -not $B3SpeedBenchmark) {
    throw 'B3AccuracyBenchmark requires B3SpeedBenchmark'
}
$xparameters = Get-ChildItem -LiteralPath $bspRoot -Filter 'xparameters.h' -Recurse -File | Select-Object -First 1
$libxil = Get-ChildItem -LiteralPath $bspRoot -Filter 'libxil.a' -Recurse -File | Select-Object -First 1
$linkerScript = Get-ChildItem -LiteralPath $appRoot -Filter 'lscript.ld' -Recurse -File | Select-Object -First 1
$xilinxSpec = Get-ChildItem -LiteralPath $appRoot -Filter 'Xilinx.spec' -Recurse -File | Select-Object -First 1
if (-not $xparameters -or -not $libxil -or -not $linkerScript -or -not $xilinxSpec) {
    throw 'Generated BSP library, headers, linker script, or Xilinx.spec were not found'
}

$includeDir = Split-Path -Parent $xparameters.FullName
$libDir = Split-Path -Parent $libxil.FullName
$modeCount = @($B3Dense, $B3FullOpen, $B3Bypass, $B3StaticMixed, $B3CalibratedStatic, $B3LiveEneuron, $B3EpochOverlap | Where-Object { $_ }).Count
if ($modeCount -gt 1) { throw 'B3 mode switches are mutually exclusive' }
if ($B3SpeedBenchmark -and $modeCount -eq 0) { throw 'B3SpeedBenchmark requires an explicit B3 mode' }
if ($B3LiveMaskBatchK -notin @(1, 16, 32, 64)) { throw 'B3LiveMaskBatchK must be one of 1, 16, 32, 64' }
$applicationMode = if ($B3Bypass) { 'b3_bypass' } elseif ($B3StaticMixed) { 'b3_static_mixed' } elseif ($B3CalibratedStatic) { 'b3_calibrated_static' } elseif ($B3LiveEneuron) { 'b3_live_eneuron' } elseif ($B3EpochOverlap) { 'b3_epoch_overlap' } elseif ($B3FullOpen) { 'b3_full_open' } elseif ($B3Dense) { 'b3_dense' } else { 'b2_packet_smoke' }
$elfStem = "b2_packet_$applicationMode"
$modeSpec = $null
if ($applicationMode -like 'b3_*') {
    if ($goldenIsQat) {
        if ($applicationMode -ne 'b3_dense') {
            throw 'QAT manifest currently supports B3Dense mode only'
        }
        $expectedLogits = @($goldenSample.dense_logits)
        $maskWords = 19
        $inputPattern = 'QAT manifest uint4 pixels, packed low-nibble-first'
        $maskPattern = 'full-open group_4way mask from QAT adapter'
    } else {
        $goldenModeName = if ($applicationMode -eq 'b3_epoch_overlap' -or $applicationMode -eq 'b3_calibrated_static') { 'b3_dense' } else { $applicationMode }
        $modeSpec = $goldenSample.modes.PSObject.Properties[$goldenModeName].Value
        if ($null -eq $modeSpec) { throw "B3 golden manifest has no mode: $goldenModeName" }
        $expectedLogits = @($modeSpec.expected_logits)
        $maskWords = [int]$modeSpec.mask_words
        $inputPattern = [string]$goldenSample.input_pattern
        if ([string]::IsNullOrWhiteSpace($inputPattern)) { throw 'B3 golden manifest sample input_pattern is missing' }
        $maskPattern = if ($applicationMode -eq 'b3_bypass') {
            'reset default full-open; no mask commands'
        } elseif ($applicationMode -eq 'b3_static_mixed') {
            '0x33333333 repeated; group_4way mixed mask, strict_2of4_candidate=false'
        } elseif ($applicationMode -eq 'b3_live_eneuron') {
            'Host live ENeuron S2 group_4way; computed on PS, not frozen mixed replay'
        } elseif ($applicationMode -eq 'b3_calibrated_static') {
            'calibrated group_4way mask from majority-vote calibration set; fixed for all held-out samples'
        } elseif ($applicationMode -eq 'b3_epoch_overlap') {
            'MASK_COMMIT then hold for JTAG 0x54/0x58 before first sample'
        } else {
            'full-open group_4way mask'
        }
    }
} else {
    $expectedLogits = @()
    $inputPattern = 'all-zero repeated 8 beats'
    $maskPattern = 'full-open group_4way mask'
    $maskWords = 19
}
$compileDefines = @()
if ($B3Dense) { $compileDefines += '-DB3_DENSE' }
if ($B3FullOpen) { $compileDefines += '-DB3_FULL_OPEN' }
if ($B3Bypass) { $compileDefines += '-DB3_BYPASS' }
if ($B3StaticMixed) { $compileDefines += '-DB3_STATIC_MIXED' }
if ($B3CalibratedStatic) { $compileDefines += '-DB3_CALIBRATED_STATIC' }
if ($B3LiveEneuron) { $compileDefines += '-DB3_LIVE_ENEURON' }
if ($B3EpochOverlap) { $compileDefines += '-DB3_EPOCH_OVERLAP' }
if ($B3SpeedBenchmark) { $compileDefines += '-DB3_SPEED_BENCHMARK' }
if ($B3AccuracyBenchmark) { $compileDefines += '-DB3_ACCURACY_BENCHMARK' }
$compileDefines += "-DB3_LIVE_MASK_BATCH_K=$B3LiveMaskBatchK"
$objectPath = Join-Path $outRoot "packet_main_$applicationMode.o"
$elfPath = Join-Path $outRoot "$elfStem.elf"
$generatedHeader = Join-Path $outRoot 'b3_fixed_vector_generated.h'
$commonFlags = @('-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard')
$env:PATH = "$toolBin;$(Split-Path -Parent $makePath);$env:PATH"
$env:RDI_PLATFORM = 'win64'

# 从黄金 manifest 生成板端只读头文件，避免 C 源码维护第二套模型/样本/mask 常量。
$goldenManifestSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $goldenManifestPath).Hash.ToLowerInvariant()
function Convert-ManifestUInt32 {
    param([Parameter(Mandatory = $true)][object]$Value)
    $text = [string]$Value
    if ($text -match '^0x') { return [Convert]::ToUInt32($text.Substring(2), 16) }
    return [uint32]$Value
}
$headerLines = @(
    '#ifndef B3_FIXED_VECTOR_GENERATED_H',
    '#define B3_FIXED_VECTOR_GENERATED_H',
    ('#define B3_MANIFEST_SCHEMA_SHA256 "{0}"' -f $goldenManifestSha256),
    "#define B3_MODEL_WORD_COUNT $([int]$golden.model.word_count)U",
    "#define B3_MASK_WORD_COUNT $([int]$maskWords)U",
    'static inline u32 b3_model_word_for_index(u32 index) {',
    '    switch (index) {'
)
foreach ($entry in $golden.model.nonzero_words.PSObject.Properties) {
    $value = [Convert]::ToUInt64(([string]$entry.Value).Replace('0x', ''), 16)
    $headerLines += ('        case {0}U: return 0x{1:X8}U;' -f [int]$entry.Name, $value)
}
$headerLines += @(
    '        default: return 0U;',
    '    }',
    '}',
    ('#define B3_BENCHMARK_SAMPLE_COUNT {0}U' -f $benchmarkSamples.Count),
    ('#define B3_BENCHMARK_UNIQUE_INPUT_COUNT {0}U' -f $(if ($B3SpeedBenchmark) { [int]$benchmarkUniqueInputCount } else { 1 })),
    'static const u32 B3_SAMPLE_IDS[B3_BENCHMARK_SAMPLE_COUNT] = {',
    ('    ' + (($benchmarkSamples | ForEach-Object { '{0}U' -f (Convert-ManifestUInt32 $_.sample_id) }) -join ', ') + ','),
    '};',
    'static const u32 B3_SAMPLE_INPUT_CRC[B3_BENCHMARK_SAMPLE_COUNT] = {',
    ('    ' + (($benchmarkSamples | ForEach-Object { '{0}U' -f (Convert-ManifestUInt32 $_.input_crc) }) -join ', ') + ','),
    '};',
    'static const u32 B3_SAMPLE_INPUT_BEATS[B3_BENCHMARK_SAMPLE_COUNT][8] = {',
    (($benchmarkSamples | ForEach-Object { '    { ' + (($_.input_beats | ForEach-Object { '{0}U' -f (Convert-ManifestUInt32 $_) }) -join ', ') + ' },' }) -join "`n"),
    '};'
)
if ($goldenIsQat) {
    $headerLines += ('static const s32 B3_DENSE_LOGITS[10] = {{ {0} }};' -f (($goldenSample.dense_logits | ForEach-Object { '{0}' -f [int]$_ }) -join ', '))
    $headerLines += ('static const u32 B3_FULL_OPEN_MASK_WORDS[19] = {{ {0} }};' -f (($goldenDenseMaskWords | ForEach-Object { '{0}U' -f (Convert-ManifestUInt32 $_) }) -join ', '))
} else {
    foreach ($modeName in @('b3_dense', 'b3_static_mixed', 'b3_live_eneuron', 'b3_bypass')) {
        $mode = $goldenSample.modes.PSObject.Properties[$modeName].Value
        $logitName = if ($modeName -eq 'b3_static_mixed') { 'B3_STATIC_MIXED_LOGITS' } elseif ($modeName -eq 'b3_live_eneuron') { 'B3_LIVE_ENEURON_LOGITS' } else { 'B3_DENSE_LOGITS' }
        if ($modeName -ne 'b3_bypass') {
            $headerLines += ('static const s32 {0}[10] = {{ {1} }};' -f $logitName, (($mode.expected_logits | ForEach-Object { '{0}' -f $_ }) -join ', '))
        }
    }
    foreach ($modeName in @('b3_dense', 'b3_static_mixed')) {
        $mode = $goldenSample.modes.PSObject.Properties[$modeName].Value
        $arrayName = if ($modeName -eq 'b3_static_mixed') { 'B3_STATIC_MIXED_MASK_WORDS' } else { 'B3_FULL_OPEN_MASK_WORDS' }
        $headerLines += ('static const u32 {0}[19] = {{ {1} }};' -f $arrayName, (($mode.mask_words_data | ForEach-Object { '{0}U' -f (Convert-ManifestUInt32 $_) }) -join ', '))
    }
}
$headerLines += 'static const s32 B3_DENSE_EXPECTED_LOGITS[B3_BENCHMARK_SAMPLE_COUNT][10] = {'
$headerLines += (($benchmarkSamples | ForEach-Object { '    { ' + (($_.dense_logits | ForEach-Object { '{0}' -f [int]$_ }) -join ', ') + ' },' }) -join "`n")
$headerLines += '};'
$headerLines += 'static const s32 B3_LIVE_EXPECTED_LOGITS[B3_BENCHMARK_SAMPLE_COUNT][10] = {'
$headerLines += (($benchmarkSamples | ForEach-Object {
        $logits = if ($goldenIsQat -or $null -eq $_.live_logits) { $_.dense_logits } else { $_.live_logits }
        '    { ' + (($logits | ForEach-Object { '{0}' -f [int]$_ }) -join ', ') + ' },'
    }) -join "`n")
$headerLines += '};'
$headerLines += 'static const s32 B3_STATIC_EXPECTED_LOGITS[B3_BENCHMARK_SAMPLE_COUNT][10] = {'
$headerLines += (($benchmarkSamples | ForEach-Object { '    { ' + (($_.dense_logits | ForEach-Object { '{0}' -f [int]$_ }) -join ', ') + ' },' }) -join "`n")
$headerLines += '};'
if ($B3CalibratedStatic) {
    $headerLines += 'static const s32 B3_CALIBRATED_STATIC_EXPECTED_LOGITS[B3_BENCHMARK_SAMPLE_COUNT][10] = {'
    $headerLines += (($benchmarkSamples | ForEach-Object { '    { ' + (($_.calibrated_static_logits | ForEach-Object { '{0}' -f [int]$_ }) -join ', ') + ' },' }) -join "`n")
    $headerLines += '};'
}
if ($B3CalibratedStatic) {
    if (-not (Test-Path -LiteralPath $calibratedMaskPath)) {
        throw "Calibrated mask manifest not found: $calibratedMaskPath"
    }
    $calibratedMask = Get-Content -LiteralPath $calibratedMaskPath -Raw | ConvertFrom-Json
    if ($calibratedMask.schema -ne 'eneuron_b3_calibrated_group4way_v1' -or
        @($calibratedMask.mask_words).Count -ne 19) {
        throw 'Calibrated mask manifest schema/mask_word count mismatch'
    }
    $headerLines += ('static const u32 B3_CALIBRATED_STATIC_MASK_WORDS[19] = {{ {0} }};' -f (($calibratedMask.mask_words | ForEach-Object { '{0}U' -f (Convert-ManifestUInt32 $_) }) -join ', '))
}
$headerLines += '#endif'
$headerLines | Set-Content -LiteralPath $generatedHeader -Encoding ascii

& $gccPath @commonFlags @compileDefines '-O2' '-g' '-Wall' '-Wextra' '-fno-tree-loop-distribute-patterns' `
    '-I' $includeDir '-I' $outRoot '-c' $packetSourcePath '-o' $objectPath
if ($LASTEXITCODE -ne 0) { throw "Packet application compile failed with exit code $LASTEXITCODE" }
& $gccPath @commonFlags "-specs=$($xilinxSpec.FullName)" "-Wl,-T,$($linkerScript.FullName)" "-L$libDir" `
    '-o' $elfPath $objectPath '-Wl,--start-group' '-lxil' '-lgcc' '-lc' '-Wl,--end-group'
if ($LASTEXITCODE -ne 0) { throw "Packet application link failed with exit code $LASTEXITCODE" }

$manifest = [ordered]@{
    schema_version = 2
    generated_at = [DateTime]::UtcNow.ToString('o')
    git_head = $gitHead
    git_tracked_worktree_clean = $gitTrackedWorktreeClean
    packet_source_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $packetSourcePath).Hash.ToLowerInvariant()
    tool = 'XSCT/Vitis 2024.1'
    hardware_build_dir = $HardwareBuildDir
    hardware_build_manifest = $hardwareManifestPath
    hardware_build_manifest_sha256 = $hardwareBuildManifestSha256
    hardware_git_head = $hardwareGitHead
    hardware_git_worktree_clean = $hardwareGitWorktreeClean
    hardware_signoff_pass = $hardwareSignoffPass
    hardware_npu_mode = [string]$hardwareManifest.npu_mode
    bitstream = $bitstream
    xsa = $xsa
    bitstream_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $bitstream).Hash.ToLowerInvariant()
    xsa_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $xsa).Hash.ToLowerInvariant()
    elf = $elfPath
    elf_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $elfPath).Hash.ToLowerInvariant()
    application = $elfStem
    application_mode = $applicationMode
    protocol = 'ENB2_PACKET_NPU_V1'
    golden_manifest = $goldenManifestPath
    benchmark_manifest = $benchmarkManifestPath
    benchmark_manifest_sha256 = if ($benchmarkManifestPath) { (Get-FileHash -Algorithm SHA256 -LiteralPath $benchmarkManifestPath).Hash.ToLowerInvariant() } else { $null }
    input_pattern = $inputPattern
    mask_pattern = $maskPattern
    mask_words = $maskWords
    mask_submit_path = 'pl_staging_command_batch_v1'
    expected_logits = $expectedLogits
    speed_benchmark = [bool]$B3SpeedBenchmark
    accuracy_benchmark = [bool]$B3AccuracyBenchmark
    speed_benchmark_samples = if ($B3SpeedBenchmark) { $benchmarkSamples.Count } else { 0 }
    benchmark_unique_input_count = if ($B3SpeedBenchmark) { [int]$benchmarkUniqueInputCount } else { 1 }
    live_mask_batch_k = $B3LiveMaskBatchK
    live_mask_update_count = if ($B3SpeedBenchmark -and $B3LiveEneuron) { [int][Math]::Ceiling($benchmarkSamples.Count / [double]$B3LiveMaskBatchK) } else { 0 }
}
$manifestPath = Join-Path $buildRoot 'packet_build_manifest.json'
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding utf8
Write-Output 'B2_PACKET_SW_BUILD_PASS'
Write-Output "B2_PACKET_APPLICATION_MODE=$applicationMode"
Write-Output "B2_PACKET_ELF=$elfPath"
Write-Output "B2_PACKET_SW_BUILD_MANIFEST=$manifestPath"
