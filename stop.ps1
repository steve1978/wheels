# Wheels — stop everything (AI backend, web app, share tunnel).
$backend = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*uvicorn app.server:app*' }
$frontend = Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
    Where-Object { $_.CommandLine -like '*next*' }
$tunnel = Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'"

$any = $false
foreach ($p in @($backend) + @($frontend) + @($tunnel)) {
    if ($p) {
        Write-Host ("  stopping {0} (PID {1})" -f $p.Name, $p.ProcessId)
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        $any = $true
    }
}
# Belt and braces: whatever still owns the app's ports goes too.
foreach ($port in @(8000, 3000)) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -Expand OwningProcess -Unique | ForEach-Object {
            Write-Host ("  stopping port-{0} owner (PID {1})" -f $port, $_)
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
            $any = $true
        }
}
Remove-Item (Join-Path $PSScriptRoot "YOUR-LINK.txt") -Force -ErrorAction SilentlyContinue
if ($any) {
    Write-Host "  Wheels is now OFF. Nothing is reachable from the internet." -ForegroundColor Green
} else {
    Write-Host "  Nothing was running."
}
