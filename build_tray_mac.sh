#!/bin/bash
set -e

echo "Building LocalLens Agent for macOS..."

# Check for virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
echo "Installing requirements..."
pip install .[tray]
pip install py2app

echo "Cleaning old builds..."
rm -rf build dist

echo "Building application bundle..."
mv pyproject.toml pyproject.toml.bak
python setup_tray_mac.py py2app
mv pyproject.toml.bak pyproject.toml

echo "Creating DMG..."
# Check if hdiutil is available (macOS only)
if command -v hdiutil &> /dev/null; then
    hdiutil create -volname "LocalLens Agent" -srcfolder dist/"LocalLens Agent.app" -ov -format UDZO dist/LocalLensAgent.dmg
    echo "Build complete! DMG is located in the dist/ folder."
else
    echo "Build complete! .app is located in the dist/ folder."
fi
