@echo off
chcp 65001 >nul
title GloLaunch AI
cd /d "%~dp0"

echo.
echo   GloLaunch AI - 快速启动
echo   ========================
echo.

:: 启动后端
start "GloLaunch Backend" cmd /k "title Backend & cd /d "%~dp0backend" & python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload"

:: 等待后端
timeout /t 2 >nul

:: 启动前端
start "GloLaunch Frontend" cmd /k "title Frontend & cd /d "%~dp0frontend" & npm run dev"

:: 等待前端
timeout /t 4 >nul

:: 打开浏览器
start "" "http://localhost:5173"

echo.
echo   OK 启动完成！
echo.
echo   工作台: http://localhost:5173
echo   API文档: http://127.0.0.1:8002/docs
echo.
echo   关闭两个黑色窗口即可停止服务
echo.

timeout /t 3 >nul
