#!/usr/bin/env python3
import io
import unittest
from unittest.mock import patch

import read_decode_list as rdl


class _FakeSocket:
    def __init__(self, responses):
        # responses: list of bytes chunks to return from recv, or Timeout/EOF markers
        self._items = list(responses)
        self.sent = b""
        self.timeouts = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, data):
        self.sent += data

    def recv(self, _size):
        if not self._items:
            return b""
        item = self._items.pop(0)
        if item is TimeoutError:
            raise TimeoutError()
        return item


class ReadDecodeListTests(unittest.TestCase):
    def test_validate_query_rejects_writes_and_compounds(self):
        self.assertEqual(rdl._validate_query(" :DECode:LIST? \n"), ":DECode:LIST?")
        for bad in ("TRMD SINGLE", ":TRMD SINGLE?", "*RST?", "DEC?\nTRMD SINGLE", "DEC?;*RST?", "DEC"):
            with self.assertRaises(rdl.DecodeReadError):
                rdl._validate_query(bad)

    def test_port_5024_refused(self):
        with self.assertRaises(rdl.DecodeReadError):
            rdl.query_text("127.0.0.1", 5024, "DEC?")

    def test_multiline_complete_on_idle_after_final_newline(self):
        fake = _FakeSocket([b"SPI, Time, MISO, MOSI\n1,1ns,'[0]','[1]'\n", TimeoutError])
        with patch.object(rdl, "_connect", return_value=fake):
            res = rdl.query_text("127.0.0.1", 5025, ":DECode:LIST1:RESult?", first_byte_timeout=1.0, idle=0.2)
        self.assertEqual(res["end_reason"], "idle_timeout")
        self.assertTrue(res["likely_complete"])
        self.assertFalse(res["truncated_risk"])
        self.assertIn("SPI, Time", res["text"])

    def test_first_byte_timeout_reports_no_data(self):
        fake = _FakeSocket([TimeoutError])
        with patch.object(rdl, "_connect", return_value=fake):
            res = rdl.query_text("127.0.0.1", 5025, "DEC?", first_byte_timeout=0.2, idle=0.2)
        self.assertEqual(res["bytes"], 0)
        self.assertEqual(res["end_reason"], "first_byte_timeout")
        self.assertFalse(res["likely_complete"])

    def test_idle_timeout_without_final_newline_is_truncation_risk(self):
        fake = _FakeSocket([b"SPI, Time, MISO, MOSI\n1,1ns", TimeoutError])
        with patch.object(rdl, "_connect", return_value=fake):
            res = rdl.query_text("127.0.0.1", 5025, ":DECode:LIST1:RESult?")
        self.assertEqual(res["end_reason"], "idle_timeout")
        self.assertFalse(res["likely_complete"])
        self.assertTrue(res["truncated_risk"])
        self.assertIn("warning", res)

    def test_drain_system_errors_until_zero(self):
        calls = [
            {"text": '-113,"Undefined header;X"\n', "end_reason": "idle_timeout", "bytes": 1},
            {"text": '0,"No error"\n', "end_reason": "idle_timeout", "bytes": 1},
        ]
        with patch.object(rdl, "query_text", side_effect=calls):
            out = rdl.drain_system_errors("127.0.0.1", 5025)
        self.assertTrue(out["terminated"])
        self.assertEqual(len(out["entries"]), 1)
        self.assertIn("-113", out["entries"][0])

    def test_zero_byte_diagnosis_drains_errors(self):
        diag = {"command": "DEC?", "bytes": 0, "text": "", "end_reason": "first_byte_timeout",
                "likely_complete": False, "truncated_risk": False}
        drain = {"entries": ['-113,"Undefined header;BAD?"'], "terminated": True, "not_empty_after_limit": False}
        with patch.object(rdl, "query_text", return_value=diag), patch.object(rdl, "drain_system_errors", return_value=drain):
            res = rdl.query_text_with_diagnosis("127.0.0.1", 5025, "DEC?")
        self.assertEqual(res["system_error"]["entries"][0].split(",")[0], "-113")
        self.assertIn("warning", res)


if __name__ == "__main__":
    unittest.main()
