# ============================================================================
#  WHEELS — start script with first-run setup.
#  Checks your machine, installs anything missing (with your permission),
#  then launches the app. Run via start.bat or:
#    powershell -ExecutionPolicy Bypass -File start.ps1
# ============================================================================
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPy = Join-Path $root "backend\.venv\Scripts\python.exe"

function Banner {
    Write-Host ""
    Write-Host '   __          ___    _ ______ ______ _       _____ ' -ForegroundColor Cyan
    Write-Host '   \ \        / / |  | |  ____|  ____| |     / ____|' -ForegroundColor Cyan
    Write-Host '    \ \  /\  / /| |__| | |__  | |__  | |    | (___  ' -ForegroundColor Cyan
    Write-Host '     \ \/  \/ / |  __  |  __| |  __| | |     \___ \ ' -ForegroundColor Cyan
    Write-Host '      \  /\  /  | |  | | |____| |____| |____ ____) |' -ForegroundColor Cyan
    Write-Host '       \/  \/   |_|  |_|______|______|______|_____/ ' -ForegroundColor Cyan
    Write-Host ""
    Write-Host "        AI car colour & wheel visualizer - runs 100% on YOUR GPU" -ForegroundColor DarkCyan
    Write-Host "  ---------------------------------------------------------------------"
    Write-Host ""
}

function Step($n, $text)  { Write-Host ("  [{0}/7] {1}" -f $n, $text) -ForegroundColor White }
function Ok($text)        { Write-Host ("        " + [char]0x2713 + " " + $text) -ForegroundColor Green }
function Warn($text)      { Write-Host ("        ! " + $text) -ForegroundColor Yellow }
function Fail($text)      { Write-Host ("        " + [char]0x2717 + " " + $text) -ForegroundColor Red }
function Die($text) {
    Fail $text
    Write-Host ""
    Write-Host "  Setup cannot continue. Fix the issue above and run start.bat again." -ForegroundColor Red
    Write-Host ""
    Read-Host "  Press Enter to close"
    exit 1
}

Banner

# ---------------------------------------------------------------- 1. GPU ----
Step 1 "Checking your graphics card..."
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $smi) { Die "No NVIDIA driver found. This app needs an NVIDIA GPU (16GB+ VRAM) and its driver from nvidia.com." }
$gpuInfo = (& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader) -split ","
$gpuName = $gpuInfo[0].Trim()
$gpuMem = [int]($gpuInfo[1] -replace "[^0-9]", "")
if ($gpuMem -lt 15000) {
    Warn "$gpuName has $([math]::Round($gpuMem/1024))GB VRAM - 16GB+ is recommended. It may be slow or fail."
} else {
    Ok "$gpuName ($([math]::Round($gpuMem/1024))GB VRAM)"
}

# ------------------------------------------------------------- 2. Python ----
# NOTE: never trust PATH alone — a double-clicked .bat inherits Explorer's
# CACHED environment, which misses recent installs. Probe known locations too,
# and after an install keep going in THIS run (no "close and re-run" dance).
function Resolve-Python {
    foreach ($cand in @("python", "python3", "py")) {
        $c = Get-Command $cand -ErrorAction SilentlyContinue
        if ($c) {
            $v = & $c.Source --version 2>&1
            if ($v -match "Python 3\.(1[0-2])\.") { return $c.Source }
        }
    }
    foreach ($d in @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles\Python312", "$env:ProgramFiles\Python311", "$env:ProgramFiles\Python310")) {
        if (Test-Path $d) {
            $exe = Get-ChildItem $d -Filter python.exe -Recurse -Depth 1 -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($exe) { return $exe.FullName }
        }
    }
    return $null
}

Step 2 "Checking Python..."
$python = Resolve-Python
if (-not $python -and (Test-Path $venvPy)) { $python = $venvPy }  # venv already built
if (-not $python) {
    Warn "Python 3.10-3.12 not found."
    $ans = Read-Host "        Install Python 3.12 automatically with winget? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        winget install --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent
        Start-Sleep -Seconds 3
        $python = Resolve-Python
    }
    if (-not $python) { Die "Python is required. Install 3.12 from python.org, then run start.bat again." }
}
Ok "Python found: $python"

# ------------------------------------------------------------- 3. Node.js ---
function Resolve-NodeDir {
    foreach ($d in @("$env:ProgramFiles\nodejs", "${env:ProgramFiles(x86)}\nodejs", "$env:LOCALAPPDATA\nodejs")) {
        if (Test-Path (Join-Path $d "node.exe")) { return $d }
    }
    $c = Get-Command node -ErrorAction SilentlyContinue
    if ($c) { return (Split-Path $c.Source -Parent) }
    return $null
}

Step 3 "Checking Node.js (runs the web interface)..."
$nodeDir = Resolve-NodeDir
if (-not $nodeDir) {
    Warn "Node.js not found."
    $ans = Read-Host "        Install Node.js LTS automatically with winget? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        winget install --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements --silent
        Start-Sleep -Seconds 3
        $nodeDir = Resolve-NodeDir
    }
    if (-not $nodeDir) { Die "Node.js is required. Install the LTS from nodejs.org, then run start.bat again." }
}
# Make node + npm available to this run and every child process we launch.
$env:Path = "$nodeDir;" + $env:Path
Ok "Node.js $(& (Join-Path $nodeDir 'node.exe') --version)"

# ------------------------------------------------- 4. Python environment ----
Step 4 "Checking the AI engine's Python environment..."
if (-not (Test-Path $venvPy)) {
    Warn "First run - creating it now (downloads ~3GB of libraries, 5-15 min)..."
    & $python -m venv (Join-Path $root "backend\.venv")
    if (-not (Test-Path $venvPy)) { Die "Could not create the Python environment." }
    & $venvPy -m pip install --upgrade pip --quiet
    Write-Host "        installing PyTorch (CUDA)..." -ForegroundColor DarkGray
    & $venvPy -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
    Write-Host "        installing the rest..." -ForegroundColor DarkGray
    & $venvPy -m pip install -r (Join-Path $root "backend\requirements.txt")
}
$torchOk = & $venvPy -c "import torch; print(torch.cuda.is_available())" 2>$null
if ($torchOk -notmatch "True") { Die "PyTorch can't see your GPU. Check your NVIDIA driver is up to date, then re-run." }
Ok "Python environment ready (PyTorch + CUDA working)"

# ---------------------------------------------------- 5. Web app packages ---
Step 5 "Checking the web interface..."
if (-not (Test-Path (Join-Path $root "frontend\node_modules"))) {
    Warn "First run - installing web packages (1-2 min)..."
    Push-Location (Join-Path $root "frontend")
    & cmd /c "npm install" | Out-Null
    Pop-Location
}
if (-not (Test-Path (Join-Path $root "frontend\.next\BUILD_ID"))) {
    Write-Host "        building the web app (~1 min)..." -ForegroundColor DarkGray
    Push-Location (Join-Path $root "frontend")
    & cmd /c "npm run build" | Out-Null
    Pop-Location
}
if (-not (Test-Path (Join-Path $root "frontend\.next\BUILD_ID"))) { Die "Web app build failed. Run 'npm run build' in the frontend folder to see why." }
Ok "Web interface ready"

# -------------------------------------------------------- 6. AI model -------
Step 6 "Checking the AI model (~30GB on first run)..."
$gguf = Join-Path $root "models\qwen-image-edit-2511-Q4_K_S.gguf"
if (-not (Test-Path $gguf)) {
    $free = [math]::Round((Get-PSDrive ($root[0])).Free / 1GB)
    if ($free -lt 45) { Die "Only ${free}GB free on drive $($root[0]): - the AI model needs ~40GB. Free up space and re-run." }
    Warn "Model not downloaded yet. It downloads AUTOMATICALLY on first launch (~30GB - can take a while)."
} else {
    Ok "Model weights found"
}

# -------------------------------------------------- 7. Wheel catalog --------
Step 7 "Checking the wheel catalog..."
$manifests = @(Get-ChildItem (Join-Path $root "backend\wheel_catalog") -Filter manifest.json -Recurse -ErrorAction SilentlyContinue)
if ($manifests.Count -eq 0) {
    Warn "No wheels yet - fetching product images from wheelmania.co.uk (~2 min)..."
    $brands = @(
        @("https://wheelmania.co.uk/alloy-wheels/bbs/", "bbs", "BBS"),
        @("https://wheelmania.co.uk/alloy-wheels/1av/", "1av", "1AV"),
        @("https://wheelmania.co.uk/alloy-wheels/1form/", "1form", "1FORM"),
        @("https://wheelmania.co.uk/alloy-wheels/oz-racing/", "oz-racing", "OZ Racing"),
        @("https://wheelmania.co.uk/alloy-wheels/velare/", "velare", "Velare"),
        @("https://wheelmania.co.uk/alloy-wheels/momo/", "momo", "MOMO")
    )
    $env:PYTHONPATH = Join-Path $root "backend"
    Push-Location (Join-Path $root "backend")
    foreach ($b in $brands) {
        Write-Host ("        fetching {0}..." -f $b[2]) -ForegroundColor DarkGray
        & $venvPy scrape_catalog.py $b[0] $b[1] $b[2] | Out-Null
    }
    Pop-Location
}
$count = 0
Get-ChildItem (Join-Path $root "backend\wheel_catalog") -Filter manifest.json -Recurse -ErrorAction SilentlyContinue |
    ForEach-Object { $count += (Get-Content $_.FullName -Raw | ConvertFrom-Json).Count }
if ($count -gt 0) { Ok "$count real wheels in the catalog" } else { Warn "Catalog empty - wheel swapping disabled (colours still work)" }

# ----------------------------------------------------------- LAUNCH ---------
Write-Host ""
Write-Host "  All checks passed - starting Wheels..." -ForegroundColor Cyan
Write-Host ""

# Clean strays so a previous session can't block the ports.
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*uvicorn app.server:app*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -Expand OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

Start-Process -FilePath $venvPy `
    -ArgumentList "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", "8000", "--app-dir", "$root\backend" `
    -WorkingDirectory "$root\backend" -WindowStyle Minimized `
    -RedirectStandardOutput "$root\backend\server.out.log" -RedirectStandardError "$root\backend\server.err.log"
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm --prefix `"$root\frontend`" run start > `"$root\frontend_run.log`" 2>&1" `
    -WindowStyle Hidden

Write-Host "  waiting for the web app " -NoNewline
for ($i = 0; $i -lt 45; $i++) {
    if (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue) { break }
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 2
}
Write-Host " up"

Write-Host "  waiting for the AI model (1 min normally; MUCH longer on first download) " -NoNewline
$ready = $false
for ($i = 0; $i -lt 600; $i++) {
    try {
        $r = Invoke-RestMethod -Uri "http://localhost:8000/readyz" -TimeoutSec 2
        if ($r.ready) { $ready = $true; break }
    } catch {}
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 3
}
Write-Host $(if ($ready) { " ready" } else { " still warming (it will finish in the background)" })

# Optional public share link.
Write-Host ""
$share = Read-Host "  Share publicly so friends can use it from their devices? [y/N]"
$url = $null
if ($share -match "^[Yy]") {
    $cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
    if (-not $cloudflared) {
        $cloudflared = @("$env:ProgramFiles\cloudflared\cloudflared.exe", "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe") |
            Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $cloudflared) {
        $ans = Read-Host "        cloudflared (free tunnel tool) is needed - install with winget? [Y/n]"
        if ($ans -eq "" -or $ans -match "^[Yy]") {
            winget install --id Cloudflare.cloudflared --accept-source-agreements --accept-package-agreements --silent | Out-Null
            $cloudflared = @("$env:ProgramFiles\cloudflared\cloudflared.exe", "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe") |
                Where-Object { Test-Path $_ } | Select-Object -First 1
        }
    }
    if ($cloudflared) {
        $log = "$root\tunnel.log"
        Remove-Item $log -Force -ErrorAction SilentlyContinue
        Start-Process -FilePath $cloudflared -ArgumentList "tunnel", "--url", "http://localhost:3000" -WindowStyle Minimized -RedirectStandardError $log
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 2
            if (Test-Path $log) {
                $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -AllMatches | ForEach-Object { $_.Matches } | Select-Object -First 1
                if ($m) { $url = $m.Value; break }
            }
        }
    } else { Warn "couldn't set up the tunnel - running locally only" }
}

Start-Process "http://localhost:3000"
Write-Host ""
Write-Host "  ==============================================================" -ForegroundColor Green
Write-Host "   Wheels is RUNNING" -ForegroundColor Green
Write-Host ""
Write-Host "   On this PC:    http://localhost:3000" -ForegroundColor White
if ($url) {
    Write-Host "   Share link:    $url" -ForegroundColor White
    Write-Host "                  (anyone with this link can use it; new link each start)"
    "Wheels share link: $url" | Set-Content -Path "$root\YOUR-LINK.txt" -Encoding utf8
}
Write-Host ""
Write-Host "   To stop:       double-click stop.bat" -ForegroundColor White
Write-Host "  ==============================================================" -ForegroundColor Green
Write-Host ""
