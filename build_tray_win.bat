@echo off
echo Building LocalLens Agent for Windows...

IF NOT EXIST "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat
echo Installing requirements...
pip install .[tray]
pip install pyinstaller

echo Cleaning old builds...
taskkill /F /IM "LocalLens Agent.exe" 2>nul
rmdir /S /Q build 2>nul
rmdir /S /Q dist 2>nul

echo Building application...
pyinstaller --noconfirm locallens-tray-win.spec

echo Build complete! The executable is located in dist/LocalLens Agent/LocalLens Agent.exe
pause
