from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rigol_dg1022z.domain import (
    ChannelSettings,
    ValidationError,
    amplitude_offset_from_high_low,
    duty_from_pulse_width,
    frequency_from_period,
    high_low_from_amplitude_offset,
    load_scale_factor,
    period_from_frequency,
    pulse_width_from_duty,
    scale_voltage_for_load_change,
)


class LoadScaleTests(unittest.TestCase):
    def test_same_load_is_unity(self) -> None:
        self.assertEqual(load_scale_factor("INF", "INF"), 1.0)
        self.assertEqual(load_scale_factor("50", "50"), 1.0)
        self.assertEqual(scale_voltage_for_load_change(2.0, "INF", "INF"), 2.0)

    def test_high_z_to_50_halves(self) -> None:
        self.assertEqual(load_scale_factor("INF", "50"), 0.5)
        self.assertEqual(scale_voltage_for_load_change(1.0, "INF", "50"), 0.5)
        self.assertEqual(scale_voltage_for_load_change(-1.0, "INF", "50"), -0.5)

    def test_50_to_high_z_doubles(self) -> None:
        self.assertEqual(load_scale_factor("50", "INF"), 2.0)
        self.assertEqual(scale_voltage_for_load_change(0.5, "50", "INF"), 1.0)
        self.assertEqual(scale_voltage_for_load_change(-0.5, "50", "INF"), -1.0)

    def test_level_expressions_roundtrip_like_generator(self) -> None:
        amplitude_vpp, offset_v = amplitude_offset_from_high_low(1.05, 0.0)

        self.assertAlmostEqual(amplitude_vpp, 1.05)
        self.assertAlmostEqual(offset_v, 0.525)
        self.assertEqual(high_low_from_amplitude_offset(amplitude_vpp, offset_v), (1.05, 0.0))

    def test_timing_expressions_roundtrip_like_generator(self) -> None:
        self.assertAlmostEqual(period_from_frequency(0.25), 4.0)
        self.assertAlmostEqual(frequency_from_period(4.0), 0.25)

    def test_pulse_width_and_duty_roundtrip_like_generator(self) -> None:
        width = pulse_width_from_duty(4.0, 80.0)

        self.assertAlmostEqual(width, 3.2)
        self.assertAlmostEqual(duty_from_pulse_width(4.0, width), 80.0)

    def test_amplitude_offset_rejects_derived_level_out_of_range(self) -> None:
        settings = ChannelSettings(
            level_mode="amplitude_offset",
            amplitude_vpp=20.0,
            offset_v=10.0,
        )

        with self.assertRaises(ValidationError):
            settings.validate()

    def test_high_low_rejects_too_small_level_difference(self) -> None:
        settings = ChannelSettings(
            level_mode="high_low",
            high_v=0.0005,
            low_v=0.0,
        )

        with self.assertRaises(ValidationError):
            settings.validate()


if __name__ == "__main__":
    unittest.main()
