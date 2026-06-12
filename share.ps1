# ============================================================================
#  WHEELS — share script. Adds a PUBLIC link to the ALREADY-RUNNING app.
#  Run via share.bat. Does NOT start a second copy of anything:
#    - if the app is running, it only opens a Cloudflare tunnel to it
#    - if the app is not running, it offers to start it first (via start.ps1)
#  Re-running rotates the URL. stop.bat closes the tunnel along with the app.
# ============================================================================
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  Wheels - public sharing" -ForegroundColor Cyan
Write-Host "  ------------------------"

# --- 1. Is the app running locally? ------------------------------------------
$appUp = [bool](Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)
if (-not $appUp) {
    Write-Host "  The app isn't running yet." -ForegroundColor Yellow
    $ans = Read-Host "  Start it now? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "start.ps1")
        $appUp = [bool](Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)
    }
    if (-not $appUp) {
        Write-Host "  Can't share - the app isn't running. Run start.bat first." -ForegroundColor Red
        exit 1
    }
}
Write-Host "  app is running locally" -ForegroundColor Green

# --- 2. cloudflared (the free tunnel tool) ------------------------------------
function Resolve-Cloudflared {
    $c = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($p in @("$env:ProgramFiles\cloudflared\cloudflared.exe",
                     "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe")) {
        if (Test-Path $p) { return $p }
    }
    return $null
}
$cloudflared = Resolve-Cloudflared
if (-not $cloudflared) {
    Write-Host "  cloudflared (free Cloudflare tunnel tool) is not installed." -ForegroundColor Yellow
    $ans = Read-Host "  Install it automatically with winget? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        winget install --id Cloudflare.cloudflared --accept-source-agreements --accept-package-agreements --silent
        Start-Sleep -Seconds 3
        $cloudflared = Resolve-Cloudflared
    }
    if (-not $cloudflared) {
        Write-Host "  cloudflared is required for sharing. Install it and re-run share.bat." -ForegroundColor Red
        exit 1
    }
}

# --- 3. One tunnel only: close any previous one, then open fresh --------------
$old = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($old) {
    Write-Host "  closing the previous share link..."
    $old | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}
Write-Host "  opening the tunnel..."
$log = Join-Path $root "tunnel.log"
Remove-Item $log -Force -ErrorAction SilentlyContinue
Start-Process -FilePath $cloudflared `
    -ArgumentList "tunnel", "--url", "http://localhost:3000" `
    -WindowStyle Minimized -RedirectStandardError $log

$url = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -AllMatches |
            ForEach-Object { $_.Matches } | Select-Object -First 1
        if ($m) { $url = $m.Value; break }
    }
}

Write-Host ""
if ($url) {
    "Your Wheels share link (anyone with it can use it):`r`n`r`n  $url`r`n`r`nThe link changes every time you run share.bat. stop.bat switches it off." |
        Set-Content -Path (Join-Path $root "YOUR-LINK.txt") -Encoding utf8
    Write-Host "  ==============================================================" -ForegroundColor Green
    Write-Host "   PUBLIC LINK (give this to your friends):" -ForegroundColor Green
    Write-Host ""
    Write-Host "   $url" -ForegroundColor White
    Write-Host ""
    Write-Host "   - also saved to YOUR-LINK.txt in this folder"
    Write-Host "   - anyone with the link can use it (no password)"
    Write-Host "   - re-run share.bat for a fresh link; stop.bat switches it off"
    Write-Host "  ==============================================================" -ForegroundColor Green
} else {
    Write-Host "  Couldn't get a link from Cloudflare - check tunnel.log and try again." -ForegroundColor Red
}
Write-Host ""
