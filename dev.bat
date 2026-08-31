@echo off
chcp 65001 >nul
title GloLaunch AI - 快速开发模式

:: 用法: dev.bat [backend|frontend|both]
:: 默认: both

set BASE_DIR=%~dp0
cd /d "%BASE_DIR%"

:: 选择 Python 启动器（优先 py，规避 Windows 应用商店桩无响应）
set PY=
py --version >nul 2>&1
if not errorlevel 1 (
    set PY=py
) else (
    python --version >nul 2>&1
    if not errorlevel 1 (
        set PY=python
    ) else (
        echo [错误] 未检测到 Python，请先安装 Python 3.8+ 并勾选 "Add Python to PATH"
        pause
        exit /b 1
    )
)

set MODE=%1
if "%MODE%"=="" set MODE=both

if "%MODE%"=="backend" (
    echo [开发] 仅启动后端 FastAPI...
    start "Backend Dev" cmd /k "cd /d \"%BASE_DIR%backend\" & %PY% -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload"
) else if "%MODE%"=="frontend" (
    echo [开发] 仅启动前端 Vite...
    start "Frontend Dev" cmd /k "cd /d \"%BASE_DIR%frontend\" & npm run dev"
) else if "%MODE%"=="both" (
    echo [开发] 同时启动前后端...
    echo [启动] 后端 FastAPI (http://127.0.0.1:8002)...
    start "Backend Dev" cmd /k "cd /d \"%BASE_DIR%backend\" & %PY% -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload"

    timeout /t 3 >nul

    echo [启动] 前端 Vite (http://localhost:5173)...
    start "Frontend Dev" cmd /k "cd /d \"%BASE_DIR%frontend\" & npm run dev"

    timeout /t 5 >nul
    echo.
    echo [提示] 默认访问 http://localhost:5173（若 5173 被占用，Vite 会自动顺延端口）
) else (
    echo 用法: dev.bat [backend^|frontend^|both]
    pause
    exit /b 1
)

echo.
echo [OK] %MODE% 已启动，终端窗口将保持运行以查看日志
pause
