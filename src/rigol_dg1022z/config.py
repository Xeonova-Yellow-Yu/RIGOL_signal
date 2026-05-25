from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .domain import BurstSettings, ChannelSettings


CONFIG_VERSION = 1
DEFAULT_VISA_ADDRESS = "TCPIP::192.168.1.191::INSTR"


@dataclass(frozen=True)
class AppConfig:
    active_channel: int = 1
    visa_address: str = DEFAULT_VISA_ADDRESS
    channels: dict[int, ChannelSettings] = field(default_factory=dict)


def default_app_config() -> AppConfig:
    return AppConfig(
        active_channel=1,
        visa_address=DEFAULT_VISA_ADDRESS,
        channels={
            1: ChannelSettings(channel=1, waveform="SIN", frequency_hz=1000.0),
            2: ChannelSettings(channel=2, waveform="PULS", frequency_hz=500.0),
        },
    )


def default_config_path() -> Path:
    override = os.environ.get("RIGOL_DG1022Z_CONFIG")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    return base / "RigolDG1022Z" / "settings.json"


def load_app_config(path: Path | None = None, fallback: AppConfig | None = None) -> AppConfig:
    fallback = fallback or default_app_config()
    path = path or default_config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fallback
    except Exception:
        return fallback
    if not isinstance(raw, dict):
        return fallback

    active_channel = raw.get("active_channel", fallback.active_channel)
    if active_channel not in (1, 2):
        active_channel = fallback.active_channel

    visa_address = raw.get("visa_address", fallback.visa_address)
    if not isinstance(visa_address, str) or not visa_address.strip():
        visa_address = fallback.visa_address

    raw_channels = raw.get("channels", {})
    channels: dict[int, ChannelSettings] = {}
    for channel in (1, 2):
        saved = raw_channels.get(str(channel), {}) if isinstance(raw_channels, dict) else {}
        channels[channel] = _channel_from_dict(saved, fallback.channels[channel])

    return AppConfig(
        active_channel=int(active_channel),
        visa_address=visa_address.strip(),
        channels=channels,
    )


def save_app_config(config: AppConfig, path: Path | None = None) -> Path:
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CONFIG_VERSION,
        "active_channel": config.active_channel,
        "visa_address": config.visa_address,
        "channels": {
            str(channel): asdict(settings)
            for channel, settings in sorted(config.channels.items())
        },
    }
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)
    return path


def _channel_from_dict(data: Any, fallback: ChannelSettings) -> ChannelSettings:
    if not isinstance(data, dict):
        return fallback
    payload = _dataclass_payload(ChannelSettings, data, fallback)
    payload["burst"] = _burst_from_dict(data.get("burst"), fallback.burst)
    try:
        settings = ChannelSettings(**payload)
        settings.validate()
        return settings
    except Exception:
        return fallback


def _burst_from_dict(data: Any, fallback: BurstSettings) -> BurstSettings:
    if not isinstance(data, dict):
        return fallback
    payload = _dataclass_payload(BurstSettings, data, fallback)
    try:
        return BurstSettings(**payload)
    except Exception:
        return fallback


def _dataclass_payload(cls: type, data: dict[str, Any], fallback: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for item in fields(cls):
        if item.name in data:
            payload[item.name] = data[item.name]
        else:
            payload[item.name] = getattr(fallback, item.name)
    return payload
