@echo off
setlocal

echo ========================================
echo Campus Coin - Setup
echo ========================================

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :error
) else (
    echo [1/4] Virtual environment already exists.
)

call .venv\Scripts\activate.bat

echo [2/4] Installing dependencies...
python -m pip install --upgrade pip
if errorlevel 1 goto :error
pip install -r requirements.txt
if errorlevel 1 goto :error

echo [3/4] Running migrations...
python manage.py migrate
if errorlevel 1 goto :error

echo [4/4] Creating administrator account...
echo If an administrator already exists, press Ctrl+C to skip this step.
python manage.py create_admin_account
if errorlevel 1 goto :error

echo.
echo Setup completed successfully.
echo Start the server with: python manage.py runserver
exit /b 0

:error
echo.
echo An error occurred during setup. Check .env and the error message above.
exit /b 1
