@echo off
chcp 65001 >nul
title GloLaunch AI - 启动服务

echo ============================================================
echo   GloLaunch AI 全链路跨境智能上新引擎
echo ============================================================
echo.

:: 切换到脚本所在目录（项目根目录）
set BASE_DIR=%~dp0
cd /d "%BASE_DIR%"

:: ========== 0. 选择 Python 启动器（优先 py，规避 Windows 应用商店桩无响应）==========
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
        echo          下载地址: https://www.python.org/downloads/
        pause
        exit /b 1
    )
)
echo [OK] 使用 Python 启动器: %PY%

:: ========== 1. 环境检测 ==========
echo [检查] 验证运行环境...

:: 检查 Node.js
node --version 2>nul | findstr /C:"v" >nul
if errorlevel 1 (
    echo [错误] 未检测到 Node.js，请先安装 Node.js 18+ 并加入 PATH
    echo          下载地址: https://nodejs.org/
    pause
    exit /b 1
)
echo [OK] Node.js 已安装

:: 检查后端依赖（uvicorn）
%PY% -m pip show uvicorn >nul 2>&1
if errorlevel 1 (
    echo [提示] 未检测到后端依赖，正在安装（首次约需 3-5 分钟，请勿关闭窗口）...
    %PY% -m pip install -r backend\requirements.txt
    if errorlevel 1 (
        echo [错误] 后端依赖安装失败，请检查网络连接后重新双击本文件。
        pause
        exit /b 1
    )
) else (
    echo [OK] 后端依赖已就绪
)

:: 检查前端依赖
if not exist "frontend\node_modules\" (
    echo [提示] 正在安装前端依赖（首次约需 2-4 分钟，请勿关闭窗口）...
    cd frontend
    call npm install --legacy-peer-deps
    cd ..
    if errorlevel 1 (
        echo [错误] 前端依赖安装失败，请检查网络连接后重新双击本文件。
        pause
        exit /b 1
    )
) else (
    echo [OK] 前端依赖已就绪
)

echo.
echo [OK] 环境检查完成，准备启动...
echo.

:: ========== 2. 清理旧进程 ==========
echo [清理] 检查端口占用...
netstat -aon 2>nul | findstr ":8000.*LISTENING" >nul
if not errorlevel 1 (
    for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000.*LISTENING"') do (
        taskkill /PID %%a /F >nul 2>&1
        echo [释放] 已关闭端口 8000 的旧进程 (PID %%a)
    )
)
netstat -aon 2>nul | findstr ":5173.*LISTENING" >nul
if not errorlevel 1 (
    for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":5173.*LISTENING"') do (
        taskkill /PID %%a /F >nul 2>&1
        echo [释放] 已关闭端口 5173 的旧进程 (PID %%a)
    )
)
timeout /t 1 >nul

:: ========== 3. 启动后端 ==========
echo.
echo [启动] 后端 FastAPI (http://127.0.0.1:8000)...
start "GloLaunch Backend" cmd /k "title GloLaunch Backend & cd /d \"%BASE_DIR%backend\" & %PY% -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

:: 等待后端初始化
timeout /t 3 >nul

:: ========== 4. 启动前端 ==========
echo [启动] 前端 Vite 工作台 (http://localhost:5173)...
start "GloLaunch Frontend" cmd /k "title GloLaunch Frontend & cd /d \"%BASE_DIR%frontend\" & npm run dev"

:: 等待前端编译
timeout /t 5 >nul

:: ========== 5. 打开浏览器 ==========
echo.
echo ============================================================
echo   OK GloLaunch AI 启动完毕！
echo ============================================================
echo.
echo   前端工作台: http://localhost:5173
echo   后端 API   : http://127.0.0.1:8000/docs
echo   健康检查   : http://127.0.0.1:8000/
echo.
echo   说明:
echo     - 每个服务在独立的终端窗口中运行
echo     - 关闭窗口即可停止对应服务
echo     - 后端支持热重载（修改代码自动生效）
echo     - 前端支持热模块替换（保存即刷新）
echo.
echo   如需重新启动，请再次双击本文件
echo ============================================================
echo.

:: 自动打开浏览器（若 5173 被占用 Vite 会自动顺延端口，浏览器将尝试 5173）
start "" "http://localhost:5173"

pause
