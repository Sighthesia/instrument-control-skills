from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / "assets" / "captures"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from keithley2000_protocol import (  # noqa: E402
    assess_reading,
    default_unit,
    main,
    normalize_function,
    parse_config,
    parse_error_queue,
    parse_identity,
    sense_path,
)
from keithley2000_scalar import parse_response  # noqa: E402


def reading(token: bytes, function: str, unit: str | None) -> dict:
    context = {"function": function, "acquisition_complete": True}
    if unit:
        context["unit"] = unit
    return parse_response(token, context=context)


class IdentityTests(unittest.TestCase):
    def test_recorded_capture_matches_verified_scope(self):
        artifact = parse_identity((CAPTURES / "identity.txt").read_bytes())
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        identity = artifact["identity"]
        self.assertEqual(identity["vendor"], "KEITHLEY INSTRUMENTS INC.")
        self.assertEqual(identity["model"], "MODEL 2000")
        self.assertEqual(identity["serial"], "0944865")
        self.assertEqual(identity["firmware_digital"], "A17")
        self.assertEqual(identity["firmware_display"], "A02")
        self.assertTrue(artifact["verified_scope"]["matches_recorded_capture"])

    def test_other_serial_does_not_match_recorded_capture(self):
        artifact = parse_identity(
            b"KEITHLEY INSTRUMENTS INC.,MODEL 2000,1234567,A17  /A02  \r"
        )
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        self.assertFalse(artifact["verified_scope"]["matches_recorded_capture"])

    def test_short_identity_is_incomplete(self):
        artifact = parse_identity(b"KEITHLEY INSTRUMENTS INC.,MODEL 2000\r")
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")
        self.assertIn("identity_field_count", artifact["integrity"]["reasons"])

    def test_two_lines_are_invalid(self):
        artifact = parse_identity((CAPTURES / "identity.txt").read_bytes() * 2)
        self.assertEqual(artifact["integrity"]["status"], "INVALID")

    def test_empty_is_incomplete(self):
        artifact = parse_identity(b"")
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")


class ConfigTests(unittest.TestCase):
    def test_quoted_function_token(self):
        artifact = parse_config(b'"VOLT:DC"\r', query=":FUNCtion?")
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        config = artifact["configuration"]
        self.assertEqual(config["value_type"], "string")
        self.assertEqual(config["value"], "VOLT:DC")
        self.assertEqual(config["function"], "VOLT:DC")

    def test_number_and_flag(self):
        number = parse_config(b"1010.000000\r")["configuration"]
        self.assertEqual(number["value_type"], "number")
        self.assertEqual(number["value"], 1010.0)
        self.assertIsNone(number["flag"])

        flag = parse_config(b"1\r")["configuration"]
        self.assertEqual(flag["value_type"], "number")
        self.assertTrue(flag["flag"])

    def test_format_elements_list(self):
        artifact = parse_config(b"READ,,\r", query=":FORMat:ELEMents?")
        config = artifact["configuration"]
        self.assertEqual(config["value_type"], "elements")
        self.assertEqual(config["value"], ["READ", "", ""])

    def test_empty_and_trailing_bytes_fail_closed(self):
        self.assertEqual(parse_config(b"")["integrity"]["status"], "INCOMPLETE")
        self.assertEqual(parse_config(b"1\r\n2\r")["integrity"]["status"], "INVALID")


class ErrorQueueTests(unittest.TestCase):
    def test_empty_queue_from_capture(self):
        artifact = parse_error_queue((CAPTURES / "error-queue-empty.txt").read_bytes())
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        self.assertTrue(artifact["drained"])
        self.assertEqual(artifact["errors"], [])

    def test_real_drain_with_init_ignored_then_empty(self):
        raw = (CAPTURES / "error-init-ignored.txt").read_bytes() + \
              (CAPTURES / "error-queue-empty.txt").read_bytes()
        artifact = parse_error_queue(raw)
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        self.assertTrue(artifact["drained"])
        self.assertEqual([record["code"] for record in artifact["records"]], [-213, 0])
        self.assertEqual([record["code"] for record in artifact["errors"]], [-213])

    def test_multi_line_queue_keeps_order_and_hashes(self):
        raw = b'-113,"Undefined header"\r-213,"Init ignored"\r0,"No error"\r'
        artifact = parse_error_queue(raw)
        self.assertEqual([record["code"] for record in artifact["records"]],
                         [-113, -213, 0])
        for record in artifact["records"]:
            self.assertEqual(len(record["line_sha256"]), 64)

    def test_unterminated_drain_is_incomplete(self):
        artifact = parse_error_queue(b'-213,"Init ignored"\r0,"No error"')
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")
        self.assertIn("unterminated_error_line", artifact["integrity"]["reasons"])

    def test_not_drained_is_incomplete(self):
        artifact = parse_error_queue(b'-213,"Init ignored"\r')
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")
        self.assertIn("error_queue_not_drained", artifact["integrity"]["reasons"])

    def test_queue_overflow_is_incomplete(self):
        artifact = parse_error_queue(b'350,Queue Overflow\r')
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")
        self.assertTrue(artifact["queue_overflow"])

    def test_unparsable_line_is_invalid(self):
        artifact = parse_error_queue(b"not a queue line\r")
        self.assertEqual(artifact["integrity"]["status"], "INVALID")


class FunctionMetadataTests(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(normalize_function("VOLTage:DC"), "VOLT:DC")
        self.assertEqual(normalize_function("'VOLT:DC'"), "VOLT:DC")
        self.assertEqual(normalize_function(":SENSe:CURRent:DC"), "CURR:DC")
        self.assertIsNone(normalize_function("bogus"))

    def test_sense_paths(self):
        self.assertEqual(sense_path("FRESistance"), "FRESistance")
        self.assertEqual(sense_path("DIOD"), "DIODe")
        self.assertIsNone(sense_path("nope"))

    def test_default_units(self):
        self.assertEqual(default_unit("VOLT:DC"), "VDC")
        self.assertEqual(default_unit("CURR:AC"), "AAC")
        self.assertEqual(default_unit("RES"), "OHM")
        self.assertEqual(default_unit("FRES"), "OHM4W")
        self.assertIsNone(default_unit("TEMP"))


class AssessmentTests(unittest.TestCase):
    def test_init_ignored_marks_reading_not_newly_triggered(self):
        value = reading((CAPTURES / "reading-dcv-25v.txt").read_bytes(), "VOLT:DC", "VDC")
        queue = parse_error_queue(b'-213,"Init ignored"\r0,"No error"\r')
        verdict = assess_reading(value, queue, "VOLT:DC")
        self.assertIn("init_ignored", verdict["flags"])
        self.assertEqual(verdict["freshness"], "not_newly_triggered")

    def test_clean_one_shot_is_complete(self):
        value = reading((CAPTURES / "reading-dcv-25v.txt").read_bytes(), "VOLT:DC", "VDC")
        queue = parse_error_queue(b'0,"No error"\r')
        verdict = assess_reading(value, queue, "VOLT:DC")
        self.assertEqual(verdict["flags"], [])
        self.assertEqual(verdict["freshness"], "one_shot_complete")

    def test_zero_frequency_flags_no_signal(self):
        value = reading(b"+0.00000000E+00\r", "FREQ", "HZ")
        verdict = assess_reading(value, parse_error_queue(b'0,"No error"\r'), "FREQ")
        self.assertEqual(verdict["flags"], ["no_signal_suspected"])

    def test_overflow_is_not_a_number(self):
        value = reading(b"+9.9E37\r", "RES", "OHM")
        verdict = assess_reading(value, None, "RES")
        self.assertEqual(verdict["flags"], ["overflow"])
        self.assertEqual(verdict["freshness"], "unknown")


class CliTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(argv)
        return code, output.getvalue()

    def test_identity_cli(self):
        code, out = self._run(["identity", str(CAPTURES / "identity.txt")])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["identity"]["serial"], "0944865")

    def test_queue_cli_with_temporary_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.txt"
            path.write_bytes(b'-213,"Init ignored"\r0,"No error"\r')
            code, out = self._run(["queue", str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["records"][0]["code"], -213)

    def test_missing_file_returns_two(self):
        code, _ = self._run(["identity", "/nonexistent/response.txt"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
