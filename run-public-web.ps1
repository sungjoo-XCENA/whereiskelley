param(
  [switch]$NoServer
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerUrl = "http://localhost:4317"
$LogsDir = Join-Path $Root "logs"

if (-not (Test-Path $LogsDir)) {
  New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
}

function Find-Python {
  $bundled = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  if (Test-Path $bundled) {
    return $bundled
  }
  return "python"
}

function Find-Cloudflared {
  $bundled = Join-Path $Root "tools\cloudflared.exe"
  if (Test-Path $bundled) {
    return $bundled
  }
  $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }
  throw "cloudflared was not found. Expected tools\cloudflared.exe or cloudflared in PATH."
}

function Test-LocalServer {
  try {
    $health = Invoke-RestMethod -Uri "$ServerUrl/api/health" -TimeoutSec 3
    return [bool]$health.ok
  } catch {
    return $false
  }
}

if (-not $NoServer -and -not (Test-LocalServer)) {
  $python = Find-Python
  Write-Host "Starting Where is Kelley local web server at $ServerUrl"
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $python
  $psi.Arguments = "app.py"
  $psi.WorkingDirectory = $Root
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $psi.Environment["WHEREISKELLEY_HOST"] = "127.0.0.1"
  $process = New-Object System.Diagnostics.Process
  $process.StartInfo = $psi
  [void]$process.Start()
  Start-Sleep -Seconds 2
  if ($process.HasExited) {
    throw "Local web server exited immediately. Run .\run-server.ps1 to see the error."
  }
} elseif (Test-LocalServer) {
  Write-Host "Local web server is already running at $ServerUrl"
}

if (-not (Test-LocalServer)) {
  throw "Local web server is not reachable at $ServerUrl"
}

$cloudflared = Find-Cloudflared
Write-Host ""
Write-Host "Where is Kelley is running locally:"
Write-Host "  $ServerUrl"
Write-Host ""
Write-Host "Starting Cloudflare Tunnel for the whole local web app."
Write-Host "Open the https://*.trycloudflare.com URL printed below from any device."
Write-Host "Keep this PowerShell window open while using the public URL."
Write-Host ""

& $cloudflared tunnel --url $ServerUrl
