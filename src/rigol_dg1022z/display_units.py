from __future__ import annotations


def preferred_frequency_unit(frequency_hz: float) -> str:
    if abs(frequency_hz) >= 1_000_000.0:
        return "MHz"
    if abs(frequency_hz) >= 1_000.0:
        return "kHz"
    return "Hz"


def preferred_period_unit(period_s: float) -> str:
    return "s" if abs(period_s) >= 1.0 else "ms"
