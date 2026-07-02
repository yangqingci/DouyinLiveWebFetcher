@echo off
setlocal
chcp 65001 >nul

set "PORTABLE_DIR=%~dp0"
cd /d "%PORTABLE_DIR%\.."

powershell -NoProfile -ExecutionPolicy Bypass -File "%PORTABLE_DIR%build.ps1" -Version final
pause
