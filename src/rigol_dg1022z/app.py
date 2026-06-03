from __future__ import annotations

import sys
from datetime import datetime

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
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
    QListView,
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

from . import __version__
from .config import (
    AppConfig,
    ChannelUiConfig,
    DeviceConfig,
    default_app_config,
    default_config_path,
    load_app_config,
    save_app_config,
)
from .display_units import (
    preferred_frequency_unit,
    preferred_level_voltage_unit,
    preferred_period_unit,
)
from .domain import (
    BurstSettings,
    ChannelSettings,
    LoadMode,
    amplitude_offset_from_high_low,
    duty_from_pulse_width,
    frequency_from_period,
    high_low_from_amplitude_offset,
    period_from_frequency,
    pulse_width_from_duty,
    scale_voltage_for_load_change,
)
from .scpi import WAVEFORM_CHOICES
from .ui_state import (
    burst_ui_state,
    coerce_burst_trigger_source,
    level_ui_state,
    waveform_ui_state,
)
from .visa import RigolVisaClient
from .waveform_preview import WaveformPreview, WaveformPreviewState


COMBO_POPUP_STYLE = """
QListView#ComboPopupView {
    background: #ffffff;
    border: 1px solid #d4dfeb;
    border-radius: 8px;
    outline: 0;
    padding: 4px;
    color: #22354c;
}
QListView#ComboPopupView::item {
    min-height: 24px;
    padding: 4px 8px;
    border-radius: 6px;
    background: transparent;
}
QListView#ComboPopupView::item:hover,
QListView#ComboPopupView::item:selected {
    background: #e9f4ff;
    color: #0f2f4d;
}
"""

CONNECTION_CONTROL_HEIGHT = 34
CONNECTION_BUTTON_WIDTH = 68
CONNECTION_DEVICE_LABEL_WIDTH = 76
CONNECTION_ROW_LABEL_WIDTH = 92
CONNECTION_ADDRESS_MIN_WIDTH = 210
CONNECTION_ADDRESS_MAX_WIDTH = 210
CONNECTION_CHANNEL_BUTTON_WIDTH = 120
CONNECTION_GRID_COLUMNS = 1
CONNECTION_GRID_GROUP_GAP = 16
WORK_TOOLBAR_LABEL_WIDTH = 36
WORK_TOOLBAR_ROW_HEIGHT = 40
WORK_TOOLBAR_ROW_SPACING = 10
WORK_TOOLBAR_CONTROL_HEIGHT = 36
RIGHT_PANEL_MIN_WIDTH = 306
RIGHT_PANEL_MAX_WIDTH = 310
RIGHT_PANEL_MARGIN_LEFT = 14
RIGHT_PANEL_MARGIN_TOP = 14
RIGHT_PANEL_MARGIN_RIGHT = 12
RIGHT_PANEL_MARGIN_BOTTOM = 14
PARAM_LABEL_WIDTH = 56
PARAM_FIELD_WIDTH = 198
PARAM_ROW_HEIGHT = 34
PARAM_FORM_HORIZONTAL_SPACING = 8
PARAM_FORM_VERTICAL_SPACING = 8
PARAM_FORM_MARGIN_H = 8
PARAM_CARD_WIDTH = (
    PARAM_FORM_MARGIN_H * 2
    + PARAM_LABEL_WIDTH
    + PARAM_FORM_HORIZONTAL_SPACING
    + PARAM_FIELD_WIDTH
)
UNIT_SLOT_WIDTH = 64
UNIT_SEP_WIDTH = 1
UNIT_COLUMN_WIDTH = UNIT_SEP_WIDTH + UNIT_SLOT_WIDTH
UNIT_SLOT_PAD_LEFT = 8
UNIT_SLOT_PAD_RIGHT = 8
VALID_FREQUENCY_UNITS = frozenset({"Hz", "kHz", "MHz"})
VALID_PERIOD_UNITS = frozenset({"ms", "s"})
VALID_LEVEL_VOLTAGE_UNITS = frozenset({"V", "mV"})
CONNECT_RETRY_COUNT = 3


class CleanComboBox(QComboBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._popup: QFrame | None = None
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMaxVisibleItems(12)
        self._prepare_popup()

    def wheelEvent(self, event) -> None:
        line_edit = self.lineEdit() if self.isEditable() else None
        if not self.hasFocus() and not (line_edit is not None and line_edit.hasFocus()):
            event.ignore()
            return
        super().wheelEvent(event)

    def showPopup(self) -> None:
        self.hidePopup()
        if self.count() <= 0:
            return

        popup = QFrame(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        popup.setObjectName("ComboPopupFrame")
        popup.setAttribute(Qt.WA_StyledBackground, True)
        popup.setAttribute(Qt.WA_TranslucentBackground, False)
        popup.setStyleSheet(APP_STYLE)

        outer = QVBoxLayout(popup)
        outer.setContentsMargins(3, 3, 3, 3)
        outer.setSpacing(0)

        row_height = 32
        visible_rows = min(max(1, self.count()), self.maxVisibleItems())
        item_host = QFrame(popup)
        item_host.setObjectName("ComboPopupItems")
        item_layout = QVBoxLayout(item_host)
        item_layout.setContentsMargins(0, 0, 0, 0)
        item_layout.setSpacing(0)
        content_width = self.width()
        for index in range(self.count()):
            item = QPushButton(self.itemText(index), item_host)
            item.setObjectName("ComboPopupItem")
            item.setFixedHeight(row_height)
            item.setCursor(Qt.PointingHandCursor)
            item.setProperty("selected", index == self.currentIndex())
            item.clicked.connect(lambda _checked=False, row=index: self._select_popup_index(row))
            item_layout.addWidget(item)
            content_width = max(content_width, item.sizeHint().width() + 18)
        item_host.setFixedHeight(self.count() * row_height)

        if self.count() > visible_rows:
            scroller = QScrollArea(popup)
            scroller.setObjectName("ComboPopupScroll")
            scroller.setFrameShape(QFrame.NoFrame)
            scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroller.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroller.setWidgetResizable(True)
            scroller.setWidget(item_host)
            outer.addWidget(scroller)
        else:
            outer.addWidget(item_host)

        height = visible_rows * row_height + 6
        width = max(self.width(), content_width, 120)
        popup.setFixedSize(width, height)

        global_bottom_left = self.mapToGlobal(QPoint(0, self.height()))
        global_top_left = self.mapToGlobal(QPoint(0, 0))
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            x = global_bottom_left.x()
            if x + width > available.right():
                x = max(available.left(), available.right() - width + 1)
            x = max(available.left(), x)

            space_below = available.bottom() - global_bottom_left.y()
            space_above = global_top_left.y() - available.top()
            if height <= space_below or space_below >= space_above:
                y = global_bottom_left.y()
            else:
                y = global_top_left.y() - height
            if y + height > available.bottom():
                y = max(available.top(), available.bottom() - height + 1)
            if y < available.top():
                y = available.top()
        else:
            x = global_bottom_left.x()
            y = global_bottom_left.y()

        popup.move(x, y)
        self._popup = popup
        popup.show()

    def hidePopup(self) -> None:
        if self._popup is not None:
            popup = self._popup
            self._popup = None
            popup.close()
            popup.deleteLater()

    def _select_popup_index(self, index: int) -> None:
        if 0 <= index < self.count():
            self.setCurrentIndex(index)
        self.hidePopup()

    def _prepare_popup(self) -> QListView:
        view = self.view()
        if not isinstance(view, QListView) or view.objectName() != "ComboPopupView":
            view = QListView(self)
            view.setObjectName("ComboPopupView")
            self.setView(view)
        view.setObjectName("ComboPopupView")
        view.setFrameShape(QFrame.NoFrame)
        view.setLineWidth(0)
        view.setMidLineWidth(0)
        view.setMouseTracking(True)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        view.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        view.setAttribute(Qt.WA_StyledBackground, True)
        view.setAttribute(Qt.WA_TranslucentBackground, False)
        view.setStyleSheet(COMBO_POPUP_STYLE)
        return view


class ConnectionStatusLabel(QLabel):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit()
        super().mousePressEvent(event)


class FocusWheelDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event) -> None:
        if not self.hasFocus() and not self.lineEdit().hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class FocusWheelSpinBox(QSpinBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event) -> None:
        if not self.hasFocus() and not self.lineEdit().hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class ChannelCard(QFrame):
    selected = Signal(int)

    def __init__(self, channel: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.channel = channel
        self.setObjectName("ChannelCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(WORK_TOOLBAR_CONTROL_HEIGHT)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 8, 4)
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


class ConnectionChannelCard(QFrame):
    selected = Signal(int)

    def __init__(self, channel: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.channel = channel
        self.setObjectName("ConnectionChannelCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(CONNECTION_CHANNEL_BUTTON_WIDTH, CONNECTION_CONTROL_HEIGHT)
        self.setFixedHeight(CONNECTION_CONTROL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 4, 8, 4)
        layout.setSpacing(8)

        self.title = QLabel(f"CH{channel}", self)
        self.title.setObjectName("ConnectionChannelTitle")
        self.title.setFixedWidth(32)
        self.output = QLabel("输出 OFF", self)
        self.output.setObjectName("ConnectionChannelOutputBadge")
        self.output.setFixedSize(68, 22)
        self.output.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.title)
        layout.addStretch(1)
        layout.addWidget(self.output, 0, Qt.AlignVCenter)

    def set_state(self, *, active: bool, connected: bool, output_on: bool) -> None:
        self.setEnabled(connected)
        self.setProperty("active", active)
        self.setProperty("connected", connected)
        self.setProperty("outputOn", "true" if output_on else "false")
        self.output.setText("输出 ON" if output_on else "输出 OFF")
        self.output.setProperty("state", "on" if output_on else "off")
        self.output.setProperty("on", "true" if output_on else "false")
        _repolish(self)
        _repolish(self.title)
        _repolish(self.output)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.selected.emit(self.channel)
        super().mouseReleaseEvent(event)


class CheckMarkCheckBox(QCheckBox):
    def sizeHint(self) -> QSize:
        text_width = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(16 + 8 + text_width, max(22, self.fontMetrics().height() + 4))

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        checked = self.isChecked()
        enabled = self.isEnabled()
        active = self.hasFocus() or self.underMouse()
        indicator_size = 16
        top = (self.height() - indicator_size) / 2
        indicator = QRectF(0.5, top + 0.5, indicator_size - 1, indicator_size - 1)

        border_color = QColor("#338de6" if active or checked else "#cfd8e5")
        fill_color = QColor("#ffffff" if enabled else "#edf1f6")
        if not enabled:
            border_color = QColor("#d9e1eb")
        painter.setPen(QPen(border_color, 1.4))
        painter.setBrush(fill_color)
        painter.drawRoundedRect(indicator, 4, 4)

        if checked:
            check_color = QColor("#1879d9" if enabled else "#8fb6df")
            painter.setPen(
                QPen(
                    check_color,
                    2.2,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawLine(
                QPointF(indicator.left() + 3.8, indicator.top() + 8.2),
                QPointF(indicator.left() + 6.8, indicator.bottom() - 4.2),
            )
            painter.drawLine(
                QPointF(indicator.left() + 6.8, indicator.bottom() - 4.2),
                QPointF(indicator.right() - 3.2, indicator.top() + 4.4),
            )

        painter.setPen(QColor("#17283b" if enabled else "#8a96a8"))
        text_rect = self.rect().adjusted(indicator_size + 8, 0, 0, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"RIGOL DG1022Z Waveform Generator Control v{__version__}")
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
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)

        self.control_page = self._build_control_page()
        root.addWidget(self.control_page, 1)

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

        version_label = QLabel(f"v{__version__}", side)
        version_label.setObjectName("SidebarVersionLabel")
        version_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(version_label)
        return side

    def _nav_button(self, text: str, parent: QWidget) -> QPushButton:
        button = QPushButton(text, parent)
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.setFixedHeight(42)
        button.setCursor(Qt.PointingHandCursor)
        button.setProperty("fullText", text)
        return button

    def _build_connection_panel(self, parent: QWidget) -> QWidget:
        card = QFrame(parent)
        self.connection_panel = card
        card.setObjectName("ConnectionCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        title = QLabel("连接配置", card)
        title.setObjectName("ConnectionTitle")
        header.addWidget(title)
        header.addStretch(1)

        self.btn_add_address = QPushButton("+", card)
        self.btn_add_address.setObjectName("ConnectionIconButton")
        self.btn_add_address.setToolTip("新增 VISA 地址")
        self.btn_add_address.setFixedSize(30, 28)
        self.btn_remove_address = QPushButton("-", card)
        self.btn_remove_address.setObjectName("ConnectionIconButton")
        self.btn_remove_address.setToolTip("删除选中的 VISA 地址")
        self.btn_remove_address.setFixedSize(30, 28)
        self.btn_log = QPushButton("日志 / 指令", card)
        self.btn_log.setObjectName("ConnectionHeaderButton")
        self.btn_log.setFixedSize(88, 28)
        header.addWidget(self.btn_add_address)
        header.addWidget(self.btn_remove_address)
        header.addWidget(self.btn_log)
        card_layout.addLayout(header)

        grid_host = QWidget(card)
        grid_host.setObjectName("ConnectionGridHost")
        grid_host.setAttribute(Qt.WA_StyledBackground, True)
        grid_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.connection_grid_host = grid_host
        self.connection_address_grid = QGridLayout(grid_host)
        self.connection_address_grid.setContentsMargins(0, 0, 0, 0)
        self.connection_address_grid.setHorizontalSpacing(CONNECTION_GRID_GROUP_GAP)
        self.connection_address_grid.setVerticalSpacing(6)
        self.connection_address_grid.setColumnStretch(0, 1)
        self.connection_address_grid.setColumnStretch(1, 0)

        addresses = list(self._startup_config.visa_addresses) or [self._startup_config.visa_address]
        for address in addresses:
            self._add_connection_row(address)
        card_layout.addWidget(grid_host)
        self._update_remove_address_state()
        return card

    def _clear_connection_grid(self) -> None:
        for row in range(self.connection_address_grid.rowCount()):
            self.connection_address_grid.setRowMinimumHeight(row, 0)
        while self.connection_address_grid.count():
            self.connection_address_grid.takeAt(0)

    def _place_connection_action_row(self) -> None:
        return

    def _rebuild_connection_grid(self) -> None:
        self._clear_connection_grid()
        column_count = CONNECTION_GRID_COLUMNS
        for index, row_data in enumerate(self.connection_rows):
            grid_row = index // column_count
            grid_col = index % column_count
            row_data["grid_row"] = grid_row
            self.connection_address_grid.addWidget(row_data["host"], grid_row, grid_col)
            self.connection_address_grid.setRowMinimumHeight(grid_row, CONNECTION_CONTROL_HEIGHT)

    def _add_connection_row(self, address: str = "") -> dict[str, QWidget]:
        parent = self.connection_grid_host

        row_host = QWidget(parent)
        row_host.setObjectName("ConnectionRowHost")
        row_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row_layout = QHBoxLayout(row_host)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        address_box = CleanComboBox(row_host)
        address_box.setEditable(True)
        address_box.setFixedWidth(CONNECTION_ADDRESS_MAX_WIDTH)
        address_box.setFixedHeight(CONNECTION_CONTROL_HEIGHT)
        address_box.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        _prepare_combo_popup(address_box)
        if address_box.lineEdit() is not None:
            address_box.lineEdit().setPlaceholderText("输入 VISA 地址")
        self._populate_address_combo(address_box, address)

        device_label = ConnectionStatusLabel(row_host)
        device_label.setObjectName("ConnectionDeviceLabel")
        device_label.setFixedSize(CONNECTION_DEVICE_LABEL_WIDTH, CONNECTION_CONTROL_HEIGHT)
        device_label.setAlignment(Qt.AlignCenter)

        row_label = ConnectionStatusLabel(row_host)
        row_label.setObjectName("ConnectionRowLabel")
        row_label.setFixedSize(CONNECTION_ROW_LABEL_WIDTH, CONNECTION_CONTROL_HEIGHT)
        row_label.setAlignment(Qt.AlignCenter)

        connect_button = QPushButton("连接", row_host)
        connect_button.setObjectName("ConnectionButton")
        connect_button.setFixedSize(CONNECTION_BUTTON_WIDTH, CONNECTION_CONTROL_HEIGHT)

        channel_buttons: dict[int, ConnectionChannelCard] = {}
        for channel in (1, 2):
            channel_button = ConnectionChannelCard(channel, row_host)
            channel_button.setToolTip(f"切换到此信号发生器 CH{channel}")
            channel_buttons[channel] = channel_button

        row_layout.addWidget(device_label)
        row_layout.addWidget(row_label)
        row_layout.addWidget(address_box)
        row_layout.addWidget(connect_button)
        row_layout.addWidget(channel_buttons[1], 1)
        row_layout.addWidget(channel_buttons[2], 1)

        row_data: dict[str, QWidget] = {
            "grid_row": len(self.connection_rows),
            "host": row_host,
            "device_label": device_label,
            "row_label": row_label,
            "address": address_box,
            "button": connect_button,
            "channel_1": channel_buttons[1],
            "channel_2": channel_buttons[2],
        }
        row_data["_status_display"] = "未连接"
        row_data["_connected"] = False
        row_data["_failed"] = False
        self.connection_rows.append(row_data)
        self.active_connection_row = row_data
        if len(self.connection_rows) == 1:
            self.address = address_box

        address_box.currentTextChanged.connect(self._save_config)
        address_box.currentTextChanged.connect(lambda _text="", r=row_data: self._set_active_connection_row(r))
        address_box.currentTextChanged.connect(lambda _text="", r=row_data: self._update_connection_row_action(r))
        device_label.clicked.connect(lambda r=row_data: self._activate_connection_row(r))
        row_label.clicked.connect(lambda r=row_data: self._activate_connection_row(r))
        for _channel, channel_button in channel_buttons.items():
            channel_button.selected.connect(
                lambda ch, r=row_data: self._activate_connection_channel(r, ch)
            )
        connect_button.clicked.connect(lambda _checked=False, r=row_data: self._toggle_connection(r))
        self._rebuild_connection_grid()
        self._renumber_connection_row_labels()
        self._set_connection_row_state(row_data, False, "未连接")
        self._update_remove_address_state()
        return row_data

    def _set_active_connection_row(self, row: dict[str, QWidget]) -> None:
        if row in self.connection_rows and row is not self.active_connection_row:
            self.active_connection_row = row
            self._renumber_connection_row_labels()

    def _activate_connection_row(self, row: dict[str, QWidget]) -> None:
        self._set_active_connection_row(row)
        address = self._connection_row_address(row)
        if address in self.clients:
            self._select_device(address)
        else:
            self._renumber_connection_row_labels()

    def _activate_connection_channel(self, row: dict[str, QWidget], channel: int) -> None:
        self._set_active_connection_row(row)
        address = self._connection_row_address(row)
        if address not in self.clients:
            self._update_connection_channel_buttons()
            return
        if address != self.active_device_key:
            self._select_device(address, navigate=False)
        if channel != self.active_channel:
            self._select_channel(channel)
        else:
            self._update_connection_channel_buttons()

    def _focused_connection_row(self) -> dict[str, QWidget] | None:
        focus = QApplication.focusWidget()
        if focus is None:
            return None
        for row in self.connection_rows:
            for key in (
                "host",
                "device_label",
                "address",
                "row_label",
                "button",
                "channel_1",
                "channel_2",
            ):
                widget = row.get(key)
                if isinstance(widget, QWidget) and (
                    focus is widget or widget.isAncestorOf(focus)
                ):
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
        for key in ("host",):
            widget = row.get(key)
            if widget is not None:
                widget.deleteLater()
        if address:
            self.device_settings.pop(address, None)
            self.device_active_channels.pop(address, None)
            self.device_ui_settings.pop(address, None)
        first = self.connection_rows[0]
        self.address = first["address"]
        self.active_connection_row = self.connection_rows[-1]
        self._rebuild_connection_grid()
        self._renumber_connection_row_labels()
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

    def _connection_row_device_name(self, row: dict[str, QWidget]) -> str:
        try:
            index = self.connection_rows.index(row) + 1
        except ValueError:
            return "设备 1"
        return f"设备 {index}"

    def _update_connection_row_label(self, row: dict[str, QWidget]) -> None:
        label = row.get("row_label")
        if not isinstance(label, QLabel):
            return
        device_label = row.get("device_label")
        if isinstance(device_label, QLabel):
            device_label.setText(self._connection_row_device_name(row))
            device_label.setToolTip(
                "点击切换到此信号发生器" if row.get("_connected", False) else "点击选中此设备行"
            )
        display = str(row.get("_status_display", "未连接"))
        address = self._connection_row_address(row)
        connected = bool(row.get("_connected", False))
        active = connected and bool(address and address == self.active_device_key)
        label.setText("● 当前" if connected and active else f"● {display}")
        label.setProperty("connected", connected)
        label.setProperty("failed", bool(row.get("_failed", False)))
        label.setProperty("active", active)
        _repolish(label)

    def _renumber_connection_row_labels(self) -> None:
        for row in self.connection_rows:
            self._update_connection_row_label(row)

    def _set_connection_row_state(
        self,
        row: dict[str, QWidget],
        connected: bool,
        text: str,
        *,
        failed: bool = False,
    ) -> None:
        display = "已连接" if connected else text
        row["_status_display"] = display
        row["_connected"] = connected
        row["_failed"] = failed
        self._update_connection_row_label(row)
        button = row.get("button")
        address = row.get("address")
        label = row.get("row_label")
        if isinstance(label, QLabel):
            if connected and self._connection_row_address(row) == self.active_device_key:
                label.setToolTip("当前控制的信号发生器")
            else:
                label.setToolTip("点击切换到此信号发生器" if connected else text)
        if isinstance(button, QPushButton):
            button.setText("断开" if connected else "连接")
            button.setProperty("connected", connected)
            _repolish(button)
        if isinstance(address, QComboBox):
            address.setEnabled(not connected)
        self._sync_connection_row_channels(row)

    def _sync_connection_row_channels(self, row: dict[str, QWidget]) -> None:
        address = self._connection_row_address(row)
        connected = bool(address and address in self.clients)
        device_settings = self.device_settings.get(address) or (
            self.channel_settings if address == self.active_device_key else {}
        )
        for channel in (1, 2):
            button = row.get(f"channel_{channel}")
            if not isinstance(button, ConnectionChannelCard):
                continue
            settings = device_settings.get(channel) if isinstance(device_settings, dict) else None
            output_on = bool(settings.output_enabled) if isinstance(settings, ChannelSettings) else False
            active = connected and address == self.active_device_key and channel == self.active_channel
            button.set_state(active=active, connected=connected, output_on=output_on)

    def _update_connection_channel_buttons(self) -> None:
        for row in self.connection_rows:
            self._sync_connection_row_channels(row)

    def _update_connection_row_action(self, row: dict[str, QWidget]) -> None:
        address = self._connection_row_address(row)
        self._set_connection_row_state(row, address in self.clients, "已连接" if address in self.clients else "未连接")

    def _update_connection_rows(self) -> None:
        for row in self.connection_rows:
            self._update_connection_row_action(row)
        self._update_connection_channel_buttons()

    def _build_control_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("ControlPage")
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        work_column = QWidget(page)
        work_column.setObjectName("WorkColumn")
        work_column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        work_layout = QVBoxLayout(work_column)
        work_layout.setContentsMargins(0, 0, 0, 0)
        work_layout.setSpacing(12)
        work_layout.addWidget(self._build_connection_panel(work_column))
        work_layout.addWidget(self._build_center_panel(), 1)

        layout.addWidget(work_column, 1)
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
        layout.setSpacing(16)

        title = QLabel("波形工作区")
        title.setObjectName("MainTitle")
        title.setFixedHeight(36)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(title)

        toolbar = QFrame(panel)
        toolbar.setObjectName("WorkToolbar")
        toolbar.setMinimumHeight(76)
        toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(14, 10, 14, 10)
        toolbar_layout.setSpacing(12)

        left = QWidget(toolbar)
        left.setObjectName("WorkToolbarLeft")
        left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        left_layout = QGridLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setHorizontalSpacing(WORK_TOOLBAR_ROW_SPACING)
        left_layout.setVerticalSpacing(8)
        left_layout.setColumnMinimumWidth(0, WORK_TOOLBAR_LABEL_WIDTH)
        left_layout.setColumnStretch(0, 0)
        left_layout.setColumnStretch(1, 1)
        left_layout.setRowMinimumHeight(0, WORK_TOOLBAR_ROW_HEIGHT)

        def _strip_row_label(text: str) -> QLabel:
            label = QLabel(text, left)
            label.setObjectName("StripRowLabel")
            label.setFixedSize(WORK_TOOLBAR_LABEL_WIDTH, WORK_TOOLBAR_ROW_HEIGHT)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            return label

        action_label = _strip_row_label("操作")
        self.channel_cards = {}

        action_row_host = QWidget(left)
        action_row_host.setObjectName("WorkToolbarActionRow")
        action_row_layout = QHBoxLayout(action_row_host)
        action_row_layout.setContentsMargins(0, 0, 0, 0)
        action_row_layout.setSpacing(WORK_TOOLBAR_ROW_SPACING)
        self.btn_apply = QPushButton("应用当前通道", action_row_host)
        self.btn_apply.setObjectName("PrimaryButton")
        self.btn_apply_all = QPushButton("应用双通道", action_row_host)
        self.btn_output_toggle = QPushButton("输出 OFF", action_row_host)
        self.btn_output_toggle.setObjectName("OutputToggleButton")
        self.btn_fire = QPushButton("软件触发 Burst", action_row_host)
        for button in (
            self.btn_apply,
            self.btn_apply_all,
            self.btn_output_toggle,
            self.btn_fire,
        ):
            button.setFixedHeight(WORK_TOOLBAR_CONTROL_HEIGHT)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            action_row_layout.addWidget(button, 1)

        left_layout.addWidget(action_label, 0, 0, Qt.AlignRight | Qt.AlignVCenter)
        left_layout.addWidget(action_row_host, 0, 1)

        toolbar_layout.addWidget(left, 1)
        layout.addWidget(toolbar)

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
        panel.setMinimumWidth(RIGHT_PANEL_MIN_WIDTH)
        panel.setMaximumWidth(RIGHT_PANEL_MAX_WIDTH)
        panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(
            RIGHT_PANEL_MARGIN_LEFT,
            RIGHT_PANEL_MARGIN_TOP,
            RIGHT_PANEL_MARGIN_RIGHT,
            RIGHT_PANEL_MARGIN_BOTTOM,
        )
        layout.setSpacing(10)

        title = QLabel("参数设置")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        scroll = QScrollArea(panel)
        scroll.setObjectName("ParameterScroll")
        self.parameter_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll_body = QWidget(scroll)
        scroll_body.setObjectName("ParameterScrollBody")
        scroll_body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        parameter_layout = QVBoxLayout(scroll_body)
        parameter_layout.setContentsMargins(0, 0, 0, 0)
        parameter_layout.setSpacing(10)
        parameter_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(scroll_body)
        layout.addWidget(scroll, 1)

        self.timing_group = QGroupBox()
        timing_form = _form_layout(self.timing_group)
        timing_form.addRow(_section_title("频率 / 周期"))
        self.frequency_mode = CleanComboBox()
        self.frequency_mode.addItem("频率", "frequency")
        self.frequency_mode.addItem("周期", "period")
        self.frequency_unit = CleanComboBox()
        self.frequency_unit.setObjectName("UnitCombo")
        self.frequency_unit.addItem("Hz", "Hz")
        self.frequency_unit.addItem("kHz", "kHz")
        self.frequency_unit.addItem("MHz", "MHz")
        self.frequency_unit.setFixedWidth(UNIT_SLOT_WIDTH)
        self.period_unit = CleanComboBox()
        self.period_unit.setObjectName("UnitCombo")
        self.period_unit.addItem("ms", "ms")
        self.period_unit.addItem("s", "s")
        self.period_unit.setFixedWidth(UNIT_SLOT_WIDTH)
        self._frequency_display_unit = "kHz"
        self._period_display_unit = "ms"
        self.frequency_hz = _double_spin(1e-9, 25_000.0, 1.0, 6, 0.1)
        self.period_s = _double_spin(0.00004, 1_000_000_000.0, 1.0, 3, 0.1)
        self.phase_deg = _double_spin(0.0, 360.0, 0.0, 3, 1.0)
        self.frequency_hz_editor = _spin_editor(self.frequency_hz, unit=self.frequency_unit)
        self.period_s_editor = _spin_editor(self.period_s, unit=self.period_unit)
        self.phase_deg_editor = _spin_editor(self.phase_deg, suffix="deg")
        timing_form.addRow(_param_row_label("输入方式"), self.frequency_mode)
        timing_form.addRow(_param_row_label("频率"), self.frequency_hz_editor)
        timing_form.addRow(_param_row_label("周期"), self.period_s_editor)
        timing_form.addRow(_param_row_label("相位"), self.phase_deg_editor)
        parameter_layout.addWidget(self.timing_group)

        self.level_group = QGroupBox()
        level_form = _form_layout(self.level_group)
        level_form.addRow(_section_title("电平"))
        self.level_mode = CleanComboBox()
        self.level_mode.addItem("幅度 + 偏置", "amplitude_offset")
        self.level_mode.addItem("高电平 + 低电平", "high_low")
        self.load = CleanComboBox(self.level_group)
        self.load.addItem("负载 High-Z", "INF")
        self.load.addItem("负载 50 ohm", "50")
        self.load.setFixedHeight(34)
        self.amplitude_vpp = _double_spin(0.001, 20.0, 2.0, 2, 0.1)
        self.offset_v = _double_spin(-10.0, 10.0, 0.0, 2, 0.1)
        self.level_voltage_unit = CleanComboBox()
        self.level_voltage_unit.setObjectName("UnitCombo")
        self.level_voltage_unit.addItem("V", "V")
        self.level_voltage_unit.addItem("mV", "mV")
        self.level_voltage_unit.setFixedWidth(UNIT_SLOT_WIDTH)
        self.low_level_voltage_unit = CleanComboBox()
        self.low_level_voltage_unit.setObjectName("UnitCombo")
        self.low_level_voltage_unit.addItem("V", "V")
        self.low_level_voltage_unit.addItem("mV", "mV")
        self.low_level_voltage_unit.setFixedWidth(UNIT_SLOT_WIDTH)
        self._level_voltage_display_unit = "V"

        self.high_v = _double_spin(-10.0, 10.0, 1.0, 2, 0.1)
        self.low_v = _double_spin(-10.0, 10.0, -1.0, 2, 0.1)
        self.amplitude_vpp_editor = _spin_editor(self.amplitude_vpp, suffix="Vpp")
        self.offset_v_editor = _spin_editor(self.offset_v, suffix="V")
        self.high_v_editor = _spin_editor(self.high_v, unit=self.level_voltage_unit)
        self.low_v_editor = _spin_editor(self.low_v, unit=self.low_level_voltage_unit)
        level_form.addRow(_param_row_label("模式"), self.level_mode)
        level_form.addRow(_param_row_label("负载"), self.load)
        level_form.addRow(_param_row_label("幅度"), self.amplitude_vpp_editor)
        level_form.addRow(_param_row_label("偏置"), self.offset_v_editor)
        level_form.addRow(_param_row_label("高电平"), self.high_v_editor)
        level_form.addRow(_param_row_label("低电平"), self.low_v_editor)
        parameter_layout.addWidget(self.level_group)

        self.shape_group = QGroupBox()
        shape_form = _form_layout(self.shape_group)
        shape_form.addRow(_section_title("波形专属参数"))
        self.duty_percent = _double_spin(0.001, 99.999, 50.0, 2, 1.0)
        self.pulse_width_s = _double_spin(16e-9, 999_999.0, 0.0001, 9, 0.00001)
        self.ramp_symmetry = _double_spin(0.0, 100.0, 50.0, 3, 1.0)
        self.duty_percent_editor = _spin_editor(self.duty_percent, inline_suffix=" %")
        self.pulse_width_s_editor = _spin_editor(self.pulse_width_s, suffix="s")
        self.ramp_symmetry_editor = _spin_editor(self.ramp_symmetry, inline_suffix=" %")
        shape_form.addRow(_param_row_label("占空比"), self.duty_percent_editor)
        shape_form.addRow(_param_row_label("脉宽"), self.pulse_width_s_editor)
        shape_form.addRow(_param_row_label("斜波对称"), self.ramp_symmetry_editor)
        parameter_layout.addWidget(self.shape_group)

        self.burst_group = QGroupBox()
        burst_layout = QVBoxLayout(self.burst_group)
        burst_layout.setContentsMargins(PARAM_FORM_MARGIN_H, 8, PARAM_FORM_MARGIN_H, 8)
        burst_layout.setSpacing(6)
        burst_layout.addWidget(_section_title("Burst"))
        burst_head = QHBoxLayout()
        burst_head.setContentsMargins(0, 0, 0, 0)
        burst_head.setSpacing(0)
        self.burst_enabled = CheckMarkCheckBox("启用 Burst")
        self.burst_status = QLabel("OFF")
        self.burst_status.setObjectName("StatePill")
        self.burst_status.setAlignment(Qt.AlignCenter)
        self.burst_status.setFixedSize(50, 22)

        burst_head.addWidget(self.burst_enabled)
        burst_head.addStretch(1)
        burst_head.addWidget(self.burst_status)
        burst_layout.addLayout(burst_head)
        self.burst_mode = CleanComboBox()
        self.burst_mode.addItem("N 周期", "TRIG")
        self.burst_mode.addItem("无限", "INF")
        self.burst_mode.addItem("门控", "GAT")
        self.burst_details = QFrame()
        self.burst_details.setObjectName("InlineDetails")
        burst_details_form = _form_layout(self.burst_details)
        burst_details_form.setContentsMargins(0, 0, 0, 0)
        self.burst_details.setFixedWidth(
            PARAM_CARD_WIDTH - PARAM_FORM_MARGIN_H * 2
        )
        self.burst_trigger_source = CleanComboBox()
        self.burst_trigger_source.addItem("手动/软件", "MAN")
        self.burst_trigger_source.addItem("内部", "INT")
        self.burst_trigger_source.addItem("外部", "EXT")
        self.burst_cycles = FocusWheelSpinBox()
        self.burst_cycles.setRange(1, 1_000_000)
        self.burst_cycles.setValue(1)
        self.burst_internal_period_unit = CleanComboBox()
        self.burst_internal_period_unit.setObjectName("UnitCombo")
        self.burst_internal_period_unit.addItem("ms", "ms")
        self.burst_internal_period_unit.addItem("s", "s")
        self.burst_internal_period_unit.setFixedWidth(UNIT_SLOT_WIDTH)
        self._burst_internal_period_display_unit = self._period_display_unit
        self.burst_internal_period = _double_spin(0.001, 1_000_000_000.0, 10.0, 3, 0.1)
        self.burst_phase = _double_spin(0.0, 360.0, 0.0, 3, 1.0)
        self.burst_delay = _double_spin(0.0, 1e6, 0.0, 3, 0.001)
        self.burst_idle_mode = CleanComboBox()
        self.burst_idle_mode.addItem("首点", "FPT")
        self.burst_idle_mode.addItem("顶部", "TOP")
        self.burst_idle_mode.addItem("中心", "CENTER")
        self.burst_idle_mode.addItem("底部", "BOTTOM")
        self.burst_idle_mode.addItem("自定义", "USER")
        self.burst_idle_point = FocusWheelSpinBox()
        self.burst_idle_point.setRange(0, 16383)
        self.burst_idle_point.setValue(0)
        self.burst_idle_point.setToolTip("自定义波形采样点号 (0–16383)")
        self.burst_gate_polarity = CleanComboBox()
        self.burst_gate_polarity.addItem("正门控", "NORM")
        self.burst_gate_polarity.addItem("反门控", "INV")
        self.burst_trigger_slope = CleanComboBox()
        self.burst_trigger_slope.addItem("上升沿", "POS")
        self.burst_trigger_slope.addItem("下降沿", "NEG")
        self.burst_cycles_editor = _spin_editor(self.burst_cycles)
        self.burst_internal_period_editor = _spin_editor(
            self.burst_internal_period, unit=self.burst_internal_period_unit
        )
        self.burst_phase_editor = _spin_editor(self.burst_phase, suffix="deg")
        self.burst_idle_point_editor = _spin_editor(self.burst_idle_point)
        self.burst_idle_point_editor.setToolTip("自定义波形采样点号 (0–16383)")
        self.burst_delay_editor = _spin_editor(self.burst_delay, suffix="s")
        self.burst_idle_row = QWidget()
        self.burst_idle_row.setObjectName("BurstIdleRow")
        _clear_widget_background(self.burst_idle_row)
        burst_idle_layout = QVBoxLayout(self.burst_idle_row)
        burst_idle_layout.setContentsMargins(0, 0, 0, 0)
        burst_idle_layout.setSpacing(4)
        burst_idle_layout.addWidget(self.burst_idle_mode)
        self.burst_idle_point_row = QWidget()
        self.burst_idle_point_row.setObjectName("BurstIdlePointRow")
        _clear_widget_background(self.burst_idle_point_row)
        burst_idle_point_layout = QHBoxLayout(self.burst_idle_point_row)
        burst_idle_point_layout.setContentsMargins(0, 0, 0, 0)
        burst_idle_point_layout.setSpacing(6)
        burst_idle_point_label = QLabel("点号")
        burst_idle_point_label.setObjectName("ParamSubLabel")
        burst_idle_point_label.setFixedWidth(40)
        burst_idle_point_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        burst_idle_point_layout.addWidget(burst_idle_point_label)
        burst_idle_point_layout.addWidget(self.burst_idle_point_editor)
        burst_idle_layout.addWidget(self.burst_idle_point_row)
        self.burst_idle_point_row.setVisible(False)
        burst_details_form.addRow(_param_row_label("类型"), self.burst_mode)
        burst_details_form.addRow(_param_row_label("触发源"), self.burst_trigger_source)
        burst_details_form.addRow(_param_row_label("周期数"), self.burst_cycles_editor)
        burst_details_form.addRow(_param_row_label("内部周期"), self.burst_internal_period_editor)
        burst_details_form.addRow(_param_row_label("相位"), self.burst_phase_editor)
        burst_details_form.addRow(_param_row_label("空闲电平"), self.burst_idle_row)
        burst_details_form.addRow(_param_row_label("延时"), self.burst_delay_editor)
        burst_details_form.addRow(_param_row_label("门控极性"), self.burst_gate_polarity)
        burst_details_form.addRow(_param_row_label("外触发沿"), self.burst_trigger_slope)
        burst_layout.addWidget(self.burst_details)
        parameter_layout.addWidget(self.burst_group)
        parameter_layout.addStretch(1)
        self._finalize_parameter_panel()
        return panel

    def _connect_signals(self) -> None:
        self.btn_remove_address.clicked.connect(lambda: self._remove_connection_row())
        self.btn_add_address.clicked.connect(lambda: self._add_connection_row(""))
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

        self.load.currentIndexChanged.connect(self._on_load_changed)
        self.level_mode.currentIndexChanged.connect(self._on_level_mode_changed)
        self.frequency_mode.currentIndexChanged.connect(self._on_frequency_mode_changed)
        for widget in (
            self.burst_mode,
            self.burst_trigger_source,
            self.burst_gate_polarity,
            self.burst_trigger_slope,
            self.burst_idle_mode,
        ):
            widget.currentIndexChanged.connect(self._on_form_changed)
        self.frequency_unit.currentIndexChanged.connect(self._on_frequency_unit_changed)
        self.period_unit.currentIndexChanged.connect(self._on_period_unit_changed)
        self.burst_internal_period_unit.currentIndexChanged.connect(
            self._on_burst_internal_period_unit_changed
        )
        self.level_voltage_unit.currentIndexChanged.connect(self._on_level_voltage_unit_changed)
        self.low_level_voltage_unit.currentIndexChanged.connect(self._on_level_voltage_unit_changed)
        self.burst_enabled.toggled.connect(self._on_burst_enabled_toggled)
        self.frequency_hz.valueChanged.connect(self._on_frequency_changed)
        self.period_s.valueChanged.connect(self._on_period_changed)
        self.duty_percent.valueChanged.connect(self._on_duty_changed)
        self.pulse_width_s.valueChanged.connect(self._on_pulse_width_changed)
        for spin in (
            self.phase_deg,
            self.ramp_symmetry,
            self.amplitude_vpp,
            self.offset_v,
            self.high_v,
            self.low_v,
            self.burst_cycles,
            self.burst_internal_period,
            self.burst_phase,
            self.burst_idle_point,
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
        if hasattr(self, "pages") and hasattr(self, "connection_page"):
            self.pages.setCurrentWidget(self.connection_page)
        if hasattr(self, "nav_connect"):
            self._set_nav_checked(self.nav_connect)

    def _toggle_sidebar(self) -> None:
        self._set_sidebar_collapsed(not self.sidebar_collapsed)

    def _set_sidebar_collapsed(self, collapsed: bool) -> None:
        if not hasattr(self, "sidebar"):
            return
        self.sidebar_collapsed = collapsed
        self.sidebar.setFixedWidth(68 if collapsed else 112)
        self.sidebar_toggle.setToolTip("展开导航栏" if collapsed else "收缩导航栏")
        self.nav_connect.setText("连接" if collapsed else "设备连接")
        self.btn_log.setText("日志" if collapsed else "日志 / 指令")
        for address, button in self.device_nav_buttons.items():
            button.setText(self._device_nav_text(address, collapsed))

    def _set_nav_checked(self, active_button: QPushButton | None) -> None:
        if not hasattr(self, "nav_connect"):
            return
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

        if address in self.device_nav_buttons:
            self.device_nav_buttons[address].setProperty("fullText", label)
            self.device_nav_buttons[address].setText(self._device_nav_text(address, self.sidebar_collapsed))

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

    def _select_device(self, address: str, *, navigate: bool = True) -> None:
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
        self._set_active_connection_row(row)
        self._set_connection_row_state(row, True, "已连接")
        if self.active_channel not in self.channel_settings:
            self.active_channel = 1
        self._load_settings_to_form(self.channel_settings[self.active_channel])
        if navigate and hasattr(self, "pages"):
            self.pages.setCurrentWidget(self.control_page)
            self._set_nav_checked(self.device_nav_buttons.get(address))
        elif hasattr(self, "nav_connect"):
            self._set_nav_checked(self.nav_connect)
        idn = self.device_idns.get(address, address)
        self._set_connected(True, idn)
        self._save_config()
        if navigate:
            self._log(f"切换到 {self.device_labels.get(address, '设备')}: {address}")

    def _select_channel(self, channel: int) -> None:
        if channel == self.active_channel:
            self._update_connection_channel_buttons()
            return
        self._save_active_settings()
        self.active_channel = channel
        if self.active_device_key:
            self.device_active_channels[self.active_device_key] = channel
        self._load_settings_to_form(self.channel_settings[channel])
        self._update_connection_channel_buttons()
        self._save_config()

    def _set_waveform(self, waveform: str) -> None:
        if self._loading_form:
            return
        if waveform in self.wave_buttons:
            self.wave_buttons[waveform].setChecked(True)
        self._sync_pulse_width_from_duty()
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
        burst_actual_s = self._period_display_to_seconds(
            self.burst_internal_period.value(),
            self._burst_internal_period_display_unit,
        )
        self._period_display_unit = new_unit
        self._configure_period_spin(new_unit, actual_s)
        self._burst_internal_period_display_unit = new_unit
        _set_combo_data(self.burst_internal_period_unit, new_unit, silent=True)
        self._configure_burst_internal_period_spin(new_unit, burst_actual_s)
        if not self._loading_form:
            self._on_form_changed()

    def _on_burst_internal_period_unit_changed(self) -> None:
        old_unit = self._burst_internal_period_display_unit
        new_unit = str(self.burst_internal_period_unit.currentData() or "ms")
        burst_actual_s = self._period_display_to_seconds(
            self.burst_internal_period.value(), old_unit
        )
        period_actual_s = self._period_display_to_seconds(
            self.period_s.value(), self._period_display_unit
        )
        self._burst_internal_period_display_unit = new_unit
        self._configure_burst_internal_period_spin(new_unit, burst_actual_s)
        self._period_display_unit = new_unit
        _set_combo_data(self.period_unit, new_unit, silent=True)
        self._configure_period_spin(new_unit, period_actual_s)
        if not self._loading_form:
            self._on_form_changed()

    def _on_level_voltage_unit_changed(self) -> None:
        old_unit = self._level_voltage_display_unit
        source = self.sender()
        if isinstance(source, QComboBox):
            new_unit = str(source.currentData() or "V")
        else:
            new_unit = str(self.level_voltage_unit.currentData() or "V")
        high_v = self._level_voltage_display_to_volts(self.high_v.value(), old_unit)
        low_v = self._level_voltage_display_to_volts(self.low_v.value(), old_unit)
        self._level_voltage_display_unit = new_unit
        self._sync_level_voltage_unit_controls(new_unit)
        self._configure_level_voltage_spin(new_unit, high_v, self.high_v)
        self._configure_level_voltage_spin(new_unit, low_v, self.low_v)
        if not self._loading_form:
            self._on_form_changed()

    def _on_level_mode_changed(self) -> None:
        if self._loading_form:
            return
        mode = self.level_mode.currentData()
        if mode == "high_low":
            high_v, low_v = high_low_from_amplitude_offset(
                self.amplitude_vpp.value(),
                self.offset_v.value(),
            )
            self._set_level_voltage_spin_value(self.high_v, high_v)
            self._set_level_voltage_spin_value(self.low_v, low_v)
        else:
            high_v = self._level_voltage_display_to_volts(self.high_v.value())
            low_v = self._level_voltage_display_to_volts(self.low_v.value())
            amplitude_vpp, offset_v = amplitude_offset_from_high_low(high_v, low_v)
            _set_spin_value_silent(self.amplitude_vpp, amplitude_vpp)
            _set_spin_value_silent(self.offset_v, offset_v)
        self._on_form_changed()

    def _on_frequency_mode_changed(self) -> None:
        if self._loading_form:
            return
        mode = self.frequency_mode.currentData()
        if mode == "period":
            self._sync_frequency_from_period()
        else:
            self._sync_period_from_frequency()
        self._sync_pulse_width_from_duty()
        self._on_form_changed()

    def _on_frequency_changed(self) -> None:
        if self._loading_form:
            return
        self._sync_period_from_frequency()
        self._sync_pulse_width_from_duty()
        self._on_form_changed()

    def _on_period_changed(self) -> None:
        if self._loading_form:
            return
        self._sync_frequency_from_period()
        self._sync_pulse_width_from_duty()
        self._on_form_changed()

    def _on_duty_changed(self) -> None:
        if self._loading_form:
            return
        self._sync_pulse_width_from_duty()
        self._on_form_changed()

    def _on_pulse_width_changed(self) -> None:
        if self._loading_form:
            return
        self._sync_duty_from_pulse_width()
        self._on_form_changed()

    def _on_burst_enabled_toggled(self, enabled: bool) -> None:
        if self._loading_form:
            return
        previous_enabled = self.channel_settings[self.active_channel].burst.enabled
        if self.burst_enabled.isChecked() != enabled:
            return
        if self.active_device_key not in self.clients:
            self._on_form_changed()
            return
        try:
            command = self.client.set_burst_enabled(self.active_channel, enabled)
        except Exception as exc:
            self.burst_enabled.blockSignals(True)
            self.burst_enabled.setChecked(previous_enabled)
            self.burst_enabled.blockSignals(False)
            self._apply_form_state_rules()
            self._refresh_view()
            self._show_error("设置 Burst 失败", exc)
            return
        self._on_form_changed()
        self._log(f"CH{self.active_channel} Burst {'开启' if enabled else '关闭'}: {command}")

    def _on_load_changed(self) -> None:
        if self._loading_form:
            return
        new_load = self.load.currentData()
        if new_load not in ("50", "INF"):
            self._on_form_changed()
            return
        previous_load: LoadMode = self.channel_settings[self.active_channel].load
        if previous_load == new_load:
            self._on_form_changed()
            return

        waveform = self._selected_waveform()
        level = level_ui_state(waveform, self.level_mode.currentData())

        def _scale_spin(spin: QDoubleSpinBox) -> None:
            scaled = scale_voltage_for_load_change(spin.value(), previous_load, new_load)
            spin.blockSignals(True)
            spin.setValue(_clamp(scaled, spin.minimum(), spin.maximum()))
            spin.blockSignals(False)

        if level.high:
            _scale_spin(self.high_v)
        if level.low:
            _scale_spin(self.low_v)
        if level.amplitude:
            _scale_spin(self.amplitude_vpp)
        if level.offset:
            _scale_spin(self.offset_v)

        self._on_form_changed()

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
            channel_ui = self.device_ui_settings.setdefault(
                self.active_device_key,
                dict(self.default_channel_ui),
            )
            channel_ui[self.active_channel] = ChannelUiConfig(
                frequency_unit=self._frequency_display_unit,
                period_unit=self._period_display_unit,
                level_voltage_unit=self._level_voltage_display_unit,
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

    def _level_voltage_display_to_volts(self, value: float, unit: str | None = None) -> float:
        factors = {"V": 1.0, "mV": 0.001}
        return float(value) * factors.get(unit or self._level_voltage_display_unit, 1.0)

    def _current_period_seconds(self) -> float:
        if self.frequency_mode.currentData() == "frequency":
            return period_from_frequency(self._frequency_display_to_hz(self.frequency_hz.value()))
        return self._period_display_to_seconds(self.period_s.value())

    def _set_frequency_spin_actual(self, actual_hz: float) -> None:
        self._configure_frequency_spin(self._frequency_display_unit, actual_hz)

    def _set_period_spin_actual(self, actual_s: float) -> None:
        self._configure_period_spin(self._period_display_unit, actual_s)

    def _sync_period_from_frequency(self) -> None:
        frequency_hz = self._frequency_display_to_hz(self.frequency_hz.value())
        self._set_period_spin_actual(period_from_frequency(frequency_hz))

    def _sync_frequency_from_period(self) -> None:
        period_s = self._period_display_to_seconds(self.period_s.value())
        self._set_frequency_spin_actual(frequency_from_period(period_s))

    def _sync_pulse_width_from_duty(self) -> None:
        if self._selected_waveform() != "PULS":
            return
        pulse_width_s = pulse_width_from_duty(
            self._current_period_seconds(),
            self.duty_percent.value(),
        )
        _set_spin_value_silent(self.pulse_width_s, pulse_width_s)

    def _sync_duty_from_pulse_width(self) -> None:
        if self._selected_waveform() != "PULS":
            return
        period_s = self._current_period_seconds()
        duty_percent = duty_from_pulse_width(period_s, self.pulse_width_s.value())
        _set_spin_value_silent(self.duty_percent, duty_percent)
        pulse_width_s = pulse_width_from_duty(period_s, duty_percent)
        _set_spin_value_silent(self.pulse_width_s, pulse_width_s)

    def _configure_frequency_spin(self, unit: str, actual_hz: float) -> None:
        factors = {"Hz": 1.0, "kHz": 1_000.0, "MHz": 1_000_000.0}
        steps = {"Hz": 1.0, "kHz": 0.1, "MHz": 0.001}
        factor = factors.get(unit, 1_000.0)
        value = _clamp(actual_hz / factor, 1e-6 / factor, 25e6 / factor)
        self.frequency_hz.blockSignals(True)
        self.frequency_hz.setDecimals(3)
        self.frequency_hz.setRange(1e-6 / factor, 25e6 / factor)
        self.frequency_hz.setSingleStep(steps.get(unit, 0.1))
        self.frequency_hz.setValue(value)
        self.frequency_hz.blockSignals(False)

    def _configure_period_spin(self, unit: str, actual_s: float) -> None:
        factors = {"ms": 0.001, "s": 1.0}
        decimals = {"ms": 3, "s": 3}
        steps = {"ms": 0.1, "s": 0.001}
        factor = factors.get(unit, 0.001)
        value = _clamp(actual_s / factor, 4e-8 / factor, 1e6 / factor)
        self.period_s.blockSignals(True)
        self.period_s.setDecimals(decimals.get(unit, 3))
        self.period_s.setRange(4e-8 / factor, 1e6 / factor)
        self.period_s.setSingleStep(steps.get(unit, 0.1))
        self.period_s.setValue(value)
        self.period_s.blockSignals(False)

    def _configure_burst_internal_period_spin(self, unit: str, actual_s: float) -> None:
        factors = {"ms": 0.001, "s": 1.0}
        steps = {"ms": 0.1, "s": 0.001}
        factor = factors.get(unit, 0.001)
        value = _clamp(actual_s / factor, 1e-6 / factor, 1e6 / factor)
        self.burst_internal_period.blockSignals(True)
        self.burst_internal_period.setDecimals(3)
        self.burst_internal_period.setRange(1e-6 / factor, 1e6 / factor)
        self.burst_internal_period.setSingleStep(steps.get(unit, 0.1))
        self.burst_internal_period.setValue(value)
        self.burst_internal_period.blockSignals(False)

    def _configure_level_voltage_spin(
        self,
        unit: str,
        actual_v: float,
        spin: QDoubleSpinBox,
    ) -> None:
        if unit == "mV":
            factor = 0.001
            decimals = 2
            step = 1.0
        else:
            factor = 1.0
            decimals = 2
            step = 0.1
        minimum_v = -10.0
        maximum_v = 10.0
        value = _clamp(actual_v / factor, minimum_v / factor, maximum_v / factor)
        spin.blockSignals(True)
        spin.setDecimals(decimals)
        spin.setRange(minimum_v / factor, maximum_v / factor)
        spin.setSingleStep(step)
        spin.setValue(value)
        spin.blockSignals(False)

    def _set_level_voltage_spin_value(self, spin: QDoubleSpinBox, actual_v: float) -> None:
        factor = 0.001 if self._level_voltage_display_unit == "mV" else 1.0
        _set_spin_value_silent(spin, actual_v / factor)

    def _sync_level_voltage_unit_controls(self, unit: str) -> None:
        _set_combo_data(self.level_voltage_unit, unit, silent=True)
        _set_combo_data(self.low_level_voltage_unit, unit, silent=True)

    def _resolved_frequency_unit(self, saved: str, frequency_hz: float) -> str:
        if saved in VALID_FREQUENCY_UNITS:
            return saved
        return preferred_frequency_unit(frequency_hz)

    def _resolved_period_unit(self, saved: str, period_s: float) -> str:
        if saved in VALID_PERIOD_UNITS:
            return saved
        return preferred_period_unit(period_s)

    def _resolved_level_voltage_unit(self, saved: str, high_v: float) -> str:
        if saved in VALID_LEVEL_VOLTAGE_UNITS:
            return saved
        return preferred_level_voltage_unit(high_v)

    def _apply_timing_display_units(self, settings: ChannelSettings) -> None:
        ui_key = (
            self.active_device_key
            or self._current_visa_address()
            or self._startup_config.visa_address
        )
        saved_ui = self.device_ui_settings.get(ui_key, {}).get(settings.channel)
        saved_freq = saved_ui.frequency_unit if isinstance(saved_ui, ChannelUiConfig) else ""
        saved_period = saved_ui.period_unit if isinstance(saved_ui, ChannelUiConfig) else ""
        frequency_unit = self._resolved_frequency_unit(saved_freq, settings.frequency_hz)
        period_unit = self._resolved_period_unit(saved_period, settings.period_s)
        self._frequency_display_unit = frequency_unit
        self._period_display_unit = period_unit
        _set_combo_data(self.frequency_unit, frequency_unit, silent=True)
        _set_combo_data(self.period_unit, period_unit, silent=True)
        self._configure_frequency_spin(frequency_unit, settings.frequency_hz)
        self._configure_period_spin(period_unit, settings.period_s)

    def _apply_level_voltage_display_units(self, settings: ChannelSettings) -> None:
        ui_key = (
            self.active_device_key
            or self._current_visa_address()
            or self._startup_config.visa_address
        )
        saved_ui = self.device_ui_settings.get(ui_key, {}).get(settings.channel)
        saved_unit = saved_ui.level_voltage_unit if isinstance(saved_ui, ChannelUiConfig) else ""
        level_unit = self._resolved_level_voltage_unit(saved_unit, settings.high_v)
        self._level_voltage_display_unit = level_unit
        self._sync_level_voltage_unit_controls(level_unit)
        self._configure_level_voltage_spin(level_unit, settings.high_v, self.high_v)
        self._configure_level_voltage_spin(level_unit, settings.low_v, self.low_v)

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
            base_period = period_from_frequency(frequency_hz)
        return pulse_width_from_duty(base_period, duty_percent)

    def _settings_from_form(self) -> ChannelSettings:
        waveform = self._selected_waveform()
        frequency_mode = self.frequency_mode.currentData()
        frequency_hz = self._frequency_display_to_hz(self.frequency_hz.value())
        period_s = self._period_display_to_seconds(self.period_s.value())
        if frequency_mode == "period":
            frequency_hz = frequency_from_period(period_s)
        else:
            period_s = period_from_frequency(frequency_hz)
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
            internal_period_s=self._period_display_to_seconds(
                self.burst_internal_period.value(),
                self._burst_internal_period_display_unit,
            ),
            phase_deg=self.burst_phase.value(),
            delay_s=self.burst_delay.value(),
            gate_polarity=self.burst_gate_polarity.currentData(),
            trigger_slope=self.burst_trigger_slope.currentData(),
            idle_mode=self.burst_idle_mode.currentData(),
            idle_point=self.burst_idle_point.value(),
        )
        level_mode = self.level_mode.currentData()
        amplitude_vpp = self.amplitude_vpp.value()
        offset_v = self.offset_v.value()
        high_v = self._level_voltage_display_to_volts(self.high_v.value())
        low_v = self._level_voltage_display_to_volts(self.low_v.value())
        if level_mode == "high_low":
            amplitude_vpp, offset_v = amplitude_offset_from_high_low(high_v, low_v)
        else:
            high_v, low_v = high_low_from_amplitude_offset(amplitude_vpp, offset_v)
        return ChannelSettings(
            channel=self.active_channel,
            waveform=waveform,
            frequency_mode=frequency_mode,
            frequency_hz=frequency_hz,
            period_s=period_s,
            level_mode=level_mode,
            amplitude_vpp=amplitude_vpp,
            offset_v=offset_v,
            high_v=high_v,
            low_v=low_v,
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
        self._apply_timing_display_units(settings)
        self.phase_deg.setValue(settings.phase_deg)
        _set_combo_data(self.level_mode, settings.level_mode)
        self.amplitude_vpp.setValue(settings.amplitude_vpp)
        self.offset_v.setValue(settings.offset_v)
        self._apply_level_voltage_display_units(settings)
        self.duty_percent.setValue(settings.duty_percent)
        self.pulse_width_s.setValue(settings.pulse_width_s)
        self.ramp_symmetry.setValue(settings.ramp_symmetry_percent)
        _set_combo_data(self.load, settings.load)
        self.burst_enabled.setChecked(settings.burst.enabled)
        _set_combo_data(self.burst_mode, settings.burst.mode)
        self.burst_cycles.setValue(settings.burst.cycles)
        _set_combo_data(self.burst_trigger_source, settings.burst.trigger_source)
        self._burst_internal_period_display_unit = self._period_display_unit
        _set_combo_data(
            self.burst_internal_period_unit,
            self._burst_internal_period_display_unit,
            silent=True,
        )
        self._configure_burst_internal_period_spin(
            self._burst_internal_period_display_unit,
            settings.burst.internal_period_s,
        )
        self.burst_phase.setValue(settings.burst.phase_deg)
        _set_combo_data(self.burst_idle_mode, settings.burst.idle_mode)
        self.burst_idle_point.setValue(settings.burst.idle_point)
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
            high_v = self._level_voltage_display_to_volts(self.high_v.value())
            low_v = self._level_voltage_display_to_volts(self.low_v.value())
            amplitude_vpp, offset_v = amplitude_offset_from_high_low(high_v, low_v)
            _set_spin_value_silent(self.amplitude_vpp, amplitude_vpp)
            _set_spin_value_silent(self.offset_v, offset_v)
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
        self.level_voltage_unit.setEnabled(level.high)
        self.low_level_voltage_unit.setEnabled(level.low)
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
        self.burst_internal_period_unit.setEnabled(burst.internal_period)
        _set_spin_enabled(self.burst_phase, burst.phase)
        self.burst_idle_mode.setEnabled(burst.idle_level)
        idle_is_user = self.burst_idle_mode.currentData() == "USER"
        _set_spin_enabled(self.burst_idle_point, burst.idle_level and idle_is_user)
        show_idle_point = burst.idle_level and idle_is_user
        self.burst_idle_point_row.setVisible(show_idle_point)
        if show_idle_point:
            self._ensure_parameter_field_visible(self.burst_idle_point_row)
        _set_spin_enabled(self.burst_delay, burst.delay)
        self.burst_gate_polarity.setEnabled(burst.gate_polarity)
        self.burst_trigger_slope.setEnabled(burst.trigger_slope)
        _set_form_row_visible(self.burst_mode, burst.fields)
        _set_form_row_visible(self.burst_trigger_source, burst.trigger_source)
        _set_form_row_visible(self.burst_cycles_editor, burst.cycles)
        _set_form_row_visible(self.burst_internal_period_editor, burst.internal_period)
        _set_form_row_visible(self.burst_phase_editor, burst.phase)
        _set_form_row_visible(self.burst_idle_row, burst.idle_level)
        _set_form_row_visible(self.burst_delay_editor, burst.delay)
        _set_form_row_visible(self.burst_gate_polarity, burst.gate_polarity)
        _set_form_row_visible(self.burst_trigger_slope, burst.trigger_slope)

    def _ensure_parameter_field_visible(self, widget: QWidget) -> None:
        scroll = getattr(self, "parameter_scroll", None)
        if scroll is None:
            return
        scroll.ensureWidgetVisible(widget, 24, 24)

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
                channel_text=f"CH{current.channel} Active",
                load_text=_format_load(current.load),
                duty_percent=current.duty_percent,
                ramp_symmetry_percent=current.ramp_symmetry_percent,
            )
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
            self._select_device(address, navigate=False)
            return
        attempts = CONNECT_RETRY_COUNT + 1
        last_exc: Exception | None = None
        connected = False
        button = row.get("button")
        address_box = row.get("address")
        if isinstance(button, QPushButton):
            button.setEnabled(False)
        if isinstance(address_box, QComboBox):
            address_box.setEnabled(False)
        try:
            for attempt in range(1, attempts + 1):
                status = "连接中" if attempt == 1 else f"重试 {attempt - 1}/{CONNECT_RETRY_COUNT}"
                self._set_connection_row_state(row, False, status)
                if isinstance(address_box, QComboBox):
                    address_box.setEnabled(False)
                QApplication.processEvents()
                client = RigolVisaClient(log=self._log)
                try:
                    result = client.connect(address)
                except Exception as exc:
                    last_exc = exc
                    client.disconnect()
                    self._log(f"连接尝试 {attempt}/{attempts} 失败: {exc}")
                    continue
                self.clients[address] = client
                self.client = client
                connected = True
                self._register_device(address, result.idn)
                self._disable_all_outputs_after_connect(address)
                self._select_device(address, navigate=False)
                self._sync_burst_state_after_connect(address)
                self._log(f"连接成功: {address} [{result.backend}] {result.idn}")
                return
        finally:
            if isinstance(button, QPushButton):
                button.setEnabled(True)
            if isinstance(address_box, QComboBox) and not connected:
                address_box.setEnabled(True)
        self._set_connection_row_state(row, False, "连接失败", failed=True)
        self._log("连接排查提示：请检查网线、IP 地址、VISA 驱动和设备电源。")
        if last_exc is not None:
            self._show_error("连接失败", last_exc)
        else:
            self._show_error("连接失败", RuntimeError("连接失败"))
        return

    def _disable_all_outputs_after_connect(self, address: str) -> None:
        client = self.clients.get(address)
        if client is None:
            return
        try:
            commands = client.set_all_outputs_off()
        except Exception as exc:
            self._log(f"连接安全：关闭 CH1/CH2 输出失败: {exc}")
            return
        channels = self.device_settings.setdefault(address, dict(self.default_channel_settings))
        for channel in (1, 2):
            settings = channels.get(channel)
            if settings is None:
                continue
            channels[channel] = ChannelSettings(
                **{**settings.__dict__, "output_enabled": False}
            )
        self._log(
            "连接安全：已关闭 CH1/CH2 输出: "
            + ", ".join(commands)
        )

    def _sync_burst_state_after_connect(self, address: str) -> None:
        client = self.clients.get(address)
        channels = self.device_settings.get(address, self.channel_settings)
        if client is None:
            return
        active_channel = self.device_active_channels.get(address, self.active_channel)
        channel_order = [
            channel
            for channel in sorted(channels)
            if channel != active_channel
        ]
        if active_channel in channels:
            channel_order.append(active_channel)
        for channel in channel_order:
            settings = channels[channel]
            enabled = bool(settings.burst.enabled and waveform_ui_state(settings.waveform).burst)
            try:
                command = client.set_burst_enabled(channel, enabled)
            except Exception as exc:
                self._log(f"CH{channel} Burst 连接同步失败: {exc}")
                continue
            state = "开启" if enabled else "关闭"
            self._log(f"CH{channel} Burst 连接同步{state}: {command}")

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
            self._show_error("应用当前通道异常", exc)
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
            self._show_error("应用双通道异常", exc)
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
        if self.active_device_key:
            self.device_settings.setdefault(self.active_device_key, dict(self.default_channel_settings))[
                self.active_channel
            ] = next_settings
        self._load_settings_to_form(next_settings)
        self._update_connection_channel_buttons()
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
            (self.connection_panel, 18, 3, 18),
            (self.center_panel, 20, 4, 20),
            (self.right_panel, 20, 4, 18),
        ):
            shadow = QGraphicsDropShadowEffect(widget)
            shadow.setBlurRadius(blur)
            shadow.setOffset(0, offset)
            shadow.setColor(QColor(30, 55, 82, alpha))
            widget.setGraphicsEffect(shadow)

    def _finalize_parameter_panel(self) -> None:
        for group in (
            self.timing_group,
            self.level_group,
            self.shape_group,
            self.burst_group,
        ):
            group.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)
            group.setFixedWidth(PARAM_CARD_WIDTH)
        for widget in (
            self.frequency_mode,
            self.frequency_hz_editor,
            self.period_s_editor,
            self.phase_deg_editor,
            self.level_mode,
            self.load,
            self.amplitude_vpp_editor,
            self.offset_v_editor,
            self.high_v_editor,
            self.low_v_editor,
            self.duty_percent_editor,
            self.pulse_width_s_editor,
            self.ramp_symmetry_editor,
            self.burst_mode,
            self.burst_trigger_source,
            self.burst_cycles_editor,
            self.burst_internal_period_editor,
            self.burst_phase_editor,
            self.burst_idle_mode,
            self.burst_delay_editor,
            self.burst_gate_polarity,
            self.burst_trigger_slope,
        ):
            _constrain_param_field(widget)
        self.burst_idle_point_editor.setFixedSize(
            PARAM_FIELD_WIDTH - 46,
            PARAM_ROW_HEIGHT,
        )

    def _apply_style(self) -> None:
        self.setStyleSheet(APP_STYLE)
        for combo in self.findChildren(QComboBox):
            _prepare_combo_popup(combo)


def _param_row_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("ParamRowLabel")
    label.setFixedSize(PARAM_LABEL_WIDTH, PARAM_ROW_HEIGHT)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return label


def _constrain_param_field(widget: QWidget) -> None:
    widget.setFixedSize(PARAM_FIELD_WIDTH, PARAM_ROW_HEIGHT)
    widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


def _form_layout(parent: QWidget) -> QFormLayout:
    layout = QFormLayout(parent)
    layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    layout.setFormAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    layout.setHorizontalSpacing(PARAM_FORM_HORIZONTAL_SPACING)
    layout.setVerticalSpacing(PARAM_FORM_VERTICAL_SPACING)
    layout.setContentsMargins(PARAM_FORM_MARGIN_H, 8, PARAM_FORM_MARGIN_H, 8)
    layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    return layout


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def _prepare_combo_popup(combo: QComboBox) -> None:
    if isinstance(combo, CleanComboBox):
        combo._prepare_popup()
        return
    view = combo.view()
    if not isinstance(view, QListView) or view.objectName() != "ComboPopupView":
        view = QListView(combo)
        view.setObjectName("ComboPopupView")
        combo.setView(view)
    view.setFrameShape(QFrame.NoFrame)
    view.setLineWidth(0)
    view.setMidLineWidth(0)
    view.setMouseTracking(True)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    view.setWindowFlag(Qt.FramelessWindowHint, True)
    view.setWindowFlag(Qt.NoDropShadowWindowHint, True)


def _double_spin(
    minimum: float,
    maximum: float,
    value: float,
    decimals: int,
    step: float,
) -> QDoubleSpinBox:
    spin = FocusWheelDoubleSpinBox()
    spin.setObjectName("ArrowSpin")
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setValue(value)
    spin.setSingleStep(step)
    spin.setKeyboardTracking(False)
    spin.setAccelerated(True)
    spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
    spin.setFrame(False)
    return spin


def _clear_widget_background(widget: QWidget) -> None:
    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.setAutoFillBackground(False)


def _unit_column_spacer(parent: QWidget) -> QWidget:
    spacer = QWidget(parent)
    spacer.setObjectName("UnitColumnSpacer")
    spacer.setFixedWidth(UNIT_COLUMN_WIDTH)
    _clear_widget_background(spacer)
    return spacer


def _unit_column_widget(
    parent: QWidget,
    *,
    unit: QComboBox | None = None,
    suffix: str = "",
) -> QWidget:
    column = QWidget(parent)
    column.setObjectName("UnitColumn")
    column.setFixedWidth(UNIT_COLUMN_WIDTH)
    _clear_widget_background(column)

    layout = QHBoxLayout(column)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    separator = QFrame(column)
    separator.setObjectName("UnitSeparator")
    separator.setFrameShape(QFrame.Shape.NoFrame)
    separator.setFixedWidth(UNIT_SEP_WIDTH)
    _clear_widget_background(separator)
    layout.addWidget(separator)

    slot = QWidget(column)
    slot.setObjectName("UnitSlot")
    slot.setFixedWidth(UNIT_SLOT_WIDTH)
    _clear_widget_background(slot)
    slot_layout = QHBoxLayout(slot)
    slot_layout.setContentsMargins(0, 0, 0, 0)
    slot_layout.setSpacing(0)
    if unit is not None:
        unit.setParent(slot)
        unit.setFixedWidth(UNIT_SLOT_WIDTH)
        _clear_widget_background(unit)
        slot_layout.addWidget(unit)
    elif suffix.strip():
        label = QLabel(suffix.strip(), slot)
        label.setObjectName("UnitLabel")
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        _clear_widget_background(label)
        slot_layout.addWidget(label, 1)
    layout.addWidget(slot)
    return column


def _spin_editor(
    spin: QDoubleSpinBox | QSpinBox,
    *,
    unit: QComboBox | None = None,
    suffix: str = "",
    inline_suffix: str = "",
) -> QWidget:
    spin.setObjectName("ArrowSpin")
    spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
    spin.setFrame(False)
    spin.setAccelerated(True)
    if inline_suffix:
        spin.setSuffix(inline_suffix)
    spin.setMinimumWidth(0)
    spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    editor = QFrame()
    editor.setObjectName("SpinEditorBox")
    editor.setFixedSize(PARAM_FIELD_WIDTH, PARAM_ROW_HEIGHT)
    editor.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    layout = QHBoxLayout(editor)
    layout.setContentsMargins(8, 3, 5, 3)
    layout.setSpacing(0)
    layout.addWidget(spin, 1)
    if unit is not None or suffix.strip():
        layout.addWidget(_unit_column_widget(editor, unit=unit, suffix=suffix))
    elif inline_suffix:
        layout.addWidget(_unit_column_spacer(editor))

    btn_up = QToolButton(editor)
    btn_up.setObjectName("SpinArrowButton")
    btn_up.setText("▲")
    btn_up.setToolTip("增加")
    btn_up.setAutoRaise(True)
    btn_up.setFixedSize(22, 22)

    btn_down = QToolButton(editor)
    btn_down.setObjectName("SpinArrowButton")
    btn_down.setText("▼")
    btn_down.setToolTip("减少")
    btn_down.setAutoRaise(True)
    btn_down.setFixedSize(22, 22)

    btn_up.clicked.connect(lambda: spin.setValue(spin.value() + spin.singleStep()))
    btn_down.clicked.connect(lambda: spin.setValue(spin.value() - spin.singleStep()))

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


def _set_spin_value_silent(spin: QDoubleSpinBox | QSpinBox, value: float) -> None:
    spin.blockSignals(True)
    spin.setValue(_clamp(float(value), float(spin.minimum()), float(spin.maximum())))
    spin.blockSignals(False)


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
QScrollArea#ParameterScroll > QWidget > QWidget {
    background: transparent;
}
QScrollArea#ParameterScroll QScrollBar:vertical {
    width: 5px;
    margin: 2px 1px 2px 0;
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
QLabel#SidebarVersionLabel {
    color: #8a9bb0;
    font-size: 10px;
    background: transparent;
    padding: 0 0 2px 0;
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
    font-size: 15px;
    font-weight: 800;
    background: transparent;
}
QLabel#ConnectionSubtitle {
    color: #607387;
    font-size: 13px;
    background: transparent;
}
QFrame#ConnectionCard QPushButton#ConnectionButton {
    min-height: 34px;
    max-height: 34px;
    padding: 0 8px;
    font-size: 12px;
}
QFrame#ConnectionChannelCard {
    min-height: 34px;
    max-height: 34px;
    background: #f7fbff;
    border: 1px solid #d3deea;
    border-radius: 8px;
}
QFrame#ConnectionChannelCard:hover {
    border-color: #9bcdf6;
}
QFrame#ConnectionChannelCard[active="true"] {
    background: #e9f4ff;
    border-color: #82bff2;
}
QFrame#ConnectionChannelCard:disabled {
    background: #f5f7fa;
    border-color: #d9e1eb;
}
QLabel#ConnectionChannelTitle {
    color: #1879d9;
    font-size: 12px;
    font-weight: 800;
    background: transparent;
}
QFrame#ConnectionChannelCard:disabled QLabel#ConnectionChannelTitle {
    color: #a7b1bf;
}
QLabel#ConnectionChannelOutputBadge {
    border-radius: 7px;
    border: 1px solid #d9e1eb;
    background: #eef2f7;
    color: #7f8b9a;
    font-size: 10px;
    font-weight: 800;
}
QLabel#ConnectionChannelOutputBadge[state="off"] {
    background: #eef2f7;
    border-color: #d9e1eb;
    color: #7f8b9a;
}
QLabel#ConnectionChannelOutputBadge[on="true"] {
    background: #e8f6ee;
    border-color: #bfe5cf;
    color: #2e9f61;
}
QFrame#ConnectionChannelCard[active="true"] QLabel#ConnectionChannelOutputBadge {
    border-color: #9bcdf6;
}
QFrame#ConnectionChannelCard:disabled QLabel#ConnectionChannelOutputBadge {
    background: #f5f7fa;
    border-color: #d9e1eb;
    color: #a7b1bf;
}
QFrame#ConnectionChannelCard[active="true"] QLabel#ConnectionChannelTitle {
    color: #1879d9;
}
QFrame#ConnectionCard QPushButton#ConnectionIconButton,
QFrame#ConnectionCard QPushButton#ConnectionHeaderButton {
    min-height: 28px;
    max-height: 28px;
    padding: 0 8px;
    font-size: 12px;
}
QFrame#ConnectionCard QPushButton#ConnectionIconButton {
    color: #1879d9;
    font-size: 17px;
    font-weight: 800;
    padding: 0;
}
QFrame#ConnectionCard QPushButton#ConnectionHeaderButton {
    color: #2f4a68;
    font-size: 11px;
    font-weight: 700;
}
QFrame#ConnectionCard QPushButton#ConnectionIconButton:hover,
QFrame#ConnectionCard QPushButton#ConnectionHeaderButton:hover {
    border-color: #338de6;
    color: #1879d9;
}
QFrame#ConnectionCard QComboBox {
    min-height: 34px;
    max-height: 34px;
    background: #f9fcff;
}
QWidget#ConnectionGridHost {
    background: transparent;
}
QWidget#ConnectionRowHost {
    background: transparent;
}
QLabel#ConnectionDeviceLabel {
    color: #2f4a68;
    background: #f3f7fb;
    border: 1px solid #d9e4ef;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 800;
}
QLabel#ConnectionRowLabel {
    color: #607387;
    font-size: 12px;
    font-weight: 700;
    background: transparent;
    padding: 0;
}
QLabel#ConnectionRowLabel[active="true"] {
    color: #1879d9;
    background: #eaf4ff;
    border-radius: 6px;
}
QLabel#ConnectionRowLabel[connected="true"] {
    color: #2e9f61;
}
QLabel#ConnectionRowLabel[connected="true"][active="true"] {
    color: #1879d9;
}
QLabel#ConnectionRowLabel[failed="true"] {
    color: #c94141;
}
QFrame#RightPanel {
    background: #f3f7fb;
    border: 1px solid #dce5ef;
    border-radius: 11px;
}
QFrame#WorkToolbar {
    background: #ffffff;
    border: 1px solid #dce5ef;
    border-radius: 10px;
}
QWidget#WorkToolbarLeft {
    background: transparent;
}
QWidget#WorkToolbarChannelRow, QWidget#WorkToolbarActionRow {
    background: transparent;
}
QWidget#WorkToolbarLeft QPushButton, QWidget#WorkToolbarLeft QComboBox {
    min-height: 36px;
    max-height: 36px;
    padding: 0 8px;
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
    padding-right: 2px;
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
    font-size: 12px;
}
QFrame#RightPanel QLabel#PanelTitle {
    font-size: 16px;
}
QFrame#RightPanel QLabel#ParamRowLabel {
    color: #607387;
    font-size: 12px;
    padding: 0;
    background: transparent;
}
QFrame#RightPanel QLabel#ParamSubLabel {
    color: #7a8ea3;
    font-size: 11px;
    padding: 0;
    background: transparent;
}
QFrame#RightPanel QGroupBox {
    background: #ffffff;
    border: 1px solid #dce5ef;
    border-radius: 10px;
    margin-top: 0;
    padding: 0;
    font-size: 12px;
}
QFrame#RightPanel QGroupBox::title {
    height: 0;
    padding: 0;
    margin: 0;
    background: transparent;
}
QLabel#SectionTitle {
    color: #0f2f4d;
    font-size: 13px;
    font-weight: 700;
    padding: 0 0 7px 0;
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
QComboBoxPrivateContainer {
    background: #ffffff;
    border: 1px solid #d4dfeb;
    border-radius: 8px;
    padding: 0;
}
QComboBoxPrivateContainer QWidget {
    background: #ffffff;
    border: none;
}
QFrame#ComboPopupFrame {
    background: #ffffff;
    border: 1px solid #d4dfeb;
    border-radius: 8px;
}
QFrame#ComboPopupItems, QScrollArea#ComboPopupScroll {
    background: transparent;
    border: none;
}
QPushButton#ComboPopupItem {
    background: transparent;
    border: none;
    border-radius: 6px;
    color: #22354c;
    font-size: 12px;
    padding: 0 10px;
    text-align: left;
}
QPushButton#ComboPopupItem:hover,
QPushButton#ComboPopupItem[selected="true"] {
    background: #e9f4ff;
    color: #0f2f4d;
}
QListView#ComboPopupView {
    background: #ffffff;
    border: 1px solid #d4dfeb;
    border-radius: 8px;
    outline: 0;
    padding: 4px;
    color: #22354c;
}
QListView#ComboPopupView::item {
    min-height: 24px;
    padding: 4px 8px;
    border-radius: 6px;
    background: transparent;
}
QListView#ComboPopupView::item:hover,
QListView#ComboPopupView::item:selected {
    background: #e9f4ff;
    color: #0f2f4d;
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
    min-height: 30px;
    max-height: 34px;
    padding: 3px 6px 3px 8px;
    font-size: 12px;
}
QFrame#RightPanel QComboBox::drop-down {
    width: 18px;
}
QFrame#SpinEditorBox QFrame#UnitSeparator {
    background: #d4dfeb;
    border: none;
    min-width: 1px;
    max-width: 1px;
    margin: 5px 0;
}
QFrame#SpinEditorBox QWidget#UnitColumn,
QFrame#SpinEditorBox QWidget#UnitColumnSpacer,
QFrame#SpinEditorBox QWidget#UnitSlot {
    background: transparent;
    border: none;
}
QFrame#SpinEditorBox QLabel#UnitLabel {
    background: transparent;
    color: #536478;
    font-size: 12px;
    padding-left: 8px;
    padding-right: 8px;
    border: none;
}
QFrame#SpinEditorBox QComboBox#UnitCombo,
QFrame#SpinEditorBox QComboBox#UnitCombo:focus,
QFrame#SpinEditorBox QComboBox#UnitCombo:disabled,
QFrame#SpinEditorBox QComboBox#UnitCombo:hover {
    background: transparent;
    border: none;
    border-radius: 0;
    min-height: 24px;
    padding: 0 8px 0 8px;
    color: #536478;
}
QFrame#RightPanel QFrame#SpinEditorBox QComboBox#UnitCombo,
QFrame#RightPanel QFrame#SpinEditorBox QComboBox#UnitCombo:focus,
QFrame#RightPanel QFrame#SpinEditorBox QComboBox#UnitCombo:disabled {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0 8px 0 8px;
    min-height: 24px;
}
QFrame#SpinEditorBox QComboBox#UnitCombo::drop-down {
    width: 10px;
    border: none;
    background: transparent;
}
QFrame#RightPanel QFrame#SpinEditorBox QLabel#UnitLabel {
    font-size: 12px;
}
QFrame#SpinEditorBox {
    background: #ffffff;
    border: 1px solid #d4dfeb;
    border-radius: 9px;
    min-height: 34px;
    max-height: 34px;
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
    min-height: 24px;
    padding: 2px 2px;
    font-size: 12px;
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
    font-size: 13px;
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
QFrame#InlineDetails {
    background: transparent;
    border: none;
}
QWidget#BurstIdleRow, QWidget#BurstIdlePointRow {
    background: transparent;
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
