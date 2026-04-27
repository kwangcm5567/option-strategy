@echo off
title Backend - FastAPI (port 8000)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
cd /d "C:\Users\kcm-s\Documents\Project Folder\Option Strategy\backend"
call venv\Scripts\activate.bat
python main.py
pause
