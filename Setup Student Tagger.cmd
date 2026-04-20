@echo off
setlocal
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set "BASE_PY="
set "VENV_DIR=%CD%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "REQUIREMENTS=%CD%\student_tagger_app\requirements.txt"

python --version >nul 2>nul
if not errorlevel 1 set "BASE_PY=python"

if not defined BASE_PY (
    py --version >nul 2>nul
    if not errorlevel 1 set "BASE_PY=py"
)

if not defined BASE_PY (
    echo No usable Python installation was found.
    echo Install Python 3.11, 3.12, or 3.13, then run this file again.
    pause
    exit /b 1
)

for /f "delims=" %%v in ('%BASE_PY% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "PY_VER=%%v"
if not defined PY_VER (
    echo Could not detect the installed Python version.
    pause
    exit /b 1
)

echo Using Python %PY_VER%.

if exist "%VENV_PY%" (
    echo Existing virtual environment found at:
    echo   %VENV_DIR%
    echo.
    set /p "REBUILD=Delete and rebuild it with Python %PY_VER%? (Y/N): "
    if not defined REBUILD set "REBUILD=Y"
    set "REBUILD=!REBUILD: =!"
    if /I not "!REBUILD!"=="Y" if /I not "!REBUILD!"=="YES" (
        echo Setup cancelled.
        pause
        exit /b 0
    )
    rmdir /s /q "%VENV_DIR%"
    if exist "%VENV_DIR%" (
        echo Could not remove the existing .venv folder.
        pause
        exit /b 1
    )
)

echo Creating virtual environment...
%BASE_PY% -m venv .venv
if errorlevel 1 (
    echo Failed to create the virtual environment.
    pause
    exit /b 1
)

echo Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed while upgrading pip.
    pause
    exit /b 1
)

echo Installing app requirements...
"%VENV_PY%" -m pip install -r "%REQUIREMENTS%"
if errorlevel 1 (
    echo Requirement install failed.
    echo Copy the exact error message for the next Codex session.
    pause
    exit /b 1
)

echo.
echo Setup finished.
echo Next step:
echo   Double-click "Launch Student Tagger.cmd"
pause
