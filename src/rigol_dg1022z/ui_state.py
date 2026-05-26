from __future__ import annotations

from dataclasses import dataclass

from .scpi import normalize_waveform


@dataclass(frozen=True)
class WaveformUiState:
    timing: bool
    amplitude: bool
    offset: bool
    high_low_mode: bool
    phase: bool
    duty: bool
    pulse_width: bool
    ramp_symmetry: bool
    burst: bool


@dataclass(frozen=True)
class LevelUiState:
    amplitude: bool
    offset: bool
    high: bool
    low: bool


@dataclass(frozen=True)
class BurstUiState:
    fields: bool
    cycles: bool
    trigger_source: bool
    internal_period: bool
    phase: bool
    delay: bool
    gate_polarity: bool
    trigger_slope: bool
    software_trigger: bool


def waveform_ui_state(waveform: str) -> WaveformUiState:
    normalized = normalize_waveform(waveform)
    is_dc = normalized == "DC"
    is_noise = normalized == "NOIS"
    return WaveformUiState(
        timing=not (is_dc or is_noise),
        amplitude=not is_dc,
        offset=True,
        high_low_mode=not (is_dc or is_noise),
        phase=not (is_dc or is_noise),
        duty=normalized in {"SQU", "PULS"},
        pulse_width=False,
        ramp_symmetry=normalized == "RAMP",
        burst=not (is_dc or is_noise),
    )


def level_ui_state(waveform: str, level_mode: str) -> LevelUiState:
    wave = waveform_ui_state(waveform)
    if not wave.high_low_mode or level_mode != "high_low":
        return LevelUiState(
            amplitude=wave.amplitude,
            offset=wave.offset,
            high=False,
            low=False,
        )
    return LevelUiState(
        amplitude=False,
        offset=False,
        high=True,
        low=True,
    )


def burst_ui_state(
    waveform: str,
    enabled: bool,
    mode: str,
    trigger_source: str,
) -> BurstUiState:
    wave = waveform_ui_state(waveform)
    active = bool(enabled and wave.burst)
    is_triggered = mode == "TRIG"
    is_gated = mode == "GAT"
    uses_internal = active and is_triggered and trigger_source == "INT"
    uses_external = active and trigger_source == "EXT"
    return BurstUiState(
        fields=active,
        cycles=active and is_triggered,
        trigger_source=active and not is_gated,
        internal_period=uses_internal,
        phase=active,
        delay=active and not is_gated,
        gate_polarity=active and is_gated,
        trigger_slope=uses_external and not is_gated,
        software_trigger=active and is_triggered and trigger_source == "MAN",
    )


def coerce_burst_trigger_source(mode: str, trigger_source: str) -> str:
    if mode == "GAT":
        return "EXT"
    if mode != "TRIG" and trigger_source == "INT":
        return "MAN"
    return trigger_source
