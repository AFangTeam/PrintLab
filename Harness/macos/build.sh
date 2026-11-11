#!/bin/zsh
set -euo pipefail
PRINTLAB_MAC_SOURCE=${0:A:h}
PRINTLAB_MAC_ROOT=${PRINTLAB_MAC_SOURCE:h:h}
PRINTLAB_MAC_BUILD="$PRINTLAB_MAC_ROOT/Runtime/macos-build"
PRINTLAB_MAC_APP="$PRINTLAB_MAC_BUILD/PrintLab.app"
PRINTLAB_MAC_ARCH=$(/usr/bin/uname -m)
mkdir -p "$PRINTLAB_MAC_BUILD/cache" "$PRINTLAB_MAC_SOURCE/Assets/PrintLab.iconset"
/usr/bin/swiftc "$PRINTLAB_MAC_SOURCE/DrawIcon.swift" -o "$PRINTLAB_MAC_BUILD/DrawIcon" -module-cache-path "$PRINTLAB_MAC_BUILD/cache" -framework AppKit
"$PRINTLAB_MAC_BUILD/DrawIcon" "$PRINTLAB_MAC_SOURCE/Assets/PrintLab-1024.png"
/usr/bin/sips -z 1024 1024 "$PRINTLAB_MAC_SOURCE/Assets/PrintLab-1024.png" >/dev/null
for PRINTLAB_ICON_SIZE in 16 32 128 256 512; do
  /usr/bin/sips -z "$PRINTLAB_ICON_SIZE" "$PRINTLAB_ICON_SIZE" "$PRINTLAB_MAC_SOURCE/Assets/PrintLab-1024.png" --out "$PRINTLAB_MAC_SOURCE/Assets/PrintLab.iconset/icon_${PRINTLAB_ICON_SIZE}x${PRINTLAB_ICON_SIZE}.png" >/dev/null
  PRINTLAB_ICON_RETINA=$(( PRINTLAB_ICON_SIZE * 2 ))
  /usr/bin/sips -z "$PRINTLAB_ICON_RETINA" "$PRINTLAB_ICON_RETINA" "$PRINTLAB_MAC_SOURCE/Assets/PrintLab-1024.png" --out "$PRINTLAB_MAC_SOURCE/Assets/PrintLab.iconset/icon_${PRINTLAB_ICON_SIZE}x${PRINTLAB_ICON_SIZE}@2x.png" >/dev/null
done
/usr/bin/iconutil -c icns "$PRINTLAB_MAC_SOURCE/Assets/PrintLab.iconset" -o "$PRINTLAB_MAC_SOURCE/Assets/PrintLab.icns"
mkdir -p "$PRINTLAB_MAC_APP/Contents/MacOS" "$PRINTLAB_MAC_APP/Contents/Resources"
/usr/bin/swiftc "$PRINTLAB_MAC_SOURCE/PrintLab.swift" -o "$PRINTLAB_MAC_APP/Contents/MacOS/PrintLab" -module-cache-path "$PRINTLAB_MAC_BUILD/cache" -framework AppKit -framework WebKit -target "${PRINTLAB_MAC_ARCH}-apple-macosx14.0" -O
cp "$PRINTLAB_MAC_SOURCE/Info.plist" "$PRINTLAB_MAC_APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :PrintLabWorkspace string $PRINTLAB_MAC_ROOT" "$PRINTLAB_MAC_APP/Contents/Info.plist"
cp "$PRINTLAB_MAC_SOURCE/Assets/PrintLab.icns" "$PRINTLAB_MAC_APP/Contents/Resources/PrintLab.icns"
/usr/bin/codesign --force --sign - --identifier com.afang.printlab "$PRINTLAB_MAC_APP"
/usr/bin/codesign --verify --deep --strict "$PRINTLAB_MAC_APP"
print -r -- "$PRINTLAB_MAC_APP"
