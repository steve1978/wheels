# Wheels — show usage stats and open the gallery of saved renders.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  Wheels - usage stats" -ForegroundColor Cyan
Write-Host "  ---------------------"
try {
    $s = Invoke-RestMethod -Uri "http://localhost:8000/api/stats" -TimeoutSec 5
} catch {
    Write-Host "  The app isn't running - start it with start.bat to see stats." -ForegroundColor Yellow
    # Fall back to the persisted file so stats still show while the app is off.
    $f = Join-Path $root "backend\stats.json"
    if (Test-Path $f) { $s = Get-Content $f -Raw | ConvertFrom-Json } else { exit 1 }
}

$vl = [int]$s.visits_local;  $ve = [int]$s.visits_external
$rl = [int]$s.renders_local; $re = [int]$s.renders_external
$uniq = if ($s.unique_external_visitors) { $s.unique_external_visitors } else { @($s.unique_external_ips).Count }

Write-Host ("   Visits:   {0,5} total   ({1} from your share link, {2} local)" -f ($vl+$ve), $ve, $vl)
Write-Host ("   Renders:  {0,5} total   ({1} from your share link, {2} local)" -f ($rl+$re), $re, $rl)
Write-Host ("   Unique external visitors: {0}" -f $uniq)
if ($s.gallery_renders_saved) { Write-Host ("   Saved render pairs in gallery: {0}" -f $s.gallery_renders_saved) }

if ($s.by_day) {
    Write-Host ""
    Write-Host "   Last days:" -ForegroundColor DarkCyan
    $s.by_day.PSObject.Properties | Sort-Object Name | Select-Object -Last 7 | ForEach-Object {
        $d = $_.Value
        $v = [int]$d.visits_local + [int]$d.visits_external
        $r = [int]$d.renders_local + [int]$d.renders_external
        Write-Host ("     {0}:  {1} visits, {2} renders ({3} external renders)" -f $_.Name, $v, $r, [int]$d.renders_external)
    }
}

$gallery = Join-Path $root "backend\gallery"
if (Test-Path $gallery) {
    Write-Host ""
    $ans = Read-Host "  Open the gallery folder (all uploads + results)? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") { Start-Process explorer.exe $gallery }
} else {
    Write-Host "  (no gallery yet - it fills up as renders happen)"
}
Write-Host ""
