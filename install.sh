#!/usr/bin/env bash
# Universal Installer for Fan Control on any Linux distribution
set -e

# Ensure running with root privileges
if [ "$(id -u)" -ne 0 ]; then
    echo "==> Requesting administrator privileges to install..."
    exec sudo bash "$0" "$@"
fi

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PREFIX="${PREFIX:-/usr/local}"
BIN_DIR="$PREFIX/bin"
LIB_DIR="$PREFIX/lib"
DATA_DIR="$PREFIX/share"
APPS_DIR="$DATA_DIR/applications"
ICONS_DIR="$DATA_DIR/icons/hicolor"

echo "==========================================="
echo "   Installing Fan Control to $PREFIX       "
echo "==========================================="

# 1. Compile C binary and shared library if needed
if [ ! -f "$DIR/build/fan-control" ] || [ ! -f "$DIR/build/libfan-ec.so" ] || [ "$1" = "--rebuild" ]; then
    echo "==> Compiling hardware EC binaries..."
    cmake -B build -S . -DCMAKE_BUILD_TYPE=Release
    cmake --build build -j"$(nproc)"
fi

# 2. Create destination directories
echo "==> Creating system directories..."
mkdir -p "$BIN_DIR" "$LIB_DIR" "$APPS_DIR"

# 3. Install binaries & libraries
echo "==> Installing executables and libraries..."
install -m 755 "$DIR/build/fan-control" "$BIN_DIR/fan-control"
install -m 755 "$DIR/fan_gui.py" "$BIN_DIR/fan-gui"
install -m 755 "$DIR/build/libfan-ec.so" "$LIB_DIR/libfan-ec.so"

# 4. Install desktop entry
echo "==> Installing desktop launcher..."
install -m 644 "$DIR/fan-control.desktop" "$APPS_DIR/fan-control.desktop"

# 5. Install high-resolution icons
echo "==> Installing application icons..."
if [ -d "$DIR/assets/icons/hicolor" ]; then
    cp -r "$DIR/assets/icons/hicolor/"* "$ICONS_DIR/"
fi

# 6. Configure hardware EC raw I/O capabilities (Passwordless access)
echo "==> Configuring direct EC hardware permissions..."
if command -v setcap >/dev/null 2>&1; then
    setcap cap_sys_rawio+ep "$BIN_DIR/fan-control"
    echo "    [OK] cap_sys_rawio granted to $BIN_DIR/fan-control"
else
    echo "    [NOTE] 'setcap' not found. You may need to run fan-control with sudo or install libcap."
fi

# 7. Update shared library and system caches
echo "==> Refreshing system caches..."
if command -v ldconfig >/dev/null 2>&1; then
    ldconfig 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q "$APPS_DIR" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f "$ICONS_DIR" 2>/dev/null || true
fi

echo ""
echo "=========================================================="
echo "  Fan Control successfully installed!"
echo "=========================================================="
echo "  • Launch GUI:     Search 'Fan Control' or run 'fan-gui'"
echo "  • CLI Query:      fan-control dump"
echo "  • CLI JSON:       fan-control json"
echo "  • To Uninstall:   sudo ./uninstall.sh"
echo "=========================================================="
