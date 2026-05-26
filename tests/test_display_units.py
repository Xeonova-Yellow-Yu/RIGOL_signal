from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rigol_dg1022z.display_units import preferred_frequency_unit, preferred_period_unit


class DisplayUnitTests(unittest.TestCase):
    def test_preferred_frequency_unit_thresholds(self) -> None:
        self.assertEqual(preferred_frequency_unit(1_500_000.0), "MHz")
        self.assertEqual(preferred_frequency_unit(5_000.0), "kHz")
        self.assertEqual(preferred_frequency_unit(0.5), "Hz")
        self.assertEqual(preferred_frequency_unit(1_000_000.0), "MHz")
        self.assertEqual(preferred_frequency_unit(999.0), "Hz")

    def test_preferred_period_unit_thresholds(self) -> None:
        self.assertEqual(preferred_period_unit(0.002), "ms")
        self.assertEqual(preferred_period_unit(0.5), "ms")
        self.assertEqual(preferred_period_unit(0.999), "ms")
        self.assertEqual(preferred_period_unit(1.0), "s")
        self.assertEqual(preferred_period_unit(3.0), "s")


if __name__ == "__main__":
    unittest.main()
