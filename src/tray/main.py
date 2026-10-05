# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2026 Mayank Pandey - LL Agent. See LICENSE.md.
import sys

from .activation import ACTIVATE_FLAG


def main():
    # Before any tray: the Activate Pro child must not start a second tray, and
    # on Windows run_win_tray() would refuse it via its single-instance mutex.
    if ACTIVATE_FLAG in sys.argv:
        from .activate_window import run
        run()
        return
    if sys.platform == "darwin":
        from .tray_mac import run_mac_tray
        run_mac_tray()
    elif sys.platform == "win32":
        from .tray_win import run_win_tray
        run_win_tray()
    else:
        print(f"Unsupported platform: {sys.platform}")
        sys.exit(1)

if __name__ == "__main__":
    main()
