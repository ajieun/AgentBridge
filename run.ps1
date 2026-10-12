# 启动本地 Agent Bridge
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        $python = Get-Command py -ErrorAction SilentlyContinue
    }
    if (-not $python) {
        Write-Host "未找到 Python。请先安装 Python 3.10+ 并勾选 Add to PATH。" -ForegroundColor Red
        exit 1
    }
    Write-Host "正在初始化 Python 虚拟环境..." -ForegroundColor Cyan
    & $python.Source -m venv .venv
    & .\.venv\Scripts\python.exe -m pip install -q -e .
}

& .\.venv\Scripts\python.exe -m agent_bridge serve @args
