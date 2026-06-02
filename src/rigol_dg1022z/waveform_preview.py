from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPaintEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .scpi import normalize_waveform


WAVEFORM_TITLES = {
    "SIN": "Sine",
    "SQU": "Square",
    "PULS": "Pulse",
    "RAMP": "Ramp",
    "NOIS": "Noise",
    "USER": "Arb",
    "DC": "DC",
}


@dataclass(frozen=True)
class WaveformPreviewState:
    waveform: str
    frequency_text: str
    level_text: str
    burst_text: str
    output_text: str
    channel_text: str = ""
    load_text: str = ""
    duty_percent: float = 50.0
    ramp_symmetry_percent: float = 50.0


class WaveformPreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = WaveformPreviewState(
            waveform="SIN",
            frequency_text="1 kHz",
            level_text="2 Vpp",
            burst_text="Burst OFF",
            output_text="Output OFF",
        )
        self.setMinimumHeight(148)
        self.setObjectName("WaveformPreview")

    def set_state(self, state: WaveformPreviewState) -> None:
        self._state = state
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -1, -1)

        panel = QRectF(rect)
        painter.setPen(QPen(QColor("#d8e2ee"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(panel, 8, 8)

        plot = QRectF(
            panel.left() + 24,
            panel.top() + 62,
            panel.width() - 48,
            max(96.0, panel.height() - 126),
        )
        self._draw_grid(painter, plot)
        self._draw_wave(painter, plot)
        self._draw_labels(painter, panel)

    def _draw_grid(self, painter: QPainter, plot: QRectF) -> None:
        painter.setPen(QPen(QColor("#edf2f7"), 1))
        for i in range(5):
            x = plot.left() + plot.width() * i / 4.0
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        for i in range(3):
            y = plot.top() + plot.height() * i / 2.0
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        painter.setPen(QPen(QColor("#d7e0ea"), 1))
        painter.drawLine(
            QPointF(plot.left(), plot.center().y()),
            QPointF(plot.right(), plot.center().y()),
        )

    def _draw_wave(self, painter: QPainter, plot: QRectF) -> None:
        waveform = normalize_waveform(self._state.waveform)
        samples = max(80, int(plot.width()))
        amp = plot.height() * 0.36
        mid = plot.center().y()
        duty = max(0.001, min(99.999, self._state.duty_percent)) / 100.0
        sym = max(1.0, min(99.0, self._state.ramp_symmetry_percent)) / 100.0

        path = QPainterPath()
        for i in range(samples):
            t = i / max(1, samples - 1)
            phase = (t * 2.0) % 1.0
            y_norm = self._sample(waveform, phase, duty, sym)
            x = plot.left() + plot.width() * t
            y = mid - y_norm * amp
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        painter.setPen(QPen(QColor("#1879d9"), 3.0))
        painter.drawPath(path)

        painter.setPen(QPen(QColor("#8bbff0"), 1, Qt.DashLine))
        painter.drawLine(QPointF(plot.left(), mid - amp), QPointF(plot.right(), mid - amp))
        painter.drawLine(QPointF(plot.left(), mid + amp), QPointF(plot.right(), mid + amp))

    def _sample(self, waveform: str, phase: float, duty: float, symmetry: float) -> float:
        if waveform == "SIN":
            return math.sin(phase * math.tau)
        if waveform == "SQU":
            return 1.0 if phase < duty else -1.0
        if waveform == "PULS":
            return 1.0 if phase < duty else -0.35
        if waveform == "RAMP":
            if phase < symmetry:
                return -1.0 + 2.0 * phase / symmetry
            return 1.0 - 2.0 * (phase - symmetry) / max(0.001, 1.0 - symmetry)
        if waveform == "NOIS":
            return 0.68 * math.sin(phase * math.tau * 11.0) + 0.25 * math.sin(phase * math.tau * 31.0)
        if waveform == "DC":
            return 0.0
        if waveform == "USER":
            return 0.78 * math.sin(phase * math.tau) + 0.22 * math.sin(phase * math.tau * 3.0)
        if waveform == "SINC":
            x = (phase - 0.5) * 10.0
            if abs(x) < 1e-6:
                return 1.0
            return math.sin(math.pi * x) / (math.pi * x)
        if waveform == "EXP_RISE":
            return -1.0 + 2.0 * (1.0 - math.exp(-5.0 * phase)) / (1.0 - math.exp(-5.0))
        if waveform == "EXP_FALL":
            return -1.0 + 2.0 * math.exp(-5.0 * phase)
        if waveform == "CARDIAC":
            p = phase
            qrs = math.exp(-((p - 0.22) / 0.035) ** 2) * 1.15
            pre = -0.22 * math.exp(-((p - 0.16) / 0.025) ** 2)
            post = 0.36 * math.exp(-((p - 0.48) / 0.10) ** 2)
            return max(-1.0, min(1.0, qrs + pre + post - 0.25))
        if waveform == "GAUSS":
            return 2.0 * math.exp(-((phase - 0.5) / 0.18) ** 2) - 1.0
        if waveform == "HAVERSINE":
            return -math.cos(phase * math.tau)
        if waveform == "LORENTZ":
            gamma = 0.09
            return 2.0 * (gamma * gamma / ((phase - 0.5) ** 2 + gamma * gamma)) - 1.0
        if waveform == "DUALTONE":
            return 0.55 * math.sin(phase * math.tau) + 0.35 * math.sin(phase * math.tau * 2.7)
        return 0.55 * math.sin(phase * math.tau) + 0.35 * math.sin(phase * math.tau * 5.0)

    def _draw_labels(self, painter: QPainter, panel: QRectF) -> None:
        waveform = normalize_waveform(self._state.waveform)
        title_font = QFont(painter.font())
        title_font.setPointSize(22)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#0f2f4d"))
        painter.drawText(
            panel.adjusted(24, 14, -24, -14),
            Qt.AlignTop | Qt.AlignLeft,
            WAVEFORM_TITLES.get(waveform, waveform),
        )

        tag_font = QFont(painter.font())
        tag_font.setPointSize(13)
        tag_font.setBold(False)
        painter.setFont(tag_font)
        painter.setPen(QColor("#40546a"))
        detail = "  |  ".join(
            part
            for part in (
                self._state.channel_text,
                WAVEFORM_TITLES.get(waveform, waveform),
                self._state.frequency_text,
                self._state.level_text,
                self._state.load_text,
                self._state.burst_text,
                self._state.output_text,
            )
            if part
        )
        detail_rect = QRectF(panel.left() + 24, panel.bottom() - 58, panel.width() - 48, 42)
        painter.drawText(detail_rect, Qt.AlignVCenter | Qt.AlignLeft | Qt.TextWordWrap, detail)
