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
$buildRoot = Join-Path $scriptRoot (Join-Path 'build' (Join-Path $gitHead 'direct'))
$bspRoot = Join-Path $buildRoot 'bsp'
$appRoot = Join-Path $buildRoot 'app'
$outRoot = Join-Path $buildRoot 'out'
$xsaCopy = Join-Path $buildRoot 'hello_zynq_b1a.xsa'
$makePath = 'G:\Xilinx\Vitis\2024.1\gnuwin\bin\make.exe'
$toolBin = 'G:\Xilinx\Vitis\2024.1\gnu\aarch32\nt\gcc-arm-none-eabi\bin'
$gccPath = Join-Path $toolBin 'arm-none-eabi-gcc.exe'

if (-not (Test-Path -LiteralPath $XsctPath)) {
    throw "XSCT not found: $XsctPath"
}
foreach ($path in @($xsaSource, $bitstreamSource, $b1aManifestPath)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "B1A artifact not found: $path"
    }
}
$b1aManifest = Get-Content -LiteralPath $b1aManifestPath -Raw | ConvertFrom-Json
$b1aBitstreamSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $bitstreamSource).Hash.ToLower()
$b1aXsaSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $xsaSource).Hash.ToLower()
if ($b1aBitstreamSha256 -ne $b1aManifest.bitstream_sha256) {
    throw 'B1A bitstream hash does not match build manifest'
}
if ($b1aXsaSha256 -ne $b1aManifest.xsa_sha256) {
    throw 'B1A XSA hash does not match build manifest'
}
$b1aGitHead = [string]$b1aManifest.git_head
foreach ($path in @($makePath, $gccPath)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Build tool not found: $path"
    }
}
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
$bspBuildDir = Split-Path -Parent $bspMakefile.FullName
$env:PATH = "$toolBin;$(Split-Path -Parent $makePath);$env:PATH"
$env:RDI_PLATFORM = 'win64'
& $makePath -C $bspBuildDir
if ($LASTEXITCODE -ne 0) {
    throw "BSP build failed with exit code $LASTEXITCODE"
}

$libxil = Get-ChildItem -LiteralPath $bspRoot -Filter 'libxil.a' -Recurse -File | Select-Object -First 1
$xparameters = Get-ChildItem -LiteralPath $bspRoot -Filter 'xparameters.h' -Recurse -File | Select-Object -First 1
$linkerScript = Get-ChildItem -LiteralPath $appRoot -Filter 'lscript.ld' -Recurse -File | Select-Object -First 1
$xilinxSpec = Get-ChildItem -LiteralPath $appRoot -Filter 'Xilinx.spec' -Recurse -File | Select-Object -First 1
if (-not $libxil -or -not $xparameters -or -not $linkerScript -or -not $xilinxSpec) {
    throw 'Generated BSP library, headers, linker script, or Xilinx.spec were not found'
}
$includeDir = Split-Path -Parent $xparameters.FullName
$libDir = Split-Path -Parent $libxil.FullName
$objectPath = Join-Path $outRoot 'main.o'
$elfPath = Join-Path $outRoot 'b1b_uart_ddr.elf'
$commonFlags = @('-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard')

& $gccPath @commonFlags '-O2' '-g' '-Wall' '-Wextra' '-fno-tree-loop-distribute-patterns' `
    "-DB1B_SW_GIT_HEAD=\`"$gitHead\`"" `
    "-DB1A_HW_SOURCE_COMMIT=\`"$b1aGitHead\`"" `
    "-DB1A_BITSTREAM_SHA256=\`"$b1aBitstreamSha256\`"" `
    "-DB1A_XSA_SHA256=\`"$b1aXsaSha256\`"" `
    "-I$includeDir" '-c' (Join-Path $scriptRoot 'src\main.c') '-o' $objectPath
if ($LASTEXITCODE -ne 0) {
    throw "Application compile failed with exit code $LASTEXITCODE"
}
& $gccPath @commonFlags "-specs=$($xilinxSpec.FullName)" "-Wl,-T,$($linkerScript.FullName)" "-L$libDir" '-o' $elfPath $objectPath '-Wl,--start-group' '-lxil' '-lgcc' '-lc' '-Wl,--end-group'
if ($LASTEXITCODE -ne 0) {
    throw "Application link failed with exit code $LASTEXITCODE"
}
$elf = Get-Item -LiteralPath $elfPath

$manifest = [ordered]@{
    schema_version = 1
    generated_at = [DateTime]::UtcNow.ToString('o')
    git_head = $gitHead
    tool = 'XSCT/Vitis 2024.1'
    b1a_git_head = $b1aGitHead
    b1a_worktree_clean = [bool]$b1aManifest.git_worktree_clean
    bitstream_sha256 = $b1aBitstreamSha256
    xsa_sha256 = $b1aXsaSha256
    elf = $elf.FullName
    elf_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $elf.FullName).Hash.ToLower()
    uart = 'CH340 VID_1A86:PID_7523 115200 8N1'
    ddr_test_base = '0x01000000'
    ddr_test_bytes = '0x00100000'
}
$manifestPath = Join-Path $buildRoot 'build_manifest.json'
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding utf8

Write-Output "B1B_BUILD_PASS"
Write-Output "B1B_ELF=$($elf.FullName)"
Write-Output "B1B_ELF_SHA256=$($manifest.elf_sha256)"
Write-Output "B1B_BUILD_MANIFEST=$manifestPath"
