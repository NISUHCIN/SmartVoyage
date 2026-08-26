<#
.SYNOPSIS
    SmartVoyage 一键停止脚本
.DESCRIPTION
    按端口查找并终止所有 SmartVoyage 相关的 Python 进程（MCP + A2A + API）。
#>

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SmartVoyage 服务停止器" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

# 从 .env 读取端口配置，支持自定义端口
$EnvVars = @{}
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([A-Z0-9_]+)=(.*)$') {
            $EnvVars[$matches[1]] = $matches[2].Trim('"')
        }
    }
}

function Get-Port([string]$Key, [int]$Default) {
    if ($EnvVars.ContainsKey($Key)) {
        $parsed = 0
        if ([int]::TryParse($EnvVars[$Key], [ref]$parsed)) { return $parsed }
    }
    return $Default
}

# 需要关闭的端口列表
$Ports = @(
    (Get-Port 'MCP_TICKET_PORT' 8001),
    (Get-Port 'MCP_WEATHER_PORT' 8002),
    (Get-Port 'MCP_ORDER_PORT' 8003),
    (Get-Port 'MCP_HOTEL_PORT' 8004),
    (Get-Port 'A2A_WEATHER_PORT' 5005),
    (Get-Port 'A2A_TICKET_PORT' 5006),
    (Get-Port 'A2A_ORDER_PORT' 5007),
    (Get-Port 'A2A_HOTEL_PORT' 5008),
    (Get-Port 'A2A_ITINERARY_PORT' 5009),
    8080, 5173
)

foreach ($port in $Ports) {
    # 查找占用该端口的进程
    $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($connections) {
        $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($procId in $pids) {
            try {
                $proc = Get-Process -Id $procId -ErrorAction Stop
                Write-Host "[停止] 端口 $port -> PID $procId ($($proc.ProcessName))" -ForegroundColor Yellow
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            } catch {
                # 进程可能已退出
            }
        }
    } else {
        Write-Host "[空闲] 端口 $port 无服务运行" -ForegroundColor DarkGray
    }
}

# 额外清理：关闭所有以 SmartVoyage 脚本路径启动的 python 进程
Write-Host ""
$svScripts = @("mcp_ticket_server", "mcp_weather_server", "mcp_order_server", "mcp_hotel_server", "weather_server", "ticket_server", "order_server", "hotel_server", "itinerary_server", "api_server")
$foundExtra = $false
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
    foreach ($script in $svScripts) {
        if ($cmd -and ($cmd -match $script)) {
            Write-Host "[清理] PID $($_.Id): $script" -ForegroundColor Yellow
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            $foundExtra = $true
            break
        }
    }
}

Write-Host ""
Write-Host "所有 SmartVoyage 服务已停止。" -ForegroundColor Green
Write-Host ""
