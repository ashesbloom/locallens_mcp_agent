# SPDX-License-Identifier: BUSL-1.1
# Copyright (c) 2026 Mayank Pandey - LL Agent. See LICENSE.md.
from setuptools import setup

APP = ['locallens_tray_entrypoint.py']
# The terms travel with the app: LICENSE.md and NOTICE.md land in Contents/Resources.
DATA_FILES = ['LICENSE.md', 'NOTICE.md']

OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'icons/ll_red_trans/icon.icns',
    'plist': {
        'LSUIElement': True,  # Runs app without a dock icon (background app)
        'CFBundleName': 'LocalLens Agent',
        'CFBundleDisplayName': 'LocalLens Agent',
        'CFBundleIdentifier': 'com.locallens.agent',
    },
    # rumps/psutil: the tray app itself.
    # Everything else below is required so the BUNDLED PYTHON can also run
    # `-m mcp_server.main` (the MCP server) when Claude Desktop invokes it
    # directly — see get_mcp_command_config() in claude_connector.py.
    # py2app's modulegraph only auto-bundles modules it can trace via imports
    # from locallens_tray_entrypoint.py; since the tray itself never imports
    # `mcp`/`mcp_server.main`/`httpx` etc., those packages must be listed
    # explicitly here (verified via `import mcp_server.main` + sys.modules
    # trace, including httpx.AsyncClient()'s lazily-imported transport deps).
    'packages': [
        'rumps', 'psutil',
        'mcp_server', 'mcp',
        'httpx', 'httpx_sse', 'httpcore', 'h11', 'certifi', 'idna',
        'anyio', 'sse_starlette', 'starlette', 'uvicorn', 'click',
        'pydantic', 'pydantic_core', 'pydantic_settings',
        'typing_extensions', 'typing_inspection',
        'jsonschema', 'jsonschema_specifications', 'referencing', 'rpds',
        'attr', 'attrs', 'packaging',
        'dotenv',
        # Activate Pro window: pywebview, plus `tray` as a whole package so
        # activate_window.html ships next to activate_window.py.
        'tray', 'webview',
    ],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
)
