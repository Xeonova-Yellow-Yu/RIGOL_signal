from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rigol_dg1022z.config import AppConfig, default_app_config, load_app_config, save_app_config
from rigol_dg1022z.domain import BurstSettings, ChannelSettings


class ConfigTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            config = AppConfig(
                active_channel=2,
                visa_address="USB0::0x1AB1::0x0642::DG1::INSTR",
                channels={
                    1: ChannelSettings(
                        channel=1,
                        waveform="SQU",
                        frequency_hz=1234.0,
                        duty_percent=35.0,
                        load="50",
                    ),
                    2: ChannelSettings(
                        channel=2,
                        waveform="PULS",
                        frequency_mode="period",
                        period_s=0.002,
                        burst=BurstSettings(enabled=True, mode="TRIG", cycles=7),
                    ),
                },
            )

            save_app_config(config, path)
            loaded = load_app_config(path, default_app_config())

            self.assertEqual(loaded.active_channel, 2)
            self.assertEqual(loaded.visa_address, "USB0::0x1AB1::0x0642::DG1::INSTR")
            self.assertEqual(loaded.channels[1].waveform, "SQU")
            self.assertEqual(loaded.channels[1].load, "50")
            self.assertEqual(loaded.channels[2].period_s, 0.002)
            self.assertEqual(loaded.channels[2].burst.cycles, 7)

    def test_missing_or_invalid_config_uses_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fallback = default_app_config()
            missing = Path(tmp) / "missing.json"
            invalid = Path(tmp) / "invalid.json"
            invalid.write_text("{not valid json", encoding="utf-8")

            self.assertEqual(load_app_config(missing, fallback), fallback)
            self.assertEqual(load_app_config(invalid, fallback), fallback)


if __name__ == "__main__":
    unittest.main()
