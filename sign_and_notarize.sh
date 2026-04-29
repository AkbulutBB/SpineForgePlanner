#!/bin/bash
# Sign all binaries in /tmp (outside iCloud File Provider) then notarize
set -e

SIGN_IDENTITY="Developer ID Application: YILMAZ MERT CIMENLIK (T858A59JCR)"
APPLE_ID="mert@fanonet.com"
TEAM_ID="T858A59JCR"
APP_PASS="jovo-vmed-izdw-bszh"
SRC="dist/SpineForgePlanner.app"
TMP_APP="/tmp/SpineForgePlanner_sign.app"
DMG="SpineForgePlanner.dmg"

echo "[1] ditto to /tmp..."
rm -rf "$TMP_APP"
ditto "$SRC" "$TMP_APP"

echo "[2] Strip xattrs in /tmp..."
xattr -cr "$TMP_APP"

echo "[3] Sign all .so files..."
find "$TMP_APP" -type f -name "*.so" | while IFS= read -r f; do
    codesign -f -o runtime --timestamp -s "$SIGN_IDENTITY" "$f" 2>/dev/null && true
done

echo "[4] Sign all .dylib files..."
find "$TMP_APP" -type f -name "*.dylib" | while IFS= read -r f; do
    codesign -f -o runtime --timestamp -s "$SIGN_IDENTITY" "$f" 2>/dev/null && true
done

echo "[4b] Sign Python.framework binary..."
find "$TMP_APP" -path "*/Python.framework/Versions/*/Python" -type f | while IFS= read -r f; do
    codesign -f -o runtime --timestamp -s "$SIGN_IDENTITY" "$f" 2>/dev/null && echo "  signed: $f" || true
done

echo "[4c] Sign Python.framework bundle..."
find "$TMP_APP" -name "Python.framework" -type d | while IFS= read -r f; do
    codesign -f -o runtime --timestamp -s "$SIGN_IDENTITY" "$f" 2>/dev/null && echo "  signed: $f" || true
done

echo "[5] Sign the main executable..."
codesign -f -o runtime --timestamp -s "$SIGN_IDENTITY" "$TMP_APP/Contents/MacOS/SpineForgePlanner"

echo "[6] Sign the .app bundle..."
codesign -f -o runtime --timestamp -s "$SIGN_IDENTITY" "$TMP_APP"
echo "Bundle sign exit: $?"

echo "[7] Verify..."
codesign --display --verbose=1 "$TMP_APP" 2>&1 | grep "Authority\|Signature\|flags"

echo "[8] Move back..."
rm -rf "$SRC"
mv "$TMP_APP" "$SRC"

echo "[9] Create DMG..."
rm -f "$DMG"
hdiutil create -volname "SpineForgePlanner" -srcfolder "$SRC" -ov -format UDBZ "$DMG"

echo "[10] Sign DMG..."
codesign -s "$SIGN_IDENTITY" --timestamp "$DMG"
echo "DMG sign exit: $?"

echo "[11] Submit for notarization..."
xcrun notarytool submit "$DMG" \
    --apple-id "$APPLE_ID" \
    --team-id "$TEAM_ID" \
    --password "$APP_PASS" \
    --wait

echo "[12] Staple..."
xcrun stapler staple "$DMG"

echo "[13] Final Gatekeeper check..."
spctl -a -vv -t install "$DMG" 2>&1

echo "=== DONE ==="
