@echo off
setlocal EnableExtensions

cd /d "%~dp0"

if not exist "pyproject.toml" (
    echo [error] 请在项目根目录运行 start.bat
    exit /b 1
)

where poetry >nul 2>&1
if errorlevel 1 (
    echo [error] 未找到 poetry，请先安装并加入 PATH
    exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
    echo [error] 未找到 npm，请先安装 Node.js
    exit /b 1
)

if not defined SERVICE_PORT set SERVICE_PORT=9001

echo.
echo [start] 启动后端  http://localhost:%SERVICE_PORT%
start "Pando Backend" cmd /k "cd /d %CD% && poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port %SERVICE_PORT%"

echo [start] 启动前端  http://localhost:5173
start "Pando Frontend" cmd /k "cd /d %CD%\website && npm run dev"

echo.
echo 前后端已在独立窗口中运行，关闭对应窗口或按 Ctrl+C 即可停止。
echo.

endlocal
