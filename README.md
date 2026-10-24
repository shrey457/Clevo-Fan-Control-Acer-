# Fan Control for Linux

A lightweight, Linux-native fan control utility and desktop graphical interface (GUI) designed for direct Embedded Controller (EC) thermal management. 

Featuring automatic system theming, High-DPI and fractional scaling optimization, dynamic thermal curves, out-of-the-box startup elevation, and precompiled installable packages for **Ubuntu/Debian**, **Fedora/RHEL**, **Arch Linux/Manjaro**, plus a **universal install script** for any other distribution.

---

##  Quick Install (Prebuilt Binaries & Packages)

All compiled packages are ready to install inside the `dist/` directory:

| Distribution | Package Format | Direct Install Command |
| :--- | :--- | :--- |
| **Ubuntu / Debian / Mint / Pop!_OS** | `.deb` | `sudo apt install ./dist/fan-control_1.2.0_amd64.deb` |
| **Fedora / RHEL / Rocky Linux** | `.rpm` | `sudo dnf install ./dist/fan-control_1.2.0_amd64.rpm` |
| **openSUSE (Tumbleweed / Leap)** | `.rpm` | `sudo zypper install ./dist/fan-control_1.2.0_amd64.rpm` |
| **Arch Linux / Manjaro / EndeavourOS** | `.pkg.tar.zst` | `sudo pacman -U ./dist/fan-control-1.2.0-1-x86_64.pkg.tar.zst` |
| **Any Other Linux Distro** | Universal Script | `sudo ./install.sh` |

---

###  1. Debian / Ubuntu / Linux Mint / Pop!_OS (`.deb`)

The native package is **~445 KB** and uses your system's native Python & Qt libraries.

To install via terminal:
```bash
sudo apt install ./dist/fan-control_1.2.0_amd64.deb
```
> [!IMPORTANT]
> Always include the `./` prefix when using `apt install`. Without `./`, `apt` searches the online repositories instead of the local file and will report `Unable to locate package`.

Alternatively, install using `dpkg`:
```bash
sudo dpkg -i dist/fan-control_1.2.0_amd64.deb
sudo apt-get install -f    # Fixes any missing dependencies automatically if needed
```

---

###  2. Fedora / RHEL / CentOS / Rocky Linux (`.rpm`)

```bash
sudo dnf install ./dist/fan-control_1.2.0_amd64.rpm
```

---

###  3. openSUSE (`.rpm`)

```bash
sudo zypper install ./dist/fan-control_1.2.0_amd64.rpm
```

---

###  4. Arch Linux / Manjaro / EndeavourOS (`.pkg.tar.zst` / `PKGBUILD`)

Install the precompiled native Arch package directly:
```bash
sudo pacman -U ./dist/fan-control-1.2.0-1-x86_64.pkg.tar.zst
```

Or compile and install using `makepkg`:
```bash
makepkg -si
```

---

###  5. Any Other Distro (Void, Alpine, Gentoo, Slackware, etc.)

For any Linux distribution without `.deb`/`.rpm`/`pacman` support, use the included universal installer script:

```bash
# 1. Install to /usr/local with full hardware capabilities, icons, and desktop launcher:
sudo ./install.sh

# 2. To uninstall at any time:
sudo ./uninstall.sh
```

Alternatively, extract the universal tarball manually:
```bash
sudo tar -xvf dist/fan-control_1.2.0_amd64.tar.gz -C /
sudo setcap cap_sys_rawio+ep /usr/bin/fan-control
```

---

##  Out-of-the-Box Authentication (First Launch)

Embedded Controller fan registers require `CAP_SYS_RAWIO` permissions:

1. **Automatic Package Setup**: The `.deb`, `.rpm`, `.pkg.tar.zst`, and `install.sh` packages configure `CAP_SYS_RAWIO` automatically during installation.
2. **First-Launch Elevation**: If permissions are ever missing (such as running directly from source), the app **prompts for your password on startup** using your desktop's native authentication dialog (Polkit `pkexec` or Qt prompt).
3. **Permanent & Seamless**: Once authenticated, permissions are permanently configured for the binary. All subsequent launches run completely passwordless with **`● Connected`** status out of the box!

---

##  Features

- **100% Linux Native GUI**:
  - **Ultra-Lightweight & Fast**: Packages are under 455 KB (no bloated 90MB PyInstaller bundles).
  - **Dynamic System Theming**: Dynamically inherits desktop themes, system palettes, and system typography across **KDE Plasma (Breeze / Breeze Dark)**, **GNOME (Adwaita / Adwaita Dark)**, **XFCE**, **Cinnamon**, and tiling window managers (**Hyprland, Sway, i3**).
  - **High-DPI & Fractional Scaling**: Vector scaling for crystal-clear text and meters on 125%, 150%, and 200% displays.
  - **4 Streamlined Fan Modes**:
    1. **Automatic**: Dynamic multi-stage fan curve reacting in real-time to CPU and GPU temperature changes. Sliders stay hidden for an uncluttered experience.
    2. **Maximum**: 100% full-blast cooling for intensive gaming, compilation, or machine learning workloads.
    3. **Quiet Mode**: Silent Zero-RPM profile setting fan speed to 0% for dead-silent operation during light desktop tasks.
    4. **Custom**: Unlocks synchronized or independent dual fan sliders (CPU & GPU), quick preset shortcuts (25%, 50%, 75%, 100%), and a hardware firmware reset switch.
  - **Proportional Vector Arc Meters**: Compact, non-overlapping circular gauges for CPU/GPU temperatures and fan speeds.
  - **Interactive Curve Editor**: Visual temperature vs. duty curve editor with real-time temperature tracking and instant preset loading.
  - **60-Second Real-Time Trend Graph**: Smooth, anti-aliased live temperature graph matching system accent colors.
  - **System Tray Integration**: Background monitoring with live telemetry tooltips and quick mode switcher.

- **Fast C CLI & Shared Library**:
  - Direct I/O port communication (`0x62`/`0x66`).
  - Standard JSON output mode (`fan-control json`) for scripting and status bars (Waybar, Polybar, etc.).
  - Exported C ABI library (`libfan-ec.so`) for easy integration into custom tools.

---

## 🛠️ Building Packages From Source

To compile all binaries and build packages for all Linux distributions in one command:

```bash
./package.sh
```

This compiles the C binaries and outputs all distribution packages into `dist/`:
- `dist/fan-control_1.2.0_amd64.deb` (Debian/Ubuntu)
- `dist/fan-control_1.2.0_amd64.rpm` (Fedora/RHEL/openSUSE)
- `dist/fan-control-1.2.0-1-x86_64.pkg.tar.zst` (Arch Linux)
- `dist/fan-control_1.2.0_amd64.tar.gz` (Universal standalone tarball)
- `dist/PKGBUILD` (Arch Linux build script)

---

##  Usage Guide

### Desktop GUI
Launch from your application launcher (search **Fan Control**), or run in terminal:
```bash
fan-gui
```

- **Minimize to Tray**: Closing or hiding sends the app to the system tray.
- **Quick Switcher**: Right-click the system tray icon to switch between Automatic, Maximum, Quiet, or Custom modes on the fly.

### Command Line Interface (CLI)
```bash
# Print live telemetry:
fan-control dump

# Output JSON (for Waybar, i3blocks, Polybar):
fan-control json

# Set both fans to 60%:
fan-control set 60

# Set CPU fan to 45% and GPU fan to 75%:
fan-control set1 45
fan-control set2 75

# Restore fans back to the laptop's automatic hardware EC firmware control:
fan-control reset

# Run independent automated thermal control loop in the terminal:
fan-control auto
```

---

##  Background Systemd Service (Optional)

To run the automated cooling curve as a background service on system boot:

1. Create a service file:
```bash
sudo nano /etc/systemd/system/fan-control.service
```

2. Add the following content:
```ini
[Unit]
Description=Hardware EC Fan Control Service
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/fan-control auto
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
```

3. Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fan-control.service
```

---

## Troubleshooting & FAQ

#### 1. Why does the app ask for my password on first start?
Fan control requires access to the laptop's hardware Embedded Controller (EC) I/O ports. On first launch, the app prompts for authentication once to grant `CAP_SYS_RAWIO` capability to `fan-control`. After this initial authorization, the app never asks for passwords again and works out of the box.

#### 2. How do I restore factory fan behavior?
- Click the **Firmware Reset** button in Custom Mode inside the GUI.
- Or run `fan-control reset` in terminal.

#### 3. Why does the app show `🔒 Secure Boot Active` / why can't I change fan speeds even after entering my password?
When **UEFI Secure Boot** is enabled in your BIOS, the Linux kernel automatically enforces **Kernel Lockdown** (`[integrity]` mode in `/sys/kernel/security/lockdown`).

Under Kernel Lockdown, Linux strictly blocks raw hardware port access (`ioperm` / `inb` / `outb` to Embedded Controller ports `0x62`/`0x66`) — even for `root` (UID 0) or binaries with `CAP_SYS_RAWIO`.

**To unlock full fan control (Acer & Clevo laptops):**
1. **Reboot** and repeatedly tap **F2** (or Del) to enter BIOS / UEFI.
2. In the **Security** tab, choose **Set Supervisor Password** and set a password. *(Acer BIOS greys out the Secure Boot setting until a supervisor password is set. Choose a simple password you'll remember!)*
3. In the **Boot** tab (or Security tab), highlight **Secure Boot** and set it to **Disabled**.
4. Press **F10** (Save & Exit), then boot into Linux.

Once booted without Secure Boot, Kernel Lockdown is lifted, and Fan Control will display **`● Connected`** with full direct hardware fan control.

---

## 📄 License

GPL-3.0 License.