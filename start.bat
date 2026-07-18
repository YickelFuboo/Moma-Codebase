@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
    mcb
    goto :eof
)

where poetry >nul 2>&1
if %errorlevel%==0 (
    poetry run mcb
    goto :eof
)

echo [ERROR] 未找到 .venv 或 poetry，请先执行: poetry install
exit /b 1
