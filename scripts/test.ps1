<#
.SYNOPSIS
    SmartVoyage 一键测试脚本：后端 pytest + 前端 vitest。
#>
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition | Split-Path -Parent
Set-Location $ProjectRoot

$Python = "python"
$LangEnvPython = "D:\Programs\Anaconda3\envs\lang_env\python.exe"
if (Test-Path $LangEnvPython) {
    $Python = $LangEnvPython
}

Write-Host "[1/2] 后端测试..."
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "[2/2] 前端测试..."
Push-Location (Join-Path $ProjectRoot "web")
try {
    npm test -- --run
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
