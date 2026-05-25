from __future__ import annotations

import sys
from datetime import datetime

from PySide6.QtCore import Qt, Signal
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
    QVBoxLayout,
    QWidget,
)

from .config import AppConfig, default_app_config, default_config_path, load_app_config, save_app_config
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
        self.setFixedHeight(116)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        self.title = QLabel(f"CH{channel}")
        self.title.setObjectName("ChannelCardTitle")
        self.meta = QLabel("SIN | 1 kHz | 2 Vpp")
        self.meta.setObjectName("ChannelCardMeta")
        self.output = QLabel("输出 OFF")
        self.output.setObjectName("ChannelOutputBadge")
        self.output.setFixedSize(86, 26)
        self.output.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.title)
        layout.addWidget(self.meta)
        layout.addWidget(self.output)
        layout.addStretch(1)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_summary(self, settings: ChannelSettings) -> None:
        self.meta.setText(
            f"{settings.waveform.upper()} | {_format_timing(settings)} | {_format_level_short(settings)}"
        )
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
        self.setWindowTitle("RIGOL DG1022Z 上位机")
        self.resize(1400, 900)
        self._connected = False
        self._loading_form = False
        self._config_path = default_config_path()
        self._startup_config = load_app_config(self._config_path, default_app_config())
        self.active_channel = self._startup_config.active_channel
        self.channel_settings = dict(self._startup_config.channels)
        self.client = RigolVisaClient(log=self._log)
        self._build_ui()
        self._apply_style()
        self._loading_form = True
        self.address.setEditText(self._startup_config.visa_address)
        self._loading_form = False
        self._load_settings_to_form(self.channel_settings[self.active_channel])
        self._set_connected(False, "未连接")

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("AppRoot")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        root.addWidget(self._build_top_bar())

        content = QHBoxLayout()
        content.setSpacing(14)
        content.addWidget(self._build_left_panel())
        content.addWidget(self._build_center_panel(), 1)
        content.addWidget(self._build_right_panel())
        root.addLayout(content, 1)

        self._build_log_window()
        self._connect_signals()

    def _build_top_bar(self) -> QWidget:
        top = QFrame()
        top.setObjectName("TopBar")
        layout = QHBoxLayout(top)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        brand = QFrame(top)
        brand.setObjectName("BrandBlock")
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(0, 0, 14, 0)
        brand_layout.setSpacing(10)
        badge = QLabel("DG", brand)
        badge.setObjectName("BrandBadge")
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignCenter)
        title_wrap = QWidget(brand)
        title_layout = QVBoxLayout(title_wrap)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)
        title = QLabel("RIGOL DG1022Z", title_wrap)
        title.setObjectName("BrandTitle")
        subtitle = QLabel("Waveform Generator Control", title_wrap)
        subtitle.setObjectName("BrandSubtitle")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        brand_layout.addWidget(badge)
        brand_layout.addWidget(title_wrap)

        visa_label = QLabel("VISA", top)
        visa_label.setObjectName("FieldLabel")
        self.address = QComboBox(top)
        self.address.setEditable(True)
        self.address.addItem("TCPIP::192.168.1.191::INSTR")
        self.address.setFixedWidth(250)

        self.btn_refresh = QPushButton("刷新", top)
        self.btn_connect = QPushButton("连接", top)
        self.btn_connect.setObjectName("PrimaryButton")
        self.btn_disconnect = QPushButton("断开", top)
        self.btn_idn = QPushButton("IDN", top)
        self.status = QLabel("未连接", top)
        self.status.setObjectName("ConnStatus")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFixedWidth(138)

        self.btn_log = QPushButton("运行日志", top)
        self.btn_error = QPushButton("查询错误", top)
        self.btn_phase = QPushButton("相位同步", top)

        for control in (
            self.address,
            self.btn_refresh,
            self.btn_connect,
            self.btn_disconnect,
            self.btn_idn,
            self.status,
            self.btn_log,
            self.btn_error,
            self.btn_phase,
        ):
            control.setFixedHeight(34)

        layout.addWidget(brand)
        layout.addWidget(visa_label)
        layout.addWidget(self.address)
        layout.addWidget(self.btn_refresh)
        layout.addWidget(self.btn_connect)
        layout.addWidget(self.btn_disconnect)
        layout.addWidget(self.btn_idn)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addWidget(self.btn_log)
        layout.addWidget(self.btn_error)
        layout.addWidget(self.btn_phase)
        return top

    def _build_log_window(self) -> None:
        self.log_window = QDialog(self)
        self.log_window.setWindowTitle("运行日志")
        self.log_window.resize(760, 360)
        layout = QVBoxLayout(self.log_window)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("运行日志")
        title.setObjectName("MainTitle")
        hint = QLabel("连接、下发、查询和错误信息会记录在这里")
        hint.setObjectName("SubtleText")
        self.log = QTextEdit(self.log_window)
        self.log.setObjectName("LogText")
        self.log.setReadOnly(True)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.btn_clear_log = QPushButton("清空日志", self.log_window)
        self.btn_close_log = QPushButton("关闭", self.log_window)
        actions.addWidget(self.btn_clear_log)
        actions.addWidget(self.btn_close_log)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.log, 1)
        layout.addLayout(actions)

    def _build_left_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("LeftPanel")
        panel.setFixedWidth(236)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("通道与输出")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        self.channel_cards = {
            1: ChannelCard(1, panel),
            2: ChannelCard(2, panel),
        }
        for card in self.channel_cards.values():
            layout.addWidget(card)

        quick = QFrame(panel)
        quick.setObjectName("Card")
        quick_layout = QVBoxLayout(quick)
        quick_layout.setContentsMargins(14, 14, 14, 14)
        quick_layout.setSpacing(10)
        quick_title = QLabel("快捷操作")
        quick_title.setObjectName("CardTitle")
        self.btn_apply = QPushButton("应用当前通道")
        self.btn_apply.setObjectName("PrimaryButton")
        self.btn_apply_all = QPushButton("应用双通道")
        self.btn_output_on = QPushButton("输出开")
        self.btn_output_off = QPushButton("输出关")
        self.btn_fire = QPushButton("软件触发 Burst")
        self.load = QComboBox()
        self.load.addItem("负载 High-Z", "INF")
        self.load.addItem("负载 50 ohm", "50")
        quick_layout.addWidget(quick_title)
        quick_layout.addWidget(self.btn_apply)
        quick_layout.addWidget(self.btn_apply_all)
        quick_layout.addWidget(self.btn_output_on)
        quick_layout.addWidget(self.btn_output_off)
        quick_layout.addWidget(self.btn_fire)
        quick_layout.addWidget(self.load)
        layout.addWidget(quick)
        layout.addStretch(1)
        return panel

    def _build_center_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("CenterPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(8)

        title = QLabel("波形显示与选择")
        title.setObjectName("MainTitle")
        layout.addWidget(title)

        self.wave_preview = WaveformPreview(panel)
        self.wave_preview.setFixedHeight(246)
        self.wave_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.wave_preview)

        selector = QFrame(panel)
        selector.setObjectName("Card")
        selector.setMinimumHeight(148)
        selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        selector_layout = QVBoxLayout(selector)
        selector_layout.setContentsMargins(14, 12, 14, 12)
        selector_layout.setSpacing(8)
        selector_title = QLabel("波形选择")
        selector_title.setObjectName("CardTitle")
        selector_layout.addWidget(selector_title)
        wave_grid = QGridLayout()
        wave_grid.setHorizontalSpacing(6)
        wave_grid.setVerticalSpacing(6)
        self.wave_group = QButtonGroup(self)
        self.wave_group.setExclusive(True)
        self.wave_buttons: dict[str, QPushButton] = {}
        for index, (label, value) in enumerate(WAVEFORM_CHOICES):
            button = QPushButton(_wave_button_label(label, value), selector)
            button.setObjectName("WaveChoice")
            button.setCheckable(True)
            button.setToolTip(label)
            button.setProperty("waveform", value)
            button.clicked.connect(lambda _checked=False, v=value: self._set_waveform(v))
            self.wave_group.addButton(button)
            self.wave_buttons[value] = button
            wave_grid.addWidget(button, index // 5, index % 5)
        selector_layout.addLayout(wave_grid)
        layout.addWidget(selector)

        summary = QFrame(panel)
        summary.setObjectName("Card")
        summary.setMinimumHeight(96)
        summary.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(16, 12, 16, 12)
        summary_layout.setSpacing(6)
        summary_title = QLabel("当前参数摘要")
        summary_title.setObjectName("CardTitle")
        self.wave_summary = QLabel()
        self.wave_summary.setObjectName("SummaryLine")
        self.level_summary = QLabel()
        self.level_summary.setObjectName("SummaryLine")
        self.burst_summary = QLabel()
        self.burst_summary.setObjectName("SummaryLine")
        summary_layout.addWidget(summary_title)
        summary_layout.addWidget(self.wave_summary)
        summary_layout.addWidget(self.level_summary)
        summary_layout.addWidget(self.burst_summary)
        layout.addWidget(summary)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("RightPanel")
        panel.setFixedWidth(386)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

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
        self.frequency_hz = _double_spin(1e-6, 25e6, 1000.0, 6, " Hz", 100.0)
        self.period_s = _double_spin(4e-8, 1e6, 0.001, 9, " s", 0.0001)
        self.phase_deg = _double_spin(-360.0, 360.0, 0.0, 3, " deg", 1.0)
        self.frequency_hz_editor = _spin_editor(self.frequency_hz)
        self.period_s_editor = _spin_editor(self.period_s)
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
        self.burst_phase = _double_spin(-360.0, 360.0, 0.0, 3, " deg", 1.0)
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
        self.btn_refresh.clicked.connect(self._refresh_resources)
        self.btn_connect.clicked.connect(self._connect)
        self.btn_disconnect.clicked.connect(self._disconnect)
        self.btn_idn.clicked.connect(self._query_idn)
        self.btn_log.clicked.connect(self._show_log_window)
        self.btn_clear_log.clicked.connect(self.log.clear)
        self.btn_close_log.clicked.connect(self.log_window.hide)
        self.address.currentTextChanged.connect(self._save_config)
        self.btn_apply.clicked.connect(self._apply_current)
        self.btn_apply_all.clicked.connect(self._apply_all)
        self.btn_output_on.clicked.connect(lambda: self._set_output(True))
        self.btn_output_off.clicked.connect(lambda: self._set_output(False))
        self.btn_fire.clicked.connect(self._fire_burst)
        self.btn_phase.clicked.connect(self._align_phase)
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
        self.burst_enabled.toggled.connect(self._on_form_changed)
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
        self.client.disconnect()
        super().closeEvent(event)

    def _select_channel(self, channel: int) -> None:
        if channel == self.active_channel:
            return
        self._save_active_settings()
        self.active_channel = channel
        self._load_settings_to_form(self.channel_settings[channel])
        self._save_config()

    def _set_waveform(self, waveform: str) -> None:
        if self._loading_form:
            return
        if waveform in self.wave_buttons:
            self.wave_buttons[waveform].setChecked(True)
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

    def _save_config(self) -> None:
        if self._loading_form or not hasattr(self, "address"):
            return
        self._save_active_settings()
        config = AppConfig(
            active_channel=self.active_channel,
            visa_address=self.address.currentText().strip(),
            channels=dict(self.channel_settings),
        )
        try:
            save_app_config(config, self._config_path)
        except Exception as exc:
            self._log(f"保存配置失败: {exc}")

    def _settings_from_form(self) -> ChannelSettings:
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
            waveform=self._selected_waveform(),
            frequency_mode=self.frequency_mode.currentData(),
            frequency_hz=self.frequency_hz.value(),
            period_s=self.period_s.value(),
            level_mode=self.level_mode.currentData(),
            amplitude_vpp=self.amplitude_vpp.value(),
            offset_v=self.offset_v.value(),
            high_v=self.high_v.value(),
            low_v=self.low_v.value(),
            duty_percent=self.duty_percent.value(),
            phase_deg=self.phase_deg.value(),
            pulse_width_s=self.pulse_width_s.value(),
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
        self.frequency_hz.setValue(settings.frequency_hz)
        self.period_s.setValue(settings.period_s)
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
        self.burst_details.setVisible(True)
        self.burst_trigger_source.setEnabled(burst.trigger_source)
        _set_spin_enabled(self.burst_cycles, burst.cycles)
        _set_spin_enabled(self.burst_internal_period, burst.internal_period)
        _set_spin_enabled(self.burst_phase, burst.phase)
        _set_spin_enabled(self.burst_delay, burst.delay)
        self.burst_gate_polarity.setEnabled(burst.gate_polarity)
        self.burst_trigger_slope.setEnabled(burst.trigger_slope)
        for field in (
            self.burst_trigger_source,
            self.burst_cycles_editor,
            self.burst_internal_period_editor,
            self.burst_phase_editor,
            self.burst_delay_editor,
            self.burst_gate_polarity,
            self.burst_trigger_slope,
        ):
            _set_form_row_visible(field, True)

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
        self.wave_summary.setText(
            f"频率：{timing_text}    周期：{current.period_s:g} s    相位：{current.phase_deg:g} deg"
        )
        self.level_summary.setText(f"电平：{level_text}    负载：{current.load}")
        self.burst_summary.setText(f"Burst：{'ON' if current.burst.enabled else 'OFF'}    输出：{'ON' if current.output_enabled else 'OFF'}")
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
        current = self.address.currentText().strip()
        self.address.clear()
        if resources:
            self.address.addItems(resources)
        if current:
            index = self.address.findText(current)
            if index < 0:
                self.address.insertItem(0, current)
                index = 0
            self.address.setCurrentIndex(index)
        self._log(f"发现 {len(resources)} 个 VISA 资源")

    def _connect(self) -> None:
        try:
            result = self.client.connect(self.address.currentText())
        except Exception as exc:
            self._set_connected(False, "连接失败")
            self._show_error("连接失败", exc)
            return
        self._set_connected(True, f"[{result.backend}] {result.idn}")

    def _disconnect(self) -> None:
        self.client.disconnect()
        self._set_connected(False, "未连接")
        self._log("已断开")

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
                self.client.apply_channel(settings)
        except Exception as exc:
            self._show_error("应用双通道失败", exc)
            return
        self._log("CH1/CH2 参数已应用")

    def _set_output(self, enabled: bool) -> None:
        self._save_active_settings()
        current = self.channel_settings[self.active_channel]
        self.channel_settings[self.active_channel] = ChannelSettings(
            **{**current.__dict__, "output_enabled": enabled}
        )
        self._load_settings_to_form(self.channel_settings[self.active_channel])
        self._save_config()
        try:
            self.client.set_output(self.active_channel, enabled)
        except Exception as exc:
            self._show_error("设置输出失败", exc)
            return
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
        self.status.setText(text)
        self.status.setProperty("connected", connected)
        self.status.setProperty("failed", text == "连接失败")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self._update_action_state()

    def _update_action_state(self) -> None:
        connected = self._connected
        settings = self.channel_settings[self.active_channel]
        burst = burst_ui_state(
            settings.waveform,
            settings.burst.enabled,
            settings.burst.mode,
            settings.burst.trigger_source,
        )
        self.btn_connect.setEnabled(not connected)
        self.btn_disconnect.setEnabled(connected)
        self.btn_idn.setEnabled(connected)
        self.btn_apply.setEnabled(connected)
        self.btn_apply_all.setEnabled(connected)
        self.btn_output_on.setEnabled(connected)
        self.btn_output_off.setEnabled(connected)
        self.btn_phase.setEnabled(connected)
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


def _spin_editor(spin: QDoubleSpinBox | QSpinBox) -> QWidget:
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


def _wave_button_label(label: str, value: str) -> str:
    return value


APP_STYLE = """
QWidget {
    font-family: "Microsoft YaHei UI", "Segoe UI", Arial;
    font-size: 12px;
    color: #17283b;
    background: #e9eff5;
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
QFrame#TopBar, QFrame#CenterPanel {
    background: #f8fafc;
    border: 1px solid #d8e0ea;
    border-radius: 10px;
}
QFrame#LeftPanel, QFrame#RightPanel {
    background: #f2f5f9;
    border: 1px solid #d8e0ea;
    border-radius: 10px;
}
QFrame#BrandBlock {
    background: transparent;
    border-right: 1px solid #d8e0ea;
}
QLabel#BrandBadge {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #12b5cb, stop:1 #1f8ed7);
    color: #eef8ff;
    border-radius: 10px;
    font-size: 15px;
    font-weight: 700;
}
QLabel#BrandTitle, QLabel#MainTitle {
    color: #0f2f4d;
    font-size: 18px;
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
    font-size: 15px;
}
QLabel#CardTitle {
    font-size: 13px;
}
QFrame#Card {
    background: #ffffff;
    border: 1px solid #dee5ef;
    border-radius: 10px;
}
QFrame#ChannelCard {
    background: #ffffff;
    border: 1px solid #dee5ef;
    border-radius: 16px;
}
QFrame#ChannelCard[active="true"] {
    border: 2px solid #cfe0f1;
}
QLabel#ChannelCardTitle {
    color: #1879d9;
    font-size: 22px;
    font-weight: 700;
    background: transparent;
}
QLabel#ChannelCardMeta {
    color: #536478;
    font-size: 12px;
    background: transparent;
}
QLabel#ChannelOutputBadge, QLabel#StatePill {
    border-radius: 8px;
    background: #edf1f6;
    border: 1px solid #d9e1eb;
    color: #8a95a5;
    font-weight: 700;
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
    background: transparent;
    border: 1px solid #d8e3ef;
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
    border: 1px solid #cfd8e5;
    border-radius: 6px;
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
QFrame#RightPanel QComboBox, QFrame#RightPanel QDoubleSpinBox, QFrame#RightPanel QSpinBox {
    min-height: 22px;
    padding: 1px 6px;
    font-size: 11px;
}
QFrame#RightPanel QComboBox::drop-down {
    width: 18px;
}
QFrame#SpinEditorBox {
    background: #ffffff;
    border: 1px solid #cfd8e5;
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
    border: 1px solid #c8d3e2;
    border-radius: 6px;
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
    background: #f0f3f7;
    border-color: #d7deea;
}
QPushButton#PrimaryButton {
    background: #1879d9;
    border-color: #1879d9;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover {
    background: #0d6fcf;
    border-color: #0d6fcf;
}
QPushButton#WaveChoice {
    min-height: 32px;
    padding: 3px 6px;
    font-size: 11px;
    font-weight: 500;
}
QPushButton#WaveChoice:checked {
    background: #1879d9;
    border-color: #1879d9;
    color: #ffffff;
    font-weight: 700;
}
QLabel#SummaryLine {
    background: transparent;
    border: none;
    padding: 3px 0;
    color: #22354c;
}
QFrame#InlineDetails {
    background: transparent;
    border: none;
}
QLabel#ConnStatus {
    border-radius: 8px;
    padding: 0 10px;
    font-weight: 700;
    background: #edf1f6;
    color: #8a95a5;
    border: 1px solid #d9e1eb;
}
QLabel#ConnStatus[connected="true"] {
    background: #e8f6ee;
    color: #2e9f61;
    border-color: #bfe5cf;
}
QLabel#ConnStatus[failed="true"] {
    background: #fde8e8;
    color: #c94141;
    border-color: #f5b5b5;
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
