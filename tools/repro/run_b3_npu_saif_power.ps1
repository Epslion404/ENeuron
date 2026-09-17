param(
    [string]$VivadoRoot = $env:VIVADO_ROOT,
    [string]$OutputDir,
    [switch]$SkipImplementation
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$vivadoBat = if ($VivadoRoot) { Join-Path $VivadoRoot 'bin\vivado.bat' } else { 'G:\Xilinx\Vivado\2024.1\bin\vivado.bat' }
if (-not (Test-Path -LiteralPath $vivadoBat)) { throw "Vivado not found: $vivadoBat" }
if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $OutputDir = Join-Path $root "artifacts\logs\b3_npu_saif_power_200mhz_$stamp"
}
$out = [IO.Path]::GetFullPath($OutputDir)
$fixture = Join-Path $out 'fixture'
New-Item -ItemType Directory -Force -Path $fixture | Out-Null

$manifest = Join-Path $root 'tools\repro\b3_qat_model_manifest.json'
$diagnostic = Join-Path $root 'artifacts\results\b3_qat_pruning_diagnostic.json'
$generator = Join-Path $root 'tools\repro\b3_npu_saif_fixture.py'
& python $generator --manifest $manifest --diagnostic $diagnostic --output-dir $fixture --sample-count 64
if ($LASTEXITCODE -ne 0) { throw 'SAIF fixture generation failed' }

$gitHead = (& git -C $root rev-parse HEAD).Trim()
$powerTcl = Join-Path $root 'tools\repro\b3_npu_saif_power.tcl'
$implLog = Join-Path $out 'vivado_implementation.log'
$postRouteNetlist = Join-Path $out 'npu_eneuron_single_clock_skeleton_200mhz_post_route_funcsim.v'
if (-not $SkipImplementation) {
    & $vivadoBat -mode batch -nolog -nojournal -notrace -source $powerTcl -tclargs implement $gitHead $out '' '' 2>&1 | Tee-Object -FilePath $implLog
    if ($LASTEXITCODE -ne 0) { throw 'Vivado post-route implementation failed' }
} elseif (-not (Test-Path -LiteralPath $postRouteNetlist)) {
    throw "Cannot skip implementation; routed netlist is missing: $postRouteNetlist"
}

$simTcl = Join-Path $root 'tools\repro\b3_npu_saif_sim.tcl'
$modelMem = Join-Path $fixture 'model.mem'
$samplesMem = Join-Path $fixture 'samples.mem'
$maskMem = Join-Path $fixture 'gated_mask.mem'
foreach ($mode in @('dense', 'gated')) {
    $simOut = Join-Path $out "${mode}_sim"
    $simLog = Join-Path $out "vivado_${mode}_sim.log"
    & $vivadoBat -mode batch -nolog -nojournal -notrace -source $simTcl -tclargs $mode $simOut $modelMem $samplesMem $maskMem $postRouteNetlist 2>&1 | Tee-Object -FilePath $simLog
    if ($LASTEXITCODE -ne 0) { throw "Vivado XSim failed for $mode" }
    Copy-Item -LiteralPath (Join-Path $simOut "${mode}.saif") -Destination (Join-Path $out "${mode}.saif") -Force
    Copy-Item -LiteralPath (Join-Path $simOut "${mode}_xsim.log") -Destination (Join-Path $out "${mode}_xsim.log") -Force
}

$powerLog = Join-Path $out 'vivado_power_post_route.log'
$denseSaif = Join-Path $out 'dense.saif'
$gatedSaif = Join-Path $out 'gated.saif'
& $vivadoBat -mode batch -nolog -nojournal -notrace -source $powerTcl -tclargs report $gitHead $out $denseSaif $gatedSaif 2>&1 | Tee-Object -FilePath $powerLog
if ($LASTEXITCODE -ne 0) { throw 'Vivado post-route SAIF power analysis failed' }

$dcp = Join-Path $out 'npu_eneuron_single_clock_skeleton_200mhz_routed.dcp'
$summary = Join-Path $out 'summary.json'
& python (Join-Path $root 'tools\repro\b3_npu_saif_power_summary.py') `
    --dense-report (Join-Path $out 'dense_power_post_route.rpt') `
    --gated-report (Join-Path $out 'gated_power_post_route.rpt') `
    --dense-saif $denseSaif --gated-saif $gatedSaif --dcp $dcp --output $summary `
    --timing-report (Join-Path $out 'timing_post_route.rpt') `
    --route-status-report (Join-Path $out 'route_status_post_route.rpt') `
    --drc-report (Join-Path $out 'drc_post_route.rpt') `
    --rtl (Join-Path $root 'npu_eneuron_single_clock_skeleton.sv') `
    --testbench (Join-Path $root 'tb_b3_npu_saif_power.sv') `
    --fixture (Join-Path $fixture 'fixture.json') `
    --post-route-netlist $postRouteNetlist
if ($LASTEXITCODE -ne 0) { throw 'Power summary validation failed' }

$hashNames = @(
    'dense.saif', 'gated.saif',
    'dense_power_post_route.rpt', 'gated_power_post_route.rpt',
    'dense_saif_unmatched.rpt', 'gated_saif_unmatched.rpt',
    'dense_xsim.log', 'gated_xsim.log',
    'npu_eneuron_single_clock_skeleton_200mhz_routed.dcp',
    'npu_eneuron_single_clock_skeleton_200mhz_post_route_funcsim.v',
    'utilization_post_route.rpt', 'timing_post_route.rpt',
    'route_status_post_route.rpt', 'drc_post_route.rpt',
    'implementation_summary.txt', 'fixture\fixture.json', 'summary.json'
)
$hashes = [ordered]@{}
foreach ($name in $hashNames) {
    $path = Join-Path $out $name
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing expected artifact: $path" }
    $hashes[$name] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
$hashes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'sha256sums.json') -Encoding UTF8
$result = Get-Content -LiteralPath $summary -Raw | ConvertFrom-Json
if ($result.status -ne 'PASS') { throw "Power summary status is $($result.status)" }
Write-Host "B3_NPU_SAIF_POWER_PASS output=$out"
