from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rigol_dg1022z.domain import BurstSettings, ChannelSettings, ValidationError
from rigol_dg1022z.scpi import (
    build_burst_state_command,
    build_channel_apply_commands,
    build_fire_burst_command,
    build_output_command,
)


class ScpiBuilderTests(unittest.TestCase):
    def test_square_high_low_burst_commands(self) -> None:
        settings = ChannelSettings(
            channel=1,
            waveform="SQU",
            frequency_hz=1000.0,
            level_mode="high_low",
            high_v=3.3,
            low_v=0.0,
            duty_percent=25.0,
            phase_deg=45.0,
            output_enabled=True,
            load="50",
            burst=BurstSettings(
                enabled=True,
                mode="TRIG",
                cycles=3,
                trigger_source="MAN",
            ),
        )

        commands = build_channel_apply_commands(settings)

        self.assertIn(":SOUR1:FUNC SQU", commands)
        self.assertIn(":SOUR1:FREQ 1000", commands)
        self.assertIn(":SOUR1:VOLT:HIGH 3.3", commands)
        self.assertIn(":SOUR1:VOLT:LOW 0", commands)
        self.assertIn(":SOUR1:PHAS 45", commands)
        self.assertIn(":SOUR1:PHAS:INIT", commands)
        self.assertIn(":SOUR1:FUNC:SQU:DCYC 25", commands)
        self.assertIn(":SOUR1:BURS:NCYC 3", commands)
        self.assertIn(":SOUR1:BURS:TRIG:SOUR MAN", commands)
        self.assertEqual(commands[-2:], [":OUTP1:LOAD 50", ":OUTP1:STAT ON"])

    def test_pulse_period_and_width_commands(self) -> None:
        settings = ChannelSettings(
            channel=2,
            waveform="pulse",
            frequency_mode="period",
            period_s=0.002,
            pulse_width_s=0.0005,
            output_enabled=False,
        )

        commands = build_channel_apply_commands(settings)

        self.assertIn(":SOUR2:FUNC PULS", commands)
        self.assertIn(":SOUR2:PER 0.002", commands)
        self.assertIn(":SOUR2:PULS:WIDT 0.0005", commands)
        self.assertIn(":SOUR2:PULS:DCYC 50", commands)
        self.assertIn(":SOUR2:PHAS:SYNC", commands)
        self.assertEqual(commands[-1], ":OUTP2:STAT OFF")

    def test_gated_burst_requires_external_trigger(self) -> None:
        settings = ChannelSettings(
            burst=BurstSettings(enabled=True, mode="GAT", trigger_source="MAN")
        )

        with self.assertRaises(ValidationError):
            build_channel_apply_commands(settings)

    def test_dc_omits_timing_phase_and_uses_offset(self) -> None:
        settings = ChannelSettings(
            waveform="DC",
            frequency_hz=0.0,
            amplitude_vpp=0.0,
            offset_v=1.25,
            phase_deg=90.0,
        )

        commands = build_channel_apply_commands(settings)

        self.assertEqual(commands[0], ":SOUR1:FUNC DC")
        self.assertIn(":SOUR1:VOLT:OFFS 1.25", commands)
        self.assertNotIn(":SOUR1:FREQ 1000", commands)
        self.assertNotIn(":SOUR1:PHAS 90", commands)

    def test_dc_rejects_high_low_mode(self) -> None:
        settings = ChannelSettings(
            waveform="DC",
            level_mode="high_low",
            high_v=1.0,
            low_v=0.0,
        )

        with self.assertRaises(ValidationError):
            build_channel_apply_commands(settings)

    def test_dc_rejects_burst(self) -> None:
        settings = ChannelSettings(
            waveform="DC",
            burst=BurstSettings(enabled=True),
        )

        with self.assertRaises(ValidationError):
            build_channel_apply_commands(settings)

    def test_output_and_fire_commands_validate_channel(self) -> None:
        self.assertEqual(build_output_command(1, True), ":OUTP1:STAT ON")
        self.assertEqual(build_burst_state_command(1, True), ":SOUR1:BURS:STAT ON")
        self.assertEqual(build_fire_burst_command(2), ":SOUR2:BURS:TRIG")
        with self.assertRaises(ValueError):
            build_output_command(3, True)

    def test_phase_rejects_negative_value(self) -> None:
        settings = ChannelSettings(phase_deg=-90.0)

        with self.assertRaises(ValidationError):
            build_channel_apply_commands(settings)


if __name__ == "__main__":
    unittest.main()
