param(
    [string]$XsctPath = 'G:\Xilinx\Vitis\2024.1\bin\xsct.bat'
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..\..')).Path
$xsaSource = Join-Path $repoRoot 'boards\hellozynq\b1a_hw\build\hello_zynq_b1a.xsa'
$bitstreamSource = Join-Path $repoRoot 'boards\hellozynq\b1a_hw\build\hello_zynq_b1a.bit'
$b1aManifestPath = Join-Path $repoRoot 'boards\hellozynq\b1a_hw\build\build_manifest.json'
$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
$gitWorktreeClean = -not [bool](& git -C $repoRoot status --porcelain --untracked-files=all)
$buildRoot = Join-Path $scriptRoot (Join-Path 'build' (Join-Path $gitHead 'high_diag'))
$bspRoot = Join-Path $buildRoot 'bsp'
$appRoot = Join-Path $buildRoot 'app'
$outRoot = Join-Path $buildRoot 'out'
$xsaCopy = Join-Path $buildRoot 'hello_zynq_b1a.xsa'
$makePath = 'G:\Xilinx\Vitis\2024.1\gnuwin\bin\make.exe'
$toolBin = 'G:\Xilinx\Vitis\2024.1\gnu\aarch32\nt\gcc-arm-none-eabi\bin'
$gccPath = Join-Path $toolBin 'arm-none-eabi-gcc.exe'
$readelfPath = Join-Path $toolBin 'arm-none-eabi-readelf.exe'
$objdumpPath = Join-Path $toolBin 'arm-none-eabi-objdump.exe'
$nmPath = Join-Path $toolBin 'arm-none-eabi-nm.exe'
$sizePath = Join-Path $toolBin 'arm-none-eabi-size.exe'
$linkerScript = Join-Path $scriptRoot 'ocm_high_diag.ld'

foreach ($path in @($XsctPath, $xsaSource, $bitstreamSource, $b1aManifestPath,
        $makePath, $gccPath, $readelfPath, $objdumpPath, $nmPath, $sizePath,
        $linkerScript)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required build input not found: $path"
    }
}

$b1aManifest = Get-Content -LiteralPath $b1aManifestPath -Raw | ConvertFrom-Json
$bitstreamSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $bitstreamSource).Hash.ToLower()
$xsaSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $xsaSource).Hash.ToLower()
if ($bitstreamSha256 -ne $b1aManifest.bitstream_sha256) {
    throw 'B1A bitstream hash does not match build manifest'
}
if ($xsaSha256 -ne $b1aManifest.xsa_sha256) {
    throw 'B1A XSA hash does not match build manifest'
}
$b1aGitHead = [string]$b1aManifest.git_head

New-Item -ItemType Directory -Path $buildRoot, $outRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $bspRoot)) {
    Copy-Item -LiteralPath $xsaSource -Destination $xsaCopy
    & $XsctPath (Join-Path $scriptRoot 'build_b1b.tcl') $xsaCopy $bspRoot $appRoot
    if ($LASTEXITCODE -ne 0) {
        throw "HSI generation failed with exit code $LASTEXITCODE"
    }
}

$bspMakefile = Get-ChildItem -LiteralPath $bspRoot -Filter 'Makefile' -Recurse -File | Sort-Object FullName | Select-Object -First 1
if (-not $bspMakefile) {
    throw 'Generated BSP Makefile was not found'
}
$env:PATH = "$toolBin;$(Split-Path -Parent $makePath);$env:PATH"
$env:RDI_PLATFORM = 'win64'
& $makePath -C (Split-Path -Parent $bspMakefile.FullName)
if ($LASTEXITCODE -ne 0) {
    throw "BSP build failed with exit code $LASTEXITCODE"
}

$libxil = Get-ChildItem -LiteralPath $bspRoot -Filter 'libxil.a' -Recurse -File | Select-Object -First 1
$xparameters = Get-ChildItem -LiteralPath $bspRoot -Filter 'xparameters.h' -Recurse -File | Select-Object -First 1
$xilinxSpec = Get-ChildItem -LiteralPath $appRoot -Filter 'Xilinx.spec' -Recurse -File | Select-Object -First 1
if (-not $libxil -or -not $xparameters -or -not $xilinxSpec) {
    throw 'Generated BSP library, headers, or Xilinx.spec were not found'
}
$includeDir = Split-Path -Parent $xparameters.FullName
$libDir = Split-Path -Parent $libxil.FullName
$objectPath = Join-Path $outRoot 'high_diag.o'
$elfPath = Join-Path $outRoot 'b1b_high_diag_ocm.elf'
$mapPath = Join-Path $outRoot 'b1b_high_diag_ocm.map'
$readelfPathOut = Join-Path $outRoot 'readelf_program_headers.txt'
$objdumpPathOut = Join-Path $outRoot 'objdump_sections.txt'
$nmPathOut = Join-Path $outRoot 'nm_symbols.txt'
$sizePathOut = Join-Path $outRoot 'size.txt'
$identityHeader = Join-Path $outRoot 'build_identity.h'
$commonFlags = @('-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard')

$identityLines = @(
    '#ifndef B1B_HIGH_DIAG_BUILD_IDENTITY_H',
    '#define B1B_HIGH_DIAG_BUILD_IDENTITY_H',
    "#define B1B_SW_GIT_HEAD `"$gitHead`"",
    "#define B1A_HW_SOURCE_COMMIT `"$b1aGitHead`"",
    "#define B1A_BITSTREAM_SHA256 `"$bitstreamSha256`"",
    "#define B1A_XSA_SHA256 `"$xsaSha256`"",
    '#endif'
)
$identityLines | Set-Content -LiteralPath $identityHeader -Encoding ascii

& $gccPath @commonFlags '-O2' '-g' '-Wall' '-Wextra' '-fno-tree-loop-distribute-patterns' `
    '-include' $identityHeader `
    "-I$includeDir" '-c' (Join-Path $scriptRoot 'src\high_diag.c') '-o' $objectPath
if ($LASTEXITCODE -ne 0) {
    throw "High diagnostic compile failed with exit code $LASTEXITCODE"
}

& $gccPath @commonFlags "-specs=$($xilinxSpec.FullName)" "-Wl,-T,$linkerScript" "-Wl,-Map,$mapPath" "-L$libDir" '-o' $elfPath $objectPath '-Wl,--start-group' '-lxil' '-lgcc' '-lc' '-Wl,--end-group'
if ($LASTEXITCODE -ne 0) {
    throw "High diagnostic link failed with exit code $LASTEXITCODE"
}

$readelfText = (& $readelfPath '-lW' $elfPath 2>&1) -join "`n"
$objdumpText = (& $objdumpPath '-h' $elfPath 2>&1) -join "`n"
$nmText = (& $nmPath '-n' $elfPath 2>&1) -join "`n"
$sizeText = (& $sizePath $elfPath 2>&1) -join "`n"
$readelfText | Set-Content -LiteralPath $readelfPathOut -Encoding ascii
$objdumpText | Set-Content -LiteralPath $objdumpPathOut -Encoding ascii
$nmText | Set-Content -LiteralPath $nmPathOut -Encoding ascii
$sizeText | Set-Content -LiteralPath $sizePathOut -Encoding ascii

$limit = [uint64]0x2F000
$loadCount = 0
foreach ($line in ($readelfText -split "`n")) {
    if ($line -match '^\s*LOAD\s+0x[0-9a-fA-F]+\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)\s+0x[0-9a-fA-F]+\s+0x([0-9a-fA-F]+)') {
        $loadCount += 1
        $physicalAddress = [Convert]::ToUInt64($Matches[2], 16)
        $memorySize = [Convert]::ToUInt64($Matches[3], 16)
        if ($physicalAddress -ge $limit -or ($physicalAddress + $memorySize) -gt $limit) {
            throw "PT_LOAD exceeds OCM application range: $line"
        }
    }
}
if ($loadCount -eq 0) {
    throw 'No PT_LOAD program header found'
}

$entryMatch = [regex]::Match($readelfText, 'Entry point 0x([0-9a-fA-F]+)')
if (-not $entryMatch.Success -or [Convert]::ToUInt64($entryMatch.Groups[1].Value, 16) -ne 0) {
    throw 'ELF entry point is not 0x00000000'
}

$symbolNames = @(
    '_vector_table', '__mmu_tbl_start', '__mmu_tbl_end', '_heap', '_heap_end',
    '_stack_end', '_stack', '_irq_stack_end', '__irq_stack',
    '_supervisor_stack_end', '__supervisor_stack', '_abort_stack_end',
    '__abort_stack', '_fiq_stack_end', '__fiq_stack', '_undef_stack_end',
    '__undef_stack', '_end'
)
$symbolValues = @{}
foreach ($line in ($nmText -split "`n")) {
    if ($line -match '^([0-9a-fA-F]+)\s+\S\s+(\S+)$') {
        $symbolValues[$Matches[2]] = [Convert]::ToUInt64($Matches[1], 16)
    }
}
foreach ($symbol in $symbolNames) {
    if (-not $symbolValues.ContainsKey($symbol)) {
        throw "Required OCM symbol is missing: $symbol"
    }
    if ($symbolValues[$symbol] -ge $limit) {
        throw "OCM symbol exceeds application range: $symbol=0x$($symbolValues[$symbol].ToString('x'))"
    }
}
if ($symbolValues['_vector_table'] -ne 0) {
    throw '_vector_table is not located at 0x00000000'
}

$elf = Get-Item -LiteralPath $elfPath
$manifest = [ordered]@{
    schema_version = 1
    generated_at = [DateTime]::UtcNow.ToString('o')
    status = 'BUILD_PASS'
    protocol = 'B1B_HIGH_DIAG_V1'
    git_head = $gitHead
    git_worktree_clean = $gitWorktreeClean
    tool = 'XSCT/Vitis 2024.1'
    b1a_git_head = $b1aGitHead
    bitstream_sha256 = $bitstreamSha256
    xsa_sha256 = $xsaSha256
    elf = $elf.FullName
    elf_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $elf.FullName).Hash.ToLower()
    linker_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $linkerScript).Hash.ToLower()
    source_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $scriptRoot 'src\high_diag.c')).Hash.ToLower()
    identity_header_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $identityHeader).Hash.ToLower()
    ocm_app_limit = '0x0002F000'
    result_record_base = '0x0002F000'
    entry_point = '0x00000000'
    load_segment_count = $loadCount
    runtime_end = ('0x{0:x8}' -f $symbolValues['_end'])
    ddr_window_base = '0x10000000'
    ddr_window_bytes = '0x00001000'
}
$manifestPath = Join-Path $buildRoot 'build_manifest.json'
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding utf8

Write-Output 'B1B_HIGH_DIAG_BUILD_PASS'
Write-Output "B1B_HIGH_DIAG_ELF=$($elf.FullName)"
Write-Output "B1B_HIGH_DIAG_ELF_SHA256=$($manifest.elf_sha256)"
Write-Output "B1B_HIGH_DIAG_RUNTIME_END=$($manifest.runtime_end)"
Write-Output "B1B_HIGH_DIAG_BUILD_MANIFEST=$manifestPath"
