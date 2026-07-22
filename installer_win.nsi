; LocalLens Agent — Windows NSIS installer
; Produces a single-file setup.exe that installs the tray app and registers
; an uninstaller. No admin rights required (user-mode install to AppData).

!define APP_NAME "LocalLens Agent"
!define APP_EXE "LocalLens Agent.exe"
!define REG_KEY "Software\LocalLens\Agent"

Name "${APP_NAME}"
OutFile "locallens-agent-installer.exe"
InstallDir "$LOCALAPPDATA\LocalLens Agent"
InstallDirRegKey HKCU "${REG_KEY}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

Page directory
Page instfiles

Section "Install"
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
        "DisplayVersion" "$%APP_VERSION%"

    ; Start Menu shortcut
    CreateDirectory "$SMPROGRAMS\LocalLens"
    CreateShortcut "$SMPROGRAMS\LocalLens\LocalLens Agent.lnk" "$INSTDIR\${APP_EXE}"

    ; Auto-start with Windows (tray app)
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" \
        "LocalLensAgent" '"$INSTDIR\${APP_EXE}"'
SectionEnd

Section "Uninstall"
    Delete "$SMPROGRAMS\LocalLens\LocalLens Agent.lnk"
    RMDir "$SMPROGRAMS\LocalLens"
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "LocalLensAgent"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalLensAgent"
    DeleteRegKey HKCU "${REG_KEY}"
    RMDir /r "$INSTDIR"
SectionEnd
