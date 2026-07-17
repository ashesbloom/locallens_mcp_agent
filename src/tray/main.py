import sys

def main():
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
