import json
import psutil
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional
import os
import sys


try:
    from mcp_server.config import get_app_data_dir
except ImportError:
    def get_app_data_dir() -> Path:
        if sys.platform == 'win32':
            base = os.getenv('APPDATA')
            if not base:
                raise RuntimeError("APPDATA environment variable is not set on Windows.")
            p = Path(base) / 'LocalLens'
        else:
            p = Path.home() / '.config' / 'LocalLens'
        return p


APP_DIR = get_app_data_dir()
PORT_FILE = APP_DIR / "port.txt"
INSTALL_DIR_FILE = APP_DIR / "install_dir.txt"
PID_FILE = APP_DIR / "scheduler.pid"


def get_locallens_port() -> int:
    """Read the port LocalLens is listening on from the port file."""
    if PORT_FILE.exists():
        try:
            return int(PORT_FILE.read_text().strip())
        except ValueError:
            pass
    return 8000  # Default port


def get_installed_app_version() -> Optional[str]:
    """
    Ask the running LocalLens backend for its app_version (GET /api/stats).

    Used for the "Updates" menu — the tray/MCP server has no other way to
    know what version of the LocalLens desktop app/backend is installed.
    Returns None if the backend isn't running or reachable; callers should
    just skip the app-update check in that case.
    """
    if not PORT_FILE.exists():
        return None
    port = get_locallens_port()
    url = f"http://127.0.0.1:{port}/api/stats"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("app_version")
    except Exception:
        return None


def get_locallens_install_dir() -> Path:
    """
    Get the installation directory of the LocalLens backend.

    Reads install_dir.txt and returns the path only if it actually exists
    on disk. Stale paths (e.g. from a different machine or removed install)
    are silently ignored so callers can fall through to other strategies.
    """
    if INSTALL_DIR_FILE.exists():
        try:
            raw = INSTALL_DIR_FILE.read_text().strip()
            if not raw:
                return None
            path = Path(raw)
            if path.exists():
                return path
            # Path is stale — log it but don't delete (drive may be unmounted)
            print(f"[LocalLens] Warning: install_dir.txt points to non-existent path: {path}")
        except Exception as e:
            print(f"[LocalLens] Warning: could not read install_dir.txt: {e}")
    return None


def is_claude_running() -> bool:
    """Check if Claude desktop application is currently running."""
    try:
        for proc in psutil.process_iter(['name', 'exe']):
            try:
                name = (proc.info.get('name') or '').lower()
                exe = (proc.info.get('exe') or '').lower()
                # macOS: process is named "Claude", Windows: "claude.exe"
                if name in ('claude', 'claude.exe'):
                    return True
                # Catch renamed / helper variants (but not Claude Helper GPU etc.)
                if 'claude' in name and 'helper' not in name and 'gpu' not in name:
                    return True
                # Match by exe path as a last resort
                if 'claude.app' in exe or '\\claude\\' in exe:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        pass
    return False


def is_locallens_running() -> bool:
    """
    Check if LocalLens backend or desktop application is running.

    Strategy (most reliable first):
    1. HTTP-ping the specific port from port.txt.
       If the ping FAILS and port.txt exists, delete it — it is stale.
    2. Check for known LocalLens process names ('backend_server',
       'LocalLens.app', 'locallens.exe') or processes running from
       the LocalLens installation directory, excluding the tray itself.
    3. PID file fallback.
    """
    # 1. HTTP check — only attempt if port.txt exists
    if PORT_FILE.exists():
        port = get_locallens_port()
        url = f"http://127.0.0.1:{port}/"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                if resp.status in (200, 404, 403, 422):
                    return True
        except urllib.error.URLError:
            # Connection refused / network unreachable → server is dead.
            # Remove the stale port.txt so future checks skip this step
            # and so a fresh start can write a new port.txt cleanly.
            try:
                PORT_FILE.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception:
            pass

    # 2. Process name / exe path check — excludes our own tray
    try:
        install_dir = get_locallens_install_dir()
        install_dir_str = str(install_dir).lower() if install_dir else ""

        for proc in psutil.process_iter(['name', 'exe']):
            try:
                name = (proc.info.get('name') or '').lower()
                exe  = (proc.info.get('exe')  or '').lower()

                # Never match our own tray process
                if 'tray' in name or 'tray' in exe:
                    continue

                # Explicit known process names for the LocalLens backend
                if name in ('backend_server', 'backend_server.exe'):
                    # Extra guard: make sure it's from the LocalLens dir
                    if not install_dir_str or install_dir_str in exe:
                        return True
                    # If we can't verify the path, still accept it — better
                    # a false-positive than a false-negative here
                    if not install_dir_str:
                        return True

                # macOS .app bundle
                if 'locallens.app' in exe:
                    return True

                # Windows executable
                if name == 'locallens.exe':
                    return True

                # Python backend running from the LocalLens installation dir
                if install_dir_str and install_dir_str in exe:
                    return True

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        pass

    # 3. PID file fallback
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            proc = psutil.Process(pid)
            exe = ''
            try:
                exe = proc.exe().lower()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass
            name = proc.name().lower()
            if 'tray' not in name and 'tray' not in exe:
                if 'locallens' in exe or 'locallens' in name or 'backend_server' in name:
                    return True
        except (OSError, ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return False


def is_locallens_app_running() -> bool:
    """
    Check if the full LocalLens **desktop application** (the GUI wrapper,
    not just the backend server) is currently running.

    This is used to decide whether the tray should protect the backend:
      - App running → backend is "external" → don't touch it.
      - App NOT running but backend alive → it's an orphan → tray can stop it.

    Detection logic:
      - macOS: the app process is the main Electron/native binary inside
        "Local Lens.app/" whose name is NOT "backend_server" and NOT "tray".
      - Windows: look for "Local Lens.exe" or "LocalLens.exe" (not backend_server).
    """
    try:
        for proc in psutil.process_iter(['name', 'exe']):
            try:
                name = (proc.info.get('name') or '').lower()
                exe  = (proc.info.get('exe')  or '').lower()

                # Skip backend workers and our own tray
                if 'backend_server' in name or 'backend_server' in exe:
                    continue
                if 'tray' in name or 'tray' in exe:
                    continue

                # macOS: "Local Lens.app" in the exe path (the main app binary)
                if 'local lens.app' in exe or 'locallens.app' in exe:
                    return True

                # Windows: the main app executable
                if name in ('local lens.exe', 'locallens.exe'):
                    return True

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        pass
    return False


def find_backend_pids() -> list:
    """
    Return a list of PIDs for all running LocalLens backend processes.

    The backend runs as system Python but sets argv[0] = 'LocalLens-Backend'
    (or 'backend_server'). So we must match on cmdline[0], not process name
    or exe path.

    Also catches Python processes that have the LocalLens install dir in their
    cmdline (e.g. direct-launch via 'python main.py').

    Excludes any process whose cmdline contains 'tray'.
    """
    pids = []
    try:
        install_dir = get_locallens_install_dir()
        install_dir_str = str(install_dir).lower() if install_dir else ""

        # Known argv[0] / binary names the LocalLens backend uses
        BACKEND_ARGV0 = {
            'locallens-backend',
            'locallens-backend.exe',
            'backend_server',
            'backend_server.exe',
        }

        for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
            try:
                name    = (proc.info.get('name')   or '').lower()
                exe     = (proc.info.get('exe')    or '').lower()
                cmdline = proc.info.get('cmdline') or []
                argv0   = cmdline[0].lower() if cmdline else ''
                cmdline_str = ' '.join(cmdline).lower()

                # Never include the tray itself
                if 'tray' in name or 'tray' in exe or 'tray' in cmdline_str:
                    continue
                # Never include our own MCP server process
                if 'locallens-mcp' in cmdline_str:
                    continue

                # Primary match: argv[0] / process binary name is a known backend name
                if argv0 in BACKEND_ARGV0 or name in BACKEND_ARGV0:
                    pids.append(proc.info['pid'])
                    continue

                # Secondary: Python process running a script inside the install dir
                if install_dir_str and install_dir_str in cmdline_str and 'python' in name:
                    pids.append(proc.info['pid'])
                    continue

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        pass
    return pids


if __name__ == "__main__":
    print(f"Claude Running:           {is_claude_running()}")
    print(f"LocalLens Backend Running:{is_locallens_running()}")
    print(f"LocalLens App Running:    {is_locallens_app_running()}")
    print(f"Backend PIDs:             {find_backend_pids()}")
    print(f"LocalLens Install Dir:    {get_locallens_install_dir()}")
    print(f"Port file exists:         {PORT_FILE.exists()}")
    if PORT_FILE.exists():
        print(f"Port:                     {get_locallens_port()}")
