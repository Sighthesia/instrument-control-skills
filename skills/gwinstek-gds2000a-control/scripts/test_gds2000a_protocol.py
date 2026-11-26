#!/usr/bin/env python3
"""Offline tests for the GDS-2000A protocol parsers.

No test opens a serial port or calls an instrument.  Real-response fixtures
were captured from a GDS-2104A (firmware V1.18, serial GEN182193) on
2026-11-26; the synthetic fixtures exercise rejection paths only.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gds2000a_protocol as protocol

ASSETS = Path(__file__).resolve().parent.parent / "assets"
HARDWARE = ASSETS / "fixtures" / "hardware"
SYNTHETIC = ASSETS / "fixtures" / "synthetic"


class IdentityTests(unittest.TestCase):
    def test_real_capture_is_complete(self) -> None:
        result = protocol.parse_identity(
            (HARDWARE / "identity.txt").read_bytes(), provenance="hardware-verified"
        )
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual("GDS-2104A", result["model"])
        self.assertEqual("GEN182193", result["serial"])
        self.assertEqual("V1.18", result["firmware"])
        self.assertEqual(4, result["profile"]["channels"])
        self.assertEqual("hardware-verified", result["integrity"]["support_level"])

    def test_missing_firmware_is_incomplete(self) -> None:
        result = protocol.parse_identity((SYNTHETIC / "identity-missing-firmware.txt").read_bytes())
        self.assertEqual("INCOMPLETE", result["status"])
        self.assertIn("firmware version is missing", result["integrity"]["reasons"])

    def test_wrong_family_is_invalid(self) -> None:
        result = protocol.parse_identity((SYNTHETIC / "identity-wrong-family.txt").read_bytes())
        self.assertEqual("INVALID", result["status"])

    def test_manual_example_with_p_prefixed_serial_is_accepted(self) -> None:
        result = protocol.parse_identity(b"GW,GDS-2064A,P930116,V0.82b\n")
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual("P930116", result["serial"])

    def test_extra_field_is_invalid(self) -> None:
        result = protocol.parse_identity(b"GW,GDS-2104A,GEN182193,V1.18,EXTRA\n")
        self.assertEqual("INVALID", result["status"])


class MeasurementTests(unittest.TestCase):
    def test_real_pk2pk_is_complete(self) -> None:
        result = protocol.parse_measurement(
            (HARDWARE / "measure-pk2pk.txt").read_bytes(),
            quantity="pk2pk",
            provenance="hardware-verified",
        )
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(0.08, result["value"])
        self.assertEqual("V or A", result["unit"])
        self.assertEqual("source-dependent", result["unit_status"])

    def test_vpp_alias_maps_to_pk2pk(self) -> None:
        result = protocol.parse_measurement(b"8.000E-02\n", quantity="vpp")
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual("pk2pk", result["quantity"])

    def test_ch_off_is_incomplete(self) -> None:
        result = protocol.parse_measurement(
            (HARDWARE / "measure-ch-off.txt").read_bytes(), quantity="pk2pk"
        )
        self.assertEqual("INCOMPLETE", result["status"])
        self.assertIsNone(result["value"])
        self.assertIn("source_channel_not_activated", result["integrity"]["reasons"])

    def test_chan_off_spelling_is_also_incomplete(self) -> None:
        result = protocol.parse_measurement(b"Chan Off\n", quantity="pk2pk")
        self.assertEqual("INCOMPLETE", result["status"])

    def test_observed_9_9e37_sentinel_is_not_a_measurement(self) -> None:
        result = protocol.parse_measurement(
            (HARDWARE / "measure-sentinel.txt").read_bytes(), quantity="pk2pk"
        )
        self.assertEqual("INCOMPLETE", result["status"])
        self.assertIsNone(result["value"])
        self.assertIn("instrument_no_result", result["integrity"]["reasons"])

    def test_nan_is_invalid(self) -> None:
        result = protocol.parse_measurement((SYNTHETIC / "measurement-nan.txt").read_bytes(), quantity="pk2pk")
        self.assertEqual("INVALID", result["status"])

    def test_malformed_number_is_invalid(self) -> None:
        result = protocol.parse_measurement(
            (SYNTHETIC / "measurement-malformed.txt").read_bytes(), quantity="pk2pk"
        )
        self.assertEqual("INVALID", result["status"])

    def test_double_lf_terminator_is_preserved_as_framing(self) -> None:
        result = protocol.parse_measurement(
            (HARDWARE / "trigger-frequency-double-lf.txt").read_bytes(),
            quantity="frequency",
            provenance="hardware-verified",
        )
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(2.0, result["value"])
        self.assertEqual(b"\n", protocol.read_frame(
            (HARDWARE / "trigger-frequency-double-lf.txt").read_bytes()
        ).trailing)

    def test_count_quantity_is_unitless(self) -> None:
        result = protocol.parse_measurement(b"6.000E+00\n", quantity="ppulse")
        self.assertEqual("COMPLETE", result["status"])
        self.assertIsNone(result["unit"])


class ErrorQueueTests(unittest.TestCase):
    def test_no_error_is_complete(self) -> None:
        result = protocol.parse_error_queue(
            (HARDWARE / "error-none.txt").read_bytes(), provenance="hardware-verified"
        )
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(0, result["code"])
        self.assertEqual("No error.", result["message"])

    def test_undefined_header_preserves_the_error(self) -> None:
        result = protocol.parse_error_queue((HARDWARE / "error-undefined-header.txt").read_bytes())
        self.assertEqual("UNVERIFIED", result["status"])
        self.assertEqual(-113, result["code"])
        self.assertEqual("Undefined header", result["message"])

    def test_parameter_not_allowed_is_preserved(self) -> None:
        result = protocol.parse_error_queue((HARDWARE / "error-parameter-not-allowed.txt").read_bytes())
        self.assertEqual("UNVERIFIED", result["status"])
        self.assertEqual(-108, result["code"])

    def test_queue_overflow_is_incomplete(self) -> None:
        result = protocol.parse_error_queue((SYNTHETIC / "error-overflow.txt").read_bytes())
        self.assertEqual("INCOMPLETE", result["status"])
        self.assertEqual(-350, result["code"])

    def test_drain_requires_a_no_error_record(self) -> None:
        result = protocol.drain_error_queue(
            [
                (HARDWARE / "error-undefined-header.txt").read_bytes(),
                (HARDWARE / "error-none.txt").read_bytes(),
            ]
        )
        self.assertTrue(result["complete"])
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(2, len(result["records"]))

    def test_drain_without_no_error_is_incomplete(self) -> None:
        result = protocol.drain_error_queue([(HARDWARE / "error-undefined-header.txt").read_bytes()])
        self.assertFalse(result["complete"])
        self.assertEqual("INCOMPLETE", result["status"])


class FramingTests(unittest.TestCase):
    def test_lf_and_crlf(self) -> None:
        self.assertEqual(b"\n", protocol.read_frame(b"OK\n").terminator)
        self.assertEqual(b"\r\n", protocol.read_frame(b"OK\r\n").terminator)
        self.assertEqual(b"OK", protocol.read_frame(b"OK\r\n").content)

    def test_unterminated_line_is_incomplete(self) -> None:
        with self.assertRaises(protocol.ProtocolError) as caught:
            protocol.read_frame(b"OK")
        self.assertEqual("INCOMPLETE", caught.exception.status)

    def test_extra_non_whitespace_bytes_are_invalid(self) -> None:
        with self.assertRaises(protocol.ProtocolError) as caught:
            protocol.read_frame(b"OK\nNEXT\n")
        self.assertEqual("INVALID", caught.exception.status)

    def test_empty_reply_is_a_framed_empty_line(self) -> None:
        frame = protocol.read_frame(b"\n")
        self.assertEqual(b"", frame.content)
        result = protocol.parse_error_queue(b"\n")
        self.assertEqual("INCOMPLETE", result["status"])

    def test_binary_block_is_not_a_line(self) -> None:
        with self.assertRaises(protocol.ProtocolError) as caught:
            protocol.read_frame(b"#40008\x00\x00")
        self.assertEqual("UNSUPPORTED", caught.exception.status)


class IEEEBlockTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        payload = b"\x00\x00\x01\x00\xff\xff\x02\x00"
        block = protocol.encode_ieee_block(payload)
        parsed = protocol.parse_ieee_block(block)
        self.assertEqual(payload, parsed.payload)
        self.assertEqual(8, parsed.declared_length)

    def test_truncated_block_is_incomplete(self) -> None:
        with self.assertRaises(protocol.ProtocolError) as caught:
            protocol.parse_ieee_block(b"#40008\x00\x00")
        self.assertEqual("INCOMPLETE", caught.exception.status)

    def test_indefinite_block_is_unsupported(self) -> None:
        with self.assertRaises(protocol.ProtocolError) as caught:
            protocol.parse_ieee_block(b"#0")
        self.assertEqual("UNSUPPORTED", caught.exception.status)

    def test_trailing_terminator_only_when_allowed(self) -> None:
        block = protocol.encode_ieee_block(b"\x00\x00") + b"\n"
        self.assertEqual(b"\n", protocol.parse_ieee_block(block, allow_terminator=True).trailing)
        with self.assertRaises(protocol.ProtocolError):
            protocol.parse_ieee_block(block)


class WaveformTests(unittest.TestCase):
    def test_real_capture_is_complete_with_code_domain_only(self) -> None:
        result = protocol.parse_waveform(
            (HARDWARE / "acquire1-memory.bin").read_bytes(), provenance="hardware-verified"
        )
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(5000, result["points"])
        self.assertEqual(10000, result["block_bytes"])
        self.assertEqual(1, result["trailing_bytes"])
        self.assertEqual("CH1", result["source"])
        self.assertEqual(1.0, result["vertical_scale"])
        self.assertEqual(1e-06, result["sampling_period"])
        self.assertEqual("UNVERIFIED", result["calibration"]["status"])
        self.assertEqual("code-domain-only", result["analysis_allowed"])
        self.assertEqual(256, result["code_min"])
        self.assertEqual(768, result["code_max"])
        self.assertEqual("little", result["sample_byte_order"])

    def test_headerless_block_is_unverified(self) -> None:
        result = protocol.parse_waveform((SYNTHETIC / "waveform-headerless.bin").read_bytes())
        self.assertEqual("UNVERIFIED", result["status"])
        self.assertTrue(result["headerless"])
        self.assertIn("headerless_block_has_no_scale_or_units", result["integrity"]["reasons"])

    def test_truncated_payload_is_incomplete(self) -> None:
        result = protocol.parse_waveform((SYNTHETIC / "waveform-truncated.bin").read_bytes())
        self.assertEqual("INCOMPLETE", result["status"])

    def test_declared_points_mismatch_is_invalid(self) -> None:
        result = protocol.parse_waveform((SYNTHETIC / "waveform-length-mismatch.bin").read_bytes())
        self.assertEqual("INVALID", result["status"])

    def test_odd_payload_is_invalid(self) -> None:
        result = protocol.parse_waveform((SYNTHETIC / "waveform-odd.bin").read_bytes())
        self.assertEqual("INVALID", result["status"])

    def test_extra_bytes_are_invalid(self) -> None:
        result = protocol.parse_waveform((SYNTHETIC / "waveform-trailing.bin").read_bytes())
        self.assertEqual("INVALID", result["status"])

    def test_missing_marker_is_invalid(self) -> None:
        result = protocol.parse_waveform((SYNTHETIC / "waveform-bad-header.bin").read_bytes())
        self.assertEqual("INVALID", result["status"])

    def test_inline_samples_are_signed_little_endian(self) -> None:
        result = protocol.parse_waveform(
            (SYNTHETIC / "waveform-headerless.bin").read_bytes(), include_samples=True
        )
        self.assertEqual([0, 1, -1, 2], result["samples"])

    def test_csv_export_refuses_overwrite(self) -> None:
        raw = (HARDWARE / "acquire1-memory.bin").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wave.csv"
            summary = protocol.waveform_to_csv(raw, path)
            self.assertEqual(5000, summary["points"])
            self.assertEqual(5001, len(path.read_text().splitlines()))
            with self.assertRaises(FileExistsError):
                protocol.waveform_to_csv(raw, path)
            protocol.waveform_to_csv(raw, path, overwrite=True)


class ExpectedArtifactTests(unittest.TestCase):
    def test_expected_identity_matches_parser(self) -> None:
        expected = json.loads((ASSETS / "expected-identity.json").read_text())
        actual = protocol.parse_identity(
            (HARDWARE / "identity.txt").read_bytes(), provenance="hardware-verified"
        )
        self.assertEqual(expected["status"], actual["status"])
        self.assertEqual(expected["model"], actual["model"])
        self.assertEqual(expected["integrity"]["raw_sha256"], actual["integrity"]["raw_sha256"])

    def test_expected_waveform_matches_parser(self) -> None:
        expected = json.loads((ASSETS / "expected-waveform.json").read_text())
        actual = protocol.parse_waveform(
            (HARDWARE / "acquire1-memory.bin").read_bytes(), provenance="hardware-verified"
        )
        for key in ("points", "block_bytes", "payload_sha256", "raw_sha256", "code_min", "code_max"):
            self.assertEqual(expected[key], actual[key])


if __name__ == "__main__":
    unittest.main()
