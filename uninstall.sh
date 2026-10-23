#!/usr/bin/env bash
# Universal Uninstaller for Fan Control
set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "==> Requesting administrator privileges to uninstall..."
    exec sudo bash "$0" "$@"
fi

PREFIX="${PREFIX:-/usr/local}"

echo "==========================================="
echo "   Uninstalling Fan Control                "
echo "==========================================="

# Remove executables and libraries
for base in "$PREFIX" "/usr" "/usr/local"; do
    if [ -d "$base" ]; then
        rm -f "$base/bin/fan-control" "$base/bin/fan-gui"
        rm -f "$base/lib/libfan-ec.so" "$base/lib64/libfan-ec.so"
        rm -f "$base/share/applications/fan-control.desktop"
        rm -f "$base/share/icons/hicolor/"*"/apps/fan-control.png"
        rm -f "$base/share/icons/hicolor/"*"/apps/fan-control-tray.png"
        rm -f "$base/share/icons/hicolor/scalable/apps/fan-control-symbolic.svg"
    fi
done

echo "==> Refreshing system caches..."
if command -v ldconfig >/dev/null 2>&1; then
    ldconfig 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications 2>/dev/null || true
    update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
    gtk-update-icon-cache -q -t -f "$PREFIX/share/icons/hicolor" 2>/dev/null || true
fi

echo ""
echo "=========================================================="
echo "  Fan Control has been successfully uninstalled."
echo "=========================================================="
