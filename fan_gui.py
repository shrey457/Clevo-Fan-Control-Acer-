#!/usr/bin/env python3
"""
Fan Control GUI - Native Linux Desktop Application
Pure native Qt6 interface with dynamic system theming, High-DPI optimization,
proportional vector meters, and 4 primary modes: Automatic, Maximum, Quiet, and Custom.
"""

from __future__ import annotations

import re
import os
import sys
import glob
import json
import time
import math
import shutil
import pathlib
import ctypes
import subprocess
from collections import deque

try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QEvent
    from PyQt6.QtGui import (
        QColor, QPainter, QPen, QBrush, QFont, QIcon, QAction,
        QLinearGradient, QPainterPath, QPalette
    )
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QGridLayout, QLabel, QSlider, QPushButton, QCheckBox, QTabWidget,
        QGroupBox, QFrame, QSystemTrayIcon, QMenu, QMessageBox, QSpinBox,
        QScrollArea, QSizePolicy, QInputDialog, QLineEdit
    )
    HAS_PYQT6 = True
except ImportError:
    from PyQt5 import QtCore, QtGui, QtWidgets
    from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF, QEvent
    from PyQt5.QtGui import (
        QColor, QPainter, QPen, QBrush, QFont, QIcon,
        QLinearGradient, QPainterPath, QPalette
    )
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QGridLayout, QLabel, QSlider, QPushButton, QCheckBox, QTabWidget,
        QGroupBox, QFrame, QSystemTrayIcon, QMenu, QMessageBox, QSpinBox,
        QScrollArea, QSizePolicy, QAction, QInputDialog, QLineEdit
    )
    HAS_PYQT6 = False

# Compatibility shims for PyQt5 / PyQt6 enum differences
if not hasattr(QSizePolicy, "Policy"):
    class _PolicyShim:
        Expanding = QSizePolicy.Expanding
        Preferred = QSizePolicy.Preferred
        Fixed = QSizePolicy.Fixed
        Minimum = QSizePolicy.Minimum
        Maximum = QSizePolicy.Maximum
    QSizePolicy.Policy = _PolicyShim

if not hasattr(Qt, "AlignmentFlag"):
    Qt.AlignmentFlag = Qt
if not hasattr(Qt, "Orientation"):
    Qt.Orientation = Qt
if not hasattr(Qt, "PenStyle"):
    Qt.PenStyle = Qt
if not hasattr(Qt, "PenCapStyle"):
    Qt.PenCapStyle = Qt
if not hasattr(QFont, "Weight"):
    class _FontWeightShim:
        DemiBold = getattr(QFont, "DemiBold", 63)
        Bold = getattr(QFont, "Bold", 75)
        Normal = getattr(QFont, "Normal", 50)
    QFont.Weight = _FontWeightShim
if not hasattr(QPainter, "RenderHint"):
    QPainter.RenderHint = QPainter
if not hasattr(QPalette, "ColorRole"):
    QPalette.ColorRole = QPalette
if not hasattr(QEvent, "Type"):
    QEvent.Type = QEvent
if not hasattr(QFrame, "Shape"):
    QFrame.Shape = QFrame
if not hasattr(QMessageBox, "StandardButton"):
    QMessageBox.StandardButton = QMessageBox


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BUNDLE_DIR = pathlib.Path(sys._MEIPASS)
else:
    BUNDLE_DIR = pathlib.Path(__file__).resolve().parent

APP_DIR = pathlib.Path(__file__).resolve().parent

def _resolve_cli_path() -> pathlib.Path:
    candidates = [
        pathlib.Path("/usr/bin/fan-control"),
        pathlib.Path("/usr/local/bin/fan-control"),
        BUNDLE_DIR / "fan-control",
        APP_DIR / "build" / "fan-control",
        APP_DIR / "fan-control",
        pathlib.Path.home() / ".local" / "bin" / "fan-control",
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return c
    which_bin = shutil.which("fan-control")
    if which_bin:
        return pathlib.Path(which_bin)
    return APP_DIR / "build" / "fan-control"

CLI_PATH = _resolve_cli_path()


def is_kernel_locked_down() -> bool:
    """Check if Linux Kernel Lockdown is active (e.g. from UEFI Secure Boot)."""
    try:
        p = pathlib.Path("/sys/kernel/security/lockdown")
        if p.is_file():
            content = p.read_text(encoding="utf-8", errors="ignore")
            if "[integrity]" in content or "[confidentiality]" in content:
                return True
    except Exception:
        pass
    return False


def find_app_icon() -> QIcon:
    """Finds the high-resolution app icon across local and system paths."""
    icon = QIcon()
    for s in (16, 22, 24, 32, 48, 64, 128, 256, 512):
        for candidate in [
            APP_DIR / "assets" / "icons" / "hicolor" / f"{s}x{s}" / "apps" / "fan-control.png",
            pathlib.Path(f"/usr/share/icons/hicolor/{s}x{s}/apps/fan-control.png"),
            pathlib.Path(f"/usr/local/share/icons/hicolor/{s}x{s}/apps/fan-control.png"),
        ]:
            if candidate.is_file():
                icon.addFile(str(candidate), QtCore.QSize(s, s))
                break
    if not icon.isNull() and icon.availableSizes():
        return icon

    for candidate in [
        BUNDLE_DIR / "assets" / "fan-control.png",
        APP_DIR / "assets" / "fan-control.png",
        pathlib.Path("/usr/share/icons/hicolor/512x512/apps/fan-control.png"),
        pathlib.Path("/usr/local/share/icons/hicolor/512x512/apps/fan-control.png"),
    ]:
        if candidate.is_file():
            return QIcon(str(candidate))
    return QIcon.fromTheme("fan-control", QIcon.fromTheme("utilities-system-monitor"))


def _build_monochrome_fan_path() -> QPainterPath:
    p = QPainterPath()
    p.setFillRule(Qt.FillRule.OddEvenFill)
    path_str = (
        "M258.6 0c-1.7 0-3.4 .1-5.1 .5C168 17 115.6 102.3 130.5 189.3c2.9 17 8.4 32.9 15.9 47.4L32 224H29.4C13.2 224 0 237.2 0 253.4c0 1.7 .1 3.4 .5 5.1C17 344 102.3 396.4 189.3 381.5c17-2.9 32.9-8.4 47.4-15.9L224 480v2.6c0 16.2 13.2 29.4 29.4 29.4c1.7 0 3.4-.1 5.1-.5C344 495 396.4 409.7 381.5 322.7c-2.9-17-8.4-32.9-15.9-47.4L480 288h2.6c16.2 0 29.4-13.2 29.4-29.4c0-1.7-.1-3.4-.5-5.1C495 168 409.7 115.6 322.7 130.5c-17 2.9-32.9 8.4-47.4 15.9L288 32v-2.6C288 13.2 274.8 0 258.6 0z"
    )
    tokens = re.findall(r"([a-zA-Z]|[-+]?(?:\d*\.\d+|\d+))", path_str)
    i = 0
    cur_x, cur_y = 0.0, 0.0
    while i < len(tokens):
        cmd = tokens[i]
        if cmd == "M":
            cur_x, cur_y = float(tokens[i + 1]), float(tokens[i + 2])
            p.moveTo(cur_x, cur_y)
            i += 3
        elif cmd == "m":
            cur_x += float(tokens[i + 1])
            cur_y += float(tokens[i + 2])
            p.moveTo(cur_x, cur_y)
            i += 3
        elif cmd == "c":
            dx1, dy1 = float(tokens[i + 1]), float(tokens[i + 2])
            dx2, dy2 = float(tokens[i + 3]), float(tokens[i + 4])
            dx, dy = float(tokens[i + 5]), float(tokens[i + 6])
            p.cubicTo(cur_x + dx1, cur_y + dy1, cur_x + dx2, cur_y + dy2, cur_x + dx, cur_y + dy)
            cur_x += dx
            cur_y += dy
            i += 7
        elif cmd == "C":
            x1, y1 = float(tokens[i + 1]), float(tokens[i + 2])
            x2, y2 = float(tokens[i + 3]), float(tokens[i + 4])
            x, y = float(tokens[i + 5]), float(tokens[i + 6])
            p.cubicTo(x1, y1, x2, y2, x, y)
            cur_x, cur_y = x, y
            i += 7
        elif cmd == "L":
            cur_x, cur_y = float(tokens[i + 1]), float(tokens[i + 2])
            p.lineTo(cur_x, cur_y)
            i += 3
        elif cmd == "H":
            cur_x = float(tokens[i + 1])
            p.lineTo(cur_x, cur_y)
            i += 2
        elif cmd == "h":
            cur_x += float(tokens[i + 1])
            p.lineTo(cur_x, cur_y)
            i += 2
        elif cmd == "V":
            cur_y = float(tokens[i + 1])
            p.lineTo(cur_x, cur_y)
            i += 2
        elif cmd == "v":
            cur_y += float(tokens[i + 1])
            p.lineTo(cur_x, cur_y)
            i += 2
        elif cmd in ("z", "Z"):
            p.closeSubpath()
            i += 1
        else:
            i += 1
    p.addEllipse(QPointF(256, 256), 96, 96)
    p.addEllipse(QPointF(256, 256), 36, 36)
    return p


def create_monochrome_tray_icon(color: QColor = None) -> QIcon:
    """Renders a sleek, crisp monochrome vector fan icon with transparent background."""
    if color is None:
        color = QColor(245, 245, 245, 245)

    base_path = _build_monochrome_fan_path()
    icon = QIcon()
    for size in (16, 22, 24, 32, 48, 64):
        pix = QtGui.QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)

        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pad = size * 0.05
        p.translate(pad, pad)
        p.scale((size - 2 * pad) / 512.0, (size - 2 * pad) / 512.0)
        p.setBrush(QBrush(color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(base_path)
        p.end()

        icon.addPixmap(pix)
    return icon


def find_tray_icon() -> QIcon:
    """Finds or dynamically generates the clean monochrome tray icon."""
    theme_icon = QIcon.fromTheme("fan-control-symbolic")
    if not theme_icon.isNull():
        return theme_icon

    icon = QIcon()
    for s in (16, 22, 24, 32, 48, 64):
        for candidate in [
            APP_DIR / "assets" / "icons" / "hicolor" / f"{s}x{s}" / "apps" / "fan-control-tray.png",
            pathlib.Path(f"/usr/share/icons/hicolor/{s}x{s}/apps/fan-control-tray.png"),
            pathlib.Path(f"/usr/local/share/icons/hicolor/{s}x{s}/apps/fan-control-tray.png"),
        ]:
            if candidate.is_file():
                icon.addFile(str(candidate), QtCore.QSize(s, s))
                break

    if not icon.isNull() and icon.availableSizes():
        return icon

    for candidate in [
        BUNDLE_DIR / "assets" / "fan-control-tray.png",
        APP_DIR / "assets" / "fan-control-tray.png",
        pathlib.Path("/usr/share/icons/hicolor/scalable/apps/fan-control-symbolic.svg"),
        pathlib.Path("/usr/local/share/icons/hicolor/scalable/apps/fan-control-symbolic.svg"),
    ]:
        if candidate.is_file():
            ic = QIcon(str(candidate))
            if not ic.isNull():
                return ic
    return create_monochrome_tray_icon()


class ECBackend:
    """Hardware Embedded Controller interface."""

    def __init__(self):
        self._lib = None
        self._has_direct_io = False
        self._init_backend()

    def _init_backend(self):
        # 1. Try to load libfan-ec.so
        so_candidates = [
            BUNDLE_DIR / "libfan-ec.so",
            APP_DIR / "build" / "libfan-ec.so",
            APP_DIR / "libfan-ec.so",
            pathlib.Path("/usr/local/lib/libfan-ec.so"),
            pathlib.Path("/usr/lib/libfan-ec.so"),
            pathlib.Path("/usr/lib64/libfan-ec.so"),
            pathlib.Path("/usr/local/lib64/libfan-ec.so"),
            pathlib.Path.home() / ".local" / "lib" / "libfan-ec.so",
        ]
        for p in so_candidates:
            if p.is_file():
                try:
                    lib = ctypes.CDLL(str(p))
                    if lib.ec_lib_init() == 0:
                        self._lib = lib
                        self._has_direct_io = True
                        return
                except Exception:
                    pass

        # 2. Check root / CAP_SYS_RAWIO capability
        if os.geteuid() == 0:
            self._has_direct_io = True
            return

        # 3. Test if fan-control CLI binary has working EC hardware permissions
        if CLI_PATH and CLI_PATH.is_file() and os.access(CLI_PATH, os.X_OK):
            try:
                res = subprocess.run([str(CLI_PATH), "json"], capture_output=True, text=True, timeout=1.2)
                if res.returncode == 0 and "cpu" in res.stdout:
                    self._has_direct_io = True
                    return
            except Exception:
                pass

        self._has_direct_io = False

    @property
    def has_direct_io(self) -> bool:
        return self._has_direct_io

    def read_status(self) -> dict:
        """Returns hardware status dict."""
        if self._lib and self._has_direct_io:
            try:
                cpu = self._lib.ec_lib_cpu_temp()
                gpu = self._lib.ec_lib_gpu_temp()
                f1_d = self._lib.ec_lib_fan1_duty_read()
                f2_d = self._lib.ec_lib_fan2_duty_read()
                f1_r = self._lib.ec_lib_fan1_rpm_read()
                f2_r = self._lib.ec_lib_fan2_rpm_read()
                return {
                    "cpu": cpu,
                    "gpu": gpu,
                    "fan1_duty": f1_d,
                    "fan2_duty": f2_d,
                    "fan1_rpm": f1_r,
                    "fan2_rpm": f2_r,
                    "source": "direct-ec"
                }
            except Exception:
                pass

        # Try CLI JSON dump
        if CLI_PATH.is_file() and os.access(CLI_PATH, os.X_OK):
            try:
                res = subprocess.run([str(CLI_PATH), "json"], capture_output=True, text=True, timeout=1.2)
                if res.returncode == 0:
                    out = res.stdout.strip()
                    s_idx = out.find("{")
                    e_idx = out.rfind("}")
                    if s_idx != -1 and e_idx != -1:
                        data = json.loads(out[s_idx:e_idx + 1])
                        data["source"] = "cli"
                        return data
            except Exception:
                pass

        # Fallback reading from sysfs and nvidia-smi
        cpu = self._read_cpu_sysfs()
        gpu = self._read_gpu_sysfs()
        return {
            "cpu": cpu,
            "gpu": gpu,
            "fan1_duty": 0,
            "fan2_duty": 0,
            "fan1_rpm": 0,
            "fan2_rpm": 0,
            "source": "sysfs-fallback"
        }

    def _read_cpu_sysfs(self) -> int:
        for z in range(8):
            t_type = f"/sys/class/thermal/thermal_zone{z}/type"
            t_temp = f"/sys/class/thermal/thermal_zone{z}/temp"
            if os.path.exists(t_type) and os.path.exists(t_temp):
                try:
                    with open(t_type) as f:
                        name = f.read().strip()
                    if any(k in name for k in ("x86_pkg_temp", "TCPU", "cpu", "acpitz")):
                        with open(t_temp) as f:
                            milli = int(f.read().strip())
                            val = milli // 1000 if milli > 1000 else milli
                            if 10 < val < 120:
                                return val
                except Exception:
                    pass
        for p in glob.glob("/sys/class/hwmon/hwmon*/temp1_input"):
            try:
                with open(p) as f:
                    val = int(f.read().strip()) // 1000
                    if 10 < val < 120:
                        return val
            except Exception:
                pass
        return 0

    def _read_gpu_sysfs(self) -> int:
        for hw in glob.glob("/sys/class/hwmon/hwmon*"):
            try:
                name_file = os.path.join(hw, "name")
                if os.path.exists(name_file):
                    with open(name_file) as f:
                        name = f.read().strip()
                    if any(d in name for d in ("nvidia", "amdgpu", "i915", "xe")):
                        for i in range(1, 9):
                            tf = os.path.join(hw, f"temp{i}_input")
                            if os.path.exists(tf):
                                with open(tf) as f:
                                    val = int(f.read().strip()) // 1000
                                    if 10 < val < 120:
                                        return val
            except Exception:
                pass
        try:
            res = subprocess.run(
                ["/usr/bin/nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=1
            )
            if res.returncode == 0 and res.stdout.strip().isdigit():
                return int(res.stdout.strip())
        except Exception:
            pass
        return 0

    def set_fan(self, fan_idx: int, pct: int) -> bool:
        pct = max(0, min(100, int(pct)))
        if self._lib and self._has_direct_io:
            if fan_idx == 1:
                return self._lib.ec_lib_fan1_duty_write(pct) == 0
            elif fan_idx == 2:
                return self._lib.ec_lib_fan2_duty_write(pct) == 0
            elif fan_idx == 0:
                return self._lib.ec_lib_fan_set_both(pct) == 0

        if CLI_PATH.is_file():
            cmd = "set" if fan_idx == 0 else f"set{fan_idx}"
            return self._run_privileged([str(CLI_PATH), cmd, str(pct)])
        return False

    def reset_firmware_auto(self) -> bool:
        if self._lib and self._has_direct_io:
            return self._lib.ec_lib_fan_reset() == 0
        if CLI_PATH.is_file():
            return self._run_privileged([str(CLI_PATH), "reset"])
        return False

    def _run_privileged(self, cmd: list[str]) -> bool:
        if is_kernel_locked_down():
            return False
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
            if p.returncode == 0:
                return True
            if os.geteuid() == 0:
                return False
            if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
                return False
            p = subprocess.run(["pkexec"] + cmd, capture_output=True, text=True, timeout=10)
            return p.returncode == 0
        except Exception:
            return False


class CircularDialWidget(QWidget):
    """Proportionally scaled vector arc gauge with centered reading."""

    def __init__(self, is_temp: bool = False, parent=None):
        super().__init__(parent)
        self.is_temp = is_temp
        self.value = 0
        self.setFixedSize(92, 92)

    def set_value(self, value: int):
        self.value = max(0, min(120, int(value)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        pad = 7.0
        rect = QRectF(pad, pad, w - pad * 2, h - pad * 2)

        pal = self.palette()
        text_col = pal.color(QPalette.ColorRole.WindowText)
        stroke = 5.5

        # Background track
        bg_col = QColor(text_col.red(), text_col.green(), text_col.blue(), 26)
        bg_pen = QPen(bg_col, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 225 * 16, -270 * 16)

        # Arc fraction and color
        if self.is_temp:
            fraction = max(0.0, min(1.0, (self.value - 20) / 80.0))
            if self.value < 55:
                arc_col = QColor(16, 185, 129)  # Soft Emerald
            elif self.value < 75:
                arc_col = QColor(245, 158, 11)  # Warm Amber
            else:
                arc_col = QColor(239, 68, 68)   # Coral Red
        else:
            fraction = max(0.0, min(1.0, self.value / 100.0))
            if self.value < 50:
                arc_col = QColor(56, 189, 248)  # Sky Cyan
            elif self.value < 85:
                arc_col = QColor(99, 102, 241)  # Indigo
            else:
                arc_col = QColor(244, 63, 94)   # Rose Red

        span_angle = int(-fraction * 270 * 16)
        val_pen = QPen(arc_col, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(val_pen)
        painter.drawArc(rect, 225 * 16, span_angle)

        # Value text in the center
        val_font = QFont(self.font())
        val_font.setPointSize(14)
        val_font.setBold(True)
        painter.setFont(val_font)
        painter.setPen(text_col)

        unit_str = "°C" if self.is_temp else "%"
        text_str = f"{self.value}{unit_str}" if self.value > 0 or not self.is_temp else "--"
        text_rect = QRectF(0, 0, w, h - 2)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text_str)


class MetricCard(QFrame):
    """Clean, high-DPI card holding title, circular dial, and secondary status badge."""

    def __init__(self, title: str, is_temp: bool = False, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(100)
        self.setFixedHeight(156)

        self.setStyleSheet("""
            MetricCard {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Title at the top
        self.lbl_title = QLabel(title)
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t_font = QFont(self.font())
        t_font.setPointSize(max(7, t_font.pointSize() - 2))
        t_font.setWeight(QFont.Weight.DemiBold)
        self.lbl_title.setFont(t_font)
        self.lbl_title.setStyleSheet("color: palette(window-text); opacity: 0.75;")

        # Circular Gauge in the middle
        self.dial = CircularDialWidget(is_temp=is_temp)

        # Status / RPM badge at the bottom
        self.lbl_sub = QLabel("—")
        self.lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s_font = QFont(self.font())
        s_font.setPointSize(max(7, s_font.pointSize() - 2))
        s_font.setBold(True)
        self.lbl_sub.setFont(s_font)
        self.lbl_sub.setStyleSheet("""
            QLabel {
                color: palette(window-text);
                background-color: palette(button);
                border: 1px solid palette(mid);
                border-radius: 4px;
                padding: 2px 8px;
            }
        """)

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.dial, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_sub, 0, Qt.AlignmentFlag.AlignCenter)

    def set_data(self, val: int, sub_text: str):
        self.dial.set_value(val)
        self.lbl_sub.setText(sub_text)


class RealtimeHistoryWidget(QWidget):
    """60-second temperature trend chart matching system accent colors."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(105)
        self.cpu_history = deque(maxlen=60)
        self.gpu_history = deque(maxlen=60)

    def add_sample(self, cpu: int, gpu: int):
        self.cpu_history.append(cpu)
        self.gpu_history.append(gpu)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        w = float(rect.width())
        h = float(rect.height())

        pal = self.palette()
        base_col = pal.color(QPalette.ColorRole.Base)
        text_col = pal.color(QPalette.ColorRole.WindowText)
        accent_col = pal.color(QPalette.ColorRole.Highlight)
        border_col = pal.color(QPalette.ColorRole.Mid)

        # Canvas background
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 8, 8)
        painter.fillPath(path, base_col)
        painter.setPen(QPen(border_col, 1))
        painter.drawPath(path)

        # Grid lines
        grid_col = QColor(border_col.red(), border_col.green(), border_col.blue(), 60)
        painter.setPen(QPen(grid_col, 1, Qt.PenStyle.DashLine))

        font = QFont(self.font())
        font.setPointSize(max(6, font.pointSize() - 3))
        painter.setFont(font)

        dim_text = QColor(text_col.red(), text_col.green(), text_col.blue(), 120)
        for temp in (40, 60, 80, 100):
            y = h - (temp / 110.0) * h
            painter.drawLine(0, int(y), int(w), int(y))
            painter.setPen(dim_text)
            painter.drawText(6, int(y) - 2, f"{temp}°C")
            painter.setPen(QPen(grid_col, 1, Qt.PenStyle.DashLine))

        if len(self.cpu_history) < 2:
            return

        def draw_series(history, line_col, grad_alpha):
            step_x = (w - 10.0) / 59.0
            pts = []
            for i, val in enumerate(history):
                x = 5.0 + i * step_x
                y = h - max(0.0, min(h, (val / 110.0) * h))
                pts.append(QPointF(x, y))

            area = QPainterPath()
            area.moveTo(pts[0].x(), h)
            for p in pts:
                area.lineTo(p)
            area.lineTo(pts[-1].x(), h)
            area.closeSubpath()

            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0, QColor(line_col.red(), line_col.green(), line_col.blue(), grad_alpha))
            grad.setColorAt(1, QColor(line_col.red(), line_col.green(), line_col.blue(), 0))
            painter.fillPath(area, QBrush(grad))

            painter.setPen(QPen(line_col, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for i in range(len(pts) - 1):
                painter.drawLine(pts[i], pts[i + 1])

        # Draw GPU (Warm Amber) and CPU (System Highlight / Blue)
        draw_series(self.gpu_history, QColor(245, 158, 11), 35)
        draw_series(self.cpu_history, accent_col, 50)

        # Legend
        leg_font = QFont(self.font())
        leg_font.setPointSize(max(7, leg_font.pointSize() - 2))
        leg_font.setBold(True)
        painter.setFont(leg_font)
        painter.setPen(accent_col)
        painter.drawText(int(w) - 135, 14, "● CPU")
        painter.setPen(QColor(245, 158, 11))
        painter.drawText(int(w) - 72, 14, "● GPU")


class CurveVisualizerWidget(QWidget):
    """Interactive visual representation of the fan curve."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.curve_points: list[tuple[int, int]] = []
        self.current_temp = 0
        self.current_duty = 0

    def set_curve(self, points: list[tuple[int, int]], cur_temp: int = 0, cur_duty: int = 0):
        self.curve_points = points
        self.current_temp = cur_temp
        self.current_duty = cur_duty
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        w = float(rect.width())
        h = float(rect.height())

        pal = self.palette()
        base_col = pal.color(QPalette.ColorRole.Base)
        text_col = pal.color(QPalette.ColorRole.WindowText)
        accent_col = pal.color(QPalette.ColorRole.Highlight)
        border_col = pal.color(QPalette.ColorRole.Mid)

        painter.fillRect(rect, base_col)

        margin_left = 34.0
        margin_bottom = 22.0
        graph_w = w - margin_left - 12.0
        graph_h = h - margin_bottom - 12.0

        grid_col = QColor(border_col.red(), border_col.green(), border_col.blue(), 70)
        painter.setPen(QPen(grid_col, 1, Qt.PenStyle.DashLine))

        font = QFont(self.font())
        font.setPointSize(max(6, font.pointSize() - 3))
        painter.setFont(font)

        dim_text = QColor(text_col.red(), text_col.green(), text_col.blue(), 130)
        for duty in (25, 50, 75, 100):
            y = 12.0 + graph_h - (duty / 100.0) * graph_h
            painter.drawLine(int(margin_left), int(y), int(w - 12), int(y))
            painter.setPen(dim_text)
            painter.drawText(4, int(y) + 3, f"{duty}%")
            painter.setPen(QPen(grid_col, 1, Qt.PenStyle.DashLine))

        for temp in (30, 50, 70, 90):
            x = margin_left + (temp / 100.0) * graph_w
            painter.drawLine(int(x), 12, int(x), int(12 + graph_h))
            painter.setPen(dim_text)
            painter.drawText(int(x) - 10, int(h - 6), f"{temp}°")
            painter.setPen(QPen(grid_col, 1, Qt.PenStyle.DashLine))

        if not self.curve_points:
            return

        pts = []
        for t, d in self.curve_points:
            px = margin_left + max(0.0, min(100.0, float(t))) / 100.0 * graph_w
            py = 12.0 + graph_h - (max(0.0, min(100.0, float(d))) / 100.0 * graph_h)
            pts.append(QPointF(px, py))

        path = QPainterPath()
        path.moveTo(pts[0].x(), 12.0 + graph_h)
        for p in pts:
            path.lineTo(p)
        path.lineTo(pts[-1].x(), 12.0 + graph_h)
        path.closeSubpath()

        grad = QLinearGradient(0, 12, 0, 12 + graph_h)
        grad.setColorAt(0, QColor(accent_col.red(), accent_col.green(), accent_col.blue(), 60))
        grad.setColorAt(1, QColor(accent_col.red(), accent_col.green(), accent_col.blue(), 0))
        painter.fillPath(path, QBrush(grad))

        painter.setPen(QPen(accent_col, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])

        for p in pts:
            painter.setBrush(base_col)
            painter.setPen(QPen(accent_col, 2))
            painter.drawEllipse(p, 4, 4)

        if self.current_temp > 0:
            cx = margin_left + max(0.0, min(100.0, float(self.current_temp))) / 100.0 * graph_w
            cy = 12.0 + graph_h - (max(0.0, min(100.0, float(self.current_duty))) / 100.0 * graph_h)
            painter.setBrush(QColor(239, 68, 68))
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawEllipse(QPointF(cx, cy), 5, 5)
            painter.setPen(QColor(239, 68, 68))
            marker_font = QFont(self.font())
            marker_font.setPointSize(max(7, marker_font.pointSize() - 2))
            marker_font.setBold(True)
            painter.setFont(marker_font)
            painter.drawText(int(cx) + 8, int(cy) - 6, f"{self.current_temp}°C ({self.current_duty}%)")


class ModeButton(QPushButton):
    """Clean selectable mode card button with subtle highlight border."""

    def __init__(self, title: str, subtitle: str, icon_str: str = "", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(54)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_lbl = QLabel(f"{icon_str}  {title}" if icon_str else title)
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont(self.font())
        title_font.setPointSize(title_font.pointSize() + 1)
        title_font.setBold(True)
        self.title_lbl.setFont(title_font)

        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_font = QFont(self.font())
        sub_font.setPointSize(max(7, sub_font.pointSize() - 2))
        self.sub_lbl.setFont(sub_font)
        self.sub_lbl.setStyleSheet("color: palette(window-text); opacity: 0.7;")

        layout.addWidget(self.title_lbl)
        layout.addWidget(self.sub_lbl)

    def set_active(self, active: bool):
        self.setChecked(active)
        pal = self.palette()
        highlight = pal.color(QPalette.ColorRole.Highlight)
        if active:
            self.setStyleSheet(f"""
                ModeButton {{
                    background-color: palette(base);
                    border: 2px solid {highlight.name()};
                    border-radius: 8px;
                }}
            """)
            self.title_lbl.setStyleSheet(f"color: {highlight.name()}; font-weight: bold;")
            self.sub_lbl.setStyleSheet("color: palette(window-text); opacity: 0.9;")
        else:
            self.setStyleSheet("""
                ModeButton {
                    background-color: palette(button);
                    border: 1px solid palette(mid);
                    border-radius: 8px;
                }
                ModeButton:hover {
                    border: 1px solid palette(highlight);
                }
            """)
            self.title_lbl.setStyleSheet("color: palette(button-text); font-weight: bold;")
            self.sub_lbl.setStyleSheet("color: palette(button-text); opacity: 0.7;")


class FanControlMainWindow(QMainWindow):
    """Main Application Window."""

    def __init__(self):
        super().__init__()
        # Clean title without hardcoded device names
        self.setWindowTitle("Fan Control")
        self.setWindowIcon(find_app_icon())
        self.setMinimumSize(480, 520)
        self.resize(680, 640)

        self.backend = ECBackend()

        # Modes: 'auto', 'max', 'quiet', 'custom', 'custom_curve'
        self.current_mode = "auto"
        self.linked_fans = True
        self.ring_temps = deque(maxlen=3)
        self.current_auto_duty = 0

        # Smart dynamic curve points (Temperature °C, Target Duty %)
        # 0% Zero-RPM operation below 55°C, dynamically ramping up under load
        self.curve_points = [
            (55, 0),
            (62, 25),
            (70, 45),
            (78, 65),
            (85, 85),
            (90, 100)
        ]

        self._apply_native_theming()
        self._setup_ui()
        self._setup_tray()
        self._setup_timer()

        # Default to Automatic Mode
        self.select_mode("auto")

        # Prompt for authorization on startup if hardware EC access is not yet active
        QTimer.singleShot(250, self._check_and_prompt_elevation)

    def _apply_native_theming(self):
        """Applies clean system theming using Qt palette roles."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: palette(window);
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
            QGroupBox {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 12px;
                font-weight: 600;
                color: palette(window-text);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0px 6px;
                background: transparent;
                color: palette(highlight);
            }
            QPushButton {
                background-color: palette(button);
                color: palette(button-text);
                border: 1px solid palette(mid);
                border-radius: 6px;
                padding: 5px 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                border-color: palette(highlight);
            }
            QPushButton:pressed {
                background-color: palette(mid);
            }
            QPushButton#primaryActionBtn {
                background-color: palette(highlight);
                color: palette(highlighted-text);
                border: 1px solid palette(highlight);
            }
            QSlider::groove:horizontal {
                height: 5px;
                background: palette(mid);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: palette(highlight);
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: palette(window-text);
                border: 2px solid palette(highlight);
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }
            QCheckBox {
                spacing: 6px;
                font-size: 11px;
                color: palette(window-text);
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                border-radius: 3px;
                border: 1px solid palette(mid);
                background: palette(base);
            }
            QCheckBox::indicator:checked {
                background: palette(highlight);
                border-color: palette(highlight);
            }
            QTabWidget::pane {
                border: 1px solid palette(mid);
                border-radius: 8px;
                background-color: palette(window);
            }
            QTabBar::tab {
                background: palette(button);
                color: palette(button-text);
                border: 1px solid palette(mid);
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 5px 12px;
                margin-right: 3px;
                font-weight: 600;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: palette(base);
                color: palette(highlight);
                border-color: palette(highlight);
            }
            QSpinBox {
                background: palette(base);
                color: palette(text);
                border: 1px solid palette(mid);
                border-radius: 6px;
                padding: 3px 6px;
            }
        """)

    def changeEvent(self, event):
        """Catches live desktop theme/palette changes and refreshes custom drawn meters."""
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange):
            self.card_cpu.dial.update()
            self.card_gpu.dial.update()
            self.card_f1.dial.update()
            self.card_f2.dial.update()
            self.graph.update()
            self.curve_vis.update()
            self._update_badge_style()
        super().changeEvent(event)

    def _setup_ui(self):
        root_container = QWidget()
        self.setCentralWidget(root_container)

        root_layout = QVBoxLayout(root_container)
        root_layout.setSpacing(10)
        root_layout.setContentsMargins(12, 10, 12, 10)

        # Clean Header Bar (No hardcoded device names)
        top_bar = QHBoxLayout()
        title = QLabel("Fan Control")
        t_font = QFont(self.font())
        t_font.setPointSize(t_font.pointSize() + 4)
        t_font.setBold(True)
        title.setFont(t_font)
        top_bar.addWidget(title)

        top_bar.addStretch()

        if is_kernel_locked_down():
            self.elevate_btn = QPushButton("Secure Boot Guide")
            self.elevate_btn.setToolTip("Click for instructions to unlock fan control in UEFI BIOS")
            self.elevate_btn.clicked.connect(self._on_elevate_clicked)
            top_bar.addWidget(self.elevate_btn)
            self.status_badge = QLabel("🔒 Secure Boot Active")
        else:
            self.elevate_btn = QPushButton("Unlock Control")
            self.elevate_btn.clicked.connect(self._on_elevate_clicked)
            if self.backend.has_direct_io:
                self.elevate_btn.setVisible(False)
            top_bar.addWidget(self.elevate_btn)
            self.status_badge = QLabel("● Connected" if self.backend.has_direct_io else "⚠ Sensor Readout")

        b_font = QFont(self.font())
        b_font.setPointSize(max(7, b_font.pointSize() - 2))
        b_font.setBold(True)
        self.status_badge.setFont(b_font)
        self._update_badge_style()
        top_bar.addWidget(self.status_badge)

        root_layout.addLayout(top_bar)

        # Tabs (Dashboard & Custom Curve Editor)
        self.tabs = QTabWidget()
        root_layout.addWidget(self.tabs)

        dash_scroll = QScrollArea()
        dash_scroll.setWidgetResizable(True)
        dash_scroll.setFrameShape(QFrame.Shape.NoFrame)

        dash_tab = QWidget()
        dash_scroll.setWidget(dash_tab)
        dash_layout = QVBoxLayout(dash_tab)
        dash_layout.setSpacing(10)
        dash_layout.setContentsMargins(6, 8, 6, 8)

        # 4 Proportional Metric Cards
        gauges_grid = QGridLayout()
        gauges_grid.setContentsMargins(0, 4, 0, 4)
        gauges_grid.setSpacing(8)

        self.card_cpu = MetricCard("CPU TEMPERATURE", is_temp=True)
        self.card_gpu = MetricCard("GPU TEMPERATURE", is_temp=True)
        self.card_f1 = MetricCard("CPU FAN", is_temp=False)
        self.card_f2 = MetricCard("GPU FAN", is_temp=False)

        gauges_grid.addWidget(self.card_cpu, 0, 0)
        gauges_grid.addWidget(self.card_gpu, 0, 1)
        gauges_grid.addWidget(self.card_f1, 0, 2)
        gauges_grid.addWidget(self.card_f2, 0, 3)
        dash_layout.addLayout(gauges_grid)

        # Primary Modes Section: 4 Distinct Mode Cards
        modes_box = QGroupBox("Operating Mode")
        modes_grid = QGridLayout(modes_box)
        modes_grid.setContentsMargins(8, 10, 8, 8)
        modes_grid.setSpacing(8)

        self.btn_mode_auto = ModeButton("Automatic", "Firmware Hardware EC Control", "✨")
        self.btn_mode_max = ModeButton("Maximum", "100% Full Speed Cooling", "⚡")
        self.btn_mode_quiet = ModeButton("Quiet Mode", "Silent Zero RPM (0%)", "🌙")
        self.btn_mode_custom = ModeButton("Custom", "Manual Sliders & Profiles", "🎛️")

        self.btn_mode_auto.clicked.connect(lambda: self.select_mode("auto", user_initiated=True))
        self.btn_mode_max.clicked.connect(lambda: self.select_mode("max", user_initiated=True))
        self.btn_mode_quiet.clicked.connect(lambda: self.select_mode("quiet", user_initiated=True))
        self.btn_mode_custom.clicked.connect(lambda: self.select_mode("custom", user_initiated=True))

        modes_grid.addWidget(self.btn_mode_auto, 0, 0)
        modes_grid.addWidget(self.btn_mode_max, 0, 1)
        modes_grid.addWidget(self.btn_mode_quiet, 1, 0)
        modes_grid.addWidget(self.btn_mode_custom, 1, 1)
        dash_layout.addWidget(modes_box)

        # Custom Controls Panel (Hidden by default; ONLY visible in Custom Mode!)
        self.custom_panel = QGroupBox("Custom Manual Controls")
        custom_layout = QGridLayout(self.custom_panel)
        custom_layout.setContentsMargins(8, 10, 8, 8)
        custom_layout.setSpacing(6)

        # Quick Preset Buttons inside Custom Mode
        quick_btns_layout = QHBoxLayout()
        quick_btns_layout.setSpacing(6)
        btn_q25 = QPushButton("25%")
        btn_q25.clicked.connect(lambda: self._set_custom_speed(25))
        btn_q50 = QPushButton("50%")
        btn_q50.clicked.connect(lambda: self._set_custom_speed(50))
        btn_q75 = QPushButton("75%")
        btn_q75.clicked.connect(lambda: self._set_custom_speed(75))
        btn_q100 = QPushButton("100%")
        btn_q100.clicked.connect(lambda: self._set_custom_speed(100))
        btn_reset_fw = QPushButton("Firmware Reset")
        btn_reset_fw.clicked.connect(self._reset_firmware)

        for btn in (btn_q25, btn_q50, btn_q75, btn_q100, btn_reset_fw):
            btn.setFixedHeight(28)
            quick_btns_layout.addWidget(btn)
        custom_layout.addLayout(quick_btns_layout, 0, 0, 1, 3)

        # Sliders
        lbl_f1 = QLabel("CPU Fan:")
        lbl_f1.setStyleSheet("font-weight: 600; font-size: 11px;")
        self.slider_f1 = QSlider(Qt.Orientation.Horizontal)
        self.slider_f1.setRange(0, 100)
        self.slider_f1.setValue(40)
        self.lbl_f1_val = QLabel("40%")
        self.lbl_f1_val.setMinimumWidth(36)

        lbl_f2 = QLabel("GPU Fan:")
        lbl_f2.setStyleSheet("font-weight: 600; font-size: 11px;")
        self.slider_f2 = QSlider(Qt.Orientation.Horizontal)
        self.slider_f2.setRange(0, 100)
        self.slider_f2.setValue(40)
        self.lbl_f2_val = QLabel("40%")
        self.lbl_f2_val.setMinimumWidth(36)

        self.chk_link = QCheckBox("Link Fans (Synchronize CPU & GPU Fan Duty)")
        self.chk_link.setChecked(True)
        self.chk_link.stateChanged.connect(self._on_link_toggled)

        self.slider_f1.valueChanged.connect(self._on_slider_f1_changed)
        self.slider_f2.valueChanged.connect(self._on_slider_f2_changed)
        self.slider_f1.sliderReleased.connect(self._on_slider_released)
        self.slider_f2.sliderReleased.connect(self._on_slider_released)

        custom_layout.addWidget(lbl_f1, 1, 0)
        custom_layout.addWidget(self.slider_f1, 1, 1)
        custom_layout.addWidget(self.lbl_f1_val, 1, 2)

        custom_layout.addWidget(lbl_f2, 2, 0)
        custom_layout.addWidget(self.slider_f2, 2, 1)
        custom_layout.addWidget(self.lbl_f2_val, 2, 2)

        custom_layout.addWidget(self.chk_link, 3, 0, 1, 3)

        # By default, Custom Panel is hidden until "Custom" mode is chosen!
        self.custom_panel.setVisible(False)
        dash_layout.addWidget(self.custom_panel)

        # Real-time temperature trend graph
        graph_box = QGroupBox("Live Temperature Trends")
        graph_layout = QVBoxLayout(graph_box)
        graph_layout.setContentsMargins(6, 10, 6, 6)
        self.graph = RealtimeHistoryWidget()
        graph_layout.addWidget(self.graph)
        dash_layout.addWidget(graph_box)

        self.tabs.addTab(dash_scroll, "Dashboard")

        # Tab 2: Custom Curve Visualizer & Editor
        curve_scroll = QScrollArea()
        curve_scroll.setWidgetResizable(True)
        curve_scroll.setFrameShape(QFrame.Shape.NoFrame)

        curve_tab = QWidget()
        curve_scroll.setWidget(curve_tab)
        curve_layout = QVBoxLayout(curve_tab)
        curve_layout.setSpacing(8)
        curve_layout.setContentsMargins(6, 8, 6, 8)

        curve_graph_box = QGroupBox("Temperature vs Duty Curve Visualizer")
        cg_layout = QVBoxLayout(curve_graph_box)
        self.curve_vis = CurveVisualizerWidget()
        self.curve_vis.set_curve(self.curve_points)
        cg_layout.addWidget(self.curve_vis)
        curve_layout.addWidget(curve_graph_box)

        points_box = QGroupBox("Custom Curve Profile Points")
        p_grid = QGridLayout(points_box)
        p_grid.setContentsMargins(8, 10, 8, 8)
        p_grid.setSpacing(6)

        p_grid.addWidget(QLabel("<b>Trigger Temp (°C)</b>"), 0, 0)
        p_grid.addWidget(QLabel("<b>Fan Speed (%)</b>"), 0, 1)

        self.spin_boxes = []
        for row, (temp, duty) in enumerate(self.curve_points, start=1):
            s_temp = QSpinBox()
            s_temp.setRange(20, 100)
            s_temp.setValue(temp)
            s_temp.valueChanged.connect(self._on_curve_spin_changed)

            s_duty = QSpinBox()
            s_duty.setRange(0, 100)
            s_duty.setValue(duty)
            s_duty.valueChanged.connect(self._on_curve_spin_changed)

            p_grid.addWidget(s_temp, row, 0)
            p_grid.addWidget(s_duty, row, 1)
            self.spin_boxes.append((s_temp, s_duty))

        btn_row = QHBoxLayout()
        btn_apply_curve = QPushButton("Apply Curve")
        btn_apply_curve.setObjectName("primaryActionBtn")
        btn_apply_curve.clicked.connect(self._save_curve_points)

        btn_preset_silent = QPushButton("Silent Preset")
        btn_preset_silent.clicked.connect(lambda: self._load_curve_preset([
            (55, 0), (65, 0), (75, 30), (85, 60), (90, 85), (95, 100)
        ]))

        btn_preset_perf = QPushButton("Aggressive Preset")
        btn_preset_perf.clicked.connect(lambda: self._load_curve_preset([
            (40, 20), (50, 40), (60, 60), (70, 80), (80, 95), (85, 100)
        ]))

        btn_row.addWidget(btn_preset_silent)
        btn_row.addWidget(btn_preset_perf)
        btn_row.addWidget(btn_apply_curve)
        p_grid.addLayout(btn_row, len(self.curve_points) + 1, 0, 1, 2)

        curve_layout.addWidget(points_box)
        self.tabs.addTab(curve_scroll, "Curve Editor")

    def _update_badge_style(self):
        if self.backend.has_direct_io:
            self.status_badge.setStyleSheet(
                "color: #10b981; background-color: rgba(16, 185, 129, 0.15); "
                "padding: 3px 8px; border-radius: 4px; font-weight: bold;"
            )
        elif is_kernel_locked_down():
            self.status_badge.setStyleSheet(
                "color: #f87171; background-color: rgba(239, 68, 68, 0.18); "
                "padding: 3px 8px; border-radius: 4px; font-weight: bold;"
            )
        else:
            self.status_badge.setStyleSheet(
                "color: #f59e0b; background-color: rgba(245, 158, 11, 0.15); "
                "padding: 3px 8px; border-radius: 4px; font-weight: bold;"
            )

    def select_mode(self, mode: str, user_initiated: bool = False):
        """Switches between Automatic, Maximum, Quiet, and Custom."""
        if user_initiated and not self.backend.has_direct_io and is_kernel_locked_down():
            self._on_elevate_clicked()
            return

        self.current_mode = mode

        self.btn_mode_auto.set_active(mode == "auto")
        self.btn_mode_max.set_active(mode == "max")
        self.btn_mode_quiet.set_active(mode == "quiet")
        self.btn_mode_custom.set_active(mode in ("custom", "custom_curve"))

        self.custom_panel.setVisible(mode in ("custom", "custom_curve"))

        if mode == "auto":
            self.ring_temps.clear()
            status = self.backend.read_status()
            cur_th = max(status.get("cpu", 0), status.get("gpu", 0))
            target = self._calc_duty_for_temp(cur_th)
            if target < 15:
                target = 0
            self.current_auto_duty = target
            self.backend.set_fan(0, target)
            self.slider_f1.blockSignals(True)
            self.slider_f2.blockSignals(True)
            self.slider_f1.setValue(target)
            self.slider_f2.setValue(target)
            self.lbl_f1_val.setText(f"{target}%")
            self.lbl_f2_val.setText(f"{target}%")
            self.slider_f1.blockSignals(False)
            self.slider_f2.blockSignals(False)
        elif mode == "max":
            self.backend.set_fan(0, 100)
            self.slider_f1.blockSignals(True)
            self.slider_f2.blockSignals(True)
            self.slider_f1.setValue(100)
            self.slider_f2.setValue(100)
            self.lbl_f1_val.setText("100%")
            self.lbl_f2_val.setText("100%")
            self.slider_f1.blockSignals(False)
            self.slider_f2.blockSignals(False)
        elif mode == "quiet":
            # Quiet mode sets fan speed to 0% (Silent Zero-RPM mode)
            self.backend.set_fan(0, 0)
            self.slider_f1.blockSignals(True)
            self.slider_f2.blockSignals(True)
            self.slider_f1.setValue(0)
            self.slider_f2.setValue(0)
            self.lbl_f1_val.setText("0%")
            self.lbl_f2_val.setText("0%")
            self.slider_f1.blockSignals(False)
            self.slider_f2.blockSignals(False)
        elif mode == "custom":
            val = self.slider_f1.value()
            self.backend.set_fan(0, val)

    def _set_custom_speed(self, pct: int):
        if not self.backend.has_direct_io and is_kernel_locked_down():
            self._on_elevate_clicked()
            return
        self.slider_f1.setValue(pct)
        self.slider_f2.setValue(pct)
        self.backend.set_fan(0, pct)

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(find_tray_icon())
        self.tray.setVisible(True)

        menu = QMenu()
        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self.showNormal)
        menu.addAction(show_action)

        menu.addSeparator()
        m_auto = QAction("Automatic (EC Firmware)", self)
        m_auto.triggered.connect(lambda: self.select_mode("auto", user_initiated=True))
        menu.addAction(m_auto)

        m_max = QAction("Maximum (100%)", self)
        m_max.triggered.connect(lambda: self.select_mode("max", user_initiated=True))
        menu.addAction(m_max)

        m_quiet = QAction("Quiet Mode (0%)", self)
        m_quiet.triggered.connect(lambda: self.select_mode("quiet", user_initiated=True))
        menu.addAction(m_quiet)

        m_custom = QAction("Custom Mode", self)
        m_custom.triggered.connect(lambda: self.select_mode("custom", user_initiated=True))
        menu.addAction(m_custom)

        menu.addSeparator()
        m_reset = QAction("Firmware Reset", self)
        m_reset.triggered.connect(self._reset_firmware)
        menu.addAction(m_reset)

        menu.addSeparator()
        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()

    def _setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_telemetry)
        self.timer.start(1000)

    def _update_telemetry(self):
        data = self.backend.read_status()
        cpu = data.get("cpu", 0)
        gpu = data.get("gpu", 0)
        f1_d = data.get("fan1_duty", 0)
        f2_d = data.get("fan2_duty", 0)
        f1_r = data.get("fan1_rpm", 0)
        f2_r = data.get("fan2_rpm", 0)

        # Update clean metric cards with status messages
        def _temp_status(t: int) -> str:
            if t <= 0:
                return "Standby"
            elif t < 55:
                return "Optimal"
            elif t < 72:
                return "Normal"
            elif t < 84:
                return "Warm"
            else:
                return "High Load"

        def _fan_status(duty: int, rpm: int) -> str:
            if rpm > 0:
                return f"{rpm:,} RPM"
            if duty > 0:
                return f"{duty}% Active"
            return "Standby"

        self.card_cpu.set_data(cpu, _temp_status(cpu))
        self.card_gpu.set_data(gpu, _temp_status(gpu))
        self.card_f1.set_data(f1_d, _fan_status(f1_d, f1_r))
        self.card_f2.set_data(f2_d, _fan_status(f2_d, f2_r))

        # Update graphs
        self.graph.add_sample(cpu, gpu)
        self.curve_vis.set_curve(self.curve_points, cur_temp=max(cpu, gpu), cur_duty=max(f1_d, f2_d))

        # Tray tooltip
        mode_label = "AUTOMATIC" if self.current_mode == "auto" else self.current_mode.upper()
        self.tray.setToolTip(f"[{mode_label}] CPU: {cpu}°C | GPU: {gpu}°C\nFan 1: {f1_d}% | Fan 2: {f2_d}%")

        # Execute Auto / Custom Curve dynamic thermal loop if active
        if self.current_mode in ("auto", "custom_curve") and cpu > 0:
            self._tick_auto_control(cpu, gpu)

    def _tick_auto_control(self, cpu: int, gpu: int):
        th = max(cpu, gpu) if gpu > 0 else cpu
        self.ring_temps.append(th)
        t_avg = int(sum(self.ring_temps) / len(self.ring_temps))

        target = self._calc_duty_for_temp(t_avg)
        # Drop directly to 0% below 15% duty for true silent Zero-RPM operation
        if target < 15:
            target = 0

        diff = target - self.current_auto_duty
        new_duty = self.current_auto_duty
        if diff > 0:
            step = 2 if t_avg < 75 else 5
            new_duty = self.current_auto_duty + step if diff >= step else target
        elif diff < 0:
            step = 1 if t_avg < 75 else 3
            new_duty = self.current_auto_duty - step if abs(diff) >= step else target
        new_duty = max(0, min(100, new_duty))

        if new_duty != self.current_auto_duty:
            self.backend.set_fan(0, new_duty)
            self.current_auto_duty = new_duty
            self.slider_f1.blockSignals(True)
            self.slider_f2.blockSignals(True)
            self.slider_f1.setValue(new_duty)
            self.slider_f2.setValue(new_duty)
            self.lbl_f1_val.setText(f"{new_duty}%")
            self.lbl_f2_val.setText(f"{new_duty}%")
            self.slider_f1.blockSignals(False)
            self.slider_f2.blockSignals(False)

    def _calc_duty_for_temp(self, temp: int) -> int:
        pts = self.curve_points
        if not pts:
            return 0
        if temp <= pts[0][0]:
            return pts[0][1]
        if temp >= pts[-1][0]:
            return pts[-1][1]
        for i in range(len(pts) - 1):
            t1, p1 = pts[i]
            t2, p2 = pts[i + 1]
            if t1 <= temp < t2:
                if t2 == t1:
                    return p1
                frac = (temp - t1) / float(t2 - t1)
                return int(p1 + (p2 - p1) * frac + 0.5)
        return pts[-1][1]

    def _on_link_toggled(self, state):
        self.linked_fans = (state == Qt.CheckState.Checked.value or state == 2)
        if self.linked_fans:
            self.slider_f2.setValue(self.slider_f1.value())

    def _on_slider_f1_changed(self, val):
        self.lbl_f1_val.setText(f"{val}%")
        if self.linked_fans:
            self.slider_f2.blockSignals(True)
            self.slider_f2.setValue(val)
            self.lbl_f2_val.setText(f"{val}%")
            self.slider_f2.blockSignals(False)

    def _on_slider_f2_changed(self, val):
        self.lbl_f2_val.setText(f"{val}%")
        if self.linked_fans:
            self.slider_f1.blockSignals(True)
            self.slider_f1.setValue(val)
            self.lbl_f1_val.setText(f"{val}%")
            self.slider_f1.blockSignals(False)

    def _on_slider_released(self):
        if not self.backend.has_direct_io and is_kernel_locked_down():
            self._on_elevate_clicked()
            return
        val1 = self.slider_f1.value()
        val2 = self.slider_f2.value()
        if self.linked_fans:
            self.backend.set_fan(0, val1)
        else:
            self.backend.set_fan(1, val1)
            self.backend.set_fan(2, val2)

    def _reset_firmware(self):
        self.select_mode("auto")
        QMessageBox.information(self, "Firmware Reset", "Fans restored to EC firmware automatic control.")

    def _on_curve_spin_changed(self):
        pts = [(s_temp.value(), s_duty.value()) for s_temp, s_duty in self.spin_boxes]
        pts.sort(key=lambda x: x[0])
        self.curve_points = pts
        self.curve_vis.set_curve(self.curve_points)

    def _load_curve_preset(self, points: list[tuple[int, int]]):
        for (s_temp, s_duty), (t, d) in zip(self.spin_boxes, points):
            s_temp.blockSignals(True)
            s_duty.blockSignals(True)
            s_temp.setValue(t)
            s_duty.setValue(d)
            s_temp.blockSignals(False)
            s_duty.blockSignals(False)
        self.curve_points = points
        self.curve_vis.set_curve(self.curve_points)

    def _save_curve_points(self):
        pts = [(s_temp.value(), s_duty.value()) for s_temp, s_duty in self.spin_boxes]
        pts.sort(key=lambda x: x[0])
        self.curve_points = pts
        self.curve_vis.set_curve(self.curve_points)
        self.current_mode = "custom_curve"
        self.btn_mode_auto.set_active(False)
        self.btn_mode_max.set_active(False)
        self.btn_mode_quiet.set_active(False)
        self.btn_mode_custom.set_active(True)
        self.custom_panel.setVisible(True)
        QMessageBox.information(self, "Curve Applied", "Custom dynamic fan curve activated.")

    def _check_and_prompt_elevation(self):
        """If direct EC access is not yet active, prompt for authorization on startup."""
        if self.backend.has_direct_io:
            return

        # Do not prompt in automated offscreen headless test environments
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return

        # If kernel lockdown is active due to UEFI Secure Boot, raw port I/O
        # is strictly forbidden by the kernel regardless of capabilities or root.
        # Do not prompt for passwords uselessly on startup.
        if is_kernel_locked_down():
            return

        # Security: Only permit capability elevation on verified system-installed binaries
        # Never grant file capabilities to user-writable paths or non-root owned files
        allowed_bins = (pathlib.Path("/usr/bin/fan-control"), pathlib.Path("/usr/local/bin/fan-control"))
        if not CLI_PATH or CLI_PATH not in allowed_bins or not CLI_PATH.is_file():
            return

        try:
            st = os.stat(CLI_PATH)
            if st.st_uid != 0 or (st.st_mode & 0o022) != 0:
                return
        except Exception:
            return

        elevated = False

        # 1. Attempt Polkit elevation via pkexec
        try:
            res = subprocess.run(
                ["pkexec", "setcap", "cap_sys_rawio+ep", str(CLI_PATH)],
                capture_output=True,
                timeout=30
            )
            if res.returncode == 0:
                elevated = True
        except Exception:
            pass

        # 2. Fallback: Prompt via Qt password dialog if pkexec was unavailable or failed
        if not elevated:
            try:
                pwd, ok = QInputDialog.getText(
                    self,
                    "Hardware Authorization Required",
                    "Fan Control requires administrator permission to access\n"
                    "the Embedded Controller hardware (run once):\n\n"
                    "Enter administrator / root password:",
                    QLineEdit.EchoMode.Password
                )
                if ok and pwd:
                    p = subprocess.run(
                        ["sudo", "-S", "-k", "setcap", "cap_sys_rawio+ep", str(CLI_PATH)],
                        input=pwd + "\n",
                        capture_output=True,
                        text=True,
                        timeout=15
                    )
                    if p.returncode == 0:
                        elevated = True
            except Exception:
                pass

        if elevated:
            self.backend._init_backend()
            if self.backend.has_direct_io:
                if hasattr(self, "elevate_btn"):
                    self.elevate_btn.setVisible(False)
                if hasattr(self, "status_badge"):
                    self.status_badge.setText("● Connected")
                    self._update_badge_style()
                self._poll_sensors()
                return

    def _on_elevate_clicked(self):
        if is_kernel_locked_down():
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning if hasattr(QMessageBox, "Icon") else QMessageBox.Warning)
            msg.setWindowTitle("UEFI Secure Boot Active")
            msg.setText(
                "<h3>Hardware Fan Control Blocked by Linux Kernel Lockdown</h3>"
                "<p>Your password was accepted, but the Linux kernel has <b>Kernel Lockdown</b> active "
                "because <b>UEFI Secure Boot</b> is enabled in your laptop BIOS.</p>"
                "<p>Under Kernel Lockdown, Linux strictly blocks direct hardware I/O port access "
                "(<code>ioperm</code> to the Embedded Controller) — even for <code>root</code> / administrator.</p>"
                "<hr>"
                "<p><b>How to unlock hardware fan control in BIOS:</b></p>"
                "<ol>"
                "<li><b>Reboot</b> your laptop and repeatedly tap <b>F2</b> (or Del) to enter BIOS / UEFI setup.</li>"
                "<li>Go to the <b>Security</b> tab and choose <b>Set Supervisor Password</b>.<br>"
                "<i>(Acer laptops lock the Secure Boot toggle until a supervisor password is set. Pick a simple password you will remember!)</i></li>"
                "<li>Go to the <b>Boot</b> tab (or Security tab), select <b>Secure Boot</b>, and change it to <b>Disabled</b>.</li>"
                "<li>Press <b>F10</b> (Save & Exit) and boot back into Linux.</li>"
                "</ol>"
                "<p>Once Secure Boot is disabled, Fan Control will automatically have full direct hardware control with no extra passwords needed.</p>"
            )
            msg.exec()
            return

        self._check_and_prompt_elevation()
        if self.backend.has_direct_io:
            if hasattr(self, "elevate_btn"):
                self.elevate_btn.setVisible(False)
            if hasattr(self, "status_badge"):
                self.status_badge.setText("● Connected")
                self._update_badge_style()
            QMessageBox.information(self, "Success", "Direct EC access active.")
        else:
            QMessageBox.warning(self, "Authorization Failed", "Could not acquire raw I/O permissions to the Embedded Controller.")


def main():
    # Enable high-DPI scaling across fractional & high-resolution displays
    if hasattr(QtCore.Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(QtCore.Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    if hasattr(QtCore.Qt, "HighDpiScaleFactorRoundingPolicy") and hasattr(QtCore.Qt.HighDpiScaleFactorRoundingPolicy, "PassThrough"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    app = QApplication(sys.argv)
    app.setApplicationName("FanControl")
    app.setWindowIcon(find_app_icon())
    window = FanControlMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
