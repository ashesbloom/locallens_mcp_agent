#!/bin/bash
# Fix_LocalLens_Agent.command
# Double-click this file to allow LocalLens Agent to open on macOS.
# It removes the Gatekeeper quarantine flag and applies an ad-hoc signature.

set -e

APP="/Applications/LocalLens Agent.app"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  LocalLens Agent — macOS Security Fix"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ ! -d "$APP" ]; then
  echo "⚠️  LocalLens Agent.app not found in /Applications."
  echo "   Please drag the app to /Applications first, then run this script."
  echo ""
  read -p "Press Enter to close..."
  exit 1
fi

echo "→ Removing quarantine flag..."
xattr -cr "$APP"

echo "→ Applying ad-hoc code signature..."
codesign --force --deep --sign - "$APP"

echo ""
echo "✅  Done! LocalLens Agent should now open normally."
echo "   Double-click the app in /Applications to launch it."
echo ""
read -p "Press Enter to close..."
