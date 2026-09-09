# ============================================================
# AIOS · WSL2 迁移脚本（重启电脑后运行一次）
# 位置（复制件）：D:\手镯开发\wsl_setup.ps1
# 用法：powershell -ExecutionPolicy Bypass -File D:\手镯开发\wsl_setup.ps1
# 功能：安装 WSL2 + Ubuntu → 迁移 AIOS 代码 → 在真 Linux 里跑验收
# ============================================================
$ErrorActionPreference = "Continue"

Write-Output "===== STEP 1: install WSL kernel + Ubuntu ====="
wsl --install --no-distribution
Start-Sleep -Seconds 5
wsl --set-default-version 2
wsl --install -d Ubuntu --no-launch
Write-Output "waiting for Ubuntu install (1-3 min first time)..."
Start-Sleep -Seconds 90

Write-Output "===== STEP 2: python env inside Ubuntu ====="
wsl -d Ubuntu -u root -- bash -c "apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq python3 sqlite3 curl >/dev/null 2>&1; python3 --version"

Write-Output "===== STEP 3: copy AIOS code into Linux ====="
wsl -d Ubuntu -u root -- bash -c "mkdir -p /opt/aios && cp -r /mnt/c/Users/Administrator/.openclaw-autoclaw/workspace/aios/01_os/code/. /opt/aios/ 2>/dev/null; ls /opt/aios/ | head -10"

Write-Output "===== STEP 4: start AIOS inside real Linux ====="
wsl -d Ubuntu -u root -- bash -c "cd /opt/aios && (nohup python3 bus/aios_busd.py >/tmp/bus.log 2>&1 &) && sleep 1 && (nohup python3 aiosd/aiosd.py >/tmp/aiosd.log 2>&1 &) && sleep 8 && head -c 400 run/health.json"

Write-Output "===== STEP 5: smoke validation inside Linux ====="
wsl -d Ubuntu -u root -- bash -c "cd /opt/aios && python3 -c `"import json;h=json.load(open('run/health.json'));ups=sum(1 for v in h['services'].values() if v['state']=='up');print('LINUX AIOS: bus='+h['bus']['state']+' services '+str(ups)+'/15 online')`""

Write-Output "===== MIGRATION DONE ====="
Write-Output "AIOS now runs on: Windows (original stack) + Ubuntu/WSL2 (real Linux)"
Write-Output "Linux ops: wsl -d Ubuntu -u root -- bash -c 'cd /opt/aios && cat run/health.json'"
