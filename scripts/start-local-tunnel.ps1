$ErrorActionPreference = "Stop"

Write-Host "Starting Where is Kelley local API tunnel for http://localhost:4317"
Write-Host "Keep this window open while using the deployed dashboard."
Write-Host ""

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
  Write-Host "cloudflared is not installed or not in PATH."
  Write-Host "Install Cloudflare Tunnel first, then run this script again."
  Write-Host "Download: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  exit 1
}

cloudflared tunnel --url http://localhost:4317
