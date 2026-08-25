<#
.SYNOPSIS
    SmartVoyage 一键停止脚本
.DESCRIPTION
    按端口查找并终止所有 SmartVoyage 相关的 Python 进程（MCP + A2A + Streamlit）。
#>

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SmartVoyage 服务停止器" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 需要关闭的端口列表
$Ports = @(8001, 8002, 8003, 8004, 5005, 5006, 5007, 5008, 5009, 8080, 5173, 8501)

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
$svScripts = @("mcp_ticket_server", "mcp_weather_server", "mcp_order_server", "mcp_hotel_server", "weather_server", "ticket_server", "order_server", "hotel_server", "itinerary_server", "api_server", "streamlit")
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
