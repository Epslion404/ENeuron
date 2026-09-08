param(
    [ValidateSet("Check", "Resume")]
    [string]$Mode = "Resume"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Read-only: no file changes, validation runs, commits, or Vivado calls.
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$safeRepo = $repoRoot.Replace("\", "/")
$requiredFiles = @(
    "WORKFLOW.md",
    "WORKFLOW_STATE.md",
    "task_plan.md",
    "progress.md",
    "findings.md",
    "docs/planning/TODO.md",
    "docs/planning/NPU_PRUNING_TODO.md",
    "docs/planning/NPU_PRUNING_NP7_TODO.md"
)

$activeTodoSpecs = @(
    [pscustomobject]@{
        Path = "docs/planning/TODO.md"
        StartPattern = "^### P16"
        Label = "TODO.md:P16"
    }
)

function Write-WorkflowLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Level,
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] [$Level] $Message"
}

function Invoke-WorkflowGit {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $output = & git -c "safe.directory=$safeRepo" @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Git 命令失败：git $($Arguments -join ' ')`n$output"
    }

    return $output
}

function Test-WorkflowFiles {
    $missing = @()
    foreach ($relativePath in $requiredFiles) {
        $fullPath = Join-Path $repoRoot $relativePath
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
            $missing += $relativePath
        }
    }

    if ($missing.Count -gt 0) {
        throw "缺少持久工作流文件：$($missing -join ', ')"
    }

    $stateText = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $repoRoot "WORKFLOW_STATE.md")
    $requiredStateFields = @(
        "最后更新：",
        "状态：",
        "## 当前活动目标",
        "## 允许动作",
        "## 禁止动作",
        "## 下一动作"
    )

    foreach ($field in $requiredStateFields) {
        if (-not $stateText.Contains($field)) {
            throw "WORKFLOW_STATE.md 缺少字段：$field"
        }
    }

    Write-WorkflowLog -Level "PASS" -Message "持久文件和状态字段完整。"
}

function Get-OpenTodoCount {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath,
        [string]$StartPattern
    )

    $lines = @(Get-Content -Encoding UTF8 -LiteralPath (Join-Path $repoRoot $RelativePath))
    if (-not [string]::IsNullOrWhiteSpace($StartPattern)) {
        $startMatch = $lines | Select-String -Pattern $StartPattern | Select-Object -First 1
        if ($null -eq $startMatch) {
            throw "活动 TODO 起始标题不存在：$RelativePath / $StartPattern"
        }
        $lines = @($lines[($startMatch.LineNumber - 1)..($lines.Count - 1)])
    }

    return @($lines | Select-String -Pattern "^- \[ \]").Count
}

function Show-WorkflowSummary {
    $head = (Invoke-WorkflowGit -Arguments @("rev-parse", "--short", "HEAD")) -join ""
    $statusLines = @(Invoke-WorkflowGit -Arguments @("status", "--short"))
    $openItemsByFile = foreach ($spec in $activeTodoSpecs) {
        [pscustomobject]@{
            Path = $spec.Label
            Count = Get-OpenTodoCount -RelativePath $spec.Path -StartPattern $spec.StartPattern
        }
    }
    $openItems = ($openItemsByFile | Measure-Object -Property Count -Sum).Sum

    Write-WorkflowLog -Level "INFO" -Message "仓库：$repoRoot"
    Write-WorkflowLog -Level "INFO" -Message "HEAD：$head"
    Write-WorkflowLog -Level "INFO" -Message "工作树条目：$($statusLines.Count)"
    Write-WorkflowLog -Level "INFO" -Message "当前主线 TODO 未完成项（$($activeTodoSpecs.Count) 份合同）：$openItems"
    foreach ($item in $openItemsByFile) {
        Write-WorkflowLog -Level "INFO" -Message "  $($item.Path)：$($item.Count)"
    }

    Write-Host "`n=== WORKFLOW_STATE.md ==="
    Get-Content -Encoding UTF8 -LiteralPath (Join-Path $repoRoot "WORKFLOW_STATE.md")

    Write-Host "`n=== git status --short ==="
    if ($statusLines.Count -eq 0) {
        Write-Host "(clean)"
    }
    else {
        $statusLines | ForEach-Object { Write-Host $_ }
    }
}

function Show-ResumeContext {
    Write-Host "`n=== 最近提交 ==="
    Invoke-WorkflowGit -Arguments @("log", "-5", "--oneline") | ForEach-Object { Write-Host $_ }

    Write-Host "`n=== progress.md 尾部 ==="
    Get-Content -Encoding UTF8 -LiteralPath (Join-Path $repoRoot "progress.md") -Tail 35

    Write-Host "`n=== findings.md 尾部 ==="
    Get-Content -Encoding UTF8 -LiteralPath (Join-Path $repoRoot "findings.md") -Tail 25

    Write-Host "`n=== 恢复完成 ==="
    Write-Host "下一步必须读取活动 TODO 的当前阶段完整合同，再判断是否已有用户批准。"
}

Push-Location $repoRoot
try {
    Write-WorkflowLog -Level "INFO" -Message "开始 $Mode 模式。"
    Test-WorkflowFiles
    Show-WorkflowSummary

    if ($Mode -eq "Resume") {
        Show-ResumeContext
    }

    Write-WorkflowLog -Level "PASS" -Message "$Mode 模式完成；未修改仓库。"
}
catch {
    Write-WorkflowLog -Level "FAIL" -Message $_.Exception.Message
    exit 1
}
finally {
    Pop-Location
}
