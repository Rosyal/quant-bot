#Requires -Version 5.0
# 在项目根目录 (含 main.py quant_bot.spec) 执行:
#   powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
# 需: pip install pyinstaller
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
python -m pip install "pyinstaller>=6.0" -q
python -m PyInstaller --noconfirm quant_bot.spec
Write-Host "完成: dist/quant-bot.exe  (在项目根目录下放 config/data 或通过 cd 到此目录后再运行)"
