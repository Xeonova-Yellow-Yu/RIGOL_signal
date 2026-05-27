from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rigol_dg1022z.domain import load_scale_factor, scale_voltage_for_load_change


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


if __name__ == "__main__":
    unittest.main()
