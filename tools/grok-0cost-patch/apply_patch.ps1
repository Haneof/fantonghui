# ==========================================================================
#  apply_patch.ps1 —— Grok 0元购流水线补丁的 PowerShell 入口
#
#  为什么需要这个文件:
#    PowerShell 不认识 \" 转义 (那是 CMD/bash 的语法)。
#    `python -c "....\"....\"...."` 会在第一个 \" 处提前闭合字符串,
#    剩下的内容被当成命令名 -> CommandNotFoundException。
#    所以: 永远不要在 PS 里写 python -c "长脚本",
#          用 .py 文件 (本脚本就是这么调的)。
#
#  用法:
#    .\apply_patch.ps1              # 打补丁 + 生成 bat
#    .\apply_patch.ps1 -DryRun      # 只看 diff, 不写盘
# ==========================================================================

[CmdletBinding()]
param(
    [string] $Reg    = "D:\API中转\grok\run_0cost_grok_register.py",
    [string] $Bat    = "D:\API中转\grok\启动_Grok_0元购全自动流水线.bat",
    [string] $Python = "python",
    [switch] $DryRun,
    [switch] $NoBat
)

$ErrorActionPreference = 'Stop'

# 控制台切 UTF-8, 否则 emoji / 中文输出会变成乱码
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding           = [System.Text.Encoding]::UTF8
    chcp 65001 > $null
} catch { Write-Warning "无法切换控制台编码, 输出可能有乱码: $_" }

$patcher = Join-Path $PSScriptRoot 'exact_patch.py'
if (-not (Test-Path -LiteralPath $patcher)) {
    throw "找不到补丁器: $patcher"
}
if (-not (Test-Path -LiteralPath $Reg)) {
    throw "找不到目标源码: $Reg"
}

# 用数组传参, PowerShell 会自己处理带空格/中文的路径, 不用手动加引号
$argv = @($patcher, '--reg', $Reg, '--bat', $Bat)
if ($DryRun) { $argv += '--dry-run' }
if ($NoBat)  { $argv += '--no-bat' }

Write-Host "==> $Python $($argv -join ' ')" -ForegroundColor Cyan
& $Python @argv
$code = $LASTEXITCODE

if ($code -ne 0) {
    Write-Host "[FAIL] 补丁未应用, 源文件保持原样 (退出码 $code)" -ForegroundColor Red
    exit $code
}

Write-Host "[DONE] 完成。" -ForegroundColor Green
