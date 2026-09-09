# AIOS Stop Script: kill aiosd tree + bus
$ErrorActionPreference = "SilentlyContinue"
$code = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $code
$aiosdPid = $null
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ForEach-Object {
    if ($_.CommandLine -match "aiosd") { $aiosdPid = $_.ProcessId }
}
if ($aiosdPid) {
    taskkill /T /F /PID $aiosdPid | Out-Null
    Write-Output "aiosd tree stopped (pid=$aiosdPid)"
} else {
    Write-Output "no running aiosd found"
}
$health = $null
if (Test-Path "run\health.json") {
    $health = Get-Content "run\health.json" -Encoding UTF8 | ConvertFrom-Json
}
if ($health -and $health.bus.pid) {
    taskkill /F /PID $health.bus.pid | Out-Null
}
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Output "AIOS fully stopped"
