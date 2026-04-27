@echo off
title Frontend - React (port 5173)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
cd /d "C:\Users\kcm-s\Documents\Project Folder\Option Strategy\frontend"
npm run dev
pause
