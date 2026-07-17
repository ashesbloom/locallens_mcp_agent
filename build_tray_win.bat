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
rmdir /S /Q build
rmdir /S /Q dist

echo Building application...
pyinstaller --noconfirm --onedir --windowed --name "LocalLens Agent" locallens_tray_entrypoint.py

echo Build complete! The executable is located in the dist/ folder.
pause
