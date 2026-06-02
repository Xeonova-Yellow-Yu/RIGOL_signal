from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Waveform = Literal["SIN", "SQU", "PULS", "RAMP", "NOIS", "DC", "USER"]
FrequencyMode = Literal["frequency", "period"]
LevelMode = Literal["amplitude_offset", "high_low"]
BurstMode = Literal["TRIG", "INF", "GAT"]
BurstIdleMode = Literal["FPT", "TOP", "CENTER", "BOTTOM", "USER"]
TriggerSource = Literal["INT", "EXT", "MAN"]
Polarity = Literal["NORM", "INV"]
Slope = Literal["POS", "NEG"]
LoadMode = Literal["50", "INF"]


class ValidationError(ValueError):
    """Raised when a requested instrument setting is not meaningful."""


def load_scale_factor(previous_load: LoadMode, new_load: LoadMode) -> float:
    if previous_load == new_load:
        return 1.0
    if previous_load == "INF" and new_load == "50":
        return 0.5
    if previous_load == "50" and new_load == "INF":
        return 2.0
    return 1.0


def scale_voltage_for_load_change(
    value: float,
    previous_load: LoadMode,
    new_load: LoadMode,
) -> float:
    return float(value) * load_scale_factor(previous_load, new_load)


def amplitude_offset_from_high_low(high_v: float, low_v: float) -> tuple[float, float]:
    high = float(high_v)
    low = float(low_v)
    return high - low, (high + low) / 2.0


def high_low_from_amplitude_offset(amplitude_vpp: float, offset_v: float) -> tuple[float, float]:
    half_amplitude = float(amplitude_vpp) / 2.0
    offset = float(offset_v)
    return offset + half_amplitude, offset - half_amplitude


def period_from_frequency(frequency_hz: float) -> float:
    frequency = float(frequency_hz)
    if frequency <= 0:
        return 0.0
    return 1.0 / frequency


def frequency_from_period(period_s: float) -> float:
    period = float(period_s)
    if period <= 0:
        return 0.0
    return 1.0 / period


def pulse_width_from_duty(
    period_s: float,
    duty_percent: float,
    limits: InstrumentLimits | None = None,
) -> float:
    limits = limits or InstrumentLimits()
    period = max(0.0, float(period_s))
    duty = _clamp_float(
        float(duty_percent),
        limits.min_duty_percent,
        limits.max_duty_percent,
    )
    maximum = min(limits.max_pulse_width_s, period * limits.max_duty_percent / 100.0)
    if maximum < limits.min_pulse_width_s:
        maximum = limits.min_pulse_width_s
    return _clamp_float(period * duty / 100.0, limits.min_pulse_width_s, maximum)


def duty_from_pulse_width(
    period_s: float,
    pulse_width_s: float,
    limits: InstrumentLimits | None = None,
) -> float:
    limits = limits or InstrumentLimits()
    period = float(period_s)
    if period <= 0:
        return limits.min_duty_percent
    return _clamp_float(
        float(pulse_width_s) / period * 100.0,
        limits.min_duty_percent,
        limits.max_duty_percent,
    )


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _canonical_waveform(value: str) -> str:
    token = value.strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "SINE": "SIN",
        "SINUSOID": "SIN",
        "SINUSOIDAL": "SIN",
        "SQUARE": "SQU",
        "PULSE": "PULS",
        "NOISE": "NOIS",
        "ARB": "USER",
    }
    return aliases.get(token, token)


@dataclass(frozen=True)
class InstrumentLimits:
    channels: tuple[int, ...] = (1, 2)
    min_frequency_hz: float = 1e-6
    max_frequency_hz: float = 25e6
    min_period_s: float = 1.0 / 25e6
    max_period_s: float = 1e6
    min_amplitude_vpp: float = 1e-3
    max_amplitude_vpp: float = 20.0
    min_voltage_v: float = -10.0
    max_voltage_v: float = 10.0
    min_duty_percent: float = 0.001
    max_duty_percent: float = 99.999
    min_phase_deg: float = 0.0
    max_phase_deg: float = 360.0
    min_pulse_width_s: float = 16e-9
    max_pulse_width_s: float = 999_999.0
    min_burst_cycles: int = 1
    max_burst_cycles: int = 1_000_000
    min_burst_idle_point: int = 0
    max_burst_idle_point: int = 16383


@dataclass(frozen=True)
class BurstSettings:
    enabled: bool = False
    mode: BurstMode = "TRIG"
    cycles: int = 1
    trigger_source: TriggerSource = "MAN"
    internal_period_s: float = 0.01
    phase_deg: float = 0.0
    delay_s: float = 0.0
    gate_polarity: Polarity = "NORM"
    trigger_slope: Slope = "POS"
    idle_mode: BurstIdleMode = "FPT"
    idle_point: int = 0

    def validate(self, limits: InstrumentLimits) -> None:
        if not self.enabled:
            return
        if self.mode not in ("TRIG", "INF", "GAT"):
            raise ValidationError(f"Burst 模式无效: {self.mode}")
        if self.trigger_source not in ("INT", "EXT", "MAN"):
            raise ValidationError(f"Burst 触发源无效: {self.trigger_source}")
        if self.mode == "GAT" and self.trigger_source != "EXT":
            raise ValidationError("门控 Burst 需要 EXT 外部触发源")
        if self.trigger_source == "INT" and self.mode != "TRIG":
            raise ValidationError("内部触发源仅适用于 N 周期 Burst")
        if self.mode == "TRIG" and not (
            limits.min_burst_cycles <= int(self.cycles) <= limits.max_burst_cycles
        ):
            raise ValidationError(
                f"Burst 周期数需在 {limits.min_burst_cycles}..{limits.max_burst_cycles}"
            )
        if self.internal_period_s <= 0:
            raise ValidationError("Burst 内部触发周期必须大于 0")
        if self.delay_s < 0:
            raise ValidationError("Burst 触发延时不能为负数")
        if not (limits.min_phase_deg <= self.phase_deg <= limits.max_phase_deg):
            raise ValidationError("Burst 相位超出范围")
        if self.idle_mode not in ("FPT", "TOP", "CENTER", "BOTTOM", "USER"):
            raise ValidationError(f"Burst 空闲电平模式无效: {self.idle_mode}")
        if not (
            limits.min_burst_idle_point
            <= int(self.idle_point)
            <= limits.max_burst_idle_point
        ):
            raise ValidationError(
                f"Burst 自定义空闲点需在 {limits.min_burst_idle_point}"
                f"..{limits.max_burst_idle_point}"
            )


@dataclass(frozen=True)
class ChannelSettings:
    channel: int = 1
    waveform: str = "SIN"
    frequency_mode: FrequencyMode = "frequency"
    frequency_hz: float = 1_000.0
    period_s: float = 0.001
    level_mode: LevelMode = "amplitude_offset"
    amplitude_vpp: float = 2.0
    offset_v: float = 0.0
    high_v: float = 1.0
    low_v: float = -1.0
    duty_percent: float = 50.0
    phase_deg: float = 0.0
    pulse_width_s: float = 0.0001
    ramp_symmetry_percent: float = 50.0
    output_enabled: bool = False
    load: LoadMode = "INF"
    burst: BurstSettings = field(default_factory=BurstSettings)

    def validate(self, limits: InstrumentLimits | None = None) -> None:
        limits = limits or InstrumentLimits()
        if self.channel not in limits.channels:
            raise ValidationError("DG1022Z 只支持 CH1/CH2")
        waveform = _canonical_waveform(self.waveform)
        if not waveform:
            raise ValidationError("波形类型不能为空")
        supports_timing = waveform not in {"DC", "NOIS"}
        supports_phase = supports_timing
        if self.burst.enabled and waveform in {"DC", "NOIS"}:
            raise ValidationError("DC/Noise 波形不支持 Burst")

        if self.frequency_mode not in ("frequency", "period"):
            raise ValidationError(f"频率/周期模式无效: {self.frequency_mode}")
        if supports_timing and self.frequency_mode == "frequency":
            if not (limits.min_frequency_hz <= self.frequency_hz <= limits.max_frequency_hz):
                raise ValidationError(
                    f"频率需在 {limits.min_frequency_hz:g}..{limits.max_frequency_hz:g} Hz"
                )
        elif supports_timing and self.frequency_mode == "period":
            if not (limits.min_period_s <= self.period_s <= limits.max_period_s):
                raise ValidationError(
                    f"周期需在 {limits.min_period_s:g}..{limits.max_period_s:g} s"
                )

        if self.level_mode not in ("amplitude_offset", "high_low"):
            raise ValidationError(f"电平模式无效: {self.level_mode}")
        if waveform in {"DC", "NOIS"} and self.level_mode == "high_low":
            raise ValidationError("DC/Noise 波形不支持高低电平模式")
        if self.level_mode == "amplitude_offset":
            if waveform != "DC" and not (
                limits.min_amplitude_vpp <= self.amplitude_vpp <= limits.max_amplitude_vpp
            ):
                raise ValidationError(
                    f"幅度需在 {limits.min_amplitude_vpp:g}..{limits.max_amplitude_vpp:g} Vpp"
                )
            self._validate_voltage("偏置", self.offset_v, limits)
            if waveform != "DC":
                high_v, low_v = high_low_from_amplitude_offset(
                    self.amplitude_vpp,
                    self.offset_v,
                )
                self._validate_voltage("高电平", high_v, limits)
                self._validate_voltage("低电平", low_v, limits)
        else:
            self._validate_voltage("高电平", self.high_v, limits)
            self._validate_voltage("低电平", self.low_v, limits)
            if self.high_v <= self.low_v:
                raise ValidationError("高电平必须大于低电平")
            amplitude_vpp, _offset_v = amplitude_offset_from_high_low(self.high_v, self.low_v)
            if not (limits.min_amplitude_vpp <= amplitude_vpp <= limits.max_amplitude_vpp):
                raise ValidationError(
                    f"高低电平差值需在 {limits.min_amplitude_vpp:g}..{limits.max_amplitude_vpp:g} Vpp"
                )

        if waveform in {"SQU", "PULS"} and not (
            limits.min_duty_percent <= self.duty_percent <= limits.max_duty_percent
        ):
            raise ValidationError("占空比需在 0.001..99.999%")
        if supports_phase and not (limits.min_phase_deg <= self.phase_deg <= limits.max_phase_deg):
            raise ValidationError("相位需在 -360..360 度")
        if waveform == "PULS" and not (
            limits.min_pulse_width_s <= self.pulse_width_s <= limits.max_pulse_width_s
        ):
            raise ValidationError("脉宽超出范围")
        if waveform == "RAMP" and not (0.0 <= self.ramp_symmetry_percent <= 100.0):
            raise ValidationError("斜波对称性需在 0..100%")
        if self.load not in ("50", "INF"):
            raise ValidationError("输出负载只能是 50Ω 或 High-Z")
        self.burst.validate(limits)

    @staticmethod
    def _validate_voltage(name: str, value: float, limits: InstrumentLimits) -> None:
        if not (limits.min_voltage_v <= value <= limits.max_voltage_v):
            raise ValidationError(f"{name}需在 {limits.min_voltage_v:g}..{limits.max_voltage_v:g} V")
