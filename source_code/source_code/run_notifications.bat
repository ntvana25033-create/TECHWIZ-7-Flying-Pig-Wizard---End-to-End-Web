@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" manage.py process_notifications
) else (
    py manage.py process_notifications
)
endlocal
