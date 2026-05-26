from __future__ import annotations

import sys
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGraphicsDropShadowEffect,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .config import (
    AppConfig,
    ChannelUiConfig,
    DeviceConfig,
    default_app_config,
    default_config_path,
    load_app_config,
    save_app_config,
)
from .domain import BurstSettings, ChannelSettings
from .scpi import WAVEFORM_CHOICES
from .ui_state import (
    burst_ui_state,
    coerce_burst_trigger_source,
    level_ui_state,
    waveform_ui_state,
)
from .visa import RigolVisaClient
from .waveform_preview import WaveformPreview, WaveformPreviewState


class ChannelCard(QFrame):
    selected = Signal(int)

    def __init__(self, channel: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.channel = channel
        self.setObjectName("ChannelCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(42)
        self.setMinimumWidth(150)
        self.setMaximumWidth(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 5, 8, 5)
        layout.setSpacing(8)

        self.title = QLabel(f"CH{channel}")
        self.title.setObjectName("ChannelCardTitle")
        self.title.setFixedWidth(38)
        self.output = QLabel("输出 OFF")
        self.output.setObjectName("ChannelOutputBadge")
        self.output.setFixedSize(68, 22)
        self.output.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.title)
        layout.addStretch(1)
        layout.addWidget(self.output, 0, Qt.AlignVCenter)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_summary(self, settings: ChannelSettings) -> None:
        output_on = bool(settings.output_enabled)
        self.output.setText("输出 ON" if output_on else "输出 OFF")
        self.output.setProperty("on", output_on)
        self.output.style().unpolish(self.output)
        self.output.style().polish(self.output)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.channel)
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RIGOL DG1022Z Waveform Generator Control")
        self.resize(1600, 980)
        self._connected = False
        self._loading_form = False
        self._config_path = default_config_path()
        self._startup_config = load_app_config(self._config_path, default_app_config())
        self.default_channel_settings = dict(default_app_config().channels)
        self.default_channel_ui = {1: ChannelUiConfig(), 2: ChannelUiConfig()}
        self.clients: dict[str, RigolVisaClient] = {}
        self.device_settings: dict[str, dict[int, ChannelSettings]] = {
            address: dict(device.channels)
            for address, device in self._startup_config.devices.items()
        }
        self.device_active_channels: dict[str, int] = {
            address: device.active_channel
            for address, device in self._startup_config.devices.items()
        }
        self.device_ui_settings: dict[str, dict[int, ChannelUiConfig]] = {
            address: dict(device.channel_ui) or dict(self.default_channel_ui)
            for address, device in self._startup_config.devices.items()
        }
        if self._startup_config.visa_address not in self.device_settings:
            self.device_settings[self._startup_config.visa_address] = dict(self._startup_config.channels)
            self.device_active_channels[self._startup_config.visa_address] = self._startup_config.active_channel
            self.device_ui_settings[self._startup_config.visa_address] = dict(self.default_channel_ui)
        self.active_channel = self.device_active_channels.get(
            self._startup_config.visa_address,
            self._startup_config.active_channel,
        )
        self.channel_settings = dict(
            self.device_settings.get(self._startup_config.visa_address, self._startup_config.channels)
        )
        self.device_labels: dict[str, str] = {}
        self.device_idns: dict[str, str] = {}
        self.device_nav_buttons: dict[str, QPushButton] = {}
        self.active_device_key = ""
        self.sidebar_collapsed = False
        self.connection_rows: list[dict[str, QWidget]] = []
        self.active_connection_row: dict[str, QWidget] | None = None
        self.available_resources: tuple[str, ...] = ()
        self.client = RigolVisaClient(log=self._log)
        self._build_ui()
        self._apply_style()
        self._load_settings_to_form(self.channel_settings[self.active_channel])
        self._set_connected(False, "未连接")

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("AppRoot")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        root.addWidget(self._build_sidebar())
        self.pages = QStackedWidget(central)
        self.pages.setObjectName("PageStack")
        self.connection_page = self._build_connection_page()
        self.control_page = self._build_control_page()
        self.pages.addWidget(self.connection_page)
        self.pages.addWidget(self.control_page)
        root.addWidget(self.pages, 1)
        self.pages.setCurrentWidget(self.connection_page)

        self._build_log_window()
        self._apply_elevation()
        self._connect_signals()

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        self.sidebar = side
        side.setObjectName("Sidebar")
        side.setFixedWidth(112)
        side.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        layout = QVBoxLayout(side)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(10)

        self.sidebar_toggle = QToolButton(side)
        self.sidebar_toggle.setObjectName("SidebarMenuButton")
        self.sidebar_toggle.setText("☰")
        self.sidebar_toggle.setToolTip("收缩/展开导航栏")
        self.sidebar_toggle.setFixedSize(48, 48)
        layout.addWidget(self.sidebar_toggle, 0, Qt.AlignHCenter)

        divider = QFrame(side)
        divider.setObjectName("SidebarDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        self.nav_connect = self._nav_button("设备连接", side)
        self.nav_connect.setChecked(True)
        layout.addWidget(self.nav_connect)

        self.device_nav_host = QWidget(side)
        self.device_nav_host.setObjectName("DeviceNavHost")
        self.device_nav_layout = QVBoxLayout(self.device_nav_host)
        self.device_nav_layout.setContentsMargins(0, 0, 0, 0)
        self.device_nav_layout.setSpacing(8)
        layout.addWidget(self.device_nav_host)

        layout.addStretch(1)

        self.btn_log = QPushButton("日志 / 指令", side)
        self.btn_log.setObjectName("SidebarLogButton")
        self.btn_log.setFixedHeight(40)
        layout.addWidget(self.btn_log)
        return side

    def _nav_button(self, text: str, parent: QWidget) -> QPushButton:
        button = QPushButton(text, parent)
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.setFixedHeight(42)
        button.setCursor(Qt.PointingHandCursor)
        button.setProperty("fullText", text)
        return button

    def _build_connection_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("ConnectionPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(0)

        card = QFrame(page)
        self.connection_panel = card
        card.setObjectName("ConnectionCard")
        card.setFixedWidth(500)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(14)

        title_block = QVBoxLayout()
        title_block.setContentsMargins(0, 0, 0, 0)
        title_block.setSpacing(6)

        title = QLabel("设备连接配置", card)
        title.setObjectName("ConnectionTitle")
        subtitle = QLabel("选择信号发生器地址后，执行统一连接检测。", card)
        subtitle.setObjectName("ConnectionSubtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        card_layout.addLayout(title_block)

        self.connection_rows_layout = QVBoxLayout()
        self.connection_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.connection_rows_layout.setSpacing(8)
        card_layout.addLayout(self.connection_rows_layout)
        addresses = list(self._startup_config.visa_addresses) or [self._startup_config.visa_address]
        for address in addresses:
            self._add_connection_row(address)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_remove_address = QPushButton("删除地址", card)
        self.btn_remove_address.setObjectName("SecondaryButton")
        self.btn_remove_address.setFixedSize(96, 38)
        self.btn_add_address = QPushButton("新增地址", card)
        self.btn_add_address.setObjectName("SecondaryButton")
        self.btn_add_address.setFixedSize(96, 38)
        self.btn_refresh = QPushButton("刷新地址", card)
        self.btn_refresh.setFixedSize(96, 38)

        actions.addWidget(self.btn_remove_address)
        actions.addStretch(1)
        actions.addWidget(self.btn_add_address)
        actions.addWidget(self.btn_refresh)
        card_layout.addLayout(actions)
        self._update_remove_address_state()

        device_list_title = QLabel("已连接信号发生器", card)
        device_list_title.setObjectName("ConnectionListTitle")
        card_layout.addWidget(device_list_title)
        self.device_list_layout = QVBoxLayout()
        self.device_list_layout.setContentsMargins(0, 0, 0, 0)
        self.device_list_layout.setSpacing(8)
        card_layout.addLayout(self.device_list_layout)

        layout.addStretch(1)
        layout.addWidget(card, 0, Qt.AlignHCenter)
        layout.addStretch(2)
        self._refresh_device_list()
        return page

    def _add_connection_row(self, address: str = "") -> dict[str, QWidget]:
        row_frame = QFrame(self.connection_panel)
        row_frame.setObjectName("ConnectionDeviceRow")
        row_frame.setFixedSize(430, 58)
        row = QHBoxLayout(row_frame)
        row.setContentsMargins(8, 7, 8, 7)
        row.setSpacing(8)

        address_box = QComboBox(row_frame)
        address_box.setEditable(True)
        address_box.setFixedSize(230, 36)
        if address_box.lineEdit() is not None:
            address_box.lineEdit().setPlaceholderText("输入 VISA 地址")
        self._populate_address_combo(address_box, address)

        status_wrap = QFrame(row_frame)
        status_wrap.setObjectName("ConnectionStatusBadge")
        status_layout = QHBoxLayout(status_wrap)
        status_layout.setContentsMargins(9, 0, 9, 0)
        status_layout.setSpacing(5)
        status_dot = QLabel(status_wrap)
        status_dot.setObjectName("StatusDot")
        status_dot.setFixedSize(10, 10)
        status_text = QLabel("未连接", status_wrap)
        status_text.setObjectName("StatusText")
        status_layout.addWidget(status_dot)
        status_layout.addWidget(status_text)
        status_wrap.setFixedSize(86, 36)

        connect_button = QPushButton("连接", row_frame)
        connect_button.setObjectName("ConnectionButton")
        connect_button.setFixedSize(76, 36)

        row.addWidget(address_box)
        row.addWidget(status_wrap)
        row.addWidget(connect_button)
        row.addStretch(1)

        row_data: dict[str, QWidget] = {
            "frame": row_frame,
            "address": address_box,
            "status_badge": status_wrap,
            "status_dot": status_dot,
            "status_text": status_text,
            "button": connect_button,
        }
        self.connection_rows.append(row_data)
        self.active_connection_row = row_data
        if len(self.connection_rows) == 1:
            self.address = address_box
            self.status_badge = status_wrap
            self.status_dot = status_dot
            self.status_text = status_text

        address_box.currentTextChanged.connect(self._save_config)
        address_box.currentTextChanged.connect(lambda _text="", r=row_data: self._set_active_connection_row(r))
        address_box.currentTextChanged.connect(lambda _text="", r=row_data: self._update_connection_row_action(r))
        connect_button.clicked.connect(lambda _checked=False, r=row_data: self._toggle_connection(r))
        self.connection_rows_layout.addWidget(row_frame)
        self._set_connection_row_state(row_data, False, "未连接")
        self._update_remove_address_state()
        return row_data

    def _set_active_connection_row(self, row: dict[str, QWidget]) -> None:
        if row in self.connection_rows:
            self.active_connection_row = row

    def _focused_connection_row(self) -> dict[str, QWidget] | None:
        focus = QApplication.focusWidget()
        if focus is None:
            return None
        for row in self.connection_rows:
            frame = row.get("frame")
            if isinstance(frame, QWidget) and (focus is frame or frame.isAncestorOf(focus)):
                return row
        return None

    def _selected_connection_row_for_removal(self) -> dict[str, QWidget] | None:
        return (
            self._focused_connection_row()
            or (self.active_connection_row if self.active_connection_row in self.connection_rows else None)
            or (self.connection_rows[-1] if self.connection_rows else None)
        )

    def _remove_connection_row(self, row: dict[str, QWidget] | None = None) -> None:
        if len(self.connection_rows) <= 1:
            self._update_remove_address_state()
            self._log("至少保留一个 VISA 地址，已取消删除")
            return
        row = row or self._selected_connection_row_for_removal()
        if row not in self.connection_rows:
            return
        address = self._connection_row_address(row)
        if address in self.clients:
            self._disconnect(address)
        self.connection_rows.remove(row)
        frame = row.get("frame")
        if frame is not None:
            frame.setParent(None)
            frame.deleteLater()
        if address:
            self.device_settings.pop(address, None)
            self.device_active_channels.pop(address, None)
            self.device_ui_settings.pop(address, None)
        first = self.connection_rows[0]
        self.address = first["address"]
        self.status_badge = first["status_badge"]
        self.status_dot = first["status_dot"]
        self.status_text = first["status_text"]
        self.active_connection_row = self.connection_rows[-1]
        self._update_remove_address_state()
        self._save_config()

    def _update_remove_address_state(self) -> None:
        if hasattr(self, "btn_remove_address"):
            self.btn_remove_address.setEnabled(len(self.connection_rows) > 1)

    def _populate_address_combo(self, combo: QComboBox, current: str = "") -> None:
        current = current.strip() or combo.currentText().strip()
        combo.blockSignals(True)
        combo.clear()
        if self.available_resources:
            combo.addItems(self.available_resources)
        if current:
            index = combo.findText(current)
            if index < 0:
                combo.insertItem(0, current)
                index = 0
            combo.setCurrentIndex(index)
        else:
            combo.setEditText("")
        combo.blockSignals(False)

    def _connection_row_address(self, row: dict[str, QWidget]) -> str:
        address = row.get("address")
        if isinstance(address, QComboBox):
            return address.currentText().strip()
        return ""

    def _current_visa_address(self) -> str:
        if self.active_device_key:
            return self.active_device_key
        for address in self._connection_row_addresses():
            return address
        return ""

    def _connection_row_addresses(self) -> tuple[str, ...]:
        seen: set[str] = set()
        addresses: list[str] = []
        for row in self.connection_rows:
            address = self._connection_row_address(row)
            if not address or address in seen:
                continue
            seen.add(address)
            addresses.append(address)
        return tuple(addresses)

    def _row_for_address(self, address: str) -> dict[str, QWidget] | None:
        address = address.strip()
        if not address:
            return None
        for row in self.connection_rows:
            if self._connection_row_address(row) == address:
                return row
        return None

    def _set_connection_row_state(
        self,
        row: dict[str, QWidget],
        connected: bool,
        text: str,
        *,
        failed: bool = False,
    ) -> None:
        badge = row.get("status_badge")
        dot = row.get("status_dot")
        label = row.get("status_text")
        button = row.get("button")
        address = row.get("address")
        display = "已连接" if connected else text
        for widget in (badge, dot, label):
            if widget is None:
                continue
            widget.setProperty("connected", connected)
            widget.setProperty("failed", failed)
            _repolish(widget)
        if isinstance(label, QLabel):
            label.setText(display)
            label.setToolTip(text)
        if isinstance(button, QPushButton):
            button.setText("断开" if connected else "连接")
            button.setProperty("connected", connected)
            _repolish(button)
        if isinstance(address, QComboBox):
            address.setEnabled(not connected)

    def _update_connection_row_action(self, row: dict[str, QWidget]) -> None:
        address = self._connection_row_address(row)
        self._set_connection_row_state(row, address in self.clients, "已连接" if address in self.clients else "未连接")

    def _update_connection_rows(self) -> None:
        for row in self.connection_rows:
            self._update_connection_row_action(row)

    def _build_control_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("ControlPage")
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self._build_center_panel(), 1)
        layout.addWidget(self._build_right_panel())
        return page

    def _build_log_window(self) -> None:
        self.log_window = QDialog(self)
        self.log_window.setWindowTitle("日志 / 指令")
        self.log_window.resize(760, 360)
        layout = QVBoxLayout(self.log_window)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("日志 / 指令")
        title.setObjectName("MainTitle")
        hint = QLabel("连接状态、参数下发、SCPI 指令和错误信息会记录在这里")
        hint.setObjectName("SubtleText")
        self.log = QTextEdit(self.log_window)
        self.log.setObjectName("LogText")
        self.log.setReadOnly(True)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.btn_error = QPushButton("查询错误", self.log_window)
        self.btn_clear_log = QPushButton("清空日志", self.log_window)
        self.btn_close_log = QPushButton("关闭", self.log_window)
        actions.addWidget(self.btn_error)
        actions.addWidget(self.btn_clear_log)
        actions.addWidget(self.btn_close_log)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.log, 1)
        layout.addLayout(actions)

    def _build_center_panel(self) -> QWidget:
        panel = QFrame()
        self.center_panel = panel
        panel.setObjectName("CenterPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(22)

        title = QLabel("波形工作区")
        title.setObjectName("MainTitle")
        title.setFixedHeight(36)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(title)

        control_row = QWidget(panel)
        control_row.setObjectName("WorkControlRow")
        control_row.setFixedHeight(132)
        control_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        control_row_layout = QHBoxLayout(control_row)
        control_row_layout.setContentsMargins(0, 0, 0, 0)
        control_row_layout.setSpacing(20)

        controls = QFrame(control_row)
        controls.setObjectName("ChannelActionStrip")
        controls.setFixedHeight(128)
        controls.setMinimumWidth(620)
        controls.setMaximumWidth(760)
        controls.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(16, 10, 18, 16)
        controls_layout.setSpacing(8)

        channel_area = QWidget(controls)
        channel_area.setObjectName("StripRow")
        channel_area.setFixedHeight(42)
        channel_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        channel_layout = QHBoxLayout(channel_area)
        channel_layout.setContentsMargins(0, 0, 0, 0)
        channel_layout.setSpacing(8)
        channel_label = QLabel("通道", channel_area)
        channel_label.setObjectName("StripRowLabel")
        channel_label.setFixedWidth(34)
        channel_layout.addWidget(channel_label, 0, Qt.AlignVCenter)
        self.channel_cards = {
            1: ChannelCard(1, controls),
            2: ChannelCard(2, controls),
        }
        for card in self.channel_cards.values():
            channel_layout.addWidget(card, 1)
        channel_layout.addStretch(1)

        actions = QFrame(controls)
        actions.setObjectName("ActionGrid")
        actions.setFixedHeight(42)
        actions.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)
        action_label = QLabel("操作", actions)
        action_label.setObjectName("StripRowLabel")
        action_label.setFixedWidth(34)
        self.btn_apply = QPushButton("应用当前通道", actions)
        self.btn_apply.setObjectName("PrimaryButton")
        self.btn_apply_all = QPushButton("应用双通道", actions)
        self.btn_output_toggle = QPushButton("输出 OFF", actions)
        self.btn_output_toggle.setObjectName("OutputToggleButton")
        self.btn_fire = QPushButton("软件触发 Burst", actions)
        self.load = QComboBox(actions)
        self.load.addItem("负载 High-Z", "INF")
        self.load.addItem("负载 50 ohm", "50")
        for button in (
            self.btn_apply,
            self.btn_apply_all,
            self.btn_output_toggle,
            self.btn_fire,
        ):
            button.setFixedHeight(36)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_apply.setMinimumWidth(106)
        self.btn_apply.setMaximumWidth(126)
        self.btn_apply_all.setMinimumWidth(94)
        self.btn_apply_all.setMaximumWidth(112)
        self.btn_output_toggle.setMinimumWidth(82)
        self.btn_output_toggle.setMaximumWidth(96)
        self.btn_fire.setMinimumWidth(104)
        self.btn_fire.setMaximumWidth(126)
        self.load.setFixedHeight(36)
        self.load.setMinimumWidth(112)
        self.load.setMaximumWidth(130)
        self.load.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        actions_layout.addWidget(action_label, 0, Qt.AlignVCenter)
        actions_layout.addWidget(self.btn_apply)
        actions_layout.addWidget(self.btn_apply_all)
        actions_layout.addWidget(self.btn_output_toggle)
        actions_layout.addWidget(self.btn_fire)
        actions_layout.addWidget(self.load)
        actions_layout.addStretch(1)

        controls_layout.addWidget(channel_area)
        controls_layout.addWidget(actions)

        summary = QFrame(control_row)
        summary.setObjectName("ChannelSummaryCard")
        summary.setFixedHeight(118)
        summary.setMinimumWidth(208)
        summary.setMaximumWidth(284)
        summary.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(14, 12, 14, 12)
        summary_layout.setSpacing(3)
        summary_title = QLabel("当前通道摘要", summary)
        summary_title.setObjectName("SummaryTitle")
        self.channel_summary_active = QLabel(summary)
        self.channel_summary_active.setObjectName("SummaryLineStrong")
        self.channel_summary_detail = QLabel(summary)
        self.channel_summary_detail.setObjectName("SummaryLine")
        self.channel_summary_state = QLabel(summary)
        self.channel_summary_state.setObjectName("SummaryLine")
        summary_layout.addWidget(summary_title)
        summary_layout.addSpacing(6)
        summary_layout.addWidget(self.channel_summary_active)
        summary_layout.addWidget(self.channel_summary_detail)
        summary_layout.addWidget(self.channel_summary_state)
        summary_layout.addStretch(1)

        control_row_layout.addWidget(controls, 760, Qt.AlignTop)
        control_row_layout.addWidget(summary, 284, Qt.AlignTop)
        control_row_layout.addStretch(1)
        layout.addWidget(control_row)

        self.wave_preview = WaveformPreview(panel)
        self.wave_preview.setFixedHeight(258)
        self.wave_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.wave_preview)

        selector = QFrame(panel)
        selector.setObjectName("Card")
        selector.setFixedHeight(158)
        selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        selector_layout = QVBoxLayout(selector)
        selector_layout.setContentsMargins(24, 14, 24, 14)
        selector_layout.setSpacing(10)
        selector_title = QLabel("波形类型")
        selector_title.setObjectName("CardTitle")
        selector_title.setFixedHeight(26)
        selector_layout.addWidget(selector_title)
        wave_grid = QGridLayout()
        wave_grid.setHorizontalSpacing(12)
        wave_grid.setVerticalSpacing(0)
        self.wave_group = QButtonGroup(self)
        self.wave_group.setExclusive(True)
        self.wave_buttons: dict[str, QPushButton] = {}
        for index, (label, value) in enumerate(WAVEFORM_CHOICES):
            button = QPushButton(_wave_button_label(label, value), selector)
            button.setObjectName("WaveChoice")
            button.setCheckable(True)
            button.setToolTip(label)
            button.setProperty("waveform", value)
            button.setFixedHeight(70)
            button.setMinimumWidth(118)
            button.setMaximumWidth(150)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.clicked.connect(lambda _checked=False, v=value: self._set_waveform(v))
            self.wave_group.addButton(button)
            self.wave_buttons[value] = button
            wave_grid.addWidget(button, 0, index)
            wave_grid.setColumnStretch(index, 1)
        wave_grid.setColumnStretch(len(WAVEFORM_CHOICES), 1)
        selector_layout.addLayout(wave_grid)
        layout.addWidget(selector)

        layout.addStretch(1)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        self.right_panel = panel
        panel.setObjectName("RightPanel")
        panel.setMinimumWidth(360)
        panel.setMaximumWidth(440)
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(26, 16, 26, 16)
        layout.setSpacing(12)

        title = QLabel("参数设置")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        scroll = QScrollArea(panel)
        scroll.setObjectName("ParameterScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll_body = QWidget(scroll)
        scroll_body.setObjectName("ParameterScrollBody")
        parameter_layout = QVBoxLayout(scroll_body)
        parameter_layout.setContentsMargins(0, 0, 2, 0)
        parameter_layout.setSpacing(10)
        scroll.setWidget(scroll_body)
        layout.addWidget(scroll, 1)

        self.timing_group = QGroupBox()
        timing_form = _form_layout(self.timing_group)
        timing_form.addRow(_section_title("频率 / 周期"))
        self.frequency_mode = QComboBox()
        self.frequency_mode.addItem("频率", "frequency")
        self.frequency_mode.addItem("周期", "period")
        self.frequency_unit = QComboBox()
        self.frequency_unit.setObjectName("UnitCombo")
        self.frequency_unit.addItem("Hz", "Hz")
        self.frequency_unit.addItem("kHz", "kHz")
        self.frequency_unit.addItem("MHz", "MHz")
        self.frequency_unit.setFixedWidth(62)
        self.period_unit = QComboBox()
        self.period_unit.setObjectName("UnitCombo")
        self.period_unit.addItem("ms", "ms")
        self.period_unit.addItem("s", "s")
        self.period_unit.setFixedWidth(54)
        self._frequency_display_unit = "kHz"
        self._period_display_unit = "ms"
        self.frequency_hz = _double_spin(1e-9, 25_000.0, 1.0, 6, "", 0.1)
        self.period_s = _double_spin(0.00004, 1_000_000_000.0, 1.0, 6, "", 0.1)
        self.phase_deg = _double_spin(0.0, 360.0, 0.0, 3, " deg", 1.0)
        self.frequency_hz_editor = _spin_editor(self.frequency_hz, self.frequency_unit)
        self.period_s_editor = _spin_editor(self.period_s, self.period_unit)
        self.phase_deg_editor = _spin_editor(self.phase_deg)
        timing_form.addRow("输入方式", self.frequency_mode)
        timing_form.addRow("频率", self.frequency_hz_editor)
        timing_form.addRow("周期", self.period_s_editor)
        timing_form.addRow("相位", self.phase_deg_editor)
        parameter_layout.addWidget(self.timing_group)

        self.level_group = QGroupBox()
        level_form = _form_layout(self.level_group)
        level_form.addRow(_section_title("电平"))
        self.level_mode = QComboBox()
        self.level_mode.addItem("幅度 + 偏置", "amplitude_offset")
        self.level_mode.addItem("高电平 + 低电平", "high_low")
        self.amplitude_vpp = _double_spin(0.001, 20.0, 2.0, 4, " Vpp", 0.1)
        self.offset_v = _double_spin(-10.0, 10.0, 0.0, 4, " V", 0.1)
        self.high_v = _double_spin(-10.0, 10.0, 1.0, 4, " V", 0.1)
        self.low_v = _double_spin(-10.0, 10.0, -1.0, 4, " V", 0.1)
        self.amplitude_vpp_editor = _spin_editor(self.amplitude_vpp)
        self.offset_v_editor = _spin_editor(self.offset_v)
        self.high_v_editor = _spin_editor(self.high_v)
        self.low_v_editor = _spin_editor(self.low_v)
        level_form.addRow("模式", self.level_mode)
        level_form.addRow("幅度", self.amplitude_vpp_editor)
        level_form.addRow("偏置", self.offset_v_editor)
        level_form.addRow("高电平", self.high_v_editor)
        level_form.addRow("低电平", self.low_v_editor)
        parameter_layout.addWidget(self.level_group)

        self.shape_group = QGroupBox()
        shape_form = _form_layout(self.shape_group)
        shape_form.addRow(_section_title("波形专属参数"))
        self.duty_percent = _double_spin(0.001, 99.999, 50.0, 3, " %", 1.0)
        self.pulse_width_s = _double_spin(16e-9, 999_999.0, 0.0001, 9, " s", 0.00001)
        self.ramp_symmetry = _double_spin(0.0, 100.0, 50.0, 3, " %", 1.0)
        self.duty_percent_editor = _spin_editor(self.duty_percent)
        self.pulse_width_s_editor = _spin_editor(self.pulse_width_s)
        self.ramp_symmetry_editor = _spin_editor(self.ramp_symmetry)
        shape_form.addRow("占空比", self.duty_percent_editor)
        shape_form.addRow("脉宽", self.pulse_width_s_editor)
        shape_form.addRow("斜波对称", self.ramp_symmetry_editor)
        parameter_layout.addWidget(self.shape_group)

        self.burst_group = QGroupBox()
        burst_layout = QVBoxLayout(self.burst_group)
        burst_layout.setContentsMargins(10, 8, 10, 8)
        burst_layout.setSpacing(6)
        burst_layout.addWidget(_section_title("Burst"))
        burst_head = QHBoxLayout()
        burst_head.setSpacing(10)
        self.burst_enabled = QCheckBox("启用 Burst")
        self.burst_status = QLabel("OFF")
        self.burst_status.setObjectName("StatePill")
        self.burst_status.setAlignment(Qt.AlignCenter)
        self.burst_status.setFixedSize(50, 22)
        burst_head.addWidget(self.burst_enabled)
        burst_head.addStretch(1)
        burst_head.addWidget(self.burst_status)
        burst_layout.addLayout(burst_head)
        self.burst_mode = QComboBox()
        self.burst_mode.addItem("N 周期", "TRIG")
        self.burst_mode.addItem("无限", "INF")
        self.burst_mode.addItem("门控", "GAT")
        self.burst_details = QFrame()
        self.burst_details.setObjectName("InlineDetails")
        burst_details_form = _form_layout(self.burst_details)
        self.burst_trigger_source = QComboBox()
        self.burst_trigger_source.addItem("手动/软件", "MAN")
        self.burst_trigger_source.addItem("内部", "INT")
        self.burst_trigger_source.addItem("外部", "EXT")
        self.burst_cycles = QSpinBox()
        self.burst_cycles.setRange(1, 1_000_000)
        self.burst_cycles.setValue(1)
        self.burst_internal_period = _double_spin(1e-6, 1e6, 0.01, 6, " s", 0.001)
        self.burst_phase = _double_spin(0.0, 360.0, 0.0, 3, " deg", 1.0)
        self.burst_delay = _double_spin(0.0, 1e6, 0.0, 6, " s", 0.001)
        self.burst_gate_polarity = QComboBox()
        self.burst_gate_polarity.addItem("正门控", "NORM")
        self.burst_gate_polarity.addItem("反门控", "INV")
        self.burst_trigger_slope = QComboBox()
        self.burst_trigger_slope.addItem("上升沿", "POS")
        self.burst_trigger_slope.addItem("下降沿", "NEG")
        self.burst_cycles_editor = _spin_editor(self.burst_cycles)
        self.burst_internal_period_editor = _spin_editor(self.burst_internal_period)
        self.burst_phase_editor = _spin_editor(self.burst_phase)
        self.burst_delay_editor = _spin_editor(self.burst_delay)
        burst_details_form.addRow("类型", self.burst_mode)
        burst_details_form.addRow("触发源", self.burst_trigger_source)
        burst_details_form.addRow("周期数", self.burst_cycles_editor)
        burst_details_form.addRow("内部周期", self.burst_internal_period_editor)
        burst_details_form.addRow("相位", self.burst_phase_editor)
        burst_details_form.addRow("延时", self.burst_delay_editor)
        burst_details_form.addRow("门控极性", self.burst_gate_polarity)
        burst_details_form.addRow("外触发沿", self.burst_trigger_slope)
        burst_layout.addWidget(self.burst_details)
        parameter_layout.addWidget(self.burst_group)
        parameter_layout.addStretch(1)
        return panel

    def _connect_signals(self) -> None:
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)
        self.nav_connect.clicked.connect(self._show_connection_page)
        self.btn_remove_address.clicked.connect(lambda: self._remove_connection_row())
        self.btn_add_address.clicked.connect(lambda: self._add_connection_row(""))
        self.btn_refresh.clicked.connect(self._refresh_resources)
        self.btn_log.clicked.connect(self._show_log_window)
        self.btn_clear_log.clicked.connect(self.log.clear)
        self.btn_close_log.clicked.connect(self.log_window.hide)
        self.btn_apply.clicked.connect(self._apply_current)
        self.btn_apply_all.clicked.connect(self._apply_all)
        self.btn_output_toggle.clicked.connect(self._toggle_output)
        self.btn_fire.clicked.connect(self._fire_burst)
        self.btn_error.clicked.connect(self._query_error)
        for channel, card in self.channel_cards.items():
            card.selected.connect(self._select_channel)

        for widget in (
            self.frequency_mode,
            self.level_mode,
            self.load,
            self.burst_mode,
            self.burst_trigger_source,
            self.burst_gate_polarity,
            self.burst_trigger_slope,
        ):
            widget.currentIndexChanged.connect(self._on_form_changed)
        self.frequency_unit.currentIndexChanged.connect(self._on_frequency_unit_changed)
        self.period_unit.currentIndexChanged.connect(self._on_period_unit_changed)
        self.burst_enabled.toggled.connect(self._on_burst_enabled_toggled)
        for spin in (
            self.frequency_hz,
            self.period_s,
            self.phase_deg,
            self.duty_percent,
            self.pulse_width_s,
            self.ramp_symmetry,
            self.amplitude_vpp,
            self.offset_v,
            self.high_v,
            self.low_v,
            self.burst_cycles,
            self.burst_internal_period,
            self.burst_phase,
            self.burst_delay,
        ):
            spin.valueChanged.connect(self._on_form_changed)

    def closeEvent(self, event) -> None:
        self._save_config()
        for client in list(self.clients.values()):
            client.disconnect()
        if not self.clients:
            self.client.disconnect()
        super().closeEvent(event)

    def _show_connection_page(self) -> None:
        self.pages.setCurrentWidget(self.connection_page)
        self._set_nav_checked(self.nav_connect)

    def _toggle_sidebar(self) -> None:
        self._set_sidebar_collapsed(not self.sidebar_collapsed)

    def _set_sidebar_collapsed(self, collapsed: bool) -> None:
        self.sidebar_collapsed = collapsed
        self.sidebar.setFixedWidth(68 if collapsed else 112)
        self.sidebar_toggle.setToolTip("展开导航栏" if collapsed else "收缩导航栏")
        self.nav_connect.setText("连接" if collapsed else "设备连接")
        self.btn_log.setText("日志" if collapsed else "日志 / 指令")
        for address, button in self.device_nav_buttons.items():
            button.setText(self._device_nav_text(address, collapsed))

    def _set_nav_checked(self, active_button: QPushButton | None) -> None:
        self.nav_connect.setChecked(active_button is self.nav_connect)
        for button in self.device_nav_buttons.values():
            button.setChecked(button is active_button)

    def _register_device(self, address: str, idn: str) -> None:
        if address not in self.device_settings:
            self.device_settings[address] = dict(self.default_channel_settings)
            self.device_active_channels[address] = 1
            self.device_ui_settings[address] = dict(self.default_channel_ui)
        label = self._device_label(idn, len(self.device_labels) + 1)
        self.device_labels[address] = label
        self.device_idns[address] = idn

        if address not in self.device_nav_buttons:
            nav = self._nav_button(self._device_nav_text(address, self.sidebar_collapsed), self.device_nav_host)
            nav.setProperty("fullText", label)
            nav.clicked.connect(lambda _checked=False, key=address: self._select_device(key))
            self.device_nav_buttons[address] = nav
            self.device_nav_layout.addWidget(nav)
        else:
            self.device_nav_buttons[address].setProperty("fullText", label)
            self.device_nav_buttons[address].setText(self._device_nav_text(address, self.sidebar_collapsed))
        self._refresh_device_list()

    def _device_label(self, idn: str, number: int) -> str:
        idn_upper = idn.upper()
        if "DG1022Z" in idn_upper:
            model = "DG1022Z"
        elif "DG1022U" in idn_upper:
            model = "DG1022U"
        elif "DG" in idn_upper:
            model = "DG"
        else:
            model = "设备"
        return f"{model} {number}"

    def _device_nav_text(self, address: str, collapsed: bool) -> str:
        label = self.device_labels.get(address, "设备")
        if not collapsed:
            return label
        number = "".join(ch for ch in label if ch.isdigit())[-1:] or str(len(self.device_nav_buttons) + 1)
        return f"DG{number}"

    def _select_device(self, address: str) -> None:
        client = self.clients.get(address)
        if client is None:
            return
        if self.active_device_key:
            self._save_active_settings()
        self.active_device_key = address
        self.client = client
        if address not in self.device_settings:
            self.device_settings[address] = dict(self.default_channel_settings)
        if address not in self.device_ui_settings:
            self.device_ui_settings[address] = dict(self.default_channel_ui)
        self.channel_settings = dict(self.device_settings[address])
        self.active_channel = self.device_active_channels.get(address, 1)
        row = self._row_for_address(address)
        if row is None:
            row = self._add_connection_row(address)
        self._set_connection_row_state(row, True, "已连接")
        if self.active_channel not in self.channel_settings:
            self.active_channel = 1
        self._load_settings_to_form(self.channel_settings[self.active_channel])
        self.pages.setCurrentWidget(self.control_page)
        self._set_nav_checked(self.device_nav_buttons.get(address))
        idn = self.device_idns.get(address, address)
        self._set_connected(True, idn)
        self._save_config()
        self._log(f"切换到 {self.device_labels.get(address, '设备')}: {address}")

    def _refresh_device_list(self) -> None:
        if not hasattr(self, "device_list_layout"):
            return
        while self.device_list_layout.count():
            item = self.device_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self.clients:
            empty = QLabel("暂无已连接信号发生器，请在上方输入或刷新 VISA 地址后连接。")
            empty.setObjectName("EmptyState")
            self.device_list_layout.addWidget(empty)
            return

        for address in self.clients:
            card = QFrame()
            card.setObjectName("DeviceListCard")
            card.setFixedHeight(74)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(12)

            text = QVBoxLayout()
            text.setContentsMargins(0, 0, 0, 0)
            text.setSpacing(4)
            title = QLabel(self.device_labels.get(address, "信号发生器"), card)
            title.setObjectName("DeviceTitle")
            meta = QLabel(address, card)
            meta.setObjectName("DeviceMeta")
            text.addWidget(title)
            text.addWidget(meta)

            state = QLabel("已连接", card)
            state.setObjectName("ConnectedPill")
            state.setAlignment(Qt.AlignCenter)
            state.setFixedSize(60, 24)

            open_btn = QPushButton("打开配置", card)
            open_btn.setObjectName("OpenDeviceButton")
            open_btn.setFixedSize(86, 30)
            open_btn.clicked.connect(lambda _checked=False, key=address: self._select_device(key))

            card_layout.addLayout(text, 1)
            card_layout.addWidget(state)
            card_layout.addWidget(open_btn)
            self.device_list_layout.addWidget(card)

    def _select_channel(self, channel: int) -> None:
        if channel == self.active_channel:
            return
        self._save_active_settings()
        self.active_channel = channel
        if self.active_device_key:
            self.device_active_channels[self.active_device_key] = channel
        self._load_settings_to_form(self.channel_settings[channel])
        self._save_config()

    def _set_waveform(self, waveform: str) -> None:
        if self._loading_form:
            return
        if waveform in self.wave_buttons:
            self.wave_buttons[waveform].setChecked(True)
        self._on_form_changed()

    def _on_frequency_unit_changed(self) -> None:
        old_unit = self._frequency_display_unit
        new_unit = str(self.frequency_unit.currentData() or "kHz")
        actual_hz = self._frequency_display_to_hz(self.frequency_hz.value(), old_unit)
        self._frequency_display_unit = new_unit
        self._configure_frequency_spin(new_unit, actual_hz)
        if not self._loading_form:
            self._on_form_changed()

    def _on_period_unit_changed(self) -> None:
        old_unit = self._period_display_unit
        new_unit = str(self.period_unit.currentData() or "ms")
        actual_s = self._period_display_to_seconds(self.period_s.value(), old_unit)
        self._period_display_unit = new_unit
        self._configure_period_spin(new_unit, actual_s)
        if not self._loading_form:
            self._on_form_changed()

    def _on_burst_enabled_toggled(self, enabled: bool) -> None:
        if self._loading_form:
            return
        self._on_form_changed()
        if self.burst_enabled.isChecked() != enabled:
            return
        if self.active_device_key not in self.clients:
            return
        try:
            command = self.client.set_burst_enabled(self.active_channel, enabled)
        except Exception as exc:
            self._show_error("设置 Burst 失败", exc)
            return
        self._log(f"CH{self.active_channel} Burst {'开启' if enabled else '关闭'}: {command}")

    def _on_form_changed(self) -> None:
        if self._loading_form:
            return
        self._save_active_settings()
        self._apply_form_state_rules()
        self._refresh_view()
        self._save_config()

    def _save_active_settings(self) -> None:
        self.channel_settings[self.active_channel] = self._settings_from_form()
        if self.active_device_key:
            self.device_settings[self.active_device_key] = dict(self.channel_settings)
            self.device_active_channels[self.active_device_key] = self.active_channel
            channel_ui = self.device_ui_settings.setdefault(self.active_device_key, dict(self.default_channel_ui))
            channel_ui[self.active_channel] = ChannelUiConfig(
                frequency_unit=self._frequency_display_unit,
                period_unit=self._period_display_unit,
            )

    def _save_config(self) -> None:
        if self._loading_form or not hasattr(self, "address"):
            return
        self._save_active_settings()
        visa_addresses = self._connection_row_addresses()
        primary_address = self._current_visa_address() or (
            visa_addresses[0] if visa_addresses else self._startup_config.visa_address
        )
        config = AppConfig(
            active_channel=self.active_channel,
            visa_address=primary_address,
            visa_addresses=visa_addresses,
            channels=dict(self.channel_settings),
            devices={
                address: DeviceConfig(
                    active_channel=self.device_active_channels.get(address, 1),
                    channels=dict(channels),
                    channel_ui=dict(self.device_ui_settings.get(address, self.default_channel_ui)),
                )
                for address, channels in self.device_settings.items()
            },
        )
        try:
            save_app_config(config, self._config_path)
        except Exception as exc:
            self._log(f"保存配置失败: {exc}")

    def _frequency_display_to_hz(self, value: float, unit: str | None = None) -> float:
        factors = {"Hz": 1.0, "kHz": 1_000.0, "MHz": 1_000_000.0}
        return float(value) * factors.get(unit or self._frequency_display_unit, 1_000.0)

    def _period_display_to_seconds(self, value: float, unit: str | None = None) -> float:
        factors = {"ms": 0.001, "s": 1.0}
        return float(value) * factors.get(unit or self._period_display_unit, 0.001)

    def _configure_frequency_spin(self, unit: str, actual_hz: float) -> None:
        factors = {"Hz": 1.0, "kHz": 1_000.0, "MHz": 1_000_000.0}
        decimals = {"Hz": 6, "kHz": 6, "MHz": 9}
        steps = {"Hz": 1.0, "kHz": 0.1, "MHz": 0.001}
        factor = factors.get(unit, 1_000.0)
        value = _clamp(actual_hz / factor, 1e-6 / factor, 25e6 / factor)
        self.frequency_hz.blockSignals(True)
        self.frequency_hz.setDecimals(decimals.get(unit, 6))
        self.frequency_hz.setRange(1e-6 / factor, 25e6 / factor)
        self.frequency_hz.setSingleStep(steps.get(unit, 0.1))
        self.frequency_hz.setValue(value)
        self.frequency_hz.blockSignals(False)

    def _configure_period_spin(self, unit: str, actual_s: float) -> None:
        factors = {"ms": 0.001, "s": 1.0}
        decimals = {"ms": 6, "s": 9}
        steps = {"ms": 0.1, "s": 0.001}
        factor = factors.get(unit, 0.001)
        value = _clamp(actual_s / factor, 4e-8 / factor, 1e6 / factor)
        self.period_s.blockSignals(True)
        self.period_s.setDecimals(decimals.get(unit, 6))
        self.period_s.setRange(4e-8 / factor, 1e6 / factor)
        self.period_s.setSingleStep(steps.get(unit, 0.1))
        self.period_s.setValue(value)
        self.period_s.blockSignals(False)

    def _preferred_frequency_unit(self, frequency_hz: float) -> str:
        if abs(frequency_hz) >= 1_000_000.0:
            return "MHz"
        if abs(frequency_hz) >= 1_000.0:
            return "kHz"
        return "Hz"

    def _preferred_period_unit(self, period_s: float) -> str:
        return "s" if abs(period_s) >= 1.0 else "ms"

    def _calculated_pulse_width_s(
        self,
        waveform: str,
        frequency_mode: str,
        frequency_hz: float,
        period_s: float,
        duty_percent: float,
    ) -> float:
        if waveform.strip().upper() != "PULS":
            return self.pulse_width_s.value()
        base_period = period_s
        if frequency_mode == "frequency" and frequency_hz > 0:
            base_period = 1.0 / frequency_hz
        return max(16e-9, base_period * duty_percent / 100.0)

    def _settings_from_form(self) -> ChannelSettings:
        waveform = self._selected_waveform()
        frequency_mode = self.frequency_mode.currentData()
        frequency_hz = self._frequency_display_to_hz(self.frequency_hz.value())
        period_s = self._period_display_to_seconds(self.period_s.value())
        duty_percent = self.duty_percent.value()
        pulse_width_s = self._calculated_pulse_width_s(
            waveform,
            frequency_mode,
            frequency_hz,
            period_s,
            duty_percent,
        )
        burst = BurstSettings(
            enabled=self.burst_enabled.isChecked(),
            mode=self.burst_mode.currentData(),
            cycles=self.burst_cycles.value(),
            trigger_source=self.burst_trigger_source.currentData(),
            internal_period_s=self.burst_internal_period.value(),
            phase_deg=self.burst_phase.value(),
            delay_s=self.burst_delay.value(),
            gate_polarity=self.burst_gate_polarity.currentData(),
            trigger_slope=self.burst_trigger_slope.currentData(),
        )
        return ChannelSettings(
            channel=self.active_channel,
            waveform=waveform,
            frequency_mode=frequency_mode,
            frequency_hz=frequency_hz,
            period_s=period_s,
            level_mode=self.level_mode.currentData(),
            amplitude_vpp=self.amplitude_vpp.value(),
            offset_v=self.offset_v.value(),
            high_v=self.high_v.value(),
            low_v=self.low_v.value(),
            duty_percent=duty_percent,
            phase_deg=self.phase_deg.value(),
            pulse_width_s=pulse_width_s,
            ramp_symmetry_percent=self.ramp_symmetry.value(),
            output_enabled=self.channel_settings[self.active_channel].output_enabled,
            load=self.load.currentData(),
            burst=burst,
        )

    def _load_settings_to_form(self, settings: ChannelSettings) -> None:
        self._loading_form = True
        self.active_channel = settings.channel
        self._set_waveform_button(settings.waveform)
        _set_combo_data(self.frequency_mode, settings.frequency_mode)
        ui_key = self.active_device_key or self._current_visa_address() or self._startup_config.visa_address
        saved_ui = self.device_ui_settings.get(ui_key, {}).get(settings.channel)
        frequency_unit = (
            saved_ui.frequency_unit
            if isinstance(saved_ui, ChannelUiConfig)
            else self._preferred_frequency_unit(settings.frequency_hz)
        )
        period_unit = (
            saved_ui.period_unit
            if isinstance(saved_ui, ChannelUiConfig)
            else self._preferred_period_unit(settings.period_s)
        )
        self._frequency_display_unit = frequency_unit
        self._period_display_unit = period_unit
        _set_combo_data(self.frequency_unit, frequency_unit, silent=True)
        _set_combo_data(self.period_unit, period_unit, silent=True)
        self._configure_frequency_spin(frequency_unit, settings.frequency_hz)
        self._configure_period_spin(period_unit, settings.period_s)
        self.phase_deg.setValue(settings.phase_deg)
        _set_combo_data(self.level_mode, settings.level_mode)
        self.amplitude_vpp.setValue(settings.amplitude_vpp)
        self.offset_v.setValue(settings.offset_v)
        self.high_v.setValue(settings.high_v)
        self.low_v.setValue(settings.low_v)
        self.duty_percent.setValue(settings.duty_percent)
        self.pulse_width_s.setValue(settings.pulse_width_s)
        self.ramp_symmetry.setValue(settings.ramp_symmetry_percent)
        _set_combo_data(self.load, settings.load)
        self.burst_enabled.setChecked(settings.burst.enabled)
        _set_combo_data(self.burst_mode, settings.burst.mode)
        self.burst_cycles.setValue(settings.burst.cycles)
        _set_combo_data(self.burst_trigger_source, settings.burst.trigger_source)
        self.burst_internal_period.setValue(settings.burst.internal_period_s)
        self.burst_phase.setValue(settings.burst.phase_deg)
        self.burst_delay.setValue(settings.burst.delay_s)
        _set_combo_data(self.burst_gate_polarity, settings.burst.gate_polarity)
        _set_combo_data(self.burst_trigger_slope, settings.burst.trigger_slope)
        self._loading_form = False
        self._apply_form_state_rules()
        self._refresh_view()

    def _apply_form_state_rules(self) -> None:
        waveform = self._selected_waveform()
        wave = waveform_ui_state(waveform)
        if not wave.high_low_mode and self.level_mode.currentData() == "high_low":
            _set_combo_data(self.level_mode, "amplitude_offset", silent=True)
        if not wave.burst and self.burst_enabled.isChecked():
            self.burst_enabled.blockSignals(True)
            self.burst_enabled.setChecked(False)
            self.burst_enabled.blockSignals(False)

        trigger_source = coerce_burst_trigger_source(
            self.burst_mode.currentData(),
            self.burst_trigger_source.currentData(),
        )
        if trigger_source != self.burst_trigger_source.currentData():
            _set_combo_data(self.burst_trigger_source, trigger_source, silent=True)

        level = level_ui_state(waveform, self.level_mode.currentData())
        burst = burst_ui_state(
            waveform,
            self.burst_enabled.isChecked(),
            self.burst_mode.currentData(),
            self.burst_trigger_source.currentData(),
        )

        self.frequency_mode.setEnabled(wave.timing)
        _set_spin_enabled(self.frequency_hz, wave.timing and self.frequency_mode.currentData() == "frequency")
        _set_spin_enabled(self.period_s, wave.timing and self.frequency_mode.currentData() == "period")
        _set_spin_enabled(self.phase_deg, wave.phase)
        self.level_mode.setEnabled(wave.high_low_mode)
        _set_spin_enabled(self.amplitude_vpp, level.amplitude)
        _set_spin_enabled(self.offset_v, level.offset)
        _set_spin_enabled(self.high_v, level.high)
        _set_spin_enabled(self.low_v, level.low)
        _set_spin_enabled(self.duty_percent, wave.duty)
        _set_spin_enabled(self.pulse_width_s, wave.pulse_width)
        _set_spin_enabled(self.ramp_symmetry, wave.ramp_symmetry)

        self.timing_group.setVisible(wave.timing)
        _set_form_row_visible(self.frequency_mode, wave.timing)
        _set_form_row_visible(self.frequency_hz_editor, wave.timing and self.frequency_mode.currentData() == "frequency")
        _set_form_row_visible(self.period_s_editor, wave.timing and self.frequency_mode.currentData() == "period")
        _set_form_row_visible(self.phase_deg_editor, wave.phase)
        _set_form_row_visible(self.level_mode, wave.high_low_mode)
        _set_form_row_visible(self.amplitude_vpp_editor, level.amplitude)
        _set_form_row_visible(self.offset_v_editor, level.offset)
        _set_form_row_visible(self.high_v_editor, level.high)
        _set_form_row_visible(self.low_v_editor, level.low)
        self.shape_group.setVisible(wave.duty or wave.pulse_width or wave.ramp_symmetry)
        _set_form_row_visible(self.duty_percent_editor, wave.duty)
        _set_form_row_visible(self.pulse_width_s_editor, wave.pulse_width)
        _set_form_row_visible(self.ramp_symmetry_editor, wave.ramp_symmetry)

        self.burst_group.setVisible(wave.burst)
        self.burst_enabled.setEnabled(wave.burst)
        self.burst_status.setText("ON" if self.burst_enabled.isChecked() else "OFF")
        self.burst_status.setProperty("on", self.burst_enabled.isChecked())
        self.burst_status.style().unpolish(self.burst_status)
        self.burst_status.style().polish(self.burst_status)
        self.burst_mode.setEnabled(burst.fields)
        self.burst_details.setVisible(burst.fields)
        self.burst_trigger_source.setEnabled(burst.trigger_source)
        _set_spin_enabled(self.burst_cycles, burst.cycles)
        _set_spin_enabled(self.burst_internal_period, burst.internal_period)
        _set_spin_enabled(self.burst_phase, burst.phase)
        _set_spin_enabled(self.burst_delay, burst.delay)
        self.burst_gate_polarity.setEnabled(burst.gate_polarity)
        self.burst_trigger_slope.setEnabled(burst.trigger_slope)
        _set_form_row_visible(self.burst_mode, burst.fields)
        _set_form_row_visible(self.burst_trigger_source, burst.trigger_source)
        _set_form_row_visible(self.burst_cycles_editor, burst.cycles)
        _set_form_row_visible(self.burst_internal_period_editor, burst.internal_period)
        _set_form_row_visible(self.burst_phase_editor, burst.phase)
        _set_form_row_visible(self.burst_delay_editor, burst.delay)
        _set_form_row_visible(self.burst_gate_polarity, burst.gate_polarity)
        _set_form_row_visible(self.burst_trigger_slope, burst.trigger_slope)

    def _refresh_view(self) -> None:
        current = self._settings_from_form()
        self.channel_settings[self.active_channel] = current
        for channel, card in self.channel_cards.items():
            card.set_active(channel == self.active_channel)
            card.set_summary(self.channel_settings[channel])

        timing_text = _format_timing(current)
        level_text = _format_level(current)
        burst_text = "Burst ON" if current.burst.enabled else "Burst OFF"
        output_text = "Output ON" if current.output_enabled else "Output OFF"
        self.wave_preview.set_state(
            WaveformPreviewState(
                waveform=current.waveform,
                frequency_text=timing_text,
                level_text=level_text,
                burst_text=burst_text,
                output_text=output_text,
                duty_percent=current.duty_percent,
                ramp_symmetry_percent=current.ramp_symmetry_percent,
            )
        )
        self.channel_summary_active.setText(f"CH{current.channel} Active")
        self.channel_summary_detail.setText(
            f"{_format_waveform_name(current.waveform)} | {timing_text} | {level_text}"
        )
        self.channel_summary_state.setText(
            f"{burst_text} | {output_text} | {_format_load(current.load)}"
        )
        self._update_action_state()

    def _selected_waveform(self) -> str:
        checked = self.wave_group.checkedButton()
        if checked is None:
            return "SIN"
        return str(checked.property("waveform") or "SIN")

    def _set_waveform_button(self, waveform: str) -> None:
        button = self.wave_buttons.get(waveform.upper()) or self.wave_buttons.get("SIN")
        if button is not None:
            button.setChecked(True)

    def _refresh_resources(self) -> None:
        try:
            resources = self.client.list_resources()
        except Exception as exc:
            self._show_error("刷新 VISA 资源失败", exc)
            return
        self.available_resources = resources
        for row in self.connection_rows:
            address_box = row.get("address")
            if isinstance(address_box, QComboBox) and address_box.isEnabled():
                self._populate_address_combo(address_box)
        self._log(f"发现 {len(resources)} 个 VISA 资源")

    def _connect(self, row: dict[str, QWidget] | None = None) -> None:
        row = row or (self.connection_rows[0] if self.connection_rows else None)
        if row is None:
            return
        address = self._connection_row_address(row)
        if not address:
            self._set_connection_row_state(row, False, "地址为空", failed=True)
            self._log("连接失败: VISA 地址为空")
            return
        if address in self.clients:
            self._set_connection_row_state(row, True, "已连接")
            self._select_device(address)
            return
        client = RigolVisaClient(log=self._log)
        try:
            result = client.connect(address)
        except Exception as exc:
            self._set_connection_row_state(row, False, "连接失败", failed=True)
            self._log("连接排查提示：请检查网线、IP 地址、VISA 驱动和设备电源。")
            self._show_error("连接失败", exc)
            return
        self.clients[address] = client
        self.client = client
        self._register_device(address, result.idn)
        self._select_device(address)
        self._log(f"连接成功: {address} [{result.backend}] {result.idn}")

    def _disconnect(self, address: str | None = None) -> None:
        address = (address or self.active_device_key or self._current_visa_address()).strip()
        self._save_active_settings()
        client = self.clients.pop(address, None)
        if client is None:
            row = self._row_for_address(address)
            if row is not None:
                self._set_connection_row_state(row, False, "未连接")
            self._update_action_state()
            return
        else:
            client.disconnect()

        nav = self.device_nav_buttons.pop(address, None)
        if nav is not None:
            nav.setParent(None)
            nav.deleteLater()
        self.device_labels.pop(address, None)
        self.device_idns.pop(address, None)
        row = self._row_for_address(address)
        if row is not None:
            self._set_connection_row_state(row, False, "未连接")
        self._refresh_device_list()
        self._log(f"已断开: {address or '当前设备'}")

        if address == self.active_device_key and self.clients:
            self._select_device(next(iter(self.clients)))
            return
        if self.clients:
            self._update_action_state()
            return

        self.active_device_key = ""
        self.client = RigolVisaClient(log=self._log)
        self._set_connected(False, "未连接")
        self._show_connection_page()

    def _toggle_connection(self, row: dict[str, QWidget] | None = None) -> None:
        row = row or (self.connection_rows[0] if self.connection_rows else None)
        if row is None:
            return
        self._set_active_connection_row(row)
        current = self._connection_row_address(row)
        if current in self.clients:
            self._disconnect(current)
        else:
            self._connect(row)

    def _query_idn(self) -> None:
        try:
            idn = self.client.query_idn()
        except Exception as exc:
            self._show_error("查询 IDN 失败", exc)
            return
        self._set_connected(True, idn)

    def _apply_current(self) -> None:
        self._save_active_settings()
        self._save_config()
        settings = self.channel_settings[self.active_channel]
        self._log(f"准备下发 CH{settings.channel}: {_format_channel_brief(settings)}")
        try:
            commands = self.client.apply_channel(settings)
        except Exception as exc:
            self._show_error("应用当前通道失败", exc)
            return
        self._log(f"CH{settings.channel} 已应用 {len(commands)} 条命令")

    def _apply_all(self) -> None:
        self._save_active_settings()
        self._save_config()
        try:
            for channel in (1, 2):
                settings = self.channel_settings[channel]
                self._log(f"准备下发 CH{settings.channel}: {_format_channel_brief(settings)}")
                self.client.apply_channel(settings)
        except Exception as exc:
            self._show_error("应用双通道失败", exc)
            return
        self._log("CH1/CH2 参数已应用")

    def _toggle_output(self) -> None:
        self._save_active_settings()
        enabled = not self.channel_settings[self.active_channel].output_enabled
        self._set_output(enabled)

    def _set_output(self, enabled: bool) -> None:
        self._save_active_settings()
        current = self.channel_settings[self.active_channel]
        next_settings = ChannelSettings(**{**current.__dict__, "output_enabled": enabled})
        try:
            self.client.set_output(self.active_channel, enabled)
        except Exception as exc:
            self._show_error("设置输出失败", exc)
            return
        self.channel_settings[self.active_channel] = next_settings
        self._load_settings_to_form(next_settings)
        self._save_config()
        self._log(f"CH{self.active_channel} 输出 {'打开' if enabled else '关闭'}")

    def _fire_burst(self) -> None:
        try:
            self.client.fire_burst(self.active_channel)
        except Exception as exc:
            self._show_error("软件触发失败", exc)
            return
        self._log(f"CH{self.active_channel} Burst 软件触发已发送")

    def _align_phase(self) -> None:
        try:
            self.client.align_phase(self.active_channel)
        except Exception as exc:
            self._show_error("相位同步失败", exc)
            return
        self._log(f"CH{self.active_channel} 相位同步命令已发送")

    def _query_error(self) -> None:
        try:
            reply = self.client.query_system_error()
        except Exception as exc:
            self._show_error("查询系统错误失败", exc)
            return
        self._log(f"系统错误: {reply}")

    def _set_connected(self, connected: bool, text: str) -> None:
        self._connected = connected
        failed = text == "连接失败"
        row = self._row_for_address(self.active_device_key) or (
            self.connection_rows[0] if self.connection_rows else None
        )
        if row is not None:
            self._set_connection_row_state(row, connected, text, failed=failed)
        self._update_action_state()

    def _update_action_state(self) -> None:
        connected = bool(self.active_device_key and self.active_device_key in self.clients)
        settings = self.channel_settings[self.active_channel]
        burst = burst_ui_state(
            settings.waveform,
            settings.burst.enabled,
            settings.burst.mode,
            settings.burst.trigger_source,
        )
        self._update_connection_rows()
        self.btn_apply.setEnabled(connected)
        self.btn_apply_all.setEnabled(connected)
        self.btn_output_toggle.setEnabled(connected)
        self.btn_output_toggle.setText("输出 ON" if settings.output_enabled else "输出 OFF")
        self.btn_output_toggle.setProperty("on", settings.output_enabled)
        _repolish(self.btn_output_toggle)
        self.btn_error.setEnabled(connected)
        self.btn_fire.setEnabled(connected and burst.software_trigger)

    def _show_log_window(self) -> None:
        self.log_window.show()
        self.log_window.raise_()
        self.log_window.activateWindow()

    def _show_error(self, title: str, exc: Exception) -> None:
        text = f"{type(exc).__name__}: {exc}"
        self._log(f"{title}: {text}")
        QMessageBox.warning(self, title, text)

    def _log(self, line: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        if hasattr(self, "log"):
            self.log.append(f"{ts}  {line}")

    def _apply_elevation(self) -> None:
        for widget, blur, offset, alpha in (
            (self.sidebar, 18, 3, 20),
            (self.connection_panel, 18, 3, 18),
            (self.center_panel, 20, 4, 20),
            (self.right_panel, 20, 4, 18),
        ):
            shadow = QGraphicsDropShadowEffect(widget)
            shadow.setBlurRadius(blur)
            shadow.setOffset(0, offset)
            shadow.setColor(QColor(30, 55, 82, alpha))
            widget.setGraphicsEffect(shadow)

    def _apply_style(self) -> None:
        self.setStyleSheet(APP_STYLE)


def _form_layout(parent: QWidget) -> QFormLayout:
    layout = QFormLayout(parent)
    layout.setLabelAlignment(Qt.AlignRight)
    layout.setFormAlignment(Qt.AlignTop)
    layout.setHorizontalSpacing(8)
    layout.setVerticalSpacing(5)
    layout.setContentsMargins(10, 8, 10, 8)
    return layout


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def _double_spin(
    minimum: float,
    maximum: float,
    value: float,
    decimals: int,
    suffix: str,
    step: float,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setObjectName("ArrowSpin")
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setValue(value)
    spin.setSingleStep(step)
    spin.setSuffix(suffix)
    spin.setKeyboardTracking(False)
    spin.setAccelerated(True)
    spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
    spin.setFrame(False)
    return spin


def _spin_editor(spin: QDoubleSpinBox | QSpinBox, unit: QComboBox | None = None) -> QWidget:
    spin.setObjectName("ArrowSpin")
    spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
    spin.setFrame(False)
    spin.setAccelerated(True)

    editor = QFrame()
    editor.setObjectName("SpinEditorBox")
    layout = QHBoxLayout(editor)
    layout.setContentsMargins(7, 2, 4, 2)
    layout.setSpacing(2)
    layout.addWidget(spin, 1)

    btn_up = QToolButton(editor)
    btn_up.setObjectName("SpinArrowButton")
    btn_up.setText("▲")
    btn_up.setToolTip("增加")
    btn_up.setAutoRaise(True)
    btn_up.setFixedSize(21, 21)

    btn_down = QToolButton(editor)
    btn_down.setObjectName("SpinArrowButton")
    btn_down.setText("▼")
    btn_down.setToolTip("减少")
    btn_down.setAutoRaise(True)
    btn_down.setFixedSize(21, 21)

    btn_up.clicked.connect(lambda: spin.setValue(spin.value() + spin.singleStep()))
    btn_down.clicked.connect(lambda: spin.setValue(spin.value() - spin.singleStep()))

    if unit is not None:
        layout.addWidget(unit)
    layout.addWidget(btn_up)
    layout.addWidget(btn_down)
    return editor


def _set_form_row_visible(field: QWidget, visible: bool) -> None:
    parent = field.parentWidget()
    layout = parent.layout() if parent is not None else None
    if isinstance(layout, QFormLayout) and hasattr(layout, "setRowVisible"):
        try:
            layout.setRowVisible(field, visible)
            return
        except TypeError:
            pass

    label = layout.labelForField(field) if isinstance(layout, QFormLayout) else None
    if label is not None:
        label.setVisible(visible)
    field.setVisible(visible)


def _set_spin_enabled(spin: QDoubleSpinBox | QSpinBox, enabled: bool) -> None:
    spin.setEnabled(enabled)
    editor = spin.parentWidget()
    if editor is not None and editor.objectName() == "SpinEditorBox":
        editor.setEnabled(enabled)
        for child in editor.findChildren(QToolButton):
            child.setEnabled(enabled)


def _set_combo_data(combo: QComboBox, data: str, *, silent: bool = False) -> None:
    index = combo.findData(data)
    if index >= 0 and combo.currentIndex() != index:
        if silent:
            combo.blockSignals(True)
        combo.setCurrentIndex(index)
        if silent:
            combo.blockSignals(False)


def _format_timing(settings: ChannelSettings) -> str:
    waveform = settings.waveform.strip().upper()
    if waveform in {"DC", "NOIS", "NOISE"}:
        return "Timing OFF"
    if settings.frequency_mode == "period":
        if abs(settings.period_s) < 1.0:
            return f"{settings.period_s * 1_000.0:g} ms"
        return f"{settings.period_s:g} s"
    hz = settings.frequency_hz
    if hz >= 1_000_000.0:
        return f"{hz / 1_000_000.0:g} MHz"
    if hz >= 1_000.0:
        return f"{hz / 1_000.0:g} kHz"
    return f"{hz:g} Hz"


def _format_level(settings: ChannelSettings) -> str:
    waveform = settings.waveform.strip().upper()
    if waveform == "DC":
        return f"DC {settings.offset_v:g} V"
    if settings.level_mode == "high_low":
        return f"{settings.high_v:g}/{settings.low_v:g} V"
    return f"{settings.amplitude_vpp:g} Vpp, {settings.offset_v:g} Voff"


def _format_level_short(settings: ChannelSettings) -> str:
    waveform = settings.waveform.strip().upper()
    if waveform == "DC":
        return f"{settings.offset_v:g} V"
    if settings.level_mode == "high_low":
        return "High/Low"
    return f"{settings.amplitude_vpp:g} Vpp"


def _format_waveform_name(waveform: str) -> str:
    names = {
        "SIN": "Sine",
        "SQU": "Square",
        "PULS": "Pulse",
        "RAMP": "Ramp",
        "NOIS": "Noise",
        "USER": "Arb",
        "DC": "DC",
    }
    token = waveform.strip().upper()
    return names.get(token, token)


def _format_load(load: str) -> str:
    return "High-Z" if load == "INF" else "50 ohm"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _format_channel_brief(settings: ChannelSettings) -> str:
    burst = "Burst ON" if settings.burst.enabled else "Burst OFF"
    output = "Output ON" if settings.output_enabled else "Output OFF"
    return (
        f"{_format_waveform_name(settings.waveform)}, {_format_timing(settings)}, "
        f"{_format_level(settings)}, {_format_load(settings.load)}, {burst}, {output}"
    )


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _wave_button_label(label: str, value: str) -> str:
    return label


APP_STYLE = """
QWidget {
    font-family: "Microsoft YaHei UI", "Segoe UI", Arial;
    font-size: 12px;
    color: #17283b;
    background: #eef4fa;
}
QLabel, QCheckBox {
    background: transparent;
}
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    background: #ffffff;
    border: 1px solid #cfd8e5;
    border-radius: 4px;
}
QCheckBox::indicator:hover {
    border-color: #338de6;
}
QCheckBox::indicator:checked {
    background: #1879d9;
    border-color: #1879d9;
}
QCheckBox::indicator:checked:disabled {
    background: #a9c7e8;
    border-color: #a9c7e8;
}
QCheckBox::indicator:disabled {
    background: #edf1f6;
    border-color: #d9e1eb;
}
QScrollArea#ParameterScroll, QWidget#ParameterScrollBody {
    background: transparent;
    border: none;
}
QWidget#AppRoot, QWidget#ControlPage, QStackedWidget#PageStack {
    background: #eef4fa;
    border: none;
}
QFrame#Sidebar {
    background: #fbfdff;
    border: 1px solid #dce5ef;
    border-radius: 12px;
}
QFrame#SidebarDivider {
    background: #dbe5ef;
    border: none;
}
QToolButton#SidebarMenuButton {
    background: transparent;
    border: none;
    border-radius: 0;
    color: #536478;
    font-family: "Segoe UI Symbol", "Microsoft YaHei UI";
    font-size: 26px;
    font-weight: 800;
    padding: 0;
}
QToolButton#SidebarMenuButton:hover {
    background: transparent;
    color: #1879d9;
}
QWidget#DeviceNavHost {
    background: transparent;
}
QPushButton#NavButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    color: #536478;
    font-size: 12px;
    font-weight: 700;
    padding: 0 6px;
}
QPushButton#NavButton:hover {
    background: #f2f7fc;
    border-color: #d9e5f0;
    color: #1e6fbf;
}
QPushButton#NavButton:checked {
    background: #e9f4ff;
    border-color: #9bcdf6;
    color: #1879d9;
}
QPushButton#SidebarLogButton {
    background: #ffffff;
    border: 1px solid #cfddec;
    border-radius: 9px;
    color: #2f4a68;
    font-size: 11px;
    font-weight: 700;
    padding: 0 4px;
}
QPushButton#SidebarLogButton:hover {
    border-color: #338de6;
    color: #1879d9;
}
QFrame#ConnectionPage {
    background: transparent;
    border: none;
}
QFrame#ConnectionCard, QFrame#CenterPanel {
    background: #fbfdff;
    border: 1px solid #dce5ef;
    border-radius: 11px;
}
QFrame#ConnectionCard {
    background: #ffffff;
    border-color: #d6e0eb;
    border-radius: 12px;
}
QLabel#ConnectionTitle {
    color: #0f2f4d;
    font-size: 24px;
    font-weight: 800;
    background: transparent;
}
QLabel#ConnectionSubtitle {
    color: #607387;
    font-size: 13px;
    background: transparent;
}
QFrame#ConnectionDeviceRow {
    background: #f7fafc;
    border: 1px solid #dce5ef;
    border-radius: 10px;
}
QFrame#ConnectionStatusBadge {
    background: #f7fafc;
    border: 1px solid #dce5ef;
    border-radius: 9px;
}
QFrame#ConnectionStatusBadge[connected="true"] {
    background: #e8f6ee;
    border-color: #bfe5cf;
}
QFrame#ConnectionStatusBadge[failed="true"] {
    background: #fff2f0;
    border-color: #f2b8b5;
}
QLabel#ConnectionListTitle {
    color: #0f2f4d;
    font-size: 14px;
    font-weight: 800;
    background: transparent;
    padding-top: 4px;
}
QFrame#RightPanel {
    background: #f3f7fb;
    border: 1px solid #dce5ef;
    border-radius: 11px;
}
QFrame#ChannelActionStrip {
    background: #ffffff;
    border: 1px solid #dce5ef;
    border-radius: 10px;
}
QFrame#ChannelActionStrip QWidget#StripRow {
    background: transparent;
    border: none;
}
QWidget#WorkControlRow {
    background: transparent;
}
QFrame#ChannelSummaryCard {
    background: #ffffff;
    border: 1px solid #dce5ef;
    border-radius: 10px;
}
QFrame#ActionGrid {
    background: transparent;
    border: none;
}
QFrame#ActionGrid QPushButton, QFrame#ActionGrid QComboBox {
    min-height: 32px;
    padding: 2px 8px;
    font-size: 12px;
}
QFrame#BrandBlock {
    background: transparent;
    border-right: 1px solid #d8e0ea;
}
QFrame#StatusIndicator {
    background: transparent;
    border: none;
}
QLabel#StatusDot {
    background: #e05a5a;
    border: 1px solid #f0b8b8;
    border-radius: 5px;
}
QLabel#StatusDot[connected="true"] {
    background: #2e9f61;
    border-color: #bfe5cf;
}
QLabel#StatusDot[failed="true"] {
    background: #d64b4b;
    border-color: #f5b5b5;
}
QLabel#StatusText {
    color: #607387;
    font-size: 12px;
    font-weight: 700;
    background: transparent;
}
QLabel#StatusText[connected="true"] {
    color: #2e9f61;
}
QLabel#StatusText[failed="true"] {
    color: #c94141;
}
QWidget#BrandTextBlock, QWidget#WaveformPreview {
    background: transparent;
}
QLabel#BrandBadge {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #22b5d5, stop:1 #1f8ed7);
    color: #eef8ff;
    border-radius: 10px;
    font-size: 18px;
    font-weight: 700;
}
QLabel#BrandTitle {
    color: #0f2f4d;
    font-size: 18px;
    font-weight: 700;
    background: transparent;
}
QLabel#MainTitle {
    color: #0f2f4d;
    font-size: 22px;
    font-weight: 700;
    background: transparent;
}
QLabel#BrandSubtitle, QLabel#SubtleText {
    color: #607387;
    font-size: 11px;
    background: transparent;
}
QLabel#FieldLabel, QLabel#PanelTitle, QLabel#CardTitle {
    color: #2f4a68;
    font-weight: 700;
    background: transparent;
}
QLabel#PanelTitle {
    font-size: 18px;
}
QLabel#CardTitle {
    color: #0f2f4d;
    font-size: 16px;
    font-weight: 700;
}
QFrame#Card {
    background: #ffffff;
    border: 1px solid #dce5ef;
    border-radius: 10px;
}
QFrame#DeviceListCard {
    background: #ffffff;
    border: 1px solid #dce5ef;
    border-radius: 10px;
}
QLabel#DeviceTitle {
    color: #0f2f4d;
    font-size: 13px;
    font-weight: 700;
    background: transparent;
}
QLabel#DeviceMeta, QLabel#EmptyState {
    color: #607387;
    font-size: 12px;
    background: transparent;
}
QLabel#ConnectedPill {
    background: #e8f6ee;
    border: 1px solid #bfe5cf;
    border-radius: 7px;
    color: #2e9f61;
    font-weight: 700;
    font-size: 11px;
}
QPushButton#OpenDeviceButton {
    padding: 3px 8px;
    font-size: 11px;
}
QFrame#ChannelCard {
    background: #ffffff;
    border: 1px solid #dce5ef;
    border-radius: 10px;
}
QFrame#ChannelCard[active="true"] {
    background: #f7fbff;
    border: 1px solid #82bff2;
}
QLabel#StripRowLabel {
    color: #607387;
    font-size: 11px;
    font-weight: 700;
    background: transparent;
}
QLabel#ChannelCardTitle {
    color: #1879d9;
    font-size: 13px;
    font-weight: 700;
    background: transparent;
}
QLabel#ChannelCardMeta {
    color: #536478;
    font-size: 11px;
    background: transparent;
}
QLabel#ChannelOutputBadge, QLabel#StatePill {
    border-radius: 7px;
    background: #edf1f6;
    border: 1px solid #d9e1eb;
    color: #8a95a5;
    font-weight: 700;
    font-size: 11px;
}
QLabel#ChannelOutputBadge[on="true"], QLabel#StatePill[on="true"] {
    background: #e8f6ee;
    border-color: #bfe5cf;
    color: #2e9f61;
}
QGroupBox {
    background: #ffffff;
    border: 1px solid #dee5ef;
    border-radius: 10px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #0f2f4d;
    background: transparent;
}
QFrame#RightPanel QLabel, QFrame#RightPanel QCheckBox {
    font-size: 11px;
}
QFrame#RightPanel QLabel#PanelTitle {
    font-size: 14px;
}
QFrame#RightPanel QGroupBox {
    background: #ffffff;
    border: 1px solid #dce5ef;
    border-radius: 10px;
    margin-top: 0;
    padding: 0;
    font-size: 11px;
}
QFrame#RightPanel QGroupBox::title {
    height: 0;
    padding: 0;
    margin: 0;
    background: transparent;
}
QLabel#SectionTitle {
    color: #0f2f4d;
    font-size: 12px;
    font-weight: 700;
    padding: 0 0 5px 0;
    background: transparent;
    border: none;
}
QComboBox, QDoubleSpinBox, QSpinBox {
    background: #ffffff;
    border: 1px solid #d4dfeb;
    border-radius: 8px;
    min-height: 26px;
    padding: 2px 6px;
}
QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {
    border-color: #338de6;
}
QComboBox:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled {
    color: #8a96a8;
    background: #edf1f6;
    border-color: #d9e1eb;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #d4dfeb;
    border-radius: 8px;
    outline: 0;
    padding: 4px;
    color: #22354c;
    selection-background-color: #e9f4ff;
    selection-color: #0f2f4d;
}
QComboBox QAbstractItemView::item {
    min-height: 24px;
    padding: 4px 8px;
    border-radius: 6px;
}
QComboBox QAbstractItemView::item:hover {
    background: #f2f7fc;
}
QListView {
    background: #ffffff;
    border: 1px solid #d4dfeb;
    border-radius: 8px;
    outline: 0;
    padding: 4px;
    color: #22354c;
    selection-background-color: #e9f4ff;
    selection-color: #0f2f4d;
}
QListView::item {
    min-height: 24px;
    padding: 4px 8px;
    border: none;
    border-radius: 6px;
}
QListView::item:selected, QListView::item:hover {
    background: #e9f4ff;
    color: #0f2f4d;
}
QFrame#RightPanel QComboBox, QFrame#RightPanel QDoubleSpinBox, QFrame#RightPanel QSpinBox {
    min-height: 22px;
    padding: 1px 6px;
    font-size: 11px;
}
QFrame#RightPanel QComboBox::drop-down {
    width: 18px;
}
QFrame#SpinEditorBox QComboBox#UnitCombo {
    background: transparent;
    border: none;
    border-left: 1px solid #d4dfeb;
    border-radius: 0;
    min-height: 18px;
    padding: 1px 2px 1px 7px;
    color: #536478;
}
QFrame#SpinEditorBox QComboBox#UnitCombo::drop-down {
    width: 14px;
}
QFrame#SpinEditorBox {
    background: #ffffff;
    border: 1px solid #d4dfeb;
    border-radius: 9px;
}
QFrame#SpinEditorBox:disabled {
    background: #edf1f6;
    border-color: #d9e1eb;
}
QDoubleSpinBox#ArrowSpin, QSpinBox#ArrowSpin {
    background: transparent;
    border: none;
    padding: 5px 2px;
    min-height: 22px;
    color: #22354c;
}
QFrame#RightPanel QDoubleSpinBox#ArrowSpin, QFrame#RightPanel QSpinBox#ArrowSpin {
    min-height: 18px;
    padding: 2px 1px;
    font-size: 11px;
}
QToolButton#SpinArrowButton {
    background: transparent;
    border: none;
    color: #7b8794;
    font-family: "Segoe UI Symbol", "Microsoft YaHei UI";
    font-size: 13px;
    font-weight: 700;
    padding: 0;
}
QFrame#RightPanel QToolButton#SpinArrowButton {
    font-size: 12px;
}
QToolButton#SpinArrowButton:hover {
    color: #334155;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #d3deea;
    border-radius: 8px;
    padding: 7px 12px;
    color: #2b3a50;
    font-weight: 500;
}
QPushButton:hover {
    border-color: #338de6;
    color: #1e6fbf;
}
QPushButton:pressed {
    background: #eef5ff;
}
QPushButton:disabled {
    color: #a7b1bf;
    background: #ffffff;
    border-color: #d7deea;
}
QPushButton#PrimaryButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2588e2, stop:1 #1879d9);
    border-color: #1879d9;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover {
    background: #0d6fcf;
    border-color: #0d6fcf;
}
QPushButton#ConnectionButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2588e2, stop:1 #1879d9);
    border-color: #1879d9;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#ConnectionButton:hover {
    background: #0d6fcf;
    border-color: #0d6fcf;
}
QPushButton#ConnectionButton[connected="true"] {
    background: #ffffff;
    border-color: #9fc6eb;
    color: #1e6fbf;
}
QPushButton#OutputToggleButton[on="true"] {
    background: #e8f6ee;
    border-color: #bfe5cf;
    color: #2e9f61;
    font-weight: 700;
}
QPushButton#WaveChoice {
    min-height: 68px;
    padding: 5px 6px;
    font-size: 13px;
    font-weight: 500;
}
QPushButton#WaveChoice:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2588e2, stop:1 #1879d9);
    border-color: #1879d9;
    color: #ffffff;
    font-weight: 700;
}
QLabel#SummaryTitle {
    color: #40546a;
    font-size: 12px;
    font-weight: 700;
    background: transparent;
}
QLabel#SummaryLine {
    color: #40546a;
    font-size: 12px;
    background: transparent;
}
QLabel#SummaryLineStrong {
    color: #1879d9;
    font-size: 12px;
    font-weight: 700;
    background: transparent;
}
QFrame#InlineDetails {
    background: transparent;
    border: none;
}
QTextEdit#LogText {
    background: #ffffff;
    color: #2c3f55;
    border: 1px solid #d7e1ec;
    border-radius: 8px;
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 11px;
    selection-background-color: #dcecff;
    padding: 6px;
}
QTextEdit#LogText {
    min-height: 220px;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: transparent;
    margin: 2px;
}
QScrollBar:vertical {
    width: 6px;
}
QScrollBar:horizontal {
    height: 6px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #cfd7e2;
    border-radius: 4px;
    min-height: 28px;
    min-width: 28px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    height: 0;
    width: 0;
}
"""


def run_app() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()
