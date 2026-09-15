@echo off
chcp 65001 >nul 2>&1
title 政务工单脱敏系统

echo ========================================
echo   政务工单脱敏系统 启动中...
echo ========================================
echo.

cd /d "%~dp0"

REM 检查 Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

REM 检查依赖是否已安装
python -c "import fastapi, uvicorn, openpyxl, multipart" >nul 2>&1
if %errorlevel% neq 0 (
    echo [信息] 首次运行，正在安装依赖...
    pip install -r requirements.txt -q
    if %errorlevel% neq 0 (
        echo [错误] 依赖安装失败，请检查网络连接
        pause
        exit /b 1
    )
    echo [信息] 依赖安装完成
    echo.
)

REM 启动服务
echo [信息] 启动服务中...
echo [信息] 服务地址: http://127.0.0.1:8080
echo [信息] 浏览器将自动打开，如未打开请手动访问上述地址
echo [信息] 关闭此窗口即可停止服务
echo.

REM 延迟2秒后打开浏览器
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8080"

python run.py

pause
