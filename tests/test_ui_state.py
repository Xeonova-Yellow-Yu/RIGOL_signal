from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rigol_dg1022z.ui_state import (
    burst_ui_state,
    coerce_burst_trigger_source,
    level_ui_state,
    waveform_ui_state,
)


class UiStateTests(unittest.TestCase):
    def test_dc_disables_timing_amplitude_and_burst(self) -> None:
        state = waveform_ui_state("DC")

        self.assertFalse(state.timing)
        self.assertFalse(state.amplitude)
        self.assertTrue(state.offset)
        self.assertFalse(state.high_low_mode)
        self.assertFalse(state.burst)

    def test_square_enables_duty_but_not_pulse_width(self) -> None:
        state = waveform_ui_state("SQU")

        self.assertTrue(state.duty)
        self.assertFalse(state.pulse_width)
        self.assertFalse(state.ramp_symmetry)

    def test_pulse_uses_duty_only(self) -> None:
        state = waveform_ui_state("PULS")

        self.assertTrue(state.duty)
        self.assertFalse(state.pulse_width)

    def test_level_state_follows_mode(self) -> None:
        state = level_ui_state("SIN", "high_low")

        self.assertFalse(state.amplitude)
        self.assertFalse(state.offset)
        self.assertTrue(state.high)
        self.assertTrue(state.low)

    def test_burst_state_matches_dg_logic(self) -> None:
        gated = burst_ui_state("SIN", True, "GAT", "EXT")
        internal = burst_ui_state("SIN", True, "TRIG", "INT")

        self.assertTrue(gated.gate_polarity)
        self.assertFalse(gated.trigger_source)
        self.assertTrue(internal.internal_period)
        self.assertFalse(internal.software_trigger)
        self.assertTrue(internal.idle_level)

    def test_trigger_source_coercion(self) -> None:
        self.assertEqual(coerce_burst_trigger_source("GAT", "MAN"), "EXT")
        self.assertEqual(coerce_burst_trigger_source("INF", "INT"), "MAN")


if __name__ == "__main__":
    unittest.main()
