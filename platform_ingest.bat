@echo off
setlocal
chcp 65001 >nul

set "PROJECT_DIR=%~dp0"
set "ENV_FILE=%PROJECT_DIR%platform_ingest.env"
set "ENV_EXAMPLE=%PROJECT_DIR%platform_ingest.env.example"

if not exist "%ENV_FILE%" (
  echo [ingest] platform_ingest.env not found, copying from platform_ingest.env.example
  copy "%ENV_EXAMPLE%" "%ENV_FILE%" >nul
  echo [ingest] Please edit platform_ingest.env, then run this script again.
  pause
  exit /b 1
)

cd /d "%PROJECT_DIR%"
python platform_ingest.py
pause
