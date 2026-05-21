param(
  [string]$Token = "",
  [switch]$NoServer
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvPath = Join-Path $Root ".env.local"
$LogsDir = Join-Path $Root "logs"
$ServerUrl = "http://localhost:4317"

function Get-EnvValue([string]$Path, [string]$Key) {
  if (-not (Test-Path $Path)) {
    return ""
  }
  foreach ($line in Get-Content $Path) {
    $trimmed = $line.Trim()
    if ($trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
      continue
    }
    $parts = $trimmed.Split("=", 2)
    if ($parts[0].Trim() -eq $Key) {
      return $parts[1].Trim().Trim('"').Trim("'")
    }
  }
  return ""
}

function New-Token {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Upsert-EnvValue([string]$Path, [string]$Key, [string]$Value) {
  $lines = @()
  if (Test-Path $Path) {
    $lines = @(Get-Content $Path)
  }
  $found = $false
  $next = foreach ($line in $lines) {
    if ($line.TrimStart().StartsWith("$Key=")) {
      $found = $true
      "$Key=$Value"
    } else {
      $line
    }
  }
  if (-not $found) {
    $next += "$Key=$Value"
  }
  Set-Content -Path $Path -Value $next -Encoding UTF8
}

if (-not $Token) {
  $Token = $env:WHEREISKELLEY_API_TOKEN
}
if (-not $Token) {
  $Token = Get-EnvValue $EnvPath "WHEREISKELLEY_API_TOKEN"
}
if (-not $Token) {
  $Token = New-Token
  Write-Host "Generated a new local API token and saved it to .env.local."
}

Upsert-EnvValue $EnvPath "WHEREISKELLEY_API_TOKEN" $Token
Upsert-EnvValue $EnvPath "WHEREISKELLEY_ALLOWED_ORIGIN" "https://whereiskelley.vercel.app"
Upsert-EnvValue $EnvPath "WHEREISKELLEY_HOST" "127.0.0.1"

if (-not (Test-Path $LogsDir)) {
  New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
}

if (-not $NoServer) {
  $python = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  if (-not (Test-Path $python)) {
    $python = "python"
  }
  $serverRunning = $false
  $existingHealth = $null
  try {
    $existingHealth = Invoke-RestMethod -Uri "$ServerUrl/api/health" -TimeoutSec 3
    $serverRunning = $true
  } catch {
    $serverRunning = $false
  }
  if ($serverRunning) {
    Write-Host "Local API is already running at $ServerUrl"
    if (-not $existingHealth.authRequired) {
      throw "Local API is running without token auth. Stop the current server and rerun this script."
    }
    Invoke-RestMethod -Uri "$ServerUrl/api/guide-collection" -Headers @{"x-whereiskelley-token" = $Token} -TimeoutSec 30 | Out-Null
  } else {
    Write-Host "Starting local API server at $ServerUrl"
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $python
    $psi.Arguments = "app.py"
    $psi.WorkingDirectory = $Root
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    [void]$process.Start()
    Start-Sleep -Seconds 2
    if ($process.HasExited) {
      throw "Local API server exited immediately. Run .\run-server.ps1 to see the error."
    }
  }
}

try {
  $health = Invoke-RestMethod -Uri "$ServerUrl/api/health" -TimeoutSec 5
  Write-Host "Local API health: ok=$($health.ok), authRequired=$($health.authRequired)"
  if (-not $health.authRequired) {
    throw "Local API is reachable but token auth is not active. Stop the old server and rerun this script."
  }
  Invoke-RestMethod -Uri "$ServerUrl/api/guide-collection" -Headers @{"x-whereiskelley-token" = $Token} -TimeoutSec 30 | Out-Null
} catch {
  if ($_.Exception.Message -like "*token auth*") {
    throw $_
  }
  throw "Local API is not reachable at $ServerUrl. Start it with .\run-server.ps1 first."
}

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
  Write-Host ""
  Write-Host "cloudflared is not installed or not in PATH."
  Write-Host "Install it first: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  Write-Host ""
  Write-Host "After the tunnel is running, add these Vercel env vars:"
  Write-Host "WHEREISKELLEY_LOCAL_API_BASE=https://your-tunnel-hostname"
  Write-Host "WHEREISKELLEY_LOCAL_API_TOKEN=$Token"
  exit 1
}

Write-Host ""
Write-Host "Starting Cloudflare quick tunnel to $ServerUrl"
Write-Host "Copy the https://*.trycloudflare.com URL printed by cloudflared."
Write-Host ""
Write-Host "Set these Vercel environment variables:"
Write-Host "WHEREISKELLEY_LOCAL_API_BASE=https://the-url-cloudflared-prints"
Write-Host "WHEREISKELLEY_LOCAL_API_TOKEN=$Token"
Write-Host "WHEREISKELLEY_LOCAL_API_TIMEOUT=60"
Write-Host ""
Write-Host "Keep this window open while using the deployed dashboard."
Write-Host ""

cloudflared tunnel --url $ServerUrl
