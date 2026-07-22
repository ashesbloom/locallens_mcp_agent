# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the LocalLens Agent Windows tray app.
# Produces a --onedir bundle in dist/LocalLens Agent/ — NSIS packages this into an installer.

block_cipher = None

a = Analysis(
    ['locallens_tray_entrypoint.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('icons', 'icons'),
    ],
    hiddenimports=[
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'PIL.ImageFont',
        'psutil',
        'tray',
        'tray.main',
        'tray.tray_win',
        'tray.actions',
        'tray.status',
        'mcp_server',
        'mcp_server.claude_connector',
        'mcp_server.config',
        'mcp_server.license',
        'mcp_server.updater',
        'mcp_server.tools',
        'mcp_server.tools.status',
        'mcp_server.tools.queries',
        'mcp_server.tools.actions',
        'mcp_server.tools.pro_tools',
        'httpx',
        'packaging',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['rumps'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LocalLens Agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX corrupts bundled DLLs on Windows
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icons/ll_black/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='LocalLens Agent',
)
