<#
.SYNOPSIS
  Stops the backend (uvicorn), the frontend (Vite), and the Cloudflare tunnel
  started by start.ps1. Postgres (Docker) is left running since it's cheap to
  keep up and has real data.

.USAGE
  .\stop.ps1
#>

$stopped = $false

$backendConn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($backendConn) {
    $backendConn.OwningProcess | ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped backend (pid $_)"
        $stopped = $true
    }
}

$frontendConn = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if ($frontendConn) {
    $frontendConn.OwningProcess | Select-Object -Unique | ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped frontend (pid $_)"
        $stopped = $true
    }
}

Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped tunnel (pid $($_.Id))"
    $stopped = $true
}

if (-not $stopped) {
    Write-Host "Nothing was running."
}

Write-Host ""
Write-Host "Postgres is still running (docker compose). Stop it with: docker compose down" -ForegroundColor DarkGray
