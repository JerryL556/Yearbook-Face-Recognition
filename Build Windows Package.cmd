@echo off
setlocal

cd /d "%~dp0"

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
set "SPEC_FILE=%CD%\student_tagger_app_windows.spec"

if not exist "%VENV_PY%" (
    echo Missing virtual environment at:
    echo   %VENV_PY%
    echo Run "Launch Student Tagger.cmd" or the setup script first.
    pause
    exit /b 1
)

echo Checking PyInstaller...
"%VENV_PY%" -m pip show pyinstaller >nul 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    "%VENV_PY%" -m pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

if not exist "%SPEC_FILE%" (
    echo Missing spec file:
    echo   %SPEC_FILE%
    pause
    exit /b 1
)

echo Building Windows package...
"%VENV_PY%" -m PyInstaller --noconfirm --clean "%SPEC_FILE%"
if errorlevel 1 (
    echo Packaging failed.
    pause
    exit /b 1
)

echo.
echo Build finished.
echo Output folder:
echo   %CD%\dist\Student Photo Tagger
pause
