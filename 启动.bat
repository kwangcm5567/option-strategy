@echo off
title Option Strategy Launcher
chcp 65001 >nul

echo [1/3] 清理旧进程...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING" 2^>nul') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173 " ^| findstr "LISTENING" 2^>nul') do taskkill /PID %%a /F >nul 2>&1

echo [2/3] 启动 Backend (port 8000)...
start "Backend - FastAPI" cmd /k "C:\Users\kcm-s\Documents\Project Folder\Option Strategy\_start_backend.bat"

echo      等待后端就绪...
:wait_backend
timeout /t 2 /nobreak >nul
curl -s http://localhost:8000/ >nul 2>&1
if errorlevel 1 goto wait_backend
echo      后端已就绪！

echo [3/3] 启动 Frontend (port 5173)...
start "Frontend - Vite" cmd /k "C:\Users\kcm-s\Documents\Project Folder\Option Strategy\_start_frontend.bat"

echo      等待前端就绪...
:wait_frontend
timeout /t 2 /nobreak >nul
curl -s http://localhost:5173/ >nul 2>&1
if errorlevel 1 goto wait_frontend
echo      前端已就绪！

echo.
echo 打开浏览器...
start http://localhost:5173

echo.
echo 两个服务都在运行中，关闭此窗口不会停止服务。
echo 若要停止服务，请直接关闭 Backend 和 Frontend 窗口。
pause
