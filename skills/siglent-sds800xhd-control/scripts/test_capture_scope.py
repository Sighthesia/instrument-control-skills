#!/usr/bin/env python3
"""Offline tests for the capture-time instrument-measurement contract.

The waveform path is exercised through a scripted ScopeSession, so the tests pin
ordering and failure behaviour rather than re-testing IEEE framing (which
``test_scope_protocol.py`` covers): measurements are read only after every
payload and descriptor is saved, an unreadable reply is never recorded as zero,
and a measurement transport failure stops the session before the optional
screenshot.
"""

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import capture_scope
from scope_protocol import ScopeProtocolError, ScopeSession


IDN = "Siglent Technologies,SDS824X HD,SDS08A0Q909185,4.8.12.1.1.6.5"


def wavedesc_bytes(*, points: int = 4) -> bytes:
    """Build the minimal 346-byte legacy WAVEDESC the capture path parses."""

    raw = bytearray(346)
    raw[:8] = b"WAVEDESC"
    struct.pack_into("<h", raw, 32, 0)  # COMM_TYPE BYTE
    struct.pack_into("<h", raw, 34, 0)  # COMM_ORDER LSB
    struct.pack_into("<i", raw, 36, 346)
    struct.pack_into("<i", raw, 60, points)
    struct.pack_into("<i", raw, 116, points)
    struct.pack_into("<f", raw, 156, 2.0)
    struct.pack_into("<f", raw, 164, 30.0)
    struct.pack_into("<h", raw, 172, 8)
    struct.pack_into("<f", raw, 176, 2.0e-7)  # sample interval
    struct.pack_into("<d", raw, 180, 0.0)  # horizontal offset
    struct.pack_into("<h", raw, 324, 28)
    struct.pack_into("<f", raw, 328, 10.0)  # probe
    return bytes(raw)


class LegacyCaptureScope(ScopeSession):
    """A ScopeSession double for one legacy stopped-frame read."""

    def __init__(self, answers=None, *, failures=None, payload=b"\x01\x02\x03\x04"):
        super().__init__("example.invalid", timeout_s=0.01)
        self.sent: list[str] = []
        self.failures = dict(failures or {})
        self.payload = payload
        self.descriptor = wavedesc_bytes(points=len(payload))
        self.answers = {
            "*IDN?": IDN,
            "SAST?": "Stop",
            "TRMD?": "SINGle",
            "ACQ:POIN?": str(len(payload)),
            "ACQ:MDEP?": "25M",
            "SARA?": "5.00E+06",
            "TDIV?": "5.00E-01",
            "TRDL?": "2.00E+00",
            "TIM:SCAL?": "5.00E-01",
            "TIM:DEL?": "2.00E+00",
            "TIM:REF:POS?": "50",
            "WFSU?": "NP,0,FP,0,SP,1",
            ":TRIGger:TYPE?": "EDGE",
            ":TRIGger:EDGE:SOURce?": "C1",
            ":TRIGger:EDGE:SLOPe?": "RISing",
            ":TRIGger:EDGE:LEVel?": "2.50E+00",
            ":TRIGger:EDGE:COUPling?": "DC",
            ":TRIGger:EDGE:HOLDoff?": "1.00E-08",
            ":TRIGger:EDGE:NREJect?": "OFF",
            ":TRIGger:EDGE:IMPedance?": "ONEMeg",
            "C1:VDIV?": "2.00E+00V",
            "C1:OFST?": "0.00E+00V",
            "C2:VDIV?": "2.00E+00V",
            "C2:OFST?": "0.00E+00V",
            ":MEASure:SIMPle:SOURce?": ["C1", "C1"],
            ":MEASure:SIMPle:VALue? PKPK": "3.30000E+00",
            ":MEASure:SIMPle:VALue? TOP": "3.30000E+00",
            ":MEASure:SIMPle:VALue? BASE": "0.00E+00",
            ":CHANnel1:UNIT?": "V",
            ":CHANnel2:UNIT?": "V",
        }
        self.answers.update(answers or {})

    def connect(self):
        return None

    def close(self):
        return None

    def write(self, command, *, allow_after_stop=False, explicit_release=False):
        self.sent.append(command)
        self._check_allowed(command, explicit_release=explicit_release)

    def query_ascii(self, command, *, allow_after_stop=False):
        self.sent.append(command)
        self._check_allowed(command)
        failure = self.failures.get(command)
        if failure is not None:
            raise failure
        if command not in self.answers:
            raise AssertionError(f"unscripted query: {command}")
        reply = self.answers[command]
        if isinstance(reply, list):
            return reply.pop(0) if len(reply) > 1 else reply[0]
        return reply

    def query_block(self, command, *, allow_after_stop=False):
        self.sent.append(command)
        self._check_allowed(command)
        normalized = command.strip().upper()
        if ":WF? DESC" in normalized:
            missing = self.expected_channels - self.dat2_channels
            if missing:
                raise ScopeProtocolError(f"DESC is deferred until DAT2 is read for every selected channel; missing {sorted(missing)}")
            payload = self.descriptor
        else:
            payload = self.payload
            self.dat2_channels.add(normalized.split(":", 1)[0])
        return SimpleNamespace(
            payload=payload,
            raw=b"\x00DAT2," + payload,
            prefix=b"\x00DAT2,",
            sha256="0" * 64,
            payload_length=len(payload),
        )


def run_capture(scope, out_dir, *extra):
    arguments = [
        "capture_scope.py",
        "--host",
        "example.invalid",
        "--out",
        str(out_dir),
        "--mode",
        "legacy",
        "--existing-stopped",
        *extra,
    ]
    with mock.patch.object(sys, "argv", arguments):
        with mock.patch.object(capture_scope, "ScopeSession", lambda *args, **kwargs: scope):
            return capture_scope.main()


class CaptureMeasurementOrderTests(unittest.TestCase):
    def test_measurements_follow_every_waveform_and_descriptor(self):
        scope = LegacyCaptureScope()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            code = run_capture(scope, out, "--channels", "C1", "--read-descriptors")
            self.assertEqual(code, 0)
            self.assertTrue((out / "manifest.json").exists())
            self.assertEqual((out / "C1" / "legacy-DAT2.payload.bin").read_bytes(), scope.payload)

            dat2_at = scope.sent.index("C1:WF? DAT2")
            desc_at = scope.sent.index("C1:WF? DESC")
            source_at = scope.sent.index(":MEASure:SIMPle:SOURce?")
            self.assertLess(dat2_at, desc_at)
            self.assertLess(desc_at, source_at)
            self.assertTrue(all(":MEASure:" not in command for command in scope.sent[:desc_at]))

    def test_unreadable_measurement_is_recorded_unverified_not_zero(self):
        scope = LegacyCaptureScope({":MEASure:SIMPle:VALue? PKPK": "***"})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.assertEqual(run_capture(scope, out, "--channels", "C1"), 0)
            manifest = json.loads((out / "manifest.json").read_text())
            pkpk = manifest["instrument_measurements"]["C1"]["pkpk"]
            self.assertIsNone(pkpk["value"])
            self.assertEqual(pkpk["status"], "UNVERIFIED")
            self.assertEqual(pkpk["raw"], "***")

    def test_single_channel_capture_does_not_claim_a_foreign_measurement(self):
        scope = LegacyCaptureScope()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.assertEqual(run_capture(scope, out, "--channels", "C2"), 0)
            manifest = json.loads((out / "manifest.json").read_text())
            c2 = manifest["instrument_measurements"]["C2"]
            self.assertEqual(c2["source"], "C1")
            self.assertEqual(c2["source_attribution"], "other-source")
            self.assertIsNone(c2["pkpk"]["value"])
            self.assertEqual(c2["pkpk"]["status"], "UNVERIFIED")
            self.assertIn("C1", c2["pkpk"]["reason"])
            self.assertNotIn("C1", manifest["instrument_measurements"])

    def test_only_the_source_channel_gets_the_measurement_in_a_multi_channel_capture(self):
        scope = LegacyCaptureScope()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.assertEqual(run_capture(scope, out, "--channels", "C1", "C2"), 0)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(manifest["instrument_measurements"]["C1"]["pkpk"]["value"], 3.3)
            self.assertIsNone(manifest["instrument_measurements"]["C2"]["pkpk"]["value"])
            self.assertEqual(manifest["instrument_measurements"]["C2"]["pkpk"]["status"], "UNVERIFIED")

    def test_unknown_unit_is_not_exported_as_a_level(self):
        scope = LegacyCaptureScope({":CHANnel1:UNIT?": "***"})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.assertEqual(run_capture(scope, out, "--channels", "C1"), 0)
            manifest = json.loads((out / "manifest.json").read_text())
            pkpk = manifest["instrument_measurements"]["C1"]["pkpk"]
            self.assertIsNone(pkpk["value"])
            self.assertEqual(pkpk["status"], "UNVERIFIED")
            self.assertEqual(pkpk["raw"], "3.30000E+00")
            self.assertIsNone(capture_scope.bundle_instrument_measurement(manifest, "C1"))

    def test_empty_overflow_and_error_text_measurements_are_unverified(self):
        for raw in ("", "1E999", "ERROR 0", "-113,\"Undefined header;MEAS:VAL?\""):
            with self.subTest(raw=raw):
                scope = LegacyCaptureScope({":MEASure:SIMPle:VALue? PKPK": raw})
                with tempfile.TemporaryDirectory() as tmp:
                    out = Path(tmp)
                    self.assertEqual(run_capture(scope, out, "--channels", "C1"), 0)
                    manifest = json.loads((out / "manifest.json").read_text())
                    pkpk = manifest["instrument_measurements"]["C1"]["pkpk"]
                    self.assertIsNone(pkpk["value"])
                    self.assertEqual(pkpk["status"], "UNVERIFIED")
                    self.assertEqual(pkpk["raw"], raw)

    def test_measurement_timeout_keeps_the_frame_and_skips_the_screenshot(self):
        scope = LegacyCaptureScope(
            failures={":MEASure:SIMPle:VALue? PKPK": ScopeProtocolError("no usable ASCII response for :MEASure:SIMPle:VALue? PKPK")}
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with mock.patch.object(capture_scope, "capture_optional_screenshot") as screenshot:
                code = run_capture(scope, out, "--channels", "C1", "--screenshot")
            self.assertEqual(code, 0)
            self.assertTrue((out / "manifest.json").exists())
            self.assertEqual((out / "C1" / "legacy-DAT2.payload.bin").read_bytes(), scope.payload)

            manifest = json.loads((out / "manifest.json").read_text())
            self.assertIn("no usable ASCII response", manifest["instrument_measurements_error"])
            self.assertEqual(manifest["screenshot"]["status"], "NOT_ATTEMPTED")
            self.assertIn("no later query", manifest["screenshot"]["reason"])
            screenshot.assert_not_called()
            self.assertEqual(scope.sent[-1], ":MEASure:SIMPle:VALue? PKPK")
            self.assertEqual(scope.sent.count(":MEASure:SIMPle:SOURce?"), 1)
            self.assertNotIn(":CHANnel1:UNIT?", scope.sent)

    def test_a_healthy_measurement_read_keeps_the_screenshot_last(self):
        scope = LegacyCaptureScope()

        def fake_screenshot(captured_scope, root):
            captured_scope.sent.append("SCREENSHOT")
            return {"status": "COMPLETE"}

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with mock.patch.object(capture_scope, "capture_optional_screenshot", side_effect=fake_screenshot) as screenshot:
                code = run_capture(scope, out, "--channels", "C1", "--screenshot")
            self.assertEqual(code, 0)
            screenshot.assert_called_once()
            self.assertEqual(scope.sent[-1], "SCREENSHOT")
            self.assertIn(":MEASure:SIMPle:SOURce?", scope.sent)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(manifest["screenshot"]["status"], "COMPLETE")
            self.assertNotIn("instrument_measurements_error", manifest)


if __name__ == "__main__":
    unittest.main()
