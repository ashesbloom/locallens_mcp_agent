"""
locallens_tray_entrypoint.py
Top-level entrypoint for the Tray app (macOS and Windows).
"""
import sys
import os

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    bundle_dir = sys._MEIPASS
    src_path = os.path.join(bundle_dir, "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
elif not getattr(sys, "frozen", False):
    # If running normally (unfrozen), ensure local src is on path
    src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "src"))
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

from tray.main import main

if __name__ == "__main__":
    main()
