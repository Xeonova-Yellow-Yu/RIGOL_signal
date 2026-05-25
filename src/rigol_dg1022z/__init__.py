"""RIGOL DG1022Z desktop controller."""

from .domain import BurstSettings, ChannelSettings, InstrumentLimits
from .scpi import build_channel_apply_commands

__all__ = [
    "BurstSettings",
    "ChannelSettings",
    "InstrumentLimits",
    "build_channel_apply_commands",
]
