from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "assets" / "fixtures"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from keithley2000_scalar import (  # noqa: E402
    main,
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

    def test_skill_documented_reading_channel_shape_is_accepted(self):
        raw = b"+1.000000E+01VDC, 0INTCHAN\n"
        expected = json.loads((ROOT / "assets" / "expected-result.json").read_text(encoding="utf-8"))
        artifact = parse_response(
            raw,
            context={
                "function": "VOLTage:DC",
                "acquisition_complete": True,
            },
        )
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        self.assertEqual(artifact["measurement"]["value"], 10.0)
        self.assertEqual(artifact["measurement"]["channel"], 0)
        self.assertEqual(artifact["measurement"]["channel_kind"], "INTCHAN")
        for key in ("schema_version", "kind"):
            self.assertEqual(artifact[key], expected[key])
        for key, value in expected["measurement"].items():
            self.assertEqual(artifact["measurement"][key], value)
        for key, value in expected["integrity"].items():
            self.assertEqual(artifact["integrity"][key], value)

    def test_invalid_three_field_reading_shape_is_unsupported(self):
        artifact = parse_response(b"+1.000000E+01VDC,0,INTCHAN\n")
        self.assertEqual(artifact["integrity"]["status"], "UNSUPPORTED")

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

    def test_arbitrary_text_is_not_guessed_as_error_queue_in_auto_mode(self):
        artifact = parse_response(b"1,hello\n")
        self.assertEqual(artifact["kind"], "unknown")
        self.assertEqual(artifact["integrity"]["status"], "UNSUPPORTED")

    def test_explicit_error_queue_mode_parses_general_error_message(self):
        artifact = parse_response(b"-222,Data out of range\n", response_type="error-queue")
        self.assertEqual(artifact["kind"], "status-record")
        self.assertEqual(artifact["record"]["code"], -222)
        self.assertEqual(artifact["integrity"]["status"], "UNVERIFIED")

    def test_error_queue_overflow_means_error_history_is_incomplete(self):
        raw = (FIXTURES / "error-queue-overflow.txt").read_bytes()
        artifact = parse_response(raw, response_type="error-queue")
        self.assertEqual(artifact["record"]["code"], 350)
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")

    def test_negative_error_queue_overflow_code_is_incomplete(self):
        artifact = parse_response(b"-350,Queue Overflow\n", response_type="error-queue")
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")

    def test_signed_error_queue_overflow_sentinels_are_auto_classified(self):
        for raw in (b"350,Queue Overflow\n", b"-350,Queue Overflow\n"):
            with self.subTest(raw=raw):
                artifact = parse_response(raw)
                self.assertEqual(artifact["kind"], "status-record")
                self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")

    def test_overflow_sentinel_with_unit_remains_overflow(self):
        for raw in (b"+9.9E37VDC\n", b"-9.9E+37VDC\n"):
            with self.subTest(raw=raw):
                artifact = parse_response(
                    raw,
                    context={"function": "VOLTage:DC", "acquisition_complete": True},
                )
                self.assertEqual(artifact["measurement"]["reading_status"], "OVERFLOW")
                self.assertIsNone(artifact["measurement"]["value"])
                self.assertEqual(artifact["integrity"]["status"], "UNVERIFIED")

    def test_manifest_hash_matches_captured_reading(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        raw = (ROOT / manifest["data"]["raw_path"]).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(manifest["data"]["raw_sha256"], digest)
        self.assertEqual(manifest["support"]["hardware_verified"], True)
        self.assertEqual(manifest["support"]["level"], "hardware-verified")
        self.assertEqual(manifest["support"]["verified_scope"]["functions"],
                         ["VOLTage:DC", "CURRent:DC"])
        self.assertEqual(manifest["instrument"]["serial"], "0944865")

    def test_hardware_capture_shapes_parse_as_observed(self):
        captures = ROOT / "assets" / "captures"

        bare = parse_response(
            (captures / "reading-dcv-25v.txt").read_bytes(),
            context={"function": "VOLT:DC"},
        )
        self.assertEqual(bare["integrity"]["status"], "INCOMPLETE")
        self.assertEqual(bare["integrity"]["reasons"], ["unit_missing"])

        full = parse_response(
            (captures / "elements-read-chan-unit.txt").read_bytes(),
            context={"function": "VOLT:DC", "acquisition_complete": True},
        )
        self.assertEqual(full["integrity"]["status"], "COMPLETE")
        self.assertEqual(full["measurement"]["channel"], 0)
        self.assertEqual(full["measurement"]["channel_kind"], "INTCHAN")

        init_ignored = parse_response(
            (captures / "error-init-ignored.txt").read_bytes(),
            response_type="error-queue",
        )
        self.assertEqual(init_ignored["record"]["code"], -213)
        self.assertEqual(init_ignored["record"]["message"], '"Init ignored"')

        dci = parse_response(
            (captures / "dci-3a-range.txt").read_bytes(),
            context={"function": "CURR:DC", "unit": "ADC",
                     "acquisition_complete": True},
        )
        self.assertEqual(dci["integrity"]["status"], "COMPLETE")
        self.assertAlmostEqual(dci["measurement"]["value"], 0.202199285)

    def test_open_input_captures_classify_as_observed(self):
        open_inputs = ROOT / "assets" / "captures" / "open-inputs"

        for name in ("resistance-2w.txt", "resistance-4w.txt", "continuity.txt",
                     "diode.txt", "temperature.txt"):
            with self.subTest(name=name):
                artifact = parse_response(
                    (open_inputs / name).read_bytes(),
                    context={"acquisition_complete": True},
                )
                self.assertEqual(artifact["integrity"]["status"], "UNVERIFIED")
                self.assertEqual(
                    artifact["integrity"]["reasons"], ["instrument_reported_overflow"]
                )
                self.assertEqual(
                    artifact["measurement"]["reading_status"], "OVERFLOW"
                )
                self.assertIsNone(artifact["measurement"]["value"])

        # No signal reads 0 Hz, which is structurally valid and must not be
        # confused with a real measurement by the parser alone.
        freq = parse_response(
            (open_inputs / "frequency.txt").read_bytes(),
            context={"function": "FREQ", "unit": "HZ", "acquisition_complete": True},
        )
        self.assertEqual(freq["integrity"]["status"], "COMPLETE")
        self.assertEqual(freq["measurement"]["value"], 0.0)

    def test_response_type_is_validated(self):
        artifact = parse_response(b"+1.0E+00VDC\n", response_type="typo")
        self.assertEqual(artifact["integrity"]["status"], "INVALID")

    def test_cli_explicit_error_queue_mode_outputs_status_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            response = Path(tmp) / "error.txt"
            response.write_bytes(b"-225,Out of memory\n")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main([str(response), "--response-type", "error-queue"])
        self.assertEqual(exit_code, 0)
        artifact = json.loads(output.getvalue())
        self.assertEqual(artifact["record"]["code"], -225)
        self.assertEqual(artifact["kind"], "status-record")
        self.assertEqual(artifact["integrity"]["raw_response_base64"], "LTIyNSxPdXQgb2YgbWVtb3J5Cg==")

    def test_explicit_measurement_mode_rejects_error_queue_line(self):
        artifact = parse_response(b"-225,Out of memory\n", response_type="measurement")
        self.assertEqual(artifact["integrity"]["status"], "UNSUPPORTED")

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

    def test_invalid_context_preserves_parsed_reading_and_raw_bytes(self):
        raw = (FIXTURES / "valid-reading.txt").read_bytes()
        artifact = parse_response(raw, context={"function": "CURRent:DC"})
        self.assertEqual(artifact["kind"], "scalar-measurement")
        self.assertEqual(artifact["integrity"]["status"], "INVALID")
        self.assertEqual(artifact["parsed_metadata"]["numeric_token"], "+1.23456789E+00")
        self.assertEqual(artifact["parsed_payload"]["response_unit"], "VDC")
        self.assertEqual(base64.b64decode(artifact["integrity"]["raw_response_base64"]), raw)

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
