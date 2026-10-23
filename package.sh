#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "==> 1. Compiling C CLI and EC shared library..."
cmake -B build -S . -DCMAKE_BUILD_TYPE=Release
cmake --build build -j"$(nproc)"

mkdir -p "$DIR/dist"

echo "==> 2. Generating Ubuntu/Debian (.deb), Fedora/RHEL (.rpm), and Universal (.tar.gz)..."
cd build
rm -f install_manifest.txt 2>/dev/null || true
cpack -G DEB
cpack -G RPM
cpack -G TGZ
cp -f fan-control_*.deb "$DIR/dist/" 2>/dev/null || true
cp -f fan-control_*.rpm "$DIR/dist/" 2>/dev/null || true
cp -f fan-control_*.tar.gz "$DIR/dist/" 2>/dev/null || true
cd "$DIR"

echo "==> 3. Generating Arch Linux package (.pkg.tar.zst)..."
ARCH_STAGING="$DIR/build/arch_pkg_root"
rm -rf "$ARCH_STAGING"
mkdir -p "$ARCH_STAGING"
DESTDIR="$ARCH_STAGING" cmake --install build --prefix /usr >/dev/null

INSTALLED_SIZE=$(du -sb "$ARCH_STAGING/usr" | awk '{print $1}')
BUILD_DATE=$(date +%s)

cat <<EOF > "$ARCH_STAGING/.PKGINFO"
pkgname = fan-control
pkgbase = fan-control
pkgver = 1.2.0-1
pkgdesc = Hardware EC Fan Control Utility and Native Desktop GUI
url = https://github.com/shreyash/fan-control
builddate = $BUILD_DATE
packager = Fan Control Maintainers <maintainers@fan-control.local>
size = $INSTALLED_SIZE
arch = x86_64
license = GPL3
depend = python
depend = python-pyqt6
depend = libcap
depend = polkit
EOF

if [ -f "$DIR/packaging/fan-control.install" ]; then
    cp -f "$DIR/packaging/fan-control.install" "$ARCH_STAGING/.INSTALL"
    tar --zstd -cf "$DIR/dist/fan-control-1.2.0-1-x86_64.pkg.tar.zst" -C "$ARCH_STAGING" .PKGINFO .INSTALL usr
else
    tar --zstd -cf "$DIR/dist/fan-control-1.2.0-1-x86_64.pkg.tar.zst" -C "$ARCH_STAGING" .PKGINFO usr
fi

cp -f "$DIR/PKGBUILD" "$DIR/dist/" 2>/dev/null || true

# Optional standalone binary if requested with --standalone
if [ "$1" = "--standalone" ] || [ "$1" = "-s" ]; then
    echo "==> Building optional standalone frozen binary with PyInstaller..."
    PYI=""
    if command -v pyinstaller >/dev/null 2>&1; then
        PYI="pyinstaller"
    elif [ -x "$HOME/.local/bin/pyinstaller" ]; then
        PYI="$HOME/.local/bin/pyinstaller"
    fi
    if [ -n "$PYI" ]; then
        "$PYI" --noconfirm --clean --onefile --windowed \
            --name fan-gui-standalone \
            --add-data "assets/fan-control.png:assets" \
            fan_gui.py
    fi
fi

echo ""
echo "=========================================================="
echo "==> Packaging complete! All packages built in dist/:"
echo "=========================================================="
ls -lh "$DIR/dist/"
