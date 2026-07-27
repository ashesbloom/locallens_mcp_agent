; LocalLens Agent — Windows NSIS installer
; Produces a single-file setup.exe that installs the tray app and registers
; an uninstaller. No admin rights required (user-mode install to AppData).

!include "MUI2.nsh"

!define APP_NAME "LocalLens Agent"
!define APP_EXE "LocalLens Agent.exe"
!define MCP_EXE "locallens-mcp.exe"
!define REG_KEY "Software\LocalLens\Agent"

; Passed by CI as /DAPP_VERSION=v1.2.3. Note this must be a compile-time
; define (${...}), NOT $%APP_VERSION% — that form reads an environment
; variable on the END USER's machine at install time, where it is always
; empty, which is why Add/Remove Programs showed a blank version.
!ifndef APP_VERSION
  !define APP_VERSION "dev"
!endif

Name "${APP_NAME}"
OutFile "locallens-agent-installer.exe"
InstallDir "$LOCALAPPDATA\LocalLens Agent"
InstallDirRegKey HKCU "${REG_KEY}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

; ── UI ───────────────────────────────────────────────────────────────────────
!define MUI_ICON   "icons\ll_black\icon.ico"
!define MUI_UNICON "icons\ll_black\icon.ico"
; 164x314 BMP3, generated from icons/ll_black/icon.png by the release workflow
; so it can never drift from the shipped app icon.
; Guarded so a local `makensis installer_win.nsi` without a prior asset build
; still compiles, falling back to MUI's default artwork.
!if /FILEEXISTS "build\installer\welcome.bmp"
  !define MUI_WELCOMEFINISHPAGE_BITMAP "build\installer\welcome.bmp"
!endif
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "Welcome to ${APP_NAME} ${APP_VERSION}"
!define MUI_WELCOMEPAGE_TEXT \
    "This will install the ${APP_NAME} menu-bar app, which connects your local \
LocalLens photo library to Claude Desktop.$\r$\n$\r$\nEverything runs on this \
machine — no photos are ever uploaded.$\r$\n$\r$\nClick Next to continue."

!define MUI_FINISHPAGE_RUN '"$INSTDIR\${APP_EXE}"'
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${APP_NAME}"
!define MUI_FINISHPAGE_TEXT \
    "${APP_NAME} has been installed and will start automatically when you sign in.\
$\r$\n$\r$\nLook for it in the system tray, next to the clock."

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ── Install ──────────────────────────────────────────────────────────────────

Section "Install"
    ; Close anything holding files in $INSTDIR open, or the File /r below
    ; fails and NSIS aborts — silently, under /S.
    ;
    ; No /T here. /T also kills the killer's process tree, and the in-app
    ; updater (tray/actions.py _install_windows_update) launches this
    ; installer as a CHILD of the tray: DETACHED_PROCESS detaches the
    ; console, not the parent link, so /T made the installer kill itself
    ; before copying a single file.
    ExecWait 'taskkill /F /IM "${APP_EXE}"'
    ; Claude Desktop keeps locallens-mcp.exe (bundled in $INSTDIR) open as a
    ; long-lived stdio child, so it holds a lock for as long as Claude runs.
    ; Claude respawns it on next launch.
    ExecWait 'taskkill /F /IM "${MCP_EXE}"'
    Sleep 500

    ; Remove the previous version rather than overwriting in place, so files
    ; dropped between releases don't linger forever. Guarded on the app exe
    ; existing so a bad/hand-edited $INSTDIR can never wipe an unrelated
    ; directory. No user data lives here — that's all in ~/.config/LocalLens.
    IfFileExists "$INSTDIR\${APP_EXE}" 0 +2
        RMDir /r "$INSTDIR"

    SetOutPath "$INSTDIR"
    ; Copy everything PyInstaller put in dist\LocalLens Agent\
    ; Use * not *.* — the Windows *.* glob skips extension-less files
    File /r "dist\LocalLens Agent\*"

    ; Write uninstaller and registry entries
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    WriteRegStr HKCU "${REG_KEY}" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalLensAgent" \
        "DisplayName" "${APP_NAME}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalLensAgent" \
        "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalLensAgent" \
        "DisplayVersion" "${APP_VERSION}"

    ; Start Menu shortcut
    CreateDirectory "$SMPROGRAMS\LocalLens"
    CreateShortcut "$SMPROGRAMS\LocalLens\LocalLens Agent.lnk" "$INSTDIR\${APP_EXE}"

    ; Auto-start with Windows (tray app)
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" \
        "LocalLensAgent" '"$INSTDIR\${APP_EXE}"'

    ; Relaunch after a SILENT install only — that's the in-app update path,
    ; which killed the running tray above and must leave the user with the
    ; app running, not just autostarted at next login.
    ; Interactive installs relaunch via MUI_FINISHPAGE_RUN instead; doing
    ; both would launch twice and trip the single-instance mutex in
    ; tray_win.py with an "Already Running" box.
    IfSilent 0 +2
        Exec '"$INSTDIR\${APP_EXE}"'
SectionEnd

Section "Uninstall"
    ExecWait 'taskkill /F /IM "${APP_EXE}"'
    ExecWait 'taskkill /F /IM "${MCP_EXE}"'
    Sleep 500
    Delete "$SMPROGRAMS\LocalLens\LocalLens Agent.lnk"
    RMDir "$SMPROGRAMS\LocalLens"
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "LocalLensAgent"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalLensAgent"
    DeleteRegKey HKCU "${REG_KEY}"
    RMDir /r "$INSTDIR"
SectionEnd
