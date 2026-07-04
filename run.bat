@echo off
setlocal
if not exist .venv\Scripts\python.exe (
    echo Creating venv...
    python -m venv .venv
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
