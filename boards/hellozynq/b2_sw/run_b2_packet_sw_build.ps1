param(
    [string]$XsctPath = 'G:\Xilinx\Vitis\2024.1\bin\xsct.bat',
    [switch]$B3Dense,
    [switch]$B3FullOpen,
    [switch]$B3Bypass,
    [switch]$B3StaticMixed,
    [switch]$B3LiveEneuron,
    [switch]$B3EpochOverlap
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..\..')).Path

# 复用已验证的 BSP/链接布局，再单独编译 packet smoke 应用。
& (Join-Path $scriptRoot 'run_b2_sw_build.ps1') -XsctPath $XsctPath

$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
$buildRoot = Join-Path $scriptRoot (Join-Path 'build' (Join-Path $gitHead 'direct'))
$bspRoot = Join-Path $buildRoot 'bsp'
$appRoot = Join-Path $buildRoot 'app'
$outRoot = Join-Path $buildRoot 'out'
$bitstream = Join-Path $repoRoot 'boards\hellozynq\b2_hw\build\hello_zynq_b2.bit'
$xsa = Join-Path $buildRoot 'hello_zynq_b2.xsa'
$goldenManifestPath = Join-Path $repoRoot 'tools\repro\b3_fixed_vector_manifest.json'
$makePath = 'G:\Xilinx\Vitis\2024.1\gnuwin\bin\make.exe'
$toolBin = 'G:\Xilinx\Vitis\2024.1\gnu\aarch32\nt\gcc-arm-none-eabi\bin'
$gccPath = Join-Path $toolBin 'arm-none-eabi-gcc.exe'

foreach ($path in @($bitstream, $xsa, $goldenManifestPath, $makePath, $gccPath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required file not found: $path" }
}
$golden = Get-Content -LiteralPath $goldenManifestPath -Raw | ConvertFrom-Json
if ($golden.schema -ne 'eneuron_b3_fixed_vector_v1' -or
    $golden.target.part -ne 'xc7z020clg484-2' -or
    $golden.target.protocol -ne 'ENB2_PACKET_NPU_V1' -or
    $golden.model.word_count -ne 634) {
    throw 'B3 golden manifest target/schema/model contract mismatch'
}
$goldenSample = @($golden.samples)[0]
if ($null -eq $goldenSample -or @($goldenSample.input_beats).Count -ne 8) {
    throw 'B3 golden manifest must contain one sample with eight input beats'
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
$modeCount = @($B3Dense, $B3FullOpen, $B3Bypass, $B3StaticMixed, $B3LiveEneuron, $B3EpochOverlap | Where-Object { $_ }).Count
if ($modeCount -gt 1) { throw 'B3 mode switches are mutually exclusive' }
$applicationMode = if ($B3Bypass) { 'b3_bypass' } elseif ($B3StaticMixed) { 'b3_static_mixed' } elseif ($B3LiveEneuron) { 'b3_live_eneuron' } elseif ($B3EpochOverlap) { 'b3_epoch_overlap' } elseif ($B3FullOpen) { 'b3_full_open' } elseif ($B3Dense) { 'b3_dense' } else { 'b2_packet_smoke' }
$elfStem = "b2_packet_$applicationMode"
$modeSpec = $null
if ($applicationMode -like 'b3_*') {
    $goldenModeName = if ($applicationMode -eq 'b3_epoch_overlap') { 'b3_dense' } else { $applicationMode }
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
    } elseif ($applicationMode -eq 'b3_epoch_overlap') {
        'MASK_COMMIT then hold for JTAG 0x54/0x58 before first sample'
    } else {
        'full-open group_4way mask'
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
if ($B3LiveEneuron) { $compileDefines += '-DB3_LIVE_ENEURON' }
if ($B3EpochOverlap) { $compileDefines += '-DB3_EPOCH_OVERLAP' }
$objectPath = Join-Path $outRoot "packet_main_$applicationMode.o"
$elfPath = Join-Path $outRoot "$elfStem.elf"
$generatedHeader = Join-Path $outRoot 'b3_fixed_vector_generated.h'
$commonFlags = @('-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard')
$env:PATH = "$toolBin;$(Split-Path -Parent $makePath);$env:PATH"
$env:RDI_PLATFORM = 'win64'

# 从黄金 manifest 生成板端只读头文件，避免 C 源码维护第二套模型/样本/mask 常量。
$goldenManifestSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $goldenManifestPath).Hash.ToLowerInvariant()
$headerLines = @(
    '#ifndef B3_FIXED_VECTOR_GENERATED_H',
    '#define B3_FIXED_VECTOR_GENERATED_H',
    ('#define B3_MANIFEST_SCHEMA_SHA256 "{0}"' -f $goldenManifestSha256),
    "#define B3_MODEL_WORD_COUNT $([int]$golden.model.word_count)U",
    "#define B3_MASK_WORD_COUNT $([int]$goldenSample.modes.b3_dense.mask_words)U",
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
    'static const u32 B3_SAMPLE_INPUT_BEATS[8] = {',
    ('    ' + (($goldenSample.input_beats | ForEach-Object { '{0}U' -f $_ }) -join ', ') + ','),
    '};'
)
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
    $headerLines += ('static const u32 {0}[19] = {{ {1} }};' -f $arrayName, (($mode.mask_words_data | ForEach-Object { '{0}U' -f $_ }) -join ', '))
}
$headerLines += '#endif'
$headerLines | Set-Content -LiteralPath $generatedHeader -Encoding ascii

& $gccPath @commonFlags @compileDefines '-O2' '-g' '-Wall' '-Wextra' '-fno-tree-loop-distribute-patterns' `
    '-I' $includeDir '-I' $outRoot '-c' (Join-Path $scriptRoot 'src\packet_main.c') '-o' $objectPath
if ($LASTEXITCODE -ne 0) { throw "Packet application compile failed with exit code $LASTEXITCODE" }
& $gccPath @commonFlags "-specs=$($xilinxSpec.FullName)" "-Wl,-T,$($linkerScript.FullName)" "-L$libDir" `
    '-o' $elfPath $objectPath '-Wl,--start-group' '-lxil' '-lgcc' '-lc' '-Wl,--end-group'
if ($LASTEXITCODE -ne 0) { throw "Packet application link failed with exit code $LASTEXITCODE" }

$manifest = [ordered]@{
    schema_version = 1
    generated_at = [DateTime]::UtcNow.ToString('o')
    git_head = $gitHead
    tool = 'XSCT/Vitis 2024.1'
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
    input_pattern = $inputPattern
    mask_pattern = $maskPattern
    mask_words = $maskWords
    expected_logits = $expectedLogits
}
$manifestPath = Join-Path $buildRoot 'packet_build_manifest.json'
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding utf8
Write-Output 'B2_PACKET_SW_BUILD_PASS'
Write-Output "B2_PACKET_APPLICATION_MODE=$applicationMode"
Write-Output "B2_PACKET_ELF=$elfPath"
Write-Output "B2_PACKET_SW_BUILD_MANIFEST=$manifestPath"
