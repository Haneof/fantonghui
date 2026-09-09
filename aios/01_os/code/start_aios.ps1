# AIOS Start Script: bus + 15 services, wait healthy, report
$ErrorActionPreference = "SilentlyContinue"
$code = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $code

Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item "run\health.json","run\bus_stats.json" -ErrorAction SilentlyContinue

$aiosd = Start-Process python -ArgumentList "aiosd/aiosd.py" -PassThru -WindowStyle Hidden -WorkingDirectory $code
Write-Output "aiosd launched (pid=$($aiosd.Id)), waiting for full stack..."

$deadline = (Get-Date).AddSeconds(20)
$ready = $false
while ((Get-Date) -lt $deadline) {
    if (Test-Path "run\health.json") {
        $h = Get-Content "run\health.json" -Encoding UTF8 | ConvertFrom-Json
        $up = 0
        foreach ($p in $h.services.PSObject.Properties) { if ($p.Value.state -eq "up") { $up++ } }
        if ($h.bus.state -eq "up" -and $up -eq 15) { $ready = $true; break }
    }
    Start-Sleep -Milliseconds 300
}
if ($ready) {
    Write-Output "AIOS RUNNING: bus + 15/15 services online"
    Write-Output "aiosd pid = $($aiosd.Id)  (stop: stop_aios.ps1)"
    Write-Output "feed events: python simulator/simd.py --script simulator/scripts/m0_smoke.json"
    Write-Output "status: status_aios.ps1  |  health: run\health.json  |  logs: run\logs\"
} else {
    Write-Output "[WARN] not all green in 20s, check run\logs\aiosd.log"
}
