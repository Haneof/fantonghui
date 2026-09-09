# AIOS Status Script
$ErrorActionPreference = "SilentlyContinue"
$code = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $code
if (-not (Test-Path "run\health.json")) { Write-Output "AIOS not running (no health.json)"; exit }
$h = Get-Content "run\health.json" -Encoding UTF8 | ConvertFrom-Json
$up = 0; $total = 0
foreach ($p in $h.services.PSObject.Properties) { $total++; if ($p.Value.state -eq "up") { $up++ } }
$busState = $h.bus.state
$epoch = [DateTime]::new(1970,1,1,8,0,0)
$age = [math]::Round(((Get-Date) - $epoch.AddSeconds($h.ts)).TotalSeconds, 1)
Write-Output "AIOS status: bus=$busState  services $up/$total online  (health age ${age}s)"
$py = @'
import sqlite3, os, json
db = os.path.join("run", "life_tree.db")
if os.path.exists(db):
    c = sqlite3.connect(db)
    n = c.execute("SELECT COUNT(*) FROM raw_log").fetchone()[0]
    s = c.execute("SELECT COUNT(*) FROM summary").fetchone()[0]
    print("life_tree: %d raw_log | %d hourly summaries" % (n, s))
else:
    print("life_tree: not created yet")
deg = os.path.join("run", "model_degrade.json")
if os.path.exists(deg):
    print("model degrade queue: %d items" % len(json.load(open(deg, encoding="utf-8"))))
ls = os.path.join("run", "lease_stats.json")
if os.path.exists(ls):
    st = json.load(open(ls, encoding="utf-8"))
    print("leases: granted %s | expired %s" % (st.get("granted",0), st.get("expired",0)))
'@
$py | python -
