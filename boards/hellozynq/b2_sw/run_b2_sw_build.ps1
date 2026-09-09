param(
    [string]$XsctPath = 'G:\Xilinx\Vitis\2024.1\bin\xsct.bat'
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..\..')).Path
$xsaSource = Join-Path $repoRoot 'boards\hellozynq\b2_hw\build\hello_zynq_b2.xsa'
$bitstreamSource = Join-Path $repoRoot 'boards\hellozynq\b2_hw\build\hello_zynq_b2.bit'
$b2ManifestPath = Join-Path $repoRoot 'boards\hellozynq\b2_hw\build\build_manifest.json'
$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
$buildRoot = Join-Path $scriptRoot (Join-Path 'build' (Join-Path $gitHead 'direct'))
$bspRoot = Join-Path $buildRoot 'bsp'
$appRoot = Join-Path $buildRoot 'app'
$outRoot = Join-Path $buildRoot 'out'
$xsaCopy = Join-Path $buildRoot 'hello_zynq_b2.xsa'
$makePath = 'G:\Xilinx\Vitis\2024.1\gnuwin\bin\make.exe'
$toolBin = 'G:\Xilinx\Vitis\2024.1\gnu\aarch32\nt\gcc-arm-none-eabi\bin'
$gccPath = Join-Path $toolBin 'arm-none-eabi-gcc.exe'

if (-not (Test-Path -LiteralPath $XsctPath)) { throw "XSCT not found: $XsctPath" }
foreach ($path in @($xsaSource, $bitstreamSource, $b2ManifestPath, $makePath, $gccPath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required file not found: $path" }
}
$b2Manifest = Get-Content -LiteralPath $b2ManifestPath -Raw | ConvertFrom-Json
if ([string]$b2Manifest.part -ne 'xc7z020clg484-2') {
    throw "B2 build manifest targets an unexpected part: $($b2Manifest.part)"
}
$b2BitstreamSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $bitstreamSource).Hash.ToLowerInvariant()
$b2XsaSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $xsaSource).Hash.ToLowerInvariant()
if ($b2BitstreamSha256 -ne $b2Manifest.bitstream_sha256 -or
    $b2XsaSha256 -ne $b2Manifest.xsa_sha256) {
    throw 'B2 artifact hash does not match build manifest'
}

New-Item -ItemType Directory -Path $buildRoot, $outRoot -Force | Out-Null
$existingXsaSha = if (Test-Path -LiteralPath $xsaCopy) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $xsaCopy).Hash.ToLowerInvariant()
} else {
    ''
}
$needsHsi = -not (Test-Path -LiteralPath $bspRoot) -or
    -not (Test-Path -LiteralPath $appRoot) -or
    ($existingXsaSha -ne $b2XsaSha256)
Copy-Item -LiteralPath $xsaSource -Destination $xsaCopy -Force
if ($needsHsi) {
    & $XsctPath (Join-Path $scriptRoot 'build_b2_sw.tcl') $xsaCopy $bspRoot $appRoot
    if ($LASTEXITCODE -ne 0) { throw "HSI generation failed with exit code $LASTEXITCODE" }
}

$bspMakefile = Get-ChildItem -LiteralPath $bspRoot -Filter 'Makefile' -Recurse -File | Select-Object -First 1
if (-not $bspMakefile) { throw 'Generated BSP Makefile was not found' }
$bspBuildDir = Split-Path -Parent $bspMakefile.FullName
$env:PATH = "$toolBin;$(Split-Path -Parent $makePath);$env:PATH"
$env:RDI_PLATFORM = 'win64'
& $makePath -C $bspBuildDir
if ($LASTEXITCODE -ne 0) { throw "BSP build failed with exit code $LASTEXITCODE" }

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
$elfPath = Join-Path $outRoot 'b2_dma_loopback.elf'
$commonFlags = @('-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard')

& $gccPath @commonFlags '-O2' '-g' '-Wall' '-Wextra' '-fno-tree-loop-distribute-patterns' `
    '-I' $includeDir '-c' (Join-Path $scriptRoot 'src\main.c') '-o' $objectPath
if ($LASTEXITCODE -ne 0) { throw "Application compile failed with exit code $LASTEXITCODE" }
& $gccPath @commonFlags "-specs=$($xilinxSpec.FullName)" "-Wl,-T,$($linkerScript.FullName)" "-L$libDir" '-o' $elfPath $objectPath '-Wl,--start-group' '-lxil' '-lgcc' '-lc' '-Wl,--end-group'
if ($LASTEXITCODE -ne 0) { throw "Application link failed with exit code $LASTEXITCODE" }

$manifest = [ordered]@{
    schema_version = 1
    generated_at = [DateTime]::UtcNow.ToString('o')
    git_head = $gitHead
    tool = 'XSCT/Vitis 2024.1'
    bitstream_sha256 = $b2BitstreamSha256
    xsa_sha256 = $b2XsaSha256
    elf = $elfPath
    elf_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $elfPath).Hash.ToLowerInvariant()
    dma_contract = 'b2_dma_contract_v1'
    address_layout = 'b2_dma_address_layout_v1'
}
$manifestPath = Join-Path $buildRoot 'build_manifest.json'
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding utf8
Write-Output "B2_SW_BUILD_PASS"
Write-Output "B2_ELF=$elfPath"
Write-Output "B2_SW_BUILD_MANIFEST=$manifestPath"
