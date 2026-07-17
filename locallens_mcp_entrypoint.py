"""
locallens_mcp_entrypoint.py
Top-level PyInstaller entrypoint — no relative imports here.
This script is the real 'main' for the frozen executable.
It simply hands off to the package's main() which uses absolute imports internally.
"""
import sys
import os

# When frozen, PyInstaller sets sys._MEIPASS to the temp extraction dir.
# Ensure the 'src' directory inside the bundle is on sys.path so that
# 'import mcp_server' resolves correctly as a package.
if getattr(sys, "frozen", False):
    bundle_dir = sys._MEIPASS
    src_path = os.path.join(bundle_dir, "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

from mcp_server.main import main  # absolute import — works correctly

if __name__ == "__main__":
    main()
