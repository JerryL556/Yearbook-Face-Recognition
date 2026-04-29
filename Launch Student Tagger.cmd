@echo off
setlocal

cd /d "%~dp0"

set "BASE_PY="
set "VENV_PY=%CD%\.venv\Scripts\python.exe"
set "REQUIREMENTS=%CD%\student_tagger_app\requirements.txt"
set "RUNNER=%CD%\student_tagger_app\run.py"

if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys" >nul 2>nul
    if errorlevel 1 (
        echo The existing .venv is broken.
        echo It points to a Python install that is no longer available.
        echo.
        echo Run "Setup Student Tagger with Python 3.11.cmd" again after confirming Python 3.11 is installed.
        pause
        exit /b 1
    )
    goto use_venv
)

python --version >nul 2>nul
if not errorlevel 1 (
    set "BASE_PY=python"
    goto detect_base
)

py -3.11 --version >nul 2>nul
if not errorlevel 1 (
    set "BASE_PY=py -3.11"
    goto detect_base
)

py --version >nul 2>nul
if not errorlevel 1 (
    set "BASE_PY=py"
    goto detect_base
)

if not defined BASE_PY (
    echo Could not find a usable Python installation.
    echo Install Python 3.11, 3.12, or 3.13, then run this launcher again.
    pause
    exit /b 1
)

:detect_base
for /f "tokens=2" %%v in ('%BASE_PY% --version 2^>nul') do set "PY_VER=%%v"
if not defined PY_VER (
    echo Could not find a usable Python installation.
    echo Install Python 3.11, 3.12, or 3.13, then run this launcher again.
    pause
    exit /b 1
)

if not exist "%VENV_PY%" (
    echo Creating virtual environment...
    %BASE_PY% -m venv .venv >nul 2>nul
    if errorlevel 1 (
        echo Could not create the virtual environment.
        echo Make sure Python 3.11, 3.12, or 3.13 is installed and available.
        pause
        exit /b 1
    )
)

:use_venv
for /f "tokens=2" %%v in ('"%VENV_PY%" --version 2^>nul') do set "VENV_VER=%%v"
if not defined VENV_VER (
    echo Could not detect the Python version inside .venv.
    pause
    exit /b 1
)

echo Checking Python packages...
"%VENV_PY%" -c "import fastapi, uvicorn, numpy, PIL" >nul 2>nul
if errorlevel 1 (
    echo Installing app requirements...
    "%VENV_PY%" -m pip install --upgrade pip
    if errorlevel 1 (
        echo Failed while upgrading pip.
        pause
        exit /b 1
    )

    "%VENV_PY%" -m pip install -r "%REQUIREMENTS%"
    if errorlevel 1 (
        echo Failed while installing requirements.
        echo If the error mentions dlib, that dependency still needs to install successfully.
        pause
        exit /b 1
    )
)

echo Starting Student Photo Tagger...
echo The app will open the browser automatically.
echo Leave this window open while using the app.
echo.
"%VENV_PY%" "%RUNNER%"

echo.
echo The app has stopped.
pause
