from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable

from .domain import ChannelSettings
from .scpi import (
    build_all_outputs_off_commands,
    build_burst_state_command,
    build_burst_state_query,
    build_channel_apply_commands,
    build_fire_burst_command,
    build_output_command,
    build_phase_align_command,
    normalize_waveform,
)


LogFn = Callable[[str], None]
BURST_STATE_VERIFY_ATTEMPTS = 3
BURST_STATE_VERIFY_DELAY_S = 0.05


@dataclass(frozen=True)
class ConnectResult:
    idn: str
    backend: str


class VisaUnavailableError(RuntimeError):
    pass


def _parse_state_reply(reply: str) -> bool | None:
    token = reply.strip().upper()
    if token in {"1", "+1", "ON", "TRUE"}:
        return True
    if token in {"0", "+0", "OFF", "FALSE"}:
        return False
    try:
        return bool(int(float(token)))
    except ValueError:
        return None


class RigolVisaClient:
    def __init__(self, log: LogFn | None = None) -> None:
        self._log = log or (lambda _line: None)
        self._rm = None
        self._backend = ""
        self._inst = None
        self._lock = threading.RLock()

    @property
    def is_connected(self) -> bool:
        return self._inst is not None

    @property
    def backend(self) -> str:
        return self._backend

    def list_resources(self) -> tuple[str, ...]:
        rm = self._ensure_resource_manager()
        with self._lock:
            return tuple(str(item) for item in rm.list_resources())

    def connect(self, address: str, timeout_ms: int = 3000) -> ConnectResult:
        address = address.strip()
        if not address:
            raise ValueError("VISA 地址不能为空")
        rm = self._ensure_resource_manager()
        with self._lock:
            self.disconnect()
            inst = rm.open_resource(address)
            try:
                inst.timeout = int(timeout_ms)
                inst.write_termination = "\n"
                inst.read_termination = "\n"
            except Exception:
                pass
            idn = str(inst.query("*IDN?")).strip()
            self._inst = inst
        self._log(f"已连接 {address} [{self._backend}] {idn}")
        return ConnectResult(idn=idn, backend=self._backend)

    def disconnect(self) -> None:
        with self._lock:
            inst = self._inst
            self._inst = None
            if inst is None:
                return
            try:
                inst.close()
            except Exception as exc:
                self._log(f"断开时忽略异常: {exc}")

    def query_idn(self) -> str:
        return self.query("*IDN?").strip()

    def query_system_error(self) -> str:
        return self.query(":SYST:ERR?").strip()

    def write(self, command: str) -> None:
        inst = self._require_inst()
        with self._lock:
            inst.write(command)
        self._log(f"> {command}")

    def query(self, command: str) -> str:
        inst = self._require_inst()
        with self._lock:
            self._log(f"> {command}")
            reply = str(inst.query(command))
        self._log(f"< {reply.strip()}")
        return reply

    def write_many(self, commands: Iterable[str]) -> None:
        for command in commands:
            self.write(command)

    def apply_channel(self, settings: ChannelSettings) -> list[str]:
        commands = build_channel_apply_commands(settings)
        self._log(f"SCPI 下发 CH{settings.channel}: {len(commands)} 条")
        self.write_many(commands)
        waveform = normalize_waveform(settings.waveform)
        if waveform not in {"DC", "NOIS"}:
            try:
                reply = self.query(f":SOUR{settings.channel}:PHAS?").strip()
                self._log(f"CH{settings.channel} 仪器相位读回: {reply}")
            except Exception as exc:
                self._log(f"CH{settings.channel} 相位读回失败: {exc}")
        return commands

    def set_output(self, channel: int, enabled: bool) -> str:
        command = build_output_command(channel, enabled)
        self.write(command)
        return command

    def set_all_outputs_off(self, channels: tuple[int, ...] = (1, 2)) -> list[str]:
        commands = build_all_outputs_off_commands(channels)
        self.write_many(commands)
        return commands

    def set_burst_enabled(self, channel: int, enabled: bool) -> str:
        command = build_burst_state_command(channel, enabled)
        query = build_burst_state_query(channel)
        expected = "ON" if enabled else "OFF"
        last_reply = ""
        for attempt in range(1, BURST_STATE_VERIFY_ATTEMPTS + 1):
            self.write(command)
            if BURST_STATE_VERIFY_DELAY_S > 0:
                time.sleep(BURST_STATE_VERIFY_DELAY_S)
            try:
                last_reply = self.query(query).strip()
            except Exception as exc:
                self._log(f"CH{channel} Burst 状态确认失败 {attempt}/{BURST_STATE_VERIFY_ATTEMPTS}: {exc}")
                if attempt >= BURST_STATE_VERIFY_ATTEMPTS:
                    raise RuntimeError(f"CH{channel} Burst 状态确认失败") from exc
                continue

            actual = _parse_state_reply(last_reply)
            if actual is enabled:
                return command
            self._log(
                f"CH{channel} Burst 回读不一致 {attempt}/{BURST_STATE_VERIFY_ATTEMPTS}: "
                f"期望 {expected}, 实际 {last_reply or '<empty>'}"
            )

        raise RuntimeError(f"CH{channel} Burst 未切换到 {expected}，仪器回读: {last_reply or '<empty>'}")

    def fire_burst(self, channel: int) -> str:
        command = build_fire_burst_command(channel)
        self.write(command)
        return command

    def align_phase(self, channel: int | None = None) -> str:
        command = build_phase_align_command(channel)
        self.write(command)
        return command

    def _require_inst(self):
        if self._inst is None:
            raise RuntimeError("尚未连接信号发生器")
        return self._inst

    def _ensure_resource_manager(self):
        if self._rm is not None:
            return self._rm
        try:
            import pyvisa
        except Exception as exc:
            raise VisaUnavailableError("未安装 pyvisa，请先安装 requirements.txt") from exc

        try:
            self._rm = pyvisa.ResourceManager()
            self._backend = "default"
            self._log("VISA 后端: default")
            return self._rm
        except Exception as default_exc:
            self._log(f"默认 VISA 后端不可用，尝试 @py: {default_exc}")
            try:
                self._rm = pyvisa.ResourceManager("@py")
                self._backend = "@py"
                self._log("VISA 后端: @py")
                return self._rm
            except Exception as py_exc:
                raise VisaUnavailableError(
                    f"VISA 后端初始化失败: default={default_exc}; @py={py_exc}"
                ) from py_exc
