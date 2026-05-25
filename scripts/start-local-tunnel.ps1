$ErrorActionPreference = "Stop"

Write-Host "Starting Where is Kelley local web tunnel for http://localhost:4317"
Write-Host "For normal use, prefer .\run-public-web.ps1 so the app does not use Vercel Functions."
Write-Host "Keep this window open while using the public URL."
Write-Host ""

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
  Write-Host "cloudflared is not installed or not in PATH."
  Write-Host "Install Cloudflare Tunnel first, then run this script again."
  Write-Host "Download: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  exit 1
}

cloudflared tunnel --url http://localhost:4317
