@echo off
setlocal
chcp 65001 >nul

set "APP_DIR=%~dp0"

cd /d "%APP_DIR%"
"%APP_DIR%DouyinDanmakuForwarder.exe"
pause
