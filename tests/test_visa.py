from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import rigol_dg1022z.visa as visa_module
from rigol_dg1022z.domain import BurstSettings, ChannelSettings
from rigol_dg1022z.visa import RigolVisaClient


class FakeInstrument:
    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.last_reply = replies[-1] if replies else ""
        self.writes: list[str] = []
        self.queries: list[str] = []
        self.events: list[tuple[str, str]] = []

    def write(self, command: str) -> None:
        self.writes.append(command)
        self.events.append(("write", command))

    def query(self, command: str) -> str:
        self.queries.append(command)
        self.events.append(("query", command))
        if self.replies:
            self.last_reply = self.replies.pop(0)
        return self.last_reply


class FailingWriteInstrument(FakeInstrument):
    def __init__(self, fail_on: str, replies: list[str] | None = None) -> None:
        super().__init__(replies or ['0,"No error"'])
        self.fail_on = fail_on

    def write(self, command: str) -> None:
        super().write(command)
        if command == self.fail_on:
            raise RuntimeError(f"write failed: {command}")


class VisaBurstStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_delay = visa_module.BURST_STATE_VERIFY_DELAY_S
        visa_module.BURST_STATE_VERIFY_DELAY_S = 0.0

    def tearDown(self) -> None:
        visa_module.BURST_STATE_VERIFY_DELAY_S = self._old_delay

    def test_set_burst_enabled_retries_until_readback_matches(self) -> None:
        inst = FakeInstrument(["1", "0"])
        client = RigolVisaClient()
        client._inst = inst

        command = client.set_burst_enabled(1, False)

        self.assertEqual(command, ":SOUR1:BURS:STAT OFF")
        self.assertEqual(inst.writes, [":SOUR1:BURS:STAT OFF", ":SOUR1:BURS:STAT OFF"])
        self.assertEqual(inst.queries, [":SOUR1:BURS:STAT?", ":SOUR1:BURS:STAT?"])

    def test_set_burst_enabled_raises_after_repeated_mismatch(self) -> None:
        inst = FakeInstrument(["1", "1", "1"])
        client = RigolVisaClient()
        client._inst = inst

        with self.assertRaises(RuntimeError):
            client.set_burst_enabled(1, False)

        self.assertEqual(len(inst.writes), visa_module.BURST_STATE_VERIFY_ATTEMPTS)
        self.assertEqual(len(inst.queries), visa_module.BURST_STATE_VERIFY_ATTEMPTS)

    def _pulse_external_burst_settings(self) -> ChannelSettings:
        return ChannelSettings(
            channel=1,
            waveform="PULS",
            frequency_mode="period",
            period_s=4.0,
            level_mode="high_low",
            high_v=1.05,
            low_v=0.0,
            duty_percent=80.0,
            pulse_width_s=3.2,
            output_enabled=False,
            burst=BurstSettings(
                enabled=True,
                mode="TRIG",
                cycles=1,
                trigger_source="EXT",
                idle_mode="USER",
                idle_point=0,
            ),
        )

    def test_apply_channel_keeps_enabled_external_burst_armed(self) -> None:
        inst = FakeInstrument(
            [
                '0,"No error"',
                "1",
                "4",
                "3.2",
                "0",
                "1",
                "TRIG",
                "EXT",
                "0",
                "1",
                '0,"No error"',
            ]
        )
        log_lines: list[str] = []
        client = RigolVisaClient(log_lines.append)
        client._inst = inst
        settings = self._pulse_external_burst_settings()

        commands = client.apply_channel(settings)

        self.assertNotIn(":SOUR1:PULS:DCYC 80", commands)
        self.assertNotIn(":SOUR1:BURS:STAT OFF", commands)
        temp_source_index = inst.events.index(("write", ":SOUR1:BURS:TRIG:SOUR MAN"))
        func_index = inst.events.index(("write", ":SOUR1:FUNC PULS"))
        slope_index = inst.events.index(("write", ":SOUR1:BURS:TRIG:SLOP POS"))
        burst_on_index = inst.events.index(("write", ":SOUR1:BURS:STAT ON"))
        final_source_index = inst.events.index(("write", ":SOUR1:BURS:TRIG:SOUR EXT"))
        opc_index = inst.events.index(("query", "*OPC?"))
        self.assertLess(temp_source_index, func_index)
        self.assertLess(slope_index, burst_on_index)
        self.assertLess(burst_on_index, final_source_index)
        self.assertLess(final_source_index, opc_index)
        self.assertEqual(inst.queries.count("*OPC?"), 1)
        self.assertIn(":SOUR1:PER?", inst.queries)
        self.assertIn(":SOUR1:PULS:WIDT?", inst.queries)
        self.assertIn(":SOUR1:BURS:TRIG:SOUR?", inst.queries)
        self.assertEqual(inst.queries[-1], ":SYST:ERR?")
        self.assertEqual(inst.queries.count(":SYST:ERR?"), 2)

    def test_apply_channel_clears_stale_error_before_apply(self) -> None:
        inst = FakeInstrument(
            [
                '-220,"Old parameter error"',
                '0,"No error"',
                "1",
                "4",
                "3.2",
                "0",
                "1",
                "TRIG",
                "EXT",
                "0",
                "1",
                '0,"No error"',
            ]
        )
        client = RigolVisaClient()
        client._inst = inst

        client.apply_channel(self._pulse_external_burst_settings())

        self.assertEqual(inst.queries.count(":SYST:ERR?"), 3)

    def test_apply_channel_aborts_when_stale_error_queue_does_not_clear(self) -> None:
        inst = FakeInstrument(
            [
                f'-220,"Old parameter error {index}"'
                for index in range(visa_module.SYSTEM_ERROR_DRAIN_LIMIT)
            ]
        )
        client = RigolVisaClient()
        client._inst = inst

        with self.assertRaisesRegex(RuntimeError, "未清空"):
            client.apply_channel(self._pulse_external_burst_settings())

        self.assertEqual(inst.queries.count(":SYST:ERR?"), visa_module.SYSTEM_ERROR_DRAIN_LIMIT)
        self.assertEqual(inst.writes, [])

    def test_apply_channel_raises_on_new_error_after_apply(self) -> None:
        inst = FakeInstrument(
            [
                '0,"No error"',
                "1",
                "4",
                "3.2",
                "0",
                "1",
                "TRIG",
                "EXT",
                "0",
                "1",
                '-220,"Parameter error"',
                '0,"No error"',
            ]
        )
        client = RigolVisaClient()
        client._inst = inst

        with self.assertRaisesRegex(RuntimeError, "SCPI"):
            client.apply_channel(self._pulse_external_burst_settings())

    def test_apply_channel_restores_burst_state_after_write_failure(self) -> None:
        inst = FailingWriteInstrument(":SOUR1:FUNC PULS")
        client = RigolVisaClient()
        client._inst = inst
        settings = ChannelSettings(
            channel=1,
            waveform="PULS",
            frequency_mode="period",
            period_s=4.0,
            level_mode="high_low",
            high_v=1.05,
            low_v=0.0,
            pulse_width_s=3.2,
            burst=BurstSettings(
                enabled=True,
                mode="TRIG",
                cycles=1,
                trigger_source="EXT",
            ),
        )

        with self.assertRaises(RuntimeError):
            client.apply_channel(settings)

        self.assertIn(("write", ":SOUR1:BURS:STAT ON"), inst.events)
        self.assertEqual(inst.events[-1], ("write", ":SOUR1:BURS:TRIG:SOUR EXT"))


if __name__ == "__main__":
    unittest.main()
