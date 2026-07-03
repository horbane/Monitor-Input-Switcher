import ctypes
import ctypes.wintypes
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)


APP_DIR = Path(__file__).resolve().parent
CONFIG_FILE = APP_DIR / "config.json"
APP_ICON_RELATIVE_PATH = "assets/icons/monitor-input-switcher.ico"
APP_ICON_256_RELATIVE_PATH = "assets/icons/monitor-input-switcher-256.png"
APP_ICON_64_RELATIVE_PATH = "assets/icons/monitor-input-switcher-64.png"
APP_ICON_32_RELATIVE_PATH = "assets/icons/monitor-input-switcher-32.png"
TRAY_ICON_RELATIVE_PATH = "assets/icons/monitor-input-switcher-64.png"
APP_USER_MODEL_ID = "MonitorInputSwitcher.App"

DEFAULT_SETTINGS = {
    "controlmymonitor_path": r"C:\Tools\controlmymonitor\ControlMyMonitor.exe",
    "target_input_name": "Other Device",
    "vcp_code": "60",
    "group_hotkey": "",
    "configured_monitors": [],
}

DARK_THEME_STYLESHEET = """
QMainWindow,
QDialog,
QWidget#RootContainer,
QWidget#SetupPage {
    background-color: qlineargradient(
        x1: 0, y1: 1, x2: 1, y2: 0,
        stop: 0 #1A1630,
        stop: 0.52 #171B2B,
        stop: 1 #111827
    );
    color: #f3f3f3;
    font-size: 13px;
}
QWidget {
    background-color: transparent;
    color: #f3f3f3;
    font-size: 13px;
}
QLabel {
    color: #f3f3f3;
    background-color: transparent;
}
QStackedWidget {
    background-color: transparent;
    border: none;
}
QGroupBox {
    background-color: #242832;
    border: 1px solid #3A3F4B;
    border-radius: 10px;
    margin-top: 12px;
    padding: 14px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #cfcfcf;
}
QLineEdit {
    background-color: #1E2430;
    border: 1px solid #3A3F4B;
    border-radius: 6px;
    padding: 7px;
    color: #ffffff;
}
QPushButton {
    background-color: #303642;
    border: 1px solid #4A5261;
    border-radius: 7px;
    padding: 7px 12px;
    color: #ffffff;
}
QPushButton:hover {
    background-color: #3A4250;
}
QPushButton:pressed {
    background-color: #252B35;
}
QPushButton:disabled {
    background-color: #262B35;
    border-color: #343A46;
    color: #777F8D;
}
QPushButton#PrimaryButton {
    background-color: #2478A8;
    border: 1px solid #4CC2FF;
    font-weight: bold;
}
QPushButton#PrimaryButton:hover {
    background-color: #2D8DC1;
}
QFrame#Divider {
    background-color: #3A3F4B;
    max-height: 1px;
    border: none;
}
"""

TRAY_MENU_STYLESHEET = """
QMenu {
    background-color: #252A34;
    color: #F3F4F6;
    border: 1px solid #3A3F4B;
    border-radius: 8px;
    padding: 6px;
}
QMenu::item {
    padding: 7px 28px 7px 24px;
    border-radius: 5px;
    background-color: transparent;
}
QMenu::item:selected {
    background-color: #3A4456;
}
QMenu::separator {
    height: 1px;
    background: #3A3F4B;
    margin: 5px 6px;
}
"""

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000


def make_auto_button_label(target_input_name):
    target_input_name = target_input_name.strip()
    if not target_input_name:
        target_input_name = DEFAULT_SETTINGS["target_input_name"]
    return f"Switch selected monitors to {target_input_name}"


def make_divider():
    divider = QFrame()
    divider.setObjectName("Divider")
    divider.setFrameShape(QFrame.HLine)
    divider.setFrameShadow(QFrame.Plain)
    return divider


def make_toggle(checked=True):
    toggle = ToggleSwitch()
    toggle.setChecked(checked)
    toggle._animation.stop()
    toggle.set_knob_position(1.0 if checked else 0.0)
    return toggle


def use_gradient_background(widget, object_name):
    """Make sure Qt paints the shared gradient on this widget."""
    widget.setObjectName(object_name)
    widget.setAttribute(Qt.WA_StyledBackground, True)


def resource_path(relative_path):
    """Find bundled files during development or after PyInstaller packaging."""
    relative_path = Path(relative_path)
    candidate_bases = [
        Path(getattr(sys, "_MEIPASS", APP_DIR)),
        APP_DIR,
    ]

    if getattr(sys, "frozen", False):
        candidate_bases.append(Path(sys.executable).resolve().parent)

    for base_path in candidate_bases:
        candidate = base_path / relative_path
        if candidate.exists():
            return candidate

    return APP_DIR / relative_path


def load_icon(relative_paths, description):
    """Load an icon if it exists, but never crash if the file is missing."""
    icon = QIcon()
    for relative_path in relative_paths:
        icon_path = resource_path(relative_path)
        if icon_path.exists():
            icon.addFile(str(icon_path))

    if not icon.isNull():
        return icon

    print(f"Warning: {description} icon file was not found.")
    return QIcon()


def get_application_icon():
    """Return the already configured QApplication icon when available."""
    app = QApplication.instance()
    if app and not app.windowIcon().isNull():
        return app.windowIcon()

    return load_icon(
        [
            APP_ICON_256_RELATIVE_PATH,
            APP_ICON_64_RELATIVE_PATH,
            APP_ICON_32_RELATIVE_PATH,
            APP_ICON_RELATIVE_PATH,
        ],
        "app",
    )


def set_windows_app_user_model_id():
    """Help Windows taskbar use this app's icon while running from Python."""
    if sys.platform != "win32":
        return

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except OSError as error:
        print(f"Warning: could not set Windows AppUserModelID: {error}")


def configure_application_metadata(app):
    """Set clean app identity for Windows notifications and Qt windows."""
    app.setApplicationName("Monitor Input Switcher")
    if hasattr(app, "setApplicationDisplayName"):
        app.setApplicationDisplayName("Monitor Input Switcher")
    app.setOrganizationName("MonitorInputSwitcher")
    app.setOrganizationDomain("")


class ToggleSwitch(QAbstractButton):
    """Small custom ON/OFF switch painted like a Windows 11 toggle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._knob_position = 0.0
        self._animation = QPropertyAnimation(self, b"knob_position", self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 24)
        self.toggled.connect(self.animate_knob)

    def sizeHint(self):
        return QSize(46, 24)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track = QRectF(1, 2, 44, 20)
        track_color = QColor("#4CC2FF") if self.isChecked() else QColor("#3E4654")
        border_color = QColor("#73D2FF") if self.isChecked() else QColor("#697180")
        knob_color = QColor("#FFFFFF") if self.isChecked() else QColor("#D5D8DE")
        shadow_color = QColor(0, 0, 0, 80)

        painter.setPen(border_color)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 10, 10)

        knob_x = 5 + (20 * self._knob_position)
        shadow = QRectF(knob_x, 6, 14, 14)
        painter.setPen(Qt.NoPen)
        painter.setBrush(shadow_color)
        painter.drawEllipse(shadow)

        knob = QRectF(knob_x, 5, 14, 14)
        painter.setBrush(knob_color)
        painter.drawEllipse(knob)

    def get_knob_position(self):
        return self._knob_position

    def set_knob_position(self, position):
        self._knob_position = position
        self.update()

    knob_position = Property(float, get_knob_position, set_knob_position)

    def animate_knob(self, checked):
        # Animate only the knob; the checked state itself still drives the logic.
        self._animation.stop()
        self._animation.setStartValue(self._knob_position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()


class MonitorInputSwitcher(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Monitor Input Switcher")
        self.setMinimumWidth(680)
        self.apply_dark_theme()
        self.app_icon = get_application_icon()
        if not self.app_icon.isNull():
            self.setWindowIcon(self.app_icon)

        self.settings = self.load_settings()
        self.backend_found = self.detect_and_save_backend_path()
        self.registered_hotkeys = {}
        self.next_hotkey_id = 1
        self.force_quit = False
        self.tray_message_shown = False
        self.tray_icon = None
        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)

        self.setup_tray_icon()

        self.configured_on_launch = self.has_valid_configured_monitors(self.settings)
        if self.configured_on_launch:
            self.show_main_app()
        else:
            self.show_setup_wizard()

    def apply_dark_theme(self):
        # Optional future feature: Windows Mica/Acrylic background.
        app = QApplication.instance()
        if app:
            app.setStyleSheet(DARK_THEME_STYLESHEET)
        else:
            self.setStyleSheet(DARK_THEME_STYLESHEET)

    def load_settings(self):
        if not CONFIG_FILE.exists():
            return DEFAULT_SETTINGS.copy()

        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as file:
                saved_settings = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            print(f"Could not load config.json: {error}")
            return DEFAULT_SETTINGS.copy()

        settings = DEFAULT_SETTINGS.copy()
        settings.update(saved_settings)

        # Older versions saved only one manual monitor identifier. That is not
        # enough for the simplified main app, so the wizard will run again.
        settings["controlmymonitor_path"] = str(
            settings.get("controlmymonitor_path", DEFAULT_SETTINGS["controlmymonitor_path"])
        )
        settings["target_input_name"] = str(
            settings.get("target_input_name", DEFAULT_SETTINGS["target_input_name"])
        )
        settings["vcp_code"] = str(settings.get("vcp_code", "60"))
        settings["group_hotkey"] = clean_hotkey_string(
            settings.get("group_hotkey", "")
        )

        configured_monitors = settings.get("configured_monitors", [])
        if not isinstance(configured_monitors, list):
            configured_monitors = []
        for monitor in configured_monitors:
            if isinstance(monitor, dict):
                monitor["hotkey"] = clean_hotkey_string(monitor.get("hotkey", ""))
        settings["configured_monitors"] = configured_monitors

        return settings

    def has_valid_configured_monitors(self, settings):
        vcp_code = str(settings.get("vcp_code", "60")).strip()
        if not vcp_code.isdigit():
            return False

        monitors = settings.get("configured_monitors", [])
        if not monitors:
            return False

        for monitor in monitors:
            if not isinstance(monitor, dict):
                return False
            if not str(monitor.get("monitor_identifier", "")).strip():
                return False
            if bool(monitor.get("enabled", True)) and not self.is_valid_input_value(
                monitor.get("target_input_value", "")
            ):
                return False

        return True

    def is_valid_input_value(self, value):
        value = str(value).strip()
        return value.isdigit() and int(value) > 0

    def detect_and_save_backend_path(self):
        found_path = self.find_backend_path(
            self.settings.get("controlmymonitor_path", "")
        )
        if not found_path:
            return False

        self.settings["controlmymonitor_path"] = str(found_path)
        try:
            self.save_settings_to_config(self.settings)
        except OSError:
            pass
        return True

    def find_backend_path(self, saved_path):
        candidates = [
            APP_DIR / "ControlMyMonitor.exe",
            APP_DIR / "controlmymonitor" / "ControlMyMonitor.exe",
            Path(saved_path) if saved_path else None,
            Path(DEFAULT_SETTINGS["controlmymonitor_path"]),
        ]

        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate

        return None

    def save_settings_to_config(self, settings):
        with CONFIG_FILE.open("w", encoding="utf-8") as file:
            json.dump(settings, file, indent=4)

    def register_global_hotkeys(self):
        self.unregister_global_hotkeys()

        if sys.platform != "win32":
            self.show_hotkey_warning()
            return False

        hotkey_actions = []
        group_hotkey = self.settings.get("group_hotkey", "")
        if group_hotkey:
            hotkey_actions.append((group_hotkey, self.switch_selected_monitors))

        for row in self.main_monitor_rows:
            hotkey = row.get("hotkey", "")
            if hotkey:
                hotkey_actions.append(
                    (hotkey, lambda checked=False, item=row: self.switch_one_monitor(item))
                )

        failed = False
        for hotkey, action in hotkey_actions:
            parsed = parse_hotkey_for_windows(hotkey)
            if parsed is None:
                failed = True
                continue

            modifiers, vk_code = parsed
            hotkey_id = self.next_hotkey_id
            self.next_hotkey_id += 1

            registered = ctypes.windll.user32.RegisterHotKey(
                int(self.winId()),
                hotkey_id,
                modifiers | MOD_NOREPEAT,
                vk_code,
            )
            if not registered:
                failed = True
                continue

            self.registered_hotkeys[hotkey_id] = action

        if failed:
            self.show_hotkey_warning()
            return False

        return True

    def unregister_global_hotkeys(self):
        if sys.platform == "win32":
            for hotkey_id in list(getattr(self, "registered_hotkeys", {})):
                ctypes.windll.user32.UnregisterHotKey(int(self.winId()), hotkey_id)

        self.registered_hotkeys = {}

    def show_hotkey_warning(self):
        self.set_error(
            "Global hotkeys could not be registered. "
            "The app will still work normally."
        )

    def setup_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        QApplication.instance().setQuitOnLastWindowClosed(False)
        self.tray_icon = QSystemTrayIcon(self)
        icon = load_icon(
            [
                APP_ICON_256_RELATIVE_PATH,
                TRAY_ICON_RELATIVE_PATH,
                APP_ICON_64_RELATIVE_PATH,
                APP_ICON_32_RELATIVE_PATH,
                APP_ICON_RELATIVE_PATH,
            ],
            "tray",
        )
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("Monitor Input Switcher")
        self.tray_icon.activated.connect(self.handle_tray_activation)
        self.update_tray_menu()
        self.tray_icon.show()

    def update_tray_menu(self):
        if not self.tray_icon:
            return

        menu = QMenu()
        # Keep the tray menu solid and readable even though the app windows use
        # transparent child widgets over a gradient background.
        menu.setStyleSheet(TRAY_MENU_STYLESHEET)

        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show_from_tray)
        menu.addAction(show_action)

        target_name = self.settings.get(
            "target_input_name",
            DEFAULT_SETTINGS["target_input_name"],
        )
        switch_action = QAction(
            f"Switch selected monitors to {target_name}",
            self,
        )
        switch_action.triggered.connect(self.switch_selected_monitors)
        switch_action.setEnabled(self.has_valid_configured_monitors(self.settings))
        menu.addAction(switch_action)

        setup_action = QAction("Re-run Setup", self)
        setup_action.triggered.connect(self.show_setup_from_tray)
        menu.addAction(setup_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_from_tray)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)

    def handle_tray_activation(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_from_tray()

    def show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def show_setup_from_tray(self):
        self.show_from_tray()
        self.show_setup_wizard()

    def quit_from_tray(self):
        self.force_quit = True
        self.unregister_global_hotkeys()
        if self.tray_icon:
            self.tray_icon.hide()
        QApplication.quit()

    def notify_still_running_in_tray(self):
        if not self.tray_icon or self.tray_message_shown:
            return

        self.tray_icon.showMessage(
            "Monitor Input Switcher",
            "Monitor Input Switcher is still running",
            QSystemTrayIcon.Information,
            3000,
        )
        self.tray_message_shown = True

    def changeEvent(self, event):
        if (
            event.type() == event.Type.WindowStateChange
            and self.tray_icon
            and self.isMinimized()
        ):
            self.hide()
            self.notify_still_running_in_tray()
        super().changeEvent(event)

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                action = self.registered_hotkeys.get(msg.wParam)
                if action:
                    action()
                    return True, 0

        return False, 0

    def closeEvent(self, event):
        if self.force_quit or not self.tray_icon:
            self.unregister_global_hotkeys()
            super().closeEvent(event)
            return

        event.ignore()
        self.hide()
        self.notify_still_running_in_tray()

    def detect_monitors_from_exe(self, exe_path):
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".txt",
                prefix="controlmymonitor_monitors_",
            ) as temp_file:
                temp_path = Path(temp_file.name)

            # /smonitors writes monitor information to a temporary text file.
            subprocess.run(
                [exe_path, "/smonitors", str(temp_path)],
                check=True,
                capture_output=True,
                text=True,
                creationflags=self.get_creation_flags(),
            )
            return parse_monitors_text(read_text_file(temp_path))
        finally:
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def read_current_input_value(self, exe_path, monitor_identifier, vcp_code):
        success, current_value, reason = self.read_current_input_value_detailed(
            exe_path,
            monitor_identifier,
            vcp_code,
        )
        if not success:
            return None
        return current_value

    def read_current_input_value_detailed(self, exe_path, monitor_identifier, vcp_code):
        try:
            # /GetValue returns the VCP value as the process exit code.
            result = subprocess.run(
                [exe_path, "/GetValue", monitor_identifier, vcp_code],
                capture_output=True,
                text=True,
                creationflags=self.get_creation_flags(),
            )
        except OSError as error:
            return False, None, f"Could not read VCP {vcp_code}."

        output = f"{result.stdout}\n{result.stderr}"
        output_lower = output.lower()
        if "error 31" in output_lower or result.returncode == 31:
            return (
                False,
                None,
                "Display returned Error 31. This is likely an internal "
                "laptop display or unsupported display.",
            )

        output_looks_like_error = any(
            text in output_lower
            for text in (
                "error",
                "failed",
                "not functioning",
                "not supported",
                "cannot",
            )
        )

        if result.returncode < 0 or output_looks_like_error:
            return False, None, f"Could not read VCP {vcp_code}."

        current_value = self.parse_vcp_value(result)
        if current_value is None:
            return False, None, "Could not parse a valid input value."

        if current_value == 0:
            return (
                False,
                None,
                "VCP input value returned 0, which is not useful for input switching.",
            )

        if current_value < 0:
            return False, None, "Could not parse a valid input value."

        return True, str(current_value), ""

    def parse_vcp_value(self, result):
        # ControlMyMonitor normally gives /GetValue through the process exit
        # code. If a future version prints a number, prefer the printed value.
        output = f"{result.stdout}\n{result.stderr}".strip()
        if output:
            match = re.search(r"\b(\d+)\b", output)
            if match:
                return int(match.group(1))
            return None

        if result.returncode is None:
            return None

        return int(result.returncode)

    def show_main_app(self):
        self.settings = self.load_settings()
        self.backend_found = Path(
            self.settings.get("controlmymonitor_path", "")
        ).exists()
        self.main_monitor_rows = []

        title_label = QLabel("Monitor Input Switcher")
        title_label.setStyleSheet("font-size: 22px; font-weight: bold;")

        target_label = QLabel(f"Target: {self.settings['target_input_name']}")
        target_label.setStyleSheet("font-size: 15px; color: #c8c8c8;")

        self.main_switch_button = QPushButton(
            make_auto_button_label(self.settings["target_input_name"])
        )
        self.main_switch_button.setObjectName("PrimaryButton")
        self.main_switch_button.setMinimumHeight(52)
        self.main_switch_button.setStyleSheet(
            "font-size: 16px; font-weight: bold; padding: 10px;"
        )
        self.main_switch_button.clicked.connect(self.switch_selected_monitors)

        monitors_group = QGroupBox("Configured monitors")
        monitors_layout = QVBoxLayout()
        monitors_layout.setSpacing(10)
        configured_monitors = self.settings["configured_monitors"]
        for index, monitor in enumerate(configured_monitors, start=1):
            row = self.create_main_monitor_row(monitor, index)
            self.main_monitor_rows.append(row)
            monitors_layout.addLayout(row["layout"])
            if index < len(configured_monitors):
                monitors_layout.addWidget(make_divider())
        monitors_group.setLayout(monitors_layout)

        rerun_setup_button = QPushButton("Re-run Setup")
        rerun_setup_button.clicked.connect(self.show_setup_wizard)

        shortcuts_group = self.create_shortcuts_group()

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.main_switch_button)
        button_layout.addWidget(rerun_setup_button)

        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(14)
        main_layout.addWidget(title_label)
        main_layout.addWidget(target_label)
        main_layout.addWidget(monitors_group)
        main_layout.addWidget(shortcuts_group)
        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.status_label)

        container = QWidget()
        container.setObjectName("RootContainer")
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        if not self.backend_found:
            self.set_error(
                "Monitor control engine was not found. "
                "Click Re-run Setup to choose ControlMyMonitor.exe."
            )
        else:
            self.register_global_hotkeys()
        self.update_tray_menu()

    def create_main_monitor_row(self, monitor, display_index):
        checkbox = make_toggle(bool(monitor.get("enabled", True)))

        friendly_label = display_label_from_config_monitor(monitor, display_index)
        label = QLabel(friendly_label)
        label.setStyleSheet("font-size: 14px; font-weight: bold;")
        label.setToolTip(str(monitor.get("monitor_identifier", "")))

        target_value = str(monitor.get("target_input_value", ""))
        detail_label = QLabel(f"Target value: {target_value}")
        detail_label.setStyleSheet("color: #a7a7a7;")

        switch_button = QPushButton("Switch this monitor")

        text_layout = QVBoxLayout()
        text_layout.addWidget(label)
        text_layout.addWidget(detail_label)

        toggle_label = QLabel("Enabled")
        toggle_label.setStyleSheet("color: #AAB2C0; font-size: 11px;")
        toggle_layout = QVBoxLayout()
        toggle_layout.setSpacing(4)
        toggle_layout.addWidget(checkbox, 0, Qt.AlignCenter)
        toggle_layout.addWidget(toggle_label, 0, Qt.AlignCenter)

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(8, 6, 8, 6)
        row_layout.addLayout(toggle_layout)
        row_layout.addLayout(text_layout, 1)
        row_layout.addWidget(switch_button)

        row = {
            "checkbox": checkbox,
            "friendly_label": friendly_label,
            "monitor_identifier": str(monitor.get("monitor_identifier", "")),
            "target_input_value": target_value,
            "hotkey": str(monitor.get("hotkey", "")),
            "monitor_config": monitor,
            "layout": row_layout,
        }
        switch_button.clicked.connect(
            lambda checked=False, item=row: self.switch_one_monitor(item)
        )
        return row

    def create_shortcuts_group(self):
        shortcuts_group = QGroupBox("Shortcuts")
        shortcuts_layout = QVBoxLayout()

        group_layout = QHBoxLayout()
        group_layout.setContentsMargins(6, 4, 6, 4)
        group_layout.addWidget(QLabel("Group switch:"))
        self.group_hotkey_label = QLabel(
            self.format_hotkey_label(self.settings.get("group_hotkey", ""))
        )
        group_layout.addWidget(self.group_hotkey_label, 1)

        set_group_button = QPushButton("Set group shortcut")
        set_group_button.clicked.connect(self.set_group_hotkey)
        group_layout.addWidget(set_group_button)

        clear_group_button = QPushButton("Clear")
        clear_group_button.clicked.connect(self.clear_group_hotkey)
        group_layout.addWidget(clear_group_button)

        shortcuts_layout.addLayout(group_layout)
        shortcuts_layout.addWidget(make_divider())

        for index, row in enumerate(self.main_monitor_rows):
            monitor_layout = QHBoxLayout()
            monitor_layout.setContentsMargins(6, 4, 6, 4)
            monitor_layout.addWidget(QLabel(f"{row['friendly_label']}:"))

            hotkey_label = QLabel(self.format_hotkey_label(row.get("hotkey", "")))
            row["hotkey_label"] = hotkey_label
            monitor_layout.addWidget(hotkey_label, 1)

            set_button = QPushButton("Set shortcut")
            set_button.clicked.connect(
                lambda checked=False, item=row: self.set_monitor_hotkey(item)
            )
            monitor_layout.addWidget(set_button)

            clear_button = QPushButton("Clear")
            clear_button.clicked.connect(
                lambda checked=False, item=row: self.clear_monitor_hotkey(item)
            )
            monitor_layout.addWidget(clear_button)

            shortcuts_layout.addLayout(monitor_layout)
            if index < len(self.main_monitor_rows) - 1:
                shortcuts_layout.addWidget(make_divider())

        shortcuts_group.setLayout(shortcuts_layout)
        return shortcuts_group

    def show_setup_wizard(self):
        self.unregister_global_hotkeys()
        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)

        wizard = SetupWizard(self)
        self.setCentralWidget(wizard)

    def format_hotkey_label(self, hotkey):
        return hotkey if hotkey else "Not set"

    def set_group_hotkey(self):
        hotkey = self.capture_hotkey()
        if not hotkey:
            return
        hotkey = clean_hotkey_string(hotkey)

        if self.hotkey_is_duplicate(hotkey, action_type="group"):
            self.set_error("This shortcut is already used by another action.")
            return

        self.settings["group_hotkey"] = hotkey
        self.group_hotkey_label.setText(self.format_hotkey_label(hotkey))
        self.save_shortcuts_and_register()

    def clear_group_hotkey(self):
        self.settings["group_hotkey"] = ""
        self.group_hotkey_label.setText(self.format_hotkey_label(""))
        self.save_shortcuts_and_register()

    def set_monitor_hotkey(self, row):
        hotkey = self.capture_hotkey()
        if not hotkey:
            return
        hotkey = clean_hotkey_string(hotkey)

        if self.hotkey_is_duplicate(hotkey, action_type="monitor", action_row=row):
            self.set_error("This shortcut is already used by another action.")
            return

        row["hotkey"] = hotkey
        row["monitor_config"]["hotkey"] = hotkey
        row["hotkey_label"].setText(self.format_hotkey_label(hotkey))
        self.save_shortcuts_and_register()

    def clear_monitor_hotkey(self, row):
        row["hotkey"] = ""
        row["monitor_config"]["hotkey"] = ""
        row["hotkey_label"].setText(self.format_hotkey_label(""))
        self.save_shortcuts_and_register()

    def capture_hotkey(self):
        dialog = HotkeyCaptureDialog(self)
        if dialog.exec() == QDialog.Accepted:
            return dialog.hotkey
        return ""

    def hotkey_is_duplicate(self, hotkey, action_type, action_row=None):
        normalized_hotkey = normalize_hotkey(hotkey)
        group_hotkey = normalize_hotkey(self.settings.get("group_hotkey", ""))

        if action_type != "group" and group_hotkey == normalized_hotkey:
            return True

        for row in self.main_monitor_rows:
            if action_type == "monitor" and row is action_row:
                continue

            if normalize_hotkey(row.get("hotkey", "")) == normalized_hotkey:
                return True

        return False

    def save_shortcuts_and_register(self):
        try:
            self.save_settings_to_config(self.settings)
        except OSError as error:
            self.set_error(f"Could not save shortcut settings: {error}")
            return

        if self.register_global_hotkeys():
            self.set_success("Shortcut settings saved.")

    def switch_selected_monitors(self):
        if not hasattr(self, "main_monitor_rows"):
            self.set_error("Finish setup before switching monitors.")
            return

        selected_rows = [
            row for row in self.main_monitor_rows if row["checkbox"].isChecked()
        ]
        target_input_name = self.settings["target_input_name"]

        if not selected_rows:
            self.set_error("Please select at least one monitor to switch.")
            return

        switch_settings_list = []
        for row in selected_rows:
            switch_settings, error = self.validate_switch_settings(
                row["monitor_identifier"],
                row["target_input_value"],
            )
            if error:
                self.set_error(error)
                return
            switch_settings_list.append(switch_settings)

        switched_count = 0
        for switch_settings in switch_settings_list:
            try:
                self.send_switch_command(switch_settings)
            except subprocess.CalledProcessError as error:
                message = error.stderr.strip() or error.stdout.strip() or str(error)
                self.set_error(
                    f"Command failed after {switched_count} monitor(s): {message}"
                )
                return
            except OSError as error:
                self.set_error(
                    "Could not run ControlMyMonitor.exe after "
                    f"{switched_count} monitor(s): {error}"
                )
                return

            switched_count += 1
            time.sleep(0.2)

        self.set_success(
            "Command sent successfully. "
            f"Switched {switched_count} monitor(s) to {target_input_name}."
        )

    def switch_one_monitor(self, monitor_row):
        switch_settings, error = self.validate_switch_settings(
            monitor_row["monitor_identifier"],
            monitor_row["target_input_value"],
        )
        if error:
            self.set_error(error)
            return

        try:
            self.send_switch_command(switch_settings)
        except subprocess.CalledProcessError as error:
            message = error.stderr.strip() or error.stdout.strip() or str(error)
            self.set_error(f"Command failed: {message}")
            return
        except OSError as error:
            self.set_error(f"Could not run ControlMyMonitor.exe: {error}")
            return

        self.set_success(
            "Command sent successfully. "
            f"Switched {monitor_row['friendly_label']} "
            f"to {self.settings['target_input_name']}."
        )

    def validate_switch_settings(self, monitor_identifier, input_value):
        exe_path = self.settings["controlmymonitor_path"]
        vcp_code = str(self.settings.get("vcp_code", "60")).strip()

        if not exe_path:
            return None, "Please enter the path to ControlMyMonitor.exe."

        if not Path(exe_path).exists():
            return None, f"ControlMyMonitor.exe was not found: {exe_path}"

        if not monitor_identifier:
            return None, "Monitor identifier is missing. Re-run setup."

        if not vcp_code.isdigit():
            return None, "The VCP code in config.json must be a number."

        if not str(input_value).strip().isdigit():
            return None, "Target input value must be a number. Re-run setup."

        return {
            "exe_path": exe_path,
            "monitor_identifier": monitor_identifier,
            "vcp_code": vcp_code,
            "input_value": str(input_value).strip(),
        }, None

    def send_switch_command(self, switch_settings):
        # This is the existing ControlMyMonitor switching command. Keep it as a
        # subprocess list so paths and monitor identifiers with spaces are safe.
        command = [
            switch_settings["exe_path"],
            "/SetValue",
            switch_settings["monitor_identifier"],
            switch_settings["vcp_code"],
            switch_settings["input_value"],
        ]

        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            creationflags=self.get_creation_flags(),
        )

    def get_creation_flags(self):
        # CREATE_NO_WINDOW prevents a console window from flashing on Windows.
        if sys.platform == "win32":
            return subprocess.CREATE_NO_WINDOW
        return 0

    def set_success(self, message):
        self.status_label.setStyleSheet("color: #0f6b2f;")
        self.status_label.setText(message)

    def set_error(self, message):
        self.status_label.setStyleSheet("color: #a12622;")
        self.status_label.setText(message)


class SetupWizard(QWidget):
    def __init__(self, app_window):
        super().__init__()
        use_gradient_background(self, "RootContainer")
        if hasattr(app_window, "app_icon") and not app_window.app_icon.isNull():
            self.setWindowIcon(app_window.app_icon)

        self.app_window = app_window
        self.detected_monitors = []
        self.unsupported_monitors = []
        self.target_rows = []
        self.current_values_read = False
        self.advanced_path_visible = False
        self.backend_found = app_window.backend_found
        self.first_page_index = 1 if self.backend_found else 0

        self.path_input = QLineEdit(
            app_window.settings.get(
                "controlmymonitor_path",
                DEFAULT_SETTINGS["controlmymonitor_path"],
            )
        )
        self.path_input.textChanged.connect(self.reset_monitor_detection)
        self.backend_status_label = QLabel()
        self.backend_status_label.setWordWrap(True)
        self.target_name_input = QLineEdit(
            app_window.settings.get(
                "target_input_name",
                DEFAULT_SETTINGS["target_input_name"],
            )
        )
        self.target_name_input.textChanged.connect(self.update_navigation)

        self.status_label = QLabel("Setup will detect monitors connected to this computer.")
        self.status_label.setWordWrap(True)

        self.stack = QStackedWidget()
        self.stack.setAttribute(Qt.WA_StyledBackground, True)
        self.stack.addWidget(self.build_path_page())
        self.stack.addWidget(self.build_detect_page())
        self.stack.addWidget(self.build_current_values_page())
        self.stack.addWidget(self.build_target_page())
        self.stack.addWidget(self.build_save_page())

        self.back_button = QPushButton("Back")
        self.next_button = QPushButton("Next")
        self.back_button.clicked.connect(self.go_back)
        self.next_button.clicked.connect(self.go_next)

        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self.back_button)
        nav_layout.addWidget(self.next_button)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(14)
        main_layout.addWidget(self.stack)
        main_layout.addWidget(self.status_label)
        main_layout.addLayout(nav_layout)
        self.setLayout(main_layout)

        self.stack.setCurrentIndex(self.first_page_index)
        self.update_navigation()

    def build_path_page(self):
        page = QWidget()
        use_gradient_background(page, "SetupPage")
        title = self.make_title("Welcome to Monitor Input Switcher")

        intro = QLabel(
            "This setup will detect your monitors and create a one-click switch button."
        )
        intro.setWordWrap(True)

        self.backend_help_label = QLabel()
        self.backend_help_label.setWordWrap(True)

        self.browse_button = QPushButton("Browse for ControlMyMonitor.exe")
        self.browse_button.clicked.connect(self.browse_backend_path)

        self.advanced_button = QPushButton("Advanced: change backend path")
        self.advanced_button.clicked.connect(self.toggle_advanced_path)

        form_layout = QFormLayout()
        form_layout.addRow("ControlMyMonitor.exe path:", self.path_input)
        self.path_form_widget = QWidget()
        self.path_form_widget.setLayout(form_layout)

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(self.backend_status_label)
        layout.addWidget(self.backend_help_label)
        layout.addWidget(self.browse_button)
        layout.addWidget(self.advanced_button)
        layout.addWidget(self.path_form_widget)
        layout.addStretch()
        page.setLayout(layout)
        self.update_backend_controls()
        return page

    def build_detect_page(self):
        page = QWidget()
        use_gradient_background(page, "SetupPage")
        title = self.make_title("Detect monitors")

        self.detect_button = QPushButton("Detect Monitors")
        self.detect_button.clicked.connect(self.detect_monitors)

        self.detected_list_layout = QVBoxLayout()
        self.detected_list_layout.addWidget(QLabel("No monitors detected yet."))

        unsupported_title = QLabel("Unsupported / skipped displays")
        unsupported_title.setStyleSheet("font-weight: bold;")

        self.unsupported_list_layout = QVBoxLayout()
        self.unsupported_list_layout.addWidget(QLabel("No skipped displays yet."))

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(self.detect_button)
        layout.addLayout(self.detected_list_layout)
        layout.addWidget(unsupported_title)
        layout.addLayout(self.unsupported_list_layout)
        layout.addStretch()
        page.setLayout(layout)
        return page

    def build_current_values_page(self):
        page = QWidget()
        use_gradient_background(page, "SetupPage")
        title = self.make_title("Read current input values")

        self.read_all_button = QPushButton("Read Current Input Values")
        self.read_all_button.clicked.connect(self.read_all_current_inputs)

        self.current_values_layout = QVBoxLayout()
        self.current_values_layout.addWidget(QLabel("Current values have not been read yet."))

        self.current_unsupported_layout = QVBoxLayout()

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(self.read_all_button)
        layout.addLayout(self.current_values_layout)
        layout.addLayout(self.current_unsupported_layout)
        layout.addStretch()
        page.setLayout(layout)
        return page

    def build_target_page(self):
        page = QWidget()
        use_gradient_background(page, "SetupPage")
        title = self.make_title("Target setup")

        helper = QLabel(
            "Enter the input values for the device/input you want to switch to. "
            "You only need to do this once."
        )
        helper.setWordWrap(True)

        examples = QLabel("Examples: Laptop, PC, PS5, Work Laptop, HDMI 2, USB-C")
        examples.setStyleSheet("color: #a7a7a7;")

        value_help_title = QLabel("Need help finding the target value?")
        value_help_title.setStyleSheet("font-weight: bold;")

        value_help = QLabel(
            "- Current value = the input this computer is using now.\n"
            "- Target value = the input you want to switch to.\n"
            "- Enter the target value manually.\n"
            "- Tip: run this app on the other device while the monitor is showing that device.\n"
            "- Common values: 15, 16, 17, 18."
        )
        value_help.setWordWrap(True)
        value_help.setStyleSheet("color: #a7a7a7;")

        value_help_card = QGroupBox()
        value_help_layout = QVBoxLayout()
        value_help_layout.addWidget(value_help_title)
        value_help_layout.addWidget(value_help)
        value_help_card.setLayout(value_help_layout)

        form_layout = QFormLayout()
        form_layout.addRow("Target input name:", self.target_name_input)

        self.target_rows_layout = QVBoxLayout()
        self.target_rows_layout.addWidget(QLabel("Detect monitors first."))

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(helper)
        layout.addWidget(examples)
        layout.addWidget(value_help_card)
        layout.addLayout(form_layout)
        layout.addLayout(self.target_rows_layout)
        layout.addStretch()
        page.setLayout(layout)
        return page

    def build_save_page(self):
        page = QWidget()
        use_gradient_background(page, "SetupPage")
        title = self.make_title("Save settings")
        self.summary_label = QLabel("Ready to save settings.")
        self.summary_label.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(self.summary_label)
        layout.addStretch()
        page.setLayout(layout)
        return page

    def make_title(self, text):
        label = QLabel(text)
        label.setStyleSheet("font-size: 16px; font-weight: bold;")
        return label

    def update_backend_controls(self):
        backend_path = self.path_input.text().strip()
        backend_found = bool(backend_path and Path(backend_path).exists())

        if backend_found:
            self.backend_status_label.setStyleSheet("color: #0f6b2f;")
            self.backend_status_label.setText("Monitor control engine found.")
            self.backend_help_label.setText("")
            self.browse_button.hide()
        else:
            self.backend_status_label.setStyleSheet("color: #a12622;")
            self.backend_status_label.setText(
                "Monitor control engine was not found."
            )
            self.backend_help_label.setText(
                "Place ControlMyMonitor.exe next to this app, or choose it manually."
            )
            self.browse_button.show()

        self.path_form_widget.setVisible(
            self.advanced_path_visible or not backend_found
        )

    def browse_backend_path(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose ControlMyMonitor.exe",
            str(APP_DIR),
            "ControlMyMonitor.exe (ControlMyMonitor.exe);;Programs (*.exe)",
        )
        if not file_path:
            return

        self.path_input.setText(file_path)
        if Path(file_path).exists():
            self.set_success("Monitor control engine found.")
        else:
            self.set_error("Selected file was not found.")
        self.update_backend_controls()

    def toggle_advanced_path(self):
        self.advanced_path_visible = not self.advanced_path_visible
        self.update_backend_controls()

    def reset_monitor_detection(self):
        # A different backend path can produce a different monitor list, so
        # setup should require detection again before the user can continue.
        self.detected_monitors = []
        self.unsupported_monitors = []
        self.current_values_read = False
        if hasattr(self, "detected_list_layout"):
            self.update_detected_list()
        if hasattr(self, "current_values_layout"):
            self.clear_layout(self.current_values_layout)
            self.current_values_layout.addWidget(
                QLabel("Current values have not been read yet.")
            )
        if hasattr(self, "target_rows_layout"):
            self.clear_layout(self.target_rows_layout)
            self.target_rows_layout.addWidget(QLabel("Detect monitors first."))
            self.target_rows = []
        if hasattr(self, "next_button"):
            self.update_navigation()

    def go_back(self):
        current_index = self.stack.currentIndex()
        if current_index > self.first_page_index:
            self.stack.setCurrentIndex(current_index - 1)
            self.update_navigation()

    def go_next(self):
        current_index = self.stack.currentIndex()

        if current_index == 0 and not self.validate_path():
            return

        if current_index == 1 and not self.detected_monitors:
            self.set_error("No controllable monitors detected yet.")
            return

        if current_index == 2 and not self.current_values_read:
            self.set_error("Current values have not been read yet.")
            return

        if current_index == 3 and not self.validate_target_setup():
            return

        if current_index == 4:
            self.save_setup()
            return

        self.stack.setCurrentIndex(current_index + 1)
        if self.stack.currentIndex() == 2 and not self.current_values_read:
            self.set_error("Current values have not been read yet.")
        if self.stack.currentIndex() == 3:
            self.populate_target_rows()
        if self.stack.currentIndex() == 4:
            self.update_summary()
        self.update_navigation()

    def update_navigation(self):
        current_index = self.stack.currentIndex()
        self.back_button.setEnabled(current_index > self.first_page_index)
        self.next_button.setText("Save Settings" if current_index == 4 else "Next")
        self.next_button.setEnabled(
            (current_index != 1 or bool(self.detected_monitors))
            and (
                current_index != 2
                or (self.current_values_read and bool(self.detected_monitors))
            )
            and (current_index != 3 or self.target_setup_is_ready())
        )

    def validate_path(self):
        exe_path = self.path_input.text().strip()
        if not exe_path:
            self.set_error(
                "Monitor control engine was not found. "
                "Place ControlMyMonitor.exe next to this app, or choose it manually."
            )
            return False

        if not Path(exe_path).exists():
            self.set_error(
                "Monitor control engine was not found. "
                "Place ControlMyMonitor.exe next to this app, or choose it manually."
            )
            self.update_backend_controls()
            return False

        self.app_window.settings["controlmymonitor_path"] = exe_path
        try:
            self.app_window.save_settings_to_config(self.app_window.settings)
        except OSError:
            pass

        self.update_backend_controls()
        self.set_success("ControlMyMonitor.exe path looks good.")
        return True

    def detect_monitors(self):
        if not self.validate_path():
            return

        self.current_values_read = False
        if hasattr(self, "current_values_layout"):
            self.clear_layout(self.current_values_layout)
            self.current_values_layout.addWidget(
                QLabel("Current values have not been read yet.")
            )

        try:
            found_monitors = self.app_window.detect_monitors_from_exe(
                self.path_input.text().strip()
            )
        except (OSError, subprocess.CalledProcessError):
            found_monitors = []

        if not found_monitors:
            self.detected_monitors = []
            self.unsupported_monitors = []
            self.set_error(
                "Could not detect monitors. "
                "Check ControlMyMonitor path and DDC/CI support."
            )
            self.update_detected_list()
            self.update_navigation()
            return

        self.classify_detected_monitors(found_monitors)
        self.update_detected_list()
        if not self.detected_monitors:
            self.set_error(
                "No controllable external monitors were found. "
                "Make sure DDC/CI is enabled in your monitor settings."
            )
            self.update_navigation()
            return

        self.set_success(
            f"Detected {len(self.detected_monitors)} controllable monitor(s)."
        )
        self.update_navigation()

    def classify_detected_monitors(self, found_monitors):
        self.detected_monitors = []
        self.unsupported_monitors = []

        exe_path = self.path_input.text().strip()
        vcp_code = DEFAULT_SETTINGS["vcp_code"]

        for monitor in found_monitors:
            success, current_value, reason = (
                self.app_window.read_current_input_value_detailed(
                    exe_path,
                    monitor["identifier"],
                    vcp_code,
                )
            )

            if success:
                monitor["current_detected_input_value"] = current_value
                monitor["supported"] = True
                self.detected_monitors.append(monitor)
            else:
                monitor["supported"] = False
                monitor["current_detected_input_value"] = None
                monitor["unsupported_reason"] = reason or (
                    "This display does not support monitor input control "
                    "or could not read VCP code 60."
                )
                self.add_unsupported_monitor(monitor)

    def add_unsupported_monitor(self, monitor):
        identifier = monitor.get("identifier", "")
        for existing_monitor in self.unsupported_monitors:
            if existing_monitor.get("identifier", "") == identifier:
                return

        self.unsupported_monitors.append(monitor)

    def make_monitor_info_label(self, monitor, extra_lines=None):
        lines = [monitor.get("display_label") or monitor.get("label", "Monitor")]
        if extra_lines:
            lines.extend(extra_lines)

        label = QLabel("\n".join(line for line in lines if line))
        label.setWordWrap(True)
        label.setToolTip(monitor.get("identifier", ""))
        return label

    def update_detected_list(self):
        self.clear_layout(self.detected_list_layout)
        self.clear_layout(self.unsupported_list_layout)

        if not self.detected_monitors:
            self.detected_list_layout.addWidget(
                QLabel("No controllable monitors detected yet.")
            )
        else:
            for monitor in self.detected_monitors:
                current_value = monitor.get("current_detected_input_value", "Not read")
                self.detected_list_layout.addWidget(
                    self.make_monitor_info_label(
                        monitor,
                        [f"Current detected input value: {current_value}"],
                    )
                )

        if not self.unsupported_monitors:
            self.unsupported_list_layout.addWidget(QLabel("No skipped displays."))
            return

        for monitor in self.unsupported_monitors:
            self.unsupported_list_layout.addWidget(
                self.make_monitor_info_label(
                    monitor,
                    [monitor["unsupported_reason"]],
                )
            )

    def read_all_current_inputs(self):
        self.current_values_read = False
        self.update_navigation()

        if not self.detected_monitors:
            self.set_error("Detect monitors before reading current input values.")
            return

        exe_path = self.path_input.text().strip()
        vcp_code = DEFAULT_SETTINGS["vcp_code"]

        for monitor in self.detected_monitors:
            success, current_value, reason = self.app_window.read_current_input_value_detailed(
                exe_path,
                monitor["identifier"],
                vcp_code,
            )
            if success:
                monitor["current_detected_input_value"] = current_value
            else:
                monitor["current_detected_input_value"] = None
                monitor["unsupported_reason"] = reason or (
                    "This display does not support monitor input control "
                    "or could not read VCP code 60."
                )
                self.add_unsupported_monitor(monitor)

        self.detected_monitors = [
            monitor
            for monitor in self.detected_monitors
            if monitor.get("current_detected_input_value") is not None
        ]

        self.update_current_values_list()
        if not self.detected_monitors:
            self.set_error(
                "Could not read current input values. Make sure DDC/CI is enabled."
            )
            self.update_navigation()
            return

        self.current_values_read = True
        self.set_success("Current input values read.")
        self.update_navigation()

    def update_current_values_list(self):
        self.clear_layout(self.current_values_layout)
        self.clear_layout(self.current_unsupported_layout)

        for monitor in self.detected_monitors:
            current_value = monitor.get("current_detected_input_value")
            if current_value is None:
                current_value = "Could not read"

            label = QLabel(
                f"{monitor.get('display_label', monitor['label'])}\n"
                f"Current detected input value: {current_value}"
            )
            label.setWordWrap(True)
            label.setToolTip(monitor["identifier"])
            self.current_values_layout.addWidget(label)

        if self.unsupported_monitors:
            title = QLabel("Unsupported / skipped displays")
            title.setStyleSheet("font-weight: bold;")
            self.current_unsupported_layout.addWidget(title)

            for monitor in self.unsupported_monitors:
                self.current_unsupported_layout.addWidget(
                    self.make_monitor_info_label(
                        monitor,
                        [monitor["unsupported_reason"]],
                    )
                )

    def populate_target_rows(self):
        self.clear_layout(self.target_rows_layout)
        self.target_rows = []
        saved_monitors = {
            monitor.get("monitor_identifier"): monitor
            for monitor in self.app_window.settings.get("configured_monitors", [])
            if isinstance(monitor, dict)
        }

        for monitor in self.detected_monitors:
            current_value = monitor.get("current_detected_input_value")
            current_value_text = current_value if current_value is not None else "Not read"
            saved_monitor = saved_monitors.get(monitor["identifier"], {})
            saved_target_value = str(saved_monitor.get("target_input_value", "")).strip()

            checkbox = make_toggle(bool(saved_monitor.get("enabled", True)))
            checkbox.setToolTip(monitor["identifier"])

            display_label = QLabel(monitor.get("display_label", monitor["label"]))
            display_label.setStyleSheet("font-size: 14px; font-weight: bold;")
            display_label.setToolTip(monitor["identifier"])

            target_input = QLineEdit(saved_target_value)
            target_input.setFixedWidth(80)
            test_button = QPushButton("Test switch")

            value_help_label = QLabel(f"Current detected value: {current_value_text}")
            value_help_label.setStyleSheet("color: #a7a7a7; font-size: 11px;")

            target_layout = QVBoxLayout()
            target_input_layout = QHBoxLayout()
            target_input_layout.addWidget(QLabel("Target input value:"))
            target_input_layout.addWidget(target_input)
            target_input_layout.addWidget(test_button)
            target_layout.addLayout(target_input_layout)
            target_layout.addWidget(value_help_label)

            label_layout = QVBoxLayout()
            label_layout.addWidget(display_label)

            toggle_layout = QHBoxLayout()
            toggle_layout.addWidget(checkbox)
            enabled_label = QLabel("Enabled")
            enabled_label.setStyleSheet("color: #AAB2C0; font-size: 11px;")
            toggle_layout.addWidget(enabled_label)
            toggle_layout.addStretch()
            label_layout.addLayout(toggle_layout)

            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.addLayout(label_layout, 1)
            row_layout.addLayout(target_layout)

            row_container = QGroupBox()
            row_container.setLayout(row_layout)

            row = {
                "checkbox": checkbox,
                "target_input": target_input,
                "test_button": test_button,
                "monitor": monitor,
            }
            target_input.textChanged.connect(self.update_target_row_state)
            checkbox.toggled.connect(self.update_target_row_state)
            test_button.clicked.connect(
                lambda checked=False, item=row: self.test_target_value(item)
            )

            self.target_rows_layout.addWidget(row_container)
            self.target_rows.append(row)
            self.update_target_row_state()

    def update_target_row_state(self, *args):
        # Only enabled monitors need a target value. Disabled monitors can stay
        # blank because they will not be switched by the group action.
        for row in self.target_rows:
            target_value = row["target_input"].text().strip()
            row["test_button"].setEnabled(
                self.app_window.is_valid_input_value(target_value)
            )
        self.update_navigation()

    def target_setup_is_ready(self):
        if not self.target_name_input.text().strip():
            return False

        if not self.target_rows:
            return False

        for row in self.target_rows:
            if not row["checkbox"].isChecked():
                continue
            if not self.app_window.is_valid_input_value(row["target_input"].text()):
                return False

        return True

    def test_target_value(self, row):
        monitor = row["monitor"]
        target_value = row["target_input"].text().strip()

        if not self.app_window.is_valid_input_value(target_value):
            self.set_error("Target input value must be a number greater than 0.")
            return

        if not self.confirm_test_switch():
            return

        exe_path = self.path_input.text().strip()
        if not exe_path or not Path(exe_path).exists():
            self.set_error("ControlMyMonitor.exe was not found. Re-run setup.")
            return

        if not self.send_setup_switch_command(monitor, target_value, "Test command"):
            return

        self.set_success(
            "Test switch command sent to "
            f"{monitor['label']} using input value {target_value}."
        )

    def confirm_test_switch(self):
        result = QMessageBox.question(
            self,
            "Confirm Test Switch",
            "This will switch this monitor to the target input.\n\n"
            "If this is your only visible screen, you may need to switch back "
            "manually using the monitor buttons or the app on the other device.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return result == QMessageBox.Yes

    def send_setup_switch_command(
        self,
        monitor,
        input_value,
        command_name,
        show_error=True,
    ):
        exe_path = self.path_input.text().strip()
        if not exe_path or not Path(exe_path).exists():
            if show_error:
                self.set_error("ControlMyMonitor.exe was not found. Re-run setup.")
            return False

        switch_settings = {
            "exe_path": exe_path,
            "monitor_identifier": monitor["identifier"],
            "vcp_code": DEFAULT_SETTINGS["vcp_code"],
            "input_value": input_value,
        }

        try:
            # This sends the same /SetValue command used by the main app, but
            # does not save anything. It is only a setup-time safety/test action.
            self.app_window.send_switch_command(switch_settings)
        except subprocess.CalledProcessError as error:
            message = error.stderr.strip() or error.stdout.strip() or str(error)
            if show_error:
                self.set_error(f"{command_name} failed: {message}")
            return False
        except OSError as error:
            if show_error:
                self.set_error(f"Could not run ControlMyMonitor.exe: {error}")
            return False

        return True

    def validate_target_setup(self):
        target_input_name = self.target_name_input.text().strip()
        if not target_input_name:
            self.set_error("Please enter a target input name.")
            return False

        if not self.target_rows:
            self.set_error(
                "No controllable external monitors were found. "
                "Make sure DDC/CI is enabled in your monitor settings."
            )
            return False

        for row in self.target_rows:
            value = row["target_input"].text().strip()
            if not row["checkbox"].isChecked():
                continue
            if not self.app_window.is_valid_input_value(value):
                self.set_error(
                    "Enter a valid target input value for each enabled monitor."
                )
                return False

        self.set_success("Target setup looks good.")
        return True

    def update_summary(self):
        target_input_name = self.target_name_input.text().strip()
        enabled_count = sum(
            1 for row in self.target_rows if row["checkbox"].isChecked()
        )
        self.summary_label.setText(
            f"Target input name: {target_input_name}\n"
            f"Configured monitors: {len(self.target_rows)}\n"
            f"Enabled for switching: {enabled_count}\n\n"
            "Click Save Settings to write config.json and open the main app."
        )

    def save_setup(self):
        if not self.validate_target_setup():
            return

        configured_monitors = []
        existing_hotkeys = {
            monitor.get("monitor_identifier"): monitor.get("hotkey", "")
            for monitor in self.app_window.settings.get("configured_monitors", [])
            if isinstance(monitor, dict)
        }
        for row in self.target_rows:
            monitor = row["monitor"]
            configured_monitors.append(
                {
                    "friendly_label": monitor["label"],
                    "display_label": monitor.get("display_label", monitor["label"]),
                    "monitor_name": monitor.get("monitor_name", ""),
                    "monitor_identifier": monitor["identifier"],
                    "current_detected_input_value": monitor.get(
                        "current_detected_input_value"
                    ),
                    "enabled": row["checkbox"].isChecked(),
                    "target_input_value": row["target_input"].text().strip(),
                    "hotkey": existing_hotkeys.get(monitor["identifier"], ""),
                }
            )

        settings = {
            "controlmymonitor_path": self.path_input.text().strip(),
            "target_input_name": self.target_name_input.text().strip(),
            "vcp_code": DEFAULT_SETTINGS["vcp_code"],
            "group_hotkey": self.app_window.settings.get("group_hotkey", ""),
            "configured_monitors": configured_monitors,
        }

        try:
            self.app_window.save_settings_to_config(settings)
        except OSError as error:
            self.set_error(f"Could not save settings: {error}")
            return

        self.app_window.settings = settings
        self.app_window.show_main_app()

    def set_success(self, message):
        self.status_label.setStyleSheet("color: #0f6b2f;")
        self.status_label.setText(message)

    def set_error(self, message):
        self.status_label.setStyleSheet("color: #a12622;")
        self.status_label.setText(message)

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()

            if widget:
                widget.deleteLater()
            elif child_layout:
                self.clear_layout(child_layout)


class HotkeyCaptureDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.hotkey = ""
        self.setWindowTitle("Set Shortcut")
        app = QApplication.instance()
        if app and not app.windowIcon().isNull():
            self.setWindowIcon(app.windowIcon())
        self.setModal(True)
        self.setMinimumWidth(360)

        label = QLabel("Press the shortcut combination now.\n\nPress Esc to cancel.")
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(label)
        self.setLayout(layout)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            return

        if event.key() in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return

        hotkey = hotkey_from_key_event(event)
        if not hotkey:
            QMessageBox.warning(
                self,
                "Shortcut Needs Modifier",
                "Please press a shortcut with Ctrl, Alt, or Shift plus another key.",
            )
            return

        if parse_hotkey_for_windows(hotkey) is None:
            QMessageBox.warning(
                self,
                "Unsupported Shortcut",
                "That key cannot be used for a shortcut.",
            )
            return

        self.hotkey = hotkey
        self.accept()


def hotkey_from_key_event(event):
    modifiers = event.modifiers()
    has_required_modifier = bool(
        modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier)
    )
    if not has_required_modifier:
        return ""

    key_name = key_name_from_key_event(event)
    if not key_name:
        return ""

    parts = []
    if modifiers & Qt.ControlModifier:
        parts.append("Ctrl")
    if modifiers & Qt.AltModifier:
        parts.append("Alt")
    if modifiers & Qt.ShiftModifier:
        parts.append("Shift")
    parts.append(key_name)
    return "+".join(parts)


def key_name_from_key_event(event):
    native_key = event.nativeVirtualKey()

    # Prefer native virtual-key codes for digits. With Shift held, Qt can report
    # a symbol such as ")" for Shift+9, but the native key remains "9".
    if 0x30 <= native_key <= 0x39:
        return chr(native_key)

    if 0x60 <= native_key <= 0x69:
        return f"Num{native_key - 0x60}"

    key = event.key()
    if event.modifiers() & Qt.KeypadModifier and Qt.Key_0 <= key <= Qt.Key_9:
        return f"Num{key - Qt.Key_0}"

    if Qt.Key_A <= key <= Qt.Key_Z:
        return chr(ord("A") + key - Qt.Key_A)

    if Qt.Key_0 <= key <= Qt.Key_9:
        return chr(ord("0") + key - Qt.Key_0)

    if Qt.Key_F1 <= key <= Qt.Key_F24:
        return f"F{key - Qt.Key_F1 + 1}"

    special_keys = {
        Qt.Key_Space: "Space",
        Qt.Key_Tab: "Tab",
        Qt.Key_Return: "Enter",
        Qt.Key_Enter: "Enter",
        Qt.Key_Backspace: "Backspace",
        Qt.Key_Insert: "Insert",
        Qt.Key_Delete: "Delete",
        Qt.Key_Home: "Home",
        Qt.Key_End: "End",
        Qt.Key_PageUp: "PageUp",
        Qt.Key_PageDown: "PageDown",
        Qt.Key_Up: "Up",
        Qt.Key_Down: "Down",
        Qt.Key_Left: "Left",
        Qt.Key_Right: "Right",
    }
    return special_keys.get(key, "")


def clean_hotkey_string(hotkey):
    normalized = normalize_hotkey(hotkey)
    if parse_hotkey_for_windows(normalized) is None:
        return ""
    return display_hotkey(normalized)


def normalize_hotkey(hotkey):
    parts = [part.strip() for part in str(hotkey).split("+") if part.strip()]
    if not parts:
        return ""

    modifiers = []
    key_part = ""
    for part in parts:
        lower_part = part.lower()
        if lower_part == "ctrl":
            modifiers.append("ctrl")
        elif lower_part == "alt":
            modifiers.append("alt")
        elif lower_part == "shift":
            modifiers.append("shift")
        else:
            key_part = normalize_key_part(lower_part)

    ordered_modifiers = [
        modifier for modifier in ("ctrl", "alt", "shift") if modifier in modifiers
    ]
    if key_part:
        ordered_modifiers.append(key_part)

    return "+".join(ordered_modifiers)


def normalize_key_part(key_part):
    key_part = key_part.strip().lower()
    if re.fullmatch(r"num[0-9]", key_part):
        return f"num{key_part[-1]}"
    if len(key_part) == 1 and key_part.isalnum():
        return key_part
    if re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", key_part):
        return key_part

    aliases = {
        "pgup": "pageup",
        "pgdn": "pagedown",
        "esc": "escape",
        "return": "enter",
    }
    return aliases.get(key_part, key_part)


def display_hotkey(normalized_hotkey):
    display_parts = []
    for part in normalized_hotkey.split("+"):
        if part == "ctrl":
            display_parts.append("Ctrl")
        elif part == "alt":
            display_parts.append("Alt")
        elif part == "shift":
            display_parts.append("Shift")
        elif re.fullmatch(r"num[0-9]", part):
            display_parts.append(f"Num{part[-1]}")
        elif len(part) == 1:
            display_parts.append(part.upper())
        elif re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", part):
            display_parts.append(part.upper())
        else:
            display_parts.append(part[:1].upper() + part[1:])

    return "+".join(display_parts)


def parse_hotkey_for_windows(hotkey):
    normalized_hotkey = normalize_hotkey(hotkey)
    parts = [part for part in normalized_hotkey.split("+") if part]
    if len(parts) < 2:
        return None

    modifiers = 0
    key_part = ""
    for part in parts:
        if part == "ctrl":
            modifiers |= MOD_CONTROL
        elif part == "alt":
            modifiers |= MOD_ALT
        elif part == "shift":
            modifiers |= MOD_SHIFT
        else:
            key_part = part

    if not modifiers or not key_part:
        return None

    vk_code = windows_vk_code_for_key(key_part)
    if vk_code is None:
        return None

    return modifiers, vk_code


def windows_vk_code_for_key(key_part):
    key = key_part.upper()

    if re.fullmatch(r"NUM[0-9]", key):
        return 0x60 + int(key[-1])

    if len(key) == 1 and "A" <= key <= "Z":
        return ord(key)

    if len(key) == 1 and "0" <= key <= "9":
        return ord(key)

    if re.fullmatch(r"F([1-9]|1[0-9]|2[0-4])", key):
        return 0x70 + int(key[1:]) - 1

    special_keys = {
        "SPACE": 0x20,
        "TAB": 0x09,
        "ENTER": 0x0D,
        "BACKSPACE": 0x08,
        "INSERT": 0x2D,
        "DELETE": 0x2E,
        "HOME": 0x24,
        "END": 0x23,
        "PAGEUP": 0x21,
        "PAGEDOWN": 0x22,
        "UP": 0x26,
        "DOWN": 0x28,
        "LEFT": 0x25,
        "RIGHT": 0x27,
    }
    return special_keys.get(key)


def read_text_file(file_path):
    for encoding in ("utf-8-sig", "utf-16", "mbcs"):
        try:
            return file_path.read_text(encoding=encoding)
        except (LookupError, UnicodeError):
            continue

    return file_path.read_text(errors="replace")


def parse_monitors_text(monitor_text):
    monitors = []
    current_monitor = {}

    for line in monitor_text.splitlines():
        line = line.strip()

        if not line:
            add_detected_monitor(monitors, current_monitor)
            current_monitor = {}
            continue

        match = re.match(r"^([^:]+):\s*\"?(.*?)\"?\s*$", line)
        if not match:
            continue

        key = match.group(1).strip()
        value = match.group(2).strip()

        if key == "Monitor Device Name" and current_monitor:
            add_detected_monitor(monitors, current_monitor)
            current_monitor = {}

        current_monitor[key] = value

    add_detected_monitor(monitors, current_monitor)
    return monitors


def add_detected_monitor(monitors, monitor):
    if not monitor:
        return

    identifier = monitor.get("Monitor Device Name", "").strip()
    if not identifier:
        return

    for existing_monitor in monitors:
        if existing_monitor["identifier"] == identifier:
            return

    display_index = len(monitors) + 1
    monitor_name = monitor.get("Monitor Name", "").strip()
    display_label = make_display_label(display_index, monitor_name)

    monitors.append(
        {
            "identifier": identifier,
            "label": display_label,
            "display_label": display_label,
            "monitor_name": monitor_name,
        }
    )


def make_monitor_label(monitor, identifier):
    short_identifier = make_short_monitor_identifier(identifier)
    monitor_name = monitor.get("Monitor Name", "").strip()

    if monitor_name:
        return f"{monitor_name} - {short_identifier}"
    return short_identifier


def make_display_label(display_index, monitor_name=""):
    base_label = f"Display {display_index}"
    monitor_name = str(monitor_name).strip()
    if monitor_name:
        return f"{base_label} ({monitor_name})"
    return base_label


def display_label_from_config_monitor(monitor, display_index):
    display_label = str(monitor.get("display_label", "")).strip()
    if display_label:
        return display_label

    monitor_name = str(monitor.get("monitor_name", "")).strip()
    if monitor_name:
        return make_display_label(display_index, monitor_name)

    friendly_label = str(monitor.get("friendly_label", "")).strip()
    extracted_name = extract_monitor_name_from_friendly_label(friendly_label)
    return make_display_label(display_index, extracted_name)


def extract_monitor_name_from_friendly_label(friendly_label):
    if not friendly_label:
        return ""

    if " - DISPLAY" in friendly_label:
        return friendly_label.split(" - DISPLAY", 1)[0].strip()

    if friendly_label.startswith("DISPLAY"):
        return ""

    return friendly_label


def make_short_monitor_identifier(identifier):
    match = re.search(r"DISPLAY(\d+)\\Monitor(\d+)", identifier)
    if match:
        return f"DISPLAY{match.group(1)} / Monitor{match.group(2)}"
    return identifier


def main():
    set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    configure_application_metadata(app)
    app_icon = get_application_icon()
    if not app_icon.isNull():
        # The taskbar usually uses the QApplication icon, while the final
        # packaged exe icon is set by PyInstaller --icon.
        app.setWindowIcon(app_icon)

    startup_mode = "--startup" in sys.argv[1:]
    window = MonitorInputSwitcher()

    if startup_mode and window.configured_on_launch and window.tray_icon:
        # Windows startup should keep a configured tray utility in the
        # background. Manual launches still show the main window normally.
        pass
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
