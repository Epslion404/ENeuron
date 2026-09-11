param(
    [string]$XsctPath = 'G:\Xilinx\Vitis\2024.1\bin\xsct.bat'
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
$makePath = 'G:\Xilinx\Vitis\2024.1\gnuwin\bin\make.exe'
$toolBin = 'G:\Xilinx\Vitis\2024.1\gnu\aarch32\nt\gcc-arm-none-eabi\bin'
$gccPath = Join-Path $toolBin 'arm-none-eabi-gcc.exe'

foreach ($path in @($bitstream, $xsa, $makePath, $gccPath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required file not found: $path" }
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
$objectPath = Join-Path $outRoot 'packet_main.o'
$elfPath = Join-Path $outRoot 'b2_packet_smoke.elf'
$commonFlags = @('-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard')
$env:PATH = "$toolBin;$(Split-Path -Parent $makePath);$env:PATH"
$env:RDI_PLATFORM = 'win64'

& $gccPath @commonFlags '-O2' '-g' '-Wall' '-Wextra' '-fno-tree-loop-distribute-patterns' `
    '-I' $includeDir '-c' (Join-Path $scriptRoot 'src\packet_main.c') '-o' $objectPath
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
    application = 'b2_packet_smoke'
    protocol = 'ENB2_PACKET_NPU_V1'
}
$manifestPath = Join-Path $buildRoot 'packet_build_manifest.json'
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding utf8
Write-Output 'B2_PACKET_SW_BUILD_PASS'
Write-Output "B2_PACKET_ELF=$elfPath"
Write-Output "B2_PACKET_SW_BUILD_MANIFEST=$manifestPath"
