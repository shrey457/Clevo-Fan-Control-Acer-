# Maintainer: Fan Control Project <maintainers@fan-control.local>
pkgname=fan-control
pkgver=1.2.0
pkgrel=1
pkgdesc="Hardware EC Fan Control Utility and Native Desktop GUI"
arch=('x86_64')
url="https://github.com/shreyash/fan-control"
license=('GPL3')
depends=('python' 'python-pyqt6' 'libcap' 'polkit')
makedepends=('cmake' 'gcc' 'make')
install=packaging/fan-control.install
source=()
sha256sums=()

build() {
    cmake -B build -S . -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr
    cmake --build build -j"$(nproc)"
}

package() {
    DESTDIR="$pkgdir" cmake --install build
}
