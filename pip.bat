@echo off
setlocal
if not exist .venv\Scripts\python.exe (
    python -m venv .venv
)
.venv\Scripts\python.exe -m pip %*
