param(
    [switch]$Full,
    [switch]$Vivado,
    [ValidateSet("Check", "Resume")]
    [string]$WorkflowMode = "Check",
    [string]$VivadoRoot = $env:VIVADO_ROOT
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workflowScript = Join-Path $repoRoot "workflow_resume.ps1"
$buildScript = Join-Path $repoRoot "boards\hellozynq\b2_hw\run_b2_build.ps1"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Executable,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host "`n=== $Name ==="
    Write-Host "$Executable $($Arguments -join ' ')"
    # 原生命令的 stderr 可能只是 Git/Vivado 警告，不能被 Stop 策略提前转成异常；最终以退出码裁决。
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Executable @Arguments 2>&1 | ForEach-Object { Write-Host $_ }
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($exitCode -ne 0) {
        throw "$Name 失败，退出码：$exitCode"
    }
}

Push-Location $repoRoot
try {
    Write-Host "B2 验证编排开始：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

    if (-not (Test-Path -LiteralPath $workflowScript -PathType Leaf)) {
        throw "缺少 workflow_resume.ps1"
    }
    Invoke-CheckedCommand "工作流状态检查" "powershell" @(
        "-ExecutionPolicy", "Bypass", "-File", $workflowScript, "-Mode", $WorkflowMode
    )

    $b2Tests = @(
        Get-ChildItem -LiteralPath $repoRoot -Filter "test_b2_*.py" -File |
            Sort-Object -Property Name |
            ForEach-Object { $_.FullName }
    )
    if ($b2Tests.Count -eq 0) {
        throw "未找到 test_b2_*.py"
    }
    Invoke-CheckedCommand "B2 合同回归" "python" (@("-X", "utf8", "-m", "pytest", "-q") + $b2Tests)

    Invoke-CheckedCommand "T1 复现检查" "python" @(
        "-X", "utf8", "tools/repro/verify_repository.py", "--t1"
    )

    if ($Full) {
        Invoke-CheckedCommand "完整 Python 回归" "python" @("-X", "utf8", "-m", "pytest", "-q")
    }

    Invoke-CheckedCommand "Git 差异空白检查" "git" @("diff", "--check")

    if ($Vivado) {
        if ([string]::IsNullOrWhiteSpace($VivadoRoot)) {
            throw "启用 -Vivado 时必须提供 -VivadoRoot 或设置 VIVADO_ROOT"
        }
        if (-not (Test-Path -LiteralPath $buildScript -PathType Leaf)) {
            throw "缺少 run_b2_build.ps1"
        }
        Invoke-CheckedCommand "Vivado B2 物理重建" "powershell" @(
            "-ExecutionPolicy", "Bypass", "-File", $buildScript, "-VivadoRoot", $VivadoRoot
        )
    }

    Write-Host "`nB2_CHECKS_PASS"
}
catch {
    Write-Host "`nB2_CHECKS_FAIL"
    Write-Host $_.Exception.Message
    exit 1
}
finally {
    Pop-Location
}
