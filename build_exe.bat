@echo off
chcp 65001 >nul
echo ============================================
echo   政务工单脱敏系统 - PyInstaller 打包
echo ============================================
echo.

cd /d "%~dp0"

echo [1/3] 清理旧的构建产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist GovDataProcessor.spec del /q GovDataProcessor.spec

echo [2/3] 开始打包（首次较慢，请耐心等待）...
python -m PyInstaller ^
  --name GovDataProcessor ^
  --windowed ^
  --clean ^
  --noconfirm ^
  --add-data "static;static" ^
  --collect-submodules src ^
  --collect-submodules uvicorn ^
  --collect-submodules openpyxl ^
  run.py

if %ERRORLEVEL% neq 0 (
  echo.
  echo [错误] 打包失败，错误码 %ERRORLEVEL%
  pause
  exit /b %ERRORLEVEL%
)

echo [3/3] 打包完成！
echo.
echo 产物位置: dist\GovDataProcessor\GovDataProcessor.exe
echo.
echo 可直接双击运行，或用 Inno Setup 制作安装包。
echo.
pause
