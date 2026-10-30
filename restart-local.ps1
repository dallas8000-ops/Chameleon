# Stops the running Chameleon windows (API 8010, website 5173, GPU worker 8189) and starts everything again
# with run-local.ps1. Port 8000 belongs to a different app on this computer and is never touched.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
foreach ($port in 8010, 5173, 8189) {
    $owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($id in $owners) {
        $process = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "Stopping $($process.ProcessName) (process $id) on port $port"
            Stop-Process -Id $id -Force
        }
    }
}
Start-Sleep -Seconds 2
& "$root\run-local.ps1"
