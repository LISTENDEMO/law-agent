param(
    [int]$BackendPort = 8765,
    [int]$FrontendPort = 3003,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Data = Join-Path $Root "data"
New-Item -ItemType Directory -Force -Path $Data | Out-Null

function Test-JsonHealth([string]$Url) {
    try {
        $response = Invoke-RestMethod -Uri $Url -TimeoutSec 5
        return $response.status -eq "alive"
    } catch {
        return $false
    }
}

function Wait-Http([string]$Url, [int]$Seconds = 45) {
    for ($i = 0; $i -lt $Seconds; $i++) {
        if (Test-JsonHealth $Url) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

$BackendHealth = "http://127.0.0.1:$BackendPort/api/v1/health"
$FrontendHealth = "http://127.0.0.1:$FrontendPort/api/v1/health"
$FrontendUrl = "http://127.0.0.1:$FrontendPort"

if (-not (Test-JsonHealth $BackendHealth)) {
    $backendListener = Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue
    if ($backendListener) {
        throw "Port $BackendPort is already in use, but $BackendHealth is not healthy. Stop that process or choose -BackendPort."
    }

    $env:PYTHONPATH = $Backend
    $backendOut = Join-Path $Data "backend-$BackendPort.out.log"
    $backendErr = Join-Path $Data "backend-$BackendPort.err.log"
    $backendProcess = Start-Process `
        -FilePath "python" `
        -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port",$BackendPort `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $backendOut `
        -RedirectStandardError $backendErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Output "Started backend PID=$($backendProcess.Id) on $BackendHealth"
}

if (-not (Wait-Http $BackendHealth 60)) {
    throw "Backend did not become healthy at $BackendHealth. Check data/backend-$BackendPort.err.log"
}

if (-not (Test-JsonHealth $FrontendHealth)) {
    $frontendListener = Get-NetTCPConnection -LocalPort $FrontendPort -State Listen -ErrorAction SilentlyContinue
    if ($frontendListener) {
        throw "Port $FrontendPort is already in use, but $FrontendHealth is not proxying to the backend. Stop that process or choose -FrontendPort."
    }

    $env:BACKEND_URL = "http://127.0.0.1:$BackendPort"
    $frontendOut = Join-Path $Data "frontend-$FrontendPort.out.log"
    $frontendErr = Join-Path $Data "frontend-$FrontendPort.err.log"
    $frontendProcess = Start-Process `
        -FilePath "npm.cmd" `
        -ArgumentList "run","dev","--","-p",$FrontendPort `
        -WorkingDirectory $Frontend `
        -RedirectStandardOutput $frontendOut `
        -RedirectStandardError $frontendErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Output "Started frontend PID=$($frontendProcess.Id) on $FrontendUrl"
}

if (-not (Wait-Http $FrontendHealth 60)) {
    throw "Frontend proxy did not become healthy at $FrontendHealth. Check data/frontend-$FrontendPort.err.log"
}

Write-Output "LOCAL_READY frontend=$FrontendUrl backend=$BackendHealth"
if (-not $NoBrowser) {
    Start-Process $FrontendUrl
}
