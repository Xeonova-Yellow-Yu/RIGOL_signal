from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .domain import BurstSettings, ChannelSettings


CONFIG_VERSION = 3
DEFAULT_VISA_ADDRESS = "TCPIP::192.168.1.191::INSTR"


@dataclass(frozen=True)
class ChannelUiConfig:
    """Per-channel UI state; empty unit strings mean use preferred defaults on first load."""

    frequency_unit: str = ""
    period_unit: str = ""
    level_voltage_unit: str = ""


@dataclass(frozen=True)
class DeviceConfig:
    active_channel: int = 1
    channels: dict[int, ChannelSettings] = field(default_factory=dict)
    channel_ui: dict[int, ChannelUiConfig] = field(default_factory=dict)


@dataclass(frozen=True)
class AppConfig:
    active_channel: int = 1
    visa_address: str = DEFAULT_VISA_ADDRESS
    visa_addresses: tuple[str, ...] = (DEFAULT_VISA_ADDRESS,)
    channels: dict[int, ChannelSettings] = field(default_factory=dict)
    devices: dict[str, DeviceConfig] = field(default_factory=dict)


def default_app_config() -> AppConfig:
    channels = {
        1: ChannelSettings(channel=1, waveform="SIN", frequency_hz=1000.0),
        2: ChannelSettings(channel=2, waveform="PULS", frequency_hz=500.0),
    }
    return AppConfig(
        active_channel=1,
        visa_address=DEFAULT_VISA_ADDRESS,
        visa_addresses=(DEFAULT_VISA_ADDRESS,),
        channels=channels,
        devices={
            DEFAULT_VISA_ADDRESS: DeviceConfig(
                active_channel=1,
                channels=dict(channels),
                channel_ui=_default_channel_ui(),
            )
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
    visa_address = visa_address.strip()

    visa_addresses = _visa_addresses_from_data(
        raw.get("visa_addresses"),
        fallback.visa_addresses,
        visa_address,
    )

    channels = _channels_from_dict(raw.get("channels", {}), fallback.channels)

    devices: dict[str, DeviceConfig] = {}
    raw_devices = raw.get("devices", {})
    if isinstance(raw_devices, dict):
        for address, device_data in raw_devices.items():
            if not isinstance(address, str) or not address.strip():
                continue
            devices[address.strip()] = _device_from_dict(device_data, channels)
    if not devices:
        devices[visa_address] = DeviceConfig(
            active_channel=int(active_channel),
            channels=dict(channels),
            channel_ui=_default_channel_ui(),
        )

    return AppConfig(
        active_channel=int(active_channel),
        visa_address=visa_address,
        visa_addresses=visa_addresses,
        channels=channels,
        devices=devices,
    )


def save_app_config(config: AppConfig, path: Path | None = None) -> Path:
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CONFIG_VERSION,
        "active_channel": config.active_channel,
        "visa_address": config.visa_address,
        "visa_addresses": list(_unique_addresses(config.visa_addresses, config.visa_address)),
        "channels": {
            str(channel): asdict(settings)
            for channel, settings in sorted(config.channels.items())
        },
        "devices": {
            address: {
                "active_channel": _valid_active_channel(device.active_channel, config.active_channel),
                "channels": {
                    str(channel): asdict(settings)
                    for channel, settings in sorted(device.channels.items())
                },
                "channel_ui": {
                    str(channel): asdict(ui)
                    for channel, ui in sorted(_normalized_channel_ui(device.channel_ui).items())
                },
            }
            for address, device in sorted(config.devices.items())
            if address.strip()
        },
    }
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)
    return path


def _valid_active_channel(value: Any, fallback: int = 1) -> int:
    return int(value) if value in (1, 2) else int(fallback if fallback in (1, 2) else 1)


def _default_channel_ui() -> dict[int, ChannelUiConfig]:
    return {
        1: ChannelUiConfig(),
        2: ChannelUiConfig(),
    }


def _unique_addresses(addresses: Any, primary: str = "") -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    candidates: list[Any] = []
    if primary:
        candidates.append(primary)
    if isinstance(addresses, (list, tuple)):
        candidates.extend(addresses)
    elif isinstance(addresses, str):
        candidates.append(addresses)
    for address in candidates:
        if not isinstance(address, str):
            continue
        item = address.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return tuple(result)


def _visa_addresses_from_data(data: Any, fallback: tuple[str, ...], primary: str) -> tuple[str, ...]:
    addresses = _unique_addresses(data, primary)
    if addresses:
        return addresses
    return _unique_addresses(fallback, primary)


def _channels_from_dict(data: Any, fallback: dict[int, ChannelSettings]) -> dict[int, ChannelSettings]:
    channels: dict[int, ChannelSettings] = {}
    raw_channels = data if isinstance(data, dict) else {}
    for channel in (1, 2):
        saved = raw_channels.get(str(channel), raw_channels.get(channel, {}))
        channels[channel] = _channel_from_dict(saved, fallback[channel])
    return channels


def _device_from_dict(data: Any, fallback_channels: dict[int, ChannelSettings]) -> DeviceConfig:
    if not isinstance(data, dict):
        return DeviceConfig(
            active_channel=1,
            channels=dict(fallback_channels),
            channel_ui=_default_channel_ui(),
        )
    active_channel = _valid_active_channel(data.get("active_channel", 1))
    channels = _channels_from_dict(data.get("channels", {}), fallback_channels)
    channel_ui = _channel_ui_from_dict(data.get("channel_ui", {}))
    return DeviceConfig(active_channel=active_channel, channels=channels, channel_ui=channel_ui)


def _normalized_channel_ui(data: dict[int, ChannelUiConfig]) -> dict[int, ChannelUiConfig]:
    normalized = _default_channel_ui()
    for channel in (1, 2):
        value = data.get(channel)
        if isinstance(value, ChannelUiConfig):
            normalized[channel] = value
    return normalized


def _channel_ui_from_dict(data: Any) -> dict[int, ChannelUiConfig]:
    result = _default_channel_ui()
    raw = data if isinstance(data, dict) else {}
    for channel in (1, 2):
        saved = raw.get(str(channel), raw.get(channel, {}))
        if not isinstance(saved, dict):
            continue
        frequency_unit = saved.get("frequency_unit", result[channel].frequency_unit)
        period_unit = saved.get("period_unit", result[channel].period_unit)
        level_voltage_unit = saved.get("level_voltage_unit", result[channel].level_voltage_unit)
        result[channel] = ChannelUiConfig(
            frequency_unit=frequency_unit if frequency_unit in {"Hz", "kHz", "MHz", ""} else "",
            period_unit=period_unit if period_unit in {"ms", "s", ""} else "",
            level_voltage_unit=level_voltage_unit if level_voltage_unit in {"V", "mV", ""} else "",
        )
    return result


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
    idle_mode = payload.get("idle_mode", fallback.idle_mode)
    if idle_mode not in ("FPT", "TOP", "CENTER", "BOTTOM", "USER"):
        payload["idle_mode"] = fallback.idle_mode
    try:
        idle_point = int(payload.get("idle_point", fallback.idle_point))
    except (TypeError, ValueError):
        idle_point = fallback.idle_point
    payload["idle_point"] = max(0, min(16383, idle_point))
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
