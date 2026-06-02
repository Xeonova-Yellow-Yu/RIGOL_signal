from __future__ import annotations

from .domain import BurstSettings, ChannelSettings, InstrumentLimits


WAVEFORM_ALIASES = {
    "SINE": "SIN",
    "SINUSOID": "SIN",
    "SINUSOIDAL": "SIN",
    "SIN": "SIN",
    "SQUARE": "SQU",
    "SQU": "SQU",
    "PULSE": "PULS",
    "PULS": "PULS",
    "RAMP": "RAMP",
    "NOISE": "NOIS",
    "NOIS": "NOIS",
    "DC": "DC",
    "USER": "USER",
    "ARB": "USER",
}


COMMON_WAVEFORMS = [
    "SIN",
    "SQU",
    "PULS",
    "RAMP",
    "NOIS",
    "DC",
    "USER",
    "SINC",
    "EXP_RISE",
    "EXP_FALL",
    "CARDIAC",
    "GAUSS",
    "HAVERSINE",
    "LORENTZ",
    "DUALTONE",
]


WAVEFORM_CHOICES = [
    ("Sine\n正弦", "SIN"),
    ("Square\n方波", "SQU"),
    ("Ramp\n斜波", "RAMP"),
    ("Pulse\n脉冲", "PULS"),
    ("Noise\n噪声", "NOIS"),
    ("Arb\n任意波", "USER"),
]


def normalize_waveform(value: str) -> str:
    token = value.strip().upper().replace(" ", "_").replace("-", "_")
    return WAVEFORM_ALIASES.get(token, token)


def _num(value: float) -> str:
    return format(float(value), ".12g")


def _state(value: bool) -> str:
    return "ON" if value else "OFF"


def build_channel_apply_commands(
    settings: ChannelSettings,
    limits: InstrumentLimits | None = None,
) -> list[str]:
    settings.validate(limits)
    ch = settings.channel
    src = f":SOUR{ch}"
    out = f":OUTP{ch}"
    waveform = normalize_waveform(settings.waveform)

    commands = [
        f"{out}:STAT OFF",
        f"{src}:SWE:STAT OFF",
        f"{src}:MOD:STAT OFF",
    ]
    if not settings.burst.enabled:
        commands.append(f"{src}:BURS:STAT OFF")
    elif settings.burst.mode == "TRIG":
        commands.extend(
            [
                f"{src}:BURS:MODE TRIG",
                f"{src}:BURS:TRIG:SOUR MAN",
            ]
        )
    commands.append(f"{src}:FUNC {waveform}")

    supports_timing = waveform not in {"DC", "NOIS"}
    supports_phase = waveform not in {"DC", "NOIS"}

    if supports_timing:
        if settings.frequency_mode == "frequency":
            commands.append(f"{src}:FREQ {_num(settings.frequency_hz)}")
        else:
            commands.append(f"{src}:PER {_num(settings.period_s)}")

    commands.append(f"{out}:LOAD {'INF' if settings.load == 'INF' else '50'}")

    if waveform == "DC":
        commands.append(f"{src}:VOLT:OFFS {_num(settings.offset_v)}")
    elif settings.level_mode == "high_low":
        commands.extend(
            [
                f"{src}:VOLT:HIGH {_num(settings.high_v)}",
                f"{src}:VOLT:LOW {_num(settings.low_v)}",
            ]
        )
    else:
        commands.extend(
            [
                f"{src}:VOLT {_num(settings.amplitude_vpp)}",
                f"{src}:VOLT:OFFS {_num(settings.offset_v)}",
            ]
        )

    if waveform == "SQU":
        commands.append(f"{src}:FUNC:SQU:DCYC {_num(settings.duty_percent)}")
    elif waveform == "PULS":
        commands.append(f"{src}:PULS:WIDT {_num(settings.pulse_width_s)}")
    elif waveform == "RAMP":
        commands.append(f"{src}:FUNC:RAMP:SYMM {_num(settings.ramp_symmetry_percent)}")

    if supports_phase:
        commands.append(f"{src}:PHAS:ADJ {_num(settings.phase_deg)}")
    commands.extend(_build_burst_commands(src, settings.burst))
    commands.append(f"{out}:STAT {_state(settings.output_enabled)}")
    return commands


def _build_burst_commands(src: str, burst: BurstSettings) -> list[str]:
    if not burst.enabled:
        return []

    commands = [
        f"{src}:BURS:MODE {burst.mode}",
        f"{src}:BURS:PHAS {_num(burst.phase_deg)}",
    ]
    if burst.mode in ("TRIG", "INF"):
        commands.append(f"{src}:BURS:TDEL {_num(burst.delay_s)}")
    if burst.mode == "TRIG":
        commands.append(f"{src}:BURS:NCYC {int(burst.cycles)}")
    if burst.mode == "GAT":
        commands.append(f"{src}:BURS:GATE:POL {burst.gate_polarity}")

    if burst.trigger_source == "INT" and burst.mode == "TRIG":
        commands.append(f"{src}:BURS:INT:PER {_num(burst.internal_period_s)}")
    elif burst.trigger_source == "EXT":
        commands.append(f"{src}:BURS:TRIG:SLOP {burst.trigger_slope}")

    commands.append(build_burst_idle_command(src, burst))
    commands.append(f"{src}:BURS:STAT ON")
    commands.append(f"{src}:BURS:TRIG:SOUR {burst.trigger_source}")
    return commands


def build_burst_idle_command(src: str, burst: BurstSettings) -> str:
    if burst.idle_mode == "USER":
        return f"{src}:BURS:IDLE {int(burst.idle_point)}"
    return f"{src}:BURS:IDLE {burst.idle_mode}"


def build_output_command(channel: int, enabled: bool) -> str:
    if channel not in (1, 2):
        raise ValueError("DG1022Z 只支持 CH1/CH2")
    return f":OUTP{channel}:STAT {_state(enabled)}"


def build_all_outputs_off_commands(channels: tuple[int, ...] = (1, 2)) -> list[str]:
    return [build_output_command(channel, False) for channel in channels]


def build_burst_state_command(channel: int, enabled: bool) -> str:
    if channel not in (1, 2):
        raise ValueError("DG1022Z 只支持 CH1/CH2")
    return f":SOUR{channel}:BURS:STAT {_state(enabled)}"


def build_burst_state_query(channel: int) -> str:
    if channel not in (1, 2):
        raise ValueError("DG1022Z 只支持 CH1/CH2")
    return f":SOUR{channel}:BURS:STAT?"


def build_fire_burst_command(channel: int) -> str:
    if channel not in (1, 2):
        raise ValueError("DG1022Z 只支持 CH1/CH2")
    return f":SOUR{channel}:BURS:TRIG"


def build_phase_align_command(channel: int | None = None) -> str:
    if channel is None:
        return ":SOUR:PHAS:INIT"
    if channel not in (1, 2):
        raise ValueError("DG1022Z 只支持 CH1/CH2")
    if channel == 1:
        return ":SOUR1:PHAS:INIT"
    return ":SOUR2:PHAS:SYNC"
