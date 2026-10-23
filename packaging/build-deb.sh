#!/bin/bash
# Builds dist/widget-studio_<version>_all.deb
set -e
cd "$(dirname "$0")/.."

VERSION=$(python3 -c "import widget_studio; print(widget_studio.VERSION)")
PKG=widget-studio
APP_ID=io.github.cyb3rl00m.WidgetStudio
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT
chmod 755 "$ROOT"

install -Dm755 bin/widget-studio "$ROOT/usr/bin/widget-studio"
mkdir -p "$ROOT/usr/lib/widget-studio"
cp -r widget_studio "$ROOT/usr/lib/widget-studio/"
find "$ROOT/usr/lib/widget-studio" -name "__pycache__" -prune -exec rm -rf {} +
find "$ROOT/usr/lib/widget-studio" -type f -exec chmod 644 {} +
install -Dm644 "data/$APP_ID.desktop" "$ROOT/usr/share/applications/$APP_ID.desktop"
install -Dm644 "data/$APP_ID.svg" "$ROOT/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
install -Dm644 "data/$APP_ID.metainfo.xml" "$ROOT/usr/share/metainfo/$APP_ID.metainfo.xml"
install -Dm644 LICENSE "$ROOT/usr/share/doc/$PKG/copyright"

SIZE=$(du -sk "$ROOT/usr" | cut -f1)
mkdir -p "$ROOT/DEBIAN"
cat > "$ROOT/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1 (>= 1.4), fontconfig
Suggests: conky-all
Maintainer: cyb3rl00m <cyb3rl00m@users.noreply.github.com>
Homepage: https://github.com/cyb3rl00m/widget-studio
Description: Design desktop widgets and pin them to your screen
 Make clock, weather, calendar and system stats widgets, change their
 colors, fonts, size and position, and see them update live on your
 desktop. Works on COSMIC, KDE Plasma and X11 desktops. Widgets are
 drawn by Conky; the app can download a Wayland-capable Conky for you.
EOF

cat > "$ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q /usr/share/icons/hicolor || true
    command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
fi
EOF
chmod 755 "$ROOT/DEBIAN/postinst"

cat > "$ROOT/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
rm -rf /usr/lib/widget-studio/widget_studio/__pycache__
EOF
chmod 755 "$ROOT/DEBIAN/prerm"

mkdir -p dist
dpkg-deb --root-owner-group --build "$ROOT" "dist/${PKG}_${VERSION}_all.deb" >/dev/null
echo "Built dist/${PKG}_${VERSION}_all.deb"
