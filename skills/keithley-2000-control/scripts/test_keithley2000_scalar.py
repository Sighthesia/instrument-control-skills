from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "assets" / "fixtures"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from keithley2000_scalar import (  # noqa: E402
    ParserError,
    parse_metadata,
    parse_response,
    read_frame,
)


class Keithley2000ScalarTests(unittest.TestCase):
    def test_read_frame_preserves_fixture_line_and_bytes(self):
        raw = (FIXTURES / "valid-reading.txt").read_bytes()
        frame = read_frame(raw)
        self.assertEqual(frame.content, b"+1.23456789E+00VDC, 0INTCHAN")
        self.assertEqual(frame.terminator, b"\n")
        self.assertEqual(frame.trailing, b"")

    def test_read_frame_preserves_crlf_terminator(self):
        frame = read_frame(b"+1.0E+00VDC\r\n")
        self.assertEqual(frame.content, b"+1.0E+00VDC")
        self.assertEqual(frame.terminator, b"\r\n")

    def test_valid_documented_ascii_reading_is_complete_with_evidence(self):
        raw = (FIXTURES / "valid-reading.txt").read_bytes()
        artifact = parse_response(
            raw,
            context={
                "function": "VOLTage:DC",
                "acquisition_complete": True,
                "query": ":MEASure:VOLTage:DC?",
            },
        )
        self.assertEqual(artifact["kind"], "scalar-measurement")
        self.assertEqual(artifact["measurement"]["value"], 1.23456789)
        self.assertEqual(artifact["measurement"]["unit"], "VDC")
        self.assertEqual(artifact["measurement"]["channel"], 0)
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        self.assertEqual(
            base64.b64decode(artifact["integrity"]["raw_response_base64"]), raw
        )

    def test_missing_function_context_is_incomplete(self):
        raw = (FIXTURES / "valid-reading.txt").read_bytes()
        artifact = parse_response(raw, context={"acquisition_complete": True})
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")
        self.assertIn("function_context_missing", artifact["integrity"]["reasons"])

    def test_unitless_sense_data_uses_explicit_context(self):
        raw = (FIXTURES / "unitless-reading.txt").read_bytes()
        artifact = parse_response(
            raw,
            context={
                "function": "VOLTage:DC",
                "unit": "V",
                "acquisition_complete": True,
                "query": ":SENSe:DATA?",
            },
        )
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        self.assertEqual(artifact["measurement"]["unit"], "V")
        self.assertEqual(artifact["measurement"]["unit_source"], "context")

    def test_unitless_value_without_context_is_incomplete(self):
        raw = (FIXTURES / "unitless-reading.txt").read_bytes()
        artifact = parse_response(raw, context={"function": "VOLTage:DC"})
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")
        self.assertIn("unit_missing", artifact["integrity"]["reasons"])

    def test_overflow_sentinel_is_not_a_finite_measurement(self):
        raw = (FIXTURES / "overflow-reading.txt").read_bytes()
        artifact = parse_response(raw, context={"function": "VOLTage:DC", "unit": "V"})
        self.assertIsNone(artifact["measurement"]["value"])
        self.assertEqual(artifact["measurement"]["reading_status"], "OVERFLOW")
        self.assertEqual(artifact["integrity"]["status"], "UNVERIFIED")

    def test_textual_overflow_status_is_preserved(self):
        artifact = parse_response(b"OVLD\n", context={"function": "VOLTage:DC", "unit": "V"})
        self.assertEqual(artifact["measurement"]["reading_status"], "OVERFLOW")
        self.assertEqual(artifact["integrity"]["status"], "UNVERIFIED")

    def test_error_queue_empty_sentinel_is_a_status_record(self):
        raw = (FIXTURES / "error-queue-empty.txt").read_bytes()
        artifact = parse_response(raw)
        self.assertEqual(artifact["kind"], "status-record")
        self.assertEqual(artifact["record"]["code"], 0)
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")

    def test_error_queue_nonzero_code_is_not_a_measurement(self):
        raw = (FIXTURES / "error-queue-nonzero.txt").read_bytes()
        artifact = parse_response(raw, response_type="error-queue")
        self.assertEqual(artifact["kind"], "status-record")
        self.assertEqual(artifact["record"]["code"], -225)
        self.assertIn("Out of memory", artifact["record"]["message"])
        self.assertEqual(artifact["integrity"]["status"], "UNVERIFIED")

    def test_error_queue_code_followed_by_numeric_text_is_not_auto_error(self):
        artifact = parse_response(b"+1.234E+00,2\n")
        self.assertEqual(artifact["integrity"]["status"], "UNSUPPORTED")

    def test_error_queue_overflow_means_error_history_is_incomplete(self):
        raw = (FIXTURES / "error-queue-overflow.txt").read_bytes()
        artifact = parse_response(raw, response_type="error-queue")
        self.assertEqual(artifact["record"]["code"], 350)
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")

    def test_empty_and_unterminated_responses_are_incomplete(self):
        empty = parse_response(b"")
        unterminated = parse_response((FIXTURES / "missing-terminator.txt").read_bytes())
        self.assertEqual(empty["integrity"]["status"], "INCOMPLETE")
        self.assertEqual(unterminated["integrity"]["status"], "INCOMPLETE")

    def test_bad_numeric_token_is_invalid(self):
        raw = (FIXTURES / "bad-number.txt").read_bytes()
        artifact = parse_response(raw)
        self.assertEqual(artifact["integrity"]["status"], "INVALID")

    def test_non_finite_numeric_token_is_invalid(self):
        artifact = parse_response(b"NaN\n")
        self.assertEqual(artifact["integrity"]["status"], "INVALID")

    def test_underflowing_numeric_token_is_invalid(self):
        artifact = parse_response(b"+1E-9999VDC\n")
        self.assertEqual(artifact["integrity"]["status"], "INVALID")

    def test_extra_lines_are_invalid_and_not_silently_ignored(self):
        raw = (FIXTURES / "extra-line.txt").read_bytes()
        artifact = parse_response(raw)
        self.assertEqual(artifact["integrity"]["status"], "INVALID")

    def test_multiple_values_are_unsupported(self):
        artifact = parse_response(b"+1.0E+00VDC,+2.0E+00VDC\n")
        self.assertEqual(artifact["integrity"]["status"], "UNSUPPORTED")

    def test_binary_block_is_unsupported(self):
        artifact = parse_response(b"#0\x00\x01\x02\n")
        self.assertEqual(artifact["integrity"]["status"], "UNSUPPORTED")

    def test_conflicting_context_unit_is_invalid(self):
        raw = (FIXTURES / "valid-reading.txt").read_bytes()
        artifact = parse_response(raw, context={"function": "VOLTage:DC", "unit": "A"})
        self.assertEqual(artifact["integrity"]["status"], "INVALID")

    def test_function_and_response_unit_conflict_is_invalid(self):
        raw = (FIXTURES / "valid-reading.txt").read_bytes()
        artifact = parse_response(raw, context={"function": "CURRent:DC"})
        self.assertEqual(artifact["integrity"]["status"], "INVALID")

    def test_period_seconds_context_has_time_dimension(self):
        raw = (FIXTURES / "period-reading.txt").read_bytes()
        artifact = parse_response(
            raw,
            context={
                "function": "PERiod",
                "unit": "s",
                "acquisition_complete": True,
            },
        )
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        self.assertEqual(artifact["measurement"]["unit"], "s")

    def test_temperature_function_and_unit_have_compatible_dimensions(self):
        raw = b"+2.350000E+01C\n"
        artifact = parse_response(
            raw,
            context={
                "function": "TEMPerature",
                "acquisition_complete": True,
            },
        )
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")

    def test_auto_mode_does_not_mistake_channel_for_error_queue(self):
        raw = (FIXTURES / "valid-reading.txt").read_bytes()
        frame = read_frame(raw)
        metadata = parse_metadata(frame)
        self.assertEqual(metadata["kind"], "scalar-measurement")


if __name__ == "__main__":
    unittest.main()
