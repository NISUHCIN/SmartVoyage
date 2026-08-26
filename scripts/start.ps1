<#
.SYNOPSIS
    SmartVoyage 一键启动脚本
.DESCRIPTION
    按依赖顺序启动 MCP 服务与 A2A 服务（后端）。
    每个服务在独立的后台窗口中运行，方便排查问题。
.PARAMETER MCPOrder
    是否启动订票 MCP（需要数据库），默认启动
.EXAMPLE
    .\start.ps1              # 启动全部后端服务
#>
param(
    [bool]$MCPOrder = $true
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SmartVoyage 服务启动器" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 .env 文件
if (-not (Test-Path ".env")) {
    Write-Host "[警告] 未找到 .env 文件！" -ForegroundColor Yellow
    if (Test-Path ".env.example") {
        Write-Host "已从 .env.example 创建 .env，请编辑填入你的密钥后重新运行。" -ForegroundColor Yellow
        Copy-Item ".env.example" ".env"
    }
    Write-Host ""
    Write-Host "按任意键退出..." -ForegroundColor Red
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# 从 .env 读取端口配置，脚本内支持覆盖默认值
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

# 服务定义：名称、脚本路径、端口、启动延迟（秒）
$Services = @(
    @{ Name = "MCP-票务查询";  Script = "mcp_servers\mcp_ticket_server.py";  Port = Get-Port 'MCP_TICKET_PORT' 8001; Delay = 3 },
    @{ Name = "MCP-天气查询";  Script = "mcp_servers\mcp_weather_server.py"; Port = Get-Port 'MCP_WEATHER_PORT' 8002; Delay = 3 },
    @{ Name = "MCP-酒店查询";  Script = "mcp_servers\mcp_hotel_server.py";  Port = Get-Port 'MCP_HOTEL_PORT' 8004; Delay = 3 }
)
if ($MCPOrder) {
    $Services += @{ Name = "MCP-票务预定"; Script = "mcp_servers\mcp_order_server.py"; Port = Get-Port 'MCP_ORDER_PORT' 8003; Delay = 3 }
}
$Services += @(
    @{ Name = "A2A-天气Agent"; Script = "agents\weather_server.py"; Port = Get-Port 'A2A_WEATHER_PORT' 5005; Delay = 3 },
    @{ Name = "A2A-票务Agent"; Script = "agents\ticket_server.py"; Port = Get-Port 'A2A_TICKET_PORT' 5006; Delay = 3 },
    @{ Name = "A2A-订票Agent"; Script = "agents\order_server.py";  Port = Get-Port 'A2A_ORDER_PORT' 5007; Delay = 3 },
    @{ Name = "A2A-酒店Agent"; Script = "agents\hotel_server.py";   Port = Get-Port 'A2A_HOTEL_PORT' 5008; Delay = 3 },
    @{ Name = "A2A-行程Agent"; Script = "agents\itinerary_server.py"; Port = Get-Port 'A2A_ITINERARY_PORT' 5009; Delay = 3 }
)

# 等待端口就绪
function Wait-Port($Port, $TimeoutSec = 15) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        try {
            $conn = New-Object System.Net.Sockets.TcpClient
            $conn.Connect("127.0.0.1", $Port)
            $conn.Close()
            return $true
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

# 按顺序启动每个服务
foreach ($svc in $Services) {
    $scriptPath = Join-Path $ProjectRoot $svc.Script
    if (-not (Test-Path $scriptPath)) {
        Write-Host "[跳过] $($svc.Name)：找不到 $scriptPath" -ForegroundColor Yellow
        continue
    }
    Write-Host "[启动] $($svc.Name) (端口 $($svc.Port))..." -NoNewline -ForegroundColor White

    # 在新的最小化窗口中启动，方便查看日志
    $title = $svc.Name
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$ProjectRoot'; python '$scriptPath'" -WindowStyle Minimized

    # 等待端口就绪
    if (Wait-Port -Port $svc.Port -TimeoutSec 20) {
        Write-Host " 就绪" -ForegroundColor Green
    } else {
        Write-Host " 超时（可能仍在启动中）" -ForegroundColor Yellow
    }

    Start-Sleep -Seconds 1
}

Write-Host ""
Write-Host "所有后端服务已启动。" -ForegroundColor Green
Write-Host ""

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  服务状态总览" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MCP 票务查询:  http://127.0.0.1:8001/mcp"
Write-Host "  MCP 天气查询:  http://127.0.0.1:8002/mcp"
if ($MCPOrder) { Write-Host "  MCP 票务预定:  http://127.0.0.1:8003/mcp" }
Write-Host "  MCP 酒店查询:  http://127.0.0.1:8004/mcp"
Write-Host "  A2A 天气Agent: http://127.0.0.1:5005"
Write-Host "  A2A 票务Agent: http://127.0.0.1:5006"
Write-Host "  A2A 订票Agent: http://127.0.0.1:5007"
Write-Host "  A2A 酒店Agent: http://127.0.0.1:5008"
Write-Host "  A2A 行程Agent: http://127.0.0.1:5009"
Write-Host ""
Write-Host "停止所有服务请运行: .\stop.ps1" -ForegroundColor Yellow
Write-Host ""
