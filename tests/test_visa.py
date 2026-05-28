from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import rigol_dg1022z.visa as visa_module
from rigol_dg1022z.visa import RigolVisaClient


class FakeInstrument:
    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.last_reply = replies[-1] if replies else ""
        self.writes: list[str] = []
        self.queries: list[str] = []

    def write(self, command: str) -> None:
        self.writes.append(command)

    def query(self, command: str) -> str:
        self.queries.append(command)
        if self.replies:
            self.last_reply = self.replies.pop(0)
        return self.last_reply


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


if __name__ == "__main__":
    unittest.main()
