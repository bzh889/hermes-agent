# ============================================================
#  抓 0x1E 藍屏兇手 — minidump + Driver Verifier(標準強度)
#  用法:對此檔 右鍵 -> 以 PowerShell 執行 (系統管理員)
#  或在管理員 PowerShell:  powershell -ExecutionPolicy Bypass -File 這個檔
# ============================================================
$ErrorActionPreference = 'Stop'

# --- 檢查管理員 ---
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[!] 需要系統管理員權限。正在嘗試自我提權..." -ForegroundColor Yellow
    Start-Process powershell.exe "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

Write-Host "=== 1. 開啟記憶體傾印 (minidump) ===" -ForegroundColor Cyan
$cc = 'HKLM:\SYSTEM\CurrentControlSet\Control\CrashControl'
Set-ItemProperty $cc -Name CrashDumpEnabled     -Value 7 -Type DWord      # 7 = Automatic
Set-ItemProperty $cc -Name AlwaysKeepMemoryDump -Value 1 -Type DWord
Set-ItemProperty $cc -Name MinidumpDir          -Value '%SystemRoot%\Minidump' -Type ExpandString
$dumpDir = Join-Path $env:SystemRoot 'Minidump'
if (-not (Test-Path $dumpDir)) { New-Item -ItemType Directory -Path $dumpDir | Out-Null }
Write-Host "  minidump 目錄: $dumpDir  (已建立/存在)" -ForegroundColor Green

Write-Host "`n=== 2. Driver Verifier — 標準檢測,只針對 4 顆第三方驅動 ===" -ForegroundColor Cyan
& verifier /standard /driver BzProtect.sys pigeon.sys dgmaster.sys DGMinFlt.sys

Write-Host "`n=== 3. 目前 Verifier 狀態 ===" -ForegroundColor Cyan
& verifier /querysettings

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host " 設定完成。Verifier 需【重開機】後生效。" -ForegroundColor Green
Write-Host " 重開機後正常使用,下次藍屏會在 C:\Windows\Minidump 產生 .dmp。" -ForegroundColor Green
Write-Host " 拿到 dump 後把路徑告訴我,我幫你解析點名兇手。" -ForegroundColor Green
Write-Host ""
Write-Host " * 若當機變太頻繁想關掉 Verifier:" -ForegroundColor Yellow
Write-Host "     管理員 PowerShell 執行:  verifier /reset   然後重開機" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Read-Host "`n按 Enter 結束"
