<#
.SYNOPSIS
  One-shot dev environment startup for MeetStream Companion.
  Starts Docker/Postgres, the FastAPI backend, a Cloudflare quick tunnel,
  then re-points the MIA agent's MCP server URL and webhook callback at the
  fresh tunnel URL automatically.

.USAGE
  Right-click > Run with PowerShell, or from a PowerShell prompt:
      .\start.ps1
  Leave the window open - closing it kills the backend and tunnel.
#>

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# 1. Docker Desktop + Postgres ------------------------------------------------
Write-Step "Checking Docker..."
$dockerReady = $false
try { docker info *> $null; $dockerReady = $true } catch {}

if (-not $dockerReady) {
    Write-Host "Starting Docker Desktop (this can take up to a minute)..."
    Start-Process "C:\Users\agent\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe"
    $waited = 0
    while ($waited -lt 120) {
        try { docker ps *> $null; $dockerReady = $true; break } catch {}
        Start-Sleep -Seconds 3
        $waited += 3
    }
    if (-not $dockerReady) {
        Write-Host "Docker did not come up in time. Start it manually and re-run this script." -ForegroundColor Red
        exit 1
    }
}
Write-Host "Docker is up."

Write-Step "Starting Postgres (docker compose up -d)..."
docker compose up -d

# 2. Backend -------------------------------------------------------------------
Write-Step "Freeing port 8000 if something is already listening..."
$existing = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $existing.OwningProcess | Select-Object -Unique | ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped previous process on :8000 (pid $_)"
    }
    Start-Sleep -Seconds 1
}

Write-Step "Starting FastAPI backend on :8000..."
$backend = Start-Process -PassThru -WindowStyle Hidden `
    -FilePath "$root\.venv\Scripts\python.exe" `
    -ArgumentList "-u", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000" `
    -RedirectStandardOutput "$root\.uvicorn.log" `
    -RedirectStandardError "$root\.uvicorn.err.log"

$waited = 0
$backendReady = $false
while ($waited -lt 120) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $backendReady = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
    $waited += 1
}
if (-not $backendReady) {
    Write-Host "Backend did not become healthy within 120s. Check .uvicorn.err.log" -ForegroundColor Red
    Write-Host "(Cold start can be slow the first time it loads the embedding model - try re-running.)" -ForegroundColor Yellow
    exit 1
}
Write-Host "Backend healthy (pid $($backend.Id))."

# 3. Cloudflare tunnel -----------------------------------------------------------
Write-Step "Starting Cloudflare quick tunnel..."
Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped previous tunnel (pid $($_.Id))"
}
$tunnelLog = "$root\.cloudflared.log"
$tunnelErrLog = "$root\.cloudflared.err.log"
Remove-Item $tunnelLog, $tunnelErrLog -ErrorAction SilentlyContinue
$tunnel = Start-Process -PassThru -WindowStyle Hidden `
    -FilePath "$root\.tools\cloudflared.exe" `
    -ArgumentList "tunnel", "--url", "http://127.0.0.1:8000" `
    -RedirectStandardOutput $tunnelLog `
    -RedirectStandardError $tunnelErrLog

$tunnelUrl = $null
$waited = 0
while ($waited -lt 60) {
    foreach ($logFile in @($tunnelLog, $tunnelErrLog)) {
        if (Test-Path $logFile) {
            $match = Select-String -Path $logFile -Pattern "https://[a-zA-Z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($match) { $tunnelUrl = $match.Matches[0].Value; break }
        }
    }
    if ($tunnelUrl) { break }
    Start-Sleep -Seconds 1
    $waited += 1
}
if (-not $tunnelUrl) {
    Write-Host "Tunnel URL did not appear in time. Check .cloudflared.log" -ForegroundColor Red
    exit 1
}
Write-Host "Tunnel is live: $tunnelUrl"

# 4. Update .env ------------------------------------------------------------------
Write-Step "Updating .env with new MCP_SERVER_URL..."
$envPath = "$root\.env"
$envContent = Get-Content $envPath
$newMcpUrl = "$tunnelUrl/mcp"
$envContent = $envContent -replace '^MCP_SERVER_URL=.*', "MCP_SERVER_URL=$newMcpUrl"
Set-Content -Path $envPath -Value $envContent -Encoding utf8
Write-Host "MCP_SERVER_URL=$newMcpUrl"

# 5. Restart backend so it picks up the new .env ------------------------------
Write-Step "Restarting backend to load new tunnel URL..."
Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
$backend = Start-Process -PassThru -WindowStyle Hidden `
    -FilePath "$root\.venv\Scripts\python.exe" `
    -ArgumentList "-u", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000" `
    -RedirectStandardOutput "$root\.uvicorn.log" `
    -RedirectStandardError "$root\.uvicorn.err.log"

$waited = 0
$backendReady = $false
while ($waited -lt 120) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $backendReady = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
    $waited += 1
}
if (-not $backendReady) {
    Write-Host "Backend did not come back up after restart. Check .uvicorn.err.log" -ForegroundColor Red
    exit 1
}
Write-Host "Backend healthy again (pid $($backend.Id))."

# 6. Re-point the live MIA agent's MCP server URL -----------------------------
Write-Step "Re-pointing MIA agent MCP server URL on MeetStream..."
try {
    $body = @{ mcp_server_url = $newMcpUrl } | ConvertTo-Json
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/agent" -Method Put -Body $body -ContentType "application/json" | Out-Null
    Write-Host "Agent config updated."
} catch {
    Write-Host "Could not update agent config automatically: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "You can retry later with:  Invoke-RestMethod -Uri http://127.0.0.1:8000/api/agent -Method Put -Body (@{mcp_server_url=`"$newMcpUrl`"} | ConvertTo-Json) -ContentType application/json"
}

# 7. Frontend -----------------------------------------------------------------------
Write-Step "Freeing port 3000 if something is already listening..."
$existingFrontend = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if ($existingFrontend) {
    $existingFrontend.OwningProcess | Select-Object -Unique | ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped previous process on :3000 (pid $_)"
    }
    Start-Sleep -Seconds 1
}

Write-Step "Starting frontend (Vite) on :3000..."
$frontendDir = "$root\frontend"
$viteJs = "$frontendDir\node_modules\vite\bin\vite.js"
if (-not (Test-Path $viteJs)) {
    Write-Host "Frontend dependencies not installed yet. Installing (first run only)..." -ForegroundColor Yellow
    Push-Location $frontendDir
    & npm install
    Pop-Location
}

$frontendLog = "$root\.frontend.log"
$frontendErrLog = "$root\.frontend.err.log"
Remove-Item $frontendLog, $frontendErrLog -ErrorAction SilentlyContinue
$frontend = Start-Process -PassThru -WindowStyle Hidden `
    -FilePath "node" `
    -ArgumentList "`"$viteJs`"", "`"$frontendDir`"", "--port", "3000" `
    -RedirectStandardOutput $frontendLog `
    -RedirectStandardError $frontendErrLog

$waited = 0
$frontendReady = $false
while ($waited -lt 90) {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) { $frontendReady = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
    $waited += 1
}
if ($frontendReady) {
    Write-Host "Frontend healthy (pid $($frontend.Id))."
} else {
    Write-Host "Frontend is taking longer than usual to come up (first run pre-bundles dependencies) - opening browser anyway, refresh if it's blank at first." -ForegroundColor Yellow
}
Start-Process "http://localhost:3000"

# 8. Summary --------------------------------------------------------------------------
Write-Step "All set."
Write-Host "Backend:   http://127.0.0.1:8000"
Write-Host "Tunnel:    $tunnelUrl"
Write-Host "Frontend:  http://localhost:3000"
Write-Host ""
Write-Host "Backend pid: $($backend.Id)   Tunnel pid: $($tunnel.Id)   Frontend pid: $($frontend.Id)"
Write-Host "To stop everything, run:  .\stop.ps1"
Write-Host ""
Write-Host "Leave this window open - closing it does not stop the background processes," -ForegroundColor DarkGray
Write-Host "but if you restart your machine or Docker resets, just re-run .\start.ps1" -ForegroundColor DarkGray
