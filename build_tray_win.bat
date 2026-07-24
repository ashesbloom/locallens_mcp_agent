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
taskkill /F /IM "LocalLens Agent.exe" /T 2>nul

:: Wait 3 seconds for Windows to release all file handles (needed when project is inside OneDrive)
timeout /t 3 /nobreak >nul

:: Use PowerShell Remove-Item which handles OneDrive-locked folders correctly
powershell -Command "Remove-Item -Path 'build' -Recurse -Force -ErrorAction SilentlyContinue"
powershell -Command "Remove-Item -Path 'dist' -Recurse -Force -ErrorAction SilentlyContinue"

:: Another short wait to let OneDrive settle after the delete
timeout /t 2 /nobreak >nul

echo Building application...
pyinstaller --noconfirm locallens-tray-win.spec
if %ERRORLEVEL% neq 0 (
    echo.
    echo BUILD FAILED! See errors above.
    echo TIP: If you see "Access Denied" or "process cannot access the file",
    echo      close any File Explorer window that has the dist\ folder open,
    echo      pause OneDrive sync temporarily, and run the script again.
    pause
    exit /b 1
)

echo.
echo Building locallens-mcp.exe (bundled alongside the tray so "Connect to
echo Claude" can find it without a separate pip/uv install)...
pyinstaller --noconfirm locallens-mcp.spec
if %ERRORLEVEL% neq 0 (
    echo.
    echo BUILD FAILED building locallens-mcp.exe! See errors above.
    pause
    exit /b 1
)
copy /Y "dist\locallens-mcp.exe" "dist\LocalLens Agent\locallens-mcp.exe" >nul

echo.
echo Build complete!
echo Executable: dist\LocalLens Agent\LocalLens Agent.exe
pause
