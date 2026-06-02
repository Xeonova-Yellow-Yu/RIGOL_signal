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
SYSTEM_ERROR_DRAIN_LIMIT = 8


@dataclass(frozen=True)
class ConnectResult:
    idn: str
    backend: str


class VisaUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class SystemErrorReadResult:
    errors: list[str]
    cleared: bool


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
        self._drain_system_errors_before_apply(settings.channel)
        try:
            self.write_many(commands)
        except Exception:
            if settings.burst.enabled:
                self._best_effort_restore_burst(settings)
            raise
        self._try_wait_for_operation(f"CH{settings.channel} 配置")
        self._log_apply_readbacks(settings)
        self._raise_system_errors_after_apply(settings.channel)
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

    def _try_wait_for_operation(self, label: str) -> None:
        try:
            reply = self.query("*OPC?").strip()
        except Exception as exc:
            self._log(f"{label} *OPC? 确认失败（非致命）: {exc}")
            return
        if _parse_state_reply(reply) is not True:
            self._log(f"{label} *OPC? 回复异常: {reply or '<empty>'}")

    def _best_effort_restore_burst(self, settings: ChannelSettings) -> None:
        channel = settings.channel
        try:
            self.write(build_burst_state_command(channel, True))
            self.write(f":SOUR{channel}:BURS:TRIG:SOUR {settings.burst.trigger_source}")
        except Exception as exc:
            self._log(f"CH{channel} Burst 恢复开启失败（非致命）: {exc}")

    def _log_apply_readbacks(self, settings: ChannelSettings) -> None:
        for query in _build_apply_readback_queries(settings):
            try:
                reply = self.query(query).strip()
            except Exception as exc:
                self._log(f"CH{settings.channel} 参数回读失败 {query}: {exc}")
                continue
            self._log(f"CH{settings.channel} 参数回读 {query} = {reply}")

    def _drain_system_errors_before_apply(self, channel: int) -> None:
        result = self._read_system_errors(channel, "下发前")
        for error in result.errors:
            self._log(f"CH{channel} 清除历史 SCPI 错误: {error}")
        if not result.cleared:
            raise RuntimeError(f"CH{channel} 下发前 SCPI 错误队列未清空，已中止应用")

    def _raise_system_errors_after_apply(self, channel: int) -> None:
        result = self._read_system_errors(channel, "下发后")
        if result.errors:
            joined = "; ".join(result.errors)
            raise RuntimeError(f"CH{channel} SCPI 错误: {joined}")
        if not result.cleared:
            raise RuntimeError(f"CH{channel} 下发后 SCPI 错误队列未清空")

    def _read_system_errors(self, channel: int, label: str) -> SystemErrorReadResult:
        errors: list[str] = []
        for _attempt in range(SYSTEM_ERROR_DRAIN_LIMIT):
            try:
                reply = self.query_system_error()
            except Exception as exc:
                self._log(f"CH{channel} {label} SCPI 错误队列读取失败（非致命）: {exc}")
                return SystemErrorReadResult(errors=errors, cleared=False)
            if _is_clear_system_error(reply):
                return SystemErrorReadResult(errors=errors, cleared=True)
            errors.append(reply)
        self._log(f"CH{channel} {label} SCPI 错误队列超过 {SYSTEM_ERROR_DRAIN_LIMIT} 条，已停止读取")
        return SystemErrorReadResult(errors=errors, cleared=False)

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


def _is_clear_system_error(reply: str) -> bool:
    token = reply.strip()
    return token.startswith("0") or token.startswith("+0")


def _build_apply_readback_queries(settings: ChannelSettings) -> list[str]:
    ch = settings.channel
    src = f":SOUR{ch}"
    waveform = normalize_waveform(settings.waveform)
    queries: list[str] = []
    if waveform not in {"DC", "NOIS"}:
        if settings.frequency_mode == "period":
            queries.append(f"{src}:PER?")
        else:
            queries.append(f"{src}:FREQ?")
        if waveform == "PULS":
            queries.append(f"{src}:PULS:WIDT?")
        queries.append(f"{src}:PHAS?")
    if settings.burst.enabled:
        queries.extend(
            [
                f"{src}:BURS:STAT?",
                f"{src}:BURS:MODE?",
                f"{src}:BURS:TRIG:SOUR?",
                f"{src}:BURS:IDLE?",
            ]
        )
        if settings.burst.mode == "TRIG":
            queries.append(f"{src}:BURS:NCYC?")
    return queries
