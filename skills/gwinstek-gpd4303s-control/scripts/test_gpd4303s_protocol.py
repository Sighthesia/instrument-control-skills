from __future__ import annotations

import hashlib
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "assets" / "fixtures"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gpd4303s_protocol import (  # noqa: E402
    COMMAND_SPECS,
    DEFAULT_BIT_ORDER,
    DOCUMENTED_ERROR_MESSAGES,
    MAX_COMMAND_CHARS,
    ProtocolError,
    build_query,
    classify_command,
    decode_status_bits,
    extract_advertised_commands,
    extract_payload,
    main,
    normalize,
    parse_command_list,
    parse_error_message,
    parse_identity,
    parse_metadata,
    parse_reading,
    parse_response,
    parse_status,
    read_frame,
    read_multiline_frame,
    validate,
)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FrameTests(unittest.TestCase):
    def test_lf(self):
        frame = read_frame(b"abc\n")
        self.assertEqual(frame.content, b"abc")
        self.assertEqual(frame.terminator, b"\n")
        self.assertEqual(frame.trailing, b"")

    def test_cr(self):
        self.assertEqual(read_frame(b"abc\r").terminator, b"\r")

    def test_crlf_is_the_observed_terminator(self):
        frame = read_frame(fixture("idn.txt"))
        self.assertEqual(frame.terminator, b"\r\n")
        self.assertEqual(frame.content, b"GW INSTEK,GPD-4303S,SN:EP924162,V2.08")

    def test_lfcr(self):
        self.assertEqual(read_frame(b"abc\n\r").terminator, b"\n\r")

    def test_empty_is_incomplete(self):
        with self.assertRaises(ProtocolError) as caught:
            read_frame(b"")
        self.assertEqual(caught.exception.status, "INCOMPLETE")

    def test_missing_terminator_is_incomplete(self):
        with self.assertRaises(ProtocolError) as caught:
            read_frame(fixture("synthetic/numeric-no-terminator.txt"))
        self.assertEqual(caught.exception.status, "INCOMPLETE")

    def test_trailing_bytes_are_invalid(self):
        with self.assertRaises(ProtocolError) as caught:
            read_frame(fixture("synthetic/numeric-extra-line.txt"))
        self.assertEqual(caught.exception.status, "INVALID")
        self.assertIn("extra bytes", str(caught.exception))

    def test_oversized_is_unsupported(self):
        with self.assertRaises(ProtocolError) as caught:
            read_frame(b"x" * 70_000 + b"\n")
        self.assertEqual(caught.exception.status, "UNSUPPORTED")

    def test_non_bytes_is_invalid(self):
        with self.assertRaises(ProtocolError):
            read_frame("24.000V\r\n")  # type: ignore[arg-type]


class MultiLineFrameTests(unittest.TestCase):
    def test_help_response_has_eighteen_lines(self):
        frame = read_multiline_frame(fixture("help-list.txt"))
        self.assertEqual(len(frame.lines), 18)
        self.assertEqual(frame.terminator, b"\r\n")
        self.assertEqual(frame.lines[-1], b"STATUS?          Returns the power supply state.")

    def test_single_line_is_accepted(self):
        frame = read_multiline_frame(b"0.000V\r\n")
        self.assertEqual(frame.lines, (b"0.000V",))

    def test_missing_terminator_is_incomplete(self):
        with self.assertRaises(ProtocolError) as caught:
            read_multiline_frame(b"a\rb")
        self.assertEqual(caught.exception.status, "INCOMPLETE")

    def test_help_response_fingerprint(self):
        # Locks the byte-exact transcription of the captured HELP? response.
        self.assertEqual(
            hashlib.sha256(fixture("help-list.txt")).hexdigest(),
            "cc99fc5c13031c04670138ced33ad3f78071b57679bbc1e4651e5416694518cf",
        )


class IdentityTests(unittest.TestCase):
    def test_captured_identity(self):
        artifact = parse_identity(fixture("idn.txt"))
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        self.assertEqual(artifact["vendor"], "GW INSTEK")
        self.assertEqual(artifact["model"], "GPD-4303S")
        self.assertEqual(artifact["serial"], "EP924162")
        self.assertEqual(artifact["firmware"], "V2.08")

    def test_wrong_model_is_invalid(self):
        artifact = parse_identity(fixture("synthetic/identity-wrong-model.txt"))
        self.assertEqual(artifact["integrity"]["status"], "INVALID")
        self.assertIsNone(artifact["model"])

    def test_missing_firmware_is_incomplete(self):
        artifact = parse_identity(fixture("synthetic/identity-missing-firmware.txt"))
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")
        self.assertIn("firmware", " ".join(artifact["integrity"]["reasons"]))

    def test_case_insensitive_identity_is_accepted(self):
        artifact = parse_identity(b"gw instek,gpd-4303s,sn:ep924162,v2.08\r\n")
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        self.assertEqual(artifact["firmware"], "v2.08")

    def test_non_ascii_is_invalid(self):
        artifact = parse_identity(b"GW INSTEK,GPD-4303S,SN:EP\xff,V2.08\r\n")
        self.assertEqual(artifact["integrity"]["status"], "INVALID")

    def test_missing_terminator_is_incomplete(self):
        artifact = parse_identity(b"GW INSTEK,GPD-4303S,SN:EP924162,V2.08")
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")


class ReadingTests(unittest.TestCase):
    def test_voltage_setting(self):
        artifact = parse_reading(fixture("vset1.txt"), quantity="voltage_setting", channel=1)
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        self.assertEqual(artifact["value"], 24.0)
        self.assertEqual(artifact["unit"], "V")
        self.assertEqual(artifact["raw_token"], "24.000")
        self.assertEqual(artifact["resolution_digits"], 3)
        self.assertEqual(artifact["channel"], 1)

    def test_current_setting_on_channel_three(self):
        artifact = parse_reading(fixture("iset3.txt"), quantity="current_setting", channel=3)
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        self.assertEqual(artifact["value"], 3.0)
        self.assertEqual(artifact["unit"], "A")
        self.assertEqual(artifact["channel"], 3)

    def test_measured_voltage_while_energised(self):
        artifact = parse_reading(fixture("vout1-on.txt"), quantity="voltage_measurement", channel=1)
        self.assertEqual(artifact["value"], 23.994)
        self.assertEqual(artifact["raw_unit"], "V")

    def test_measured_current_while_energised(self):
        artifact = parse_reading(fixture("iout1-on.txt"), quantity="current_measurement", channel=1)
        self.assertEqual(artifact["value"], 0.002)
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")

    def test_unitless_response_is_incomplete(self):
        artifact = parse_reading(
            fixture("synthetic/vset1-unitless.txt"), quantity="voltage_setting", channel=1
        )
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")
        self.assertIsNone(artifact["unit"])
        self.assertEqual(artifact["value"], 24.0)
        self.assertEqual(artifact["integrity"]["reasons"], ["response_unit_missing"])

    def test_conflicting_unit_is_invalid(self):
        artifact = parse_reading(
            fixture("synthetic/vset1-wrong-unit.txt"), quantity="voltage_setting", channel=1
        )
        self.assertEqual(artifact["integrity"]["status"], "INVALID")

    def test_unknown_quantity_is_invalid(self):
        artifact = parse_reading(fixture("vset1.txt"), quantity="frequency", channel=1)
        self.assertEqual(artifact["integrity"]["status"], "INVALID")

    def test_extra_line_is_invalid(self):
        artifact = parse_reading(
            fixture("synthetic/numeric-extra-line.txt"), quantity="voltage_measurement", channel=1
        )
        self.assertEqual(artifact["integrity"]["status"], "INVALID")

    def test_missing_terminator_is_incomplete(self):
        artifact = parse_reading(
            fixture("synthetic/numeric-no-terminator.txt"),
            quantity="voltage_setting",
            channel=1,
        )
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")


class StatusTests(unittest.TestCase):
    def test_output_off_capture_decodes(self):
        artifact = parse_status(fixture("status-output-off.txt"))
        decoded = artifact["decoded"]
        self.assertEqual(artifact["raw_text"], "00110010")
        self.assertEqual(decoded["output"], "off")
        self.assertEqual(decoded["beep"], "off")
        self.assertEqual(decoded["baud_code"], "10")
        self.assertEqual(decoded["baud_bps"], 9600)
        self.assertEqual(decoded["tracking_code"], "11")
        self.assertEqual(decoded["tracking"], "series")
        self.assertEqual(decoded["ch1_regulation"], "CC")

    def test_output_on_capture_decodes(self):
        artifact = parse_status(fixture("status-output-on.txt"))
        self.assertEqual(artifact["raw_text"], "11110110")
        self.assertEqual(artifact["decoded"]["output"], "on")
        self.assertEqual(artifact["decoded"]["ch1_regulation"], "CV")
        self.assertEqual(artifact["decoded"]["ch2_regulation"], "CV")

    def test_bit_order_stays_unverified(self):
        artifact = parse_status(fixture("status-output-off.txt"))
        self.assertEqual(artifact["bit_order"], DEFAULT_BIT_ORDER)
        self.assertEqual(artifact["integrity"]["status"], "UNVERIFIED")
        self.assertEqual(artifact["integrity"]["reasons"], ["status_bit_order_not_documented"])
        checks = {check["name"]: check["status"] for check in artifact["integrity"]["checks"]}
        self.assertEqual(checks["status_bit_order"], "not_checked")

    def test_alternate_order_is_reported(self):
        artifact = parse_status(fixture("status-output-off.txt"))
        self.assertEqual(artifact["decoded"]["output"], "off")
        self.assertEqual(artifact["decoded_alternate_order"]["output"], "on")
        self.assertEqual(artifact["decoded_alternate_order"]["baud_bps"], 115200)

    def test_msb_first_wire_mapping(self):
        decoded = decode_status_bits([0, 0, 1, 1, 0, 0, 1, 0], bit_order="msb-first")
        self.assertEqual(decoded["wire_order"], [0, 0, 1, 1, 0, 0, 1, 0])
        self.assertEqual(decoded["tracking_code"], "00")
        self.assertEqual(decoded["tracking"], "undefined")

    def test_explicit_bit_order_is_honoured(self):
        artifact = parse_status(fixture("status-output-off.txt"), bit_order="msb-first")
        self.assertEqual(artifact["bit_order"], "msb-first")
        self.assertEqual(artifact["decoded"]["baud_bps"], 115200)

    def test_bad_bit_order_is_invalid(self):
        with self.assertRaises(ProtocolError):
            decode_status_bits([0, 0, 1, 1, 0, 0, 1, 0], bit_order="middle-first")

    def test_short_status_is_invalid(self):
        artifact = parse_status(fixture("synthetic/status-short.txt"))
        self.assertEqual(artifact["integrity"]["status"], "INVALID")

    def test_non_binary_status_is_invalid(self):
        artifact = parse_status(fixture("synthetic/status-non-binary.txt"))
        self.assertEqual(artifact["integrity"]["status"], "INVALID")


class ErrorMessageTests(unittest.TestCase):
    def test_captured_invalid_character(self):
        artifact = parse_error_message(fixture("invalid-character.txt"))
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        self.assertEqual(artifact["code"], "b")
        self.assertEqual(artifact["normalized"], "invalid character")
        self.assertEqual(artifact["message"], "Invalid Character.")
        # The instrument capitalises and punctuates differently from manual p. 46.
        self.assertFalse(artifact["written_as_documented"])

    def test_documented_undefined_header(self):
        artifact = parse_error_message(fixture("synthetic/error-undefined-header.txt"))
        self.assertEqual(artifact["code"], "f")
        self.assertTrue(artifact["written_as_documented"])

    def test_unknown_message_is_unsupported(self):
        artifact = parse_error_message(fixture("synthetic/error-unknown.txt"))
        self.assertEqual(artifact["integrity"]["status"], "UNSUPPORTED")
        self.assertIsNone(artifact["code"])

    def test_every_documented_message_is_recognised(self):
        for key, entry in DOCUMENTED_ERROR_MESSAGES.items():
            with self.subTest(message=key):
                artifact = parse_error_message(entry["manual_text"].encode("ascii") + b"\r\n")
                self.assertEqual(artifact["code"], entry["code"])
                self.assertEqual(artifact["pdf_page"], entry["pdf_page"])


class CommandListTests(unittest.TestCase):
    def test_captured_list(self):
        artifact = parse_command_list(fixture("help-list.txt"))
        self.assertEqual(artifact["integrity"]["status"], "COMPLETE")
        self.assertEqual(artifact["line_count"], 18)
        self.assertIn("OUT<Boolean>", artifact["advertised_commands"])
        self.assertIn("ERR?", artifact["advertised_commands"])
        self.assertNotIn("HELP?", artifact["advertised_commands"])

    def test_stop_pages_only_splits_channel_hint_lines(self):
        lines = ["ISET<x>:<NR2>    Sets the value of current.", "   x:1=CH1,2=CH2"]
        self.assertEqual(extract_advertised_commands(lines), ["ISET<x>"])

    def test_empty_list_is_incomplete(self):
        artifact = parse_command_list(b"")
        self.assertEqual(artifact["integrity"]["status"], "INCOMPLETE")


class ClassifyTests(unittest.TestCase):
    def test_every_documented_form_classifies(self):
        samples = {
            "ISET<X>:<NR2>": "ISET2:1.500",
            "ISET<X>?": "ISET2?",
            "VSET<X>:<NR2>": "VSET1:24.000",
            "VSET<X>?": "VSET1?",
            "IOUT<X>?": "IOUT1?",
            "VOUT<X>?": "VOUT1?",
            "TRACK<NR1>": "TRACK0",
            "BEEP<Boolean>": "BEEP0",
            "OUT<Boolean>": "OUT1",
            "STATUS?": "STATUS?",
            "*IDN?": "*IDN?",
            "RCL<NR1>": "RCL1",
            "SAV<NR1>": "SAV1",
            "BAUD<NR1>": "BAUD2",
            "LOCAL": "LOCAL",
            "REMOTE": "REMOTE",
            "ERR?": "ERR?",
            "HELP?": "HELP?",
        }
        self.assertEqual(len(COMMAND_SPECS), len(samples))
        for name, text in samples.items():
            with self.subTest(name=name):
                result = classify_command(text)
                self.assertTrue(result["known"])
                self.assertEqual(result["name"], name)
                self.assertEqual(result["problems"], [])
                self.assertIsInstance(result["pdf_page"], int)

    def test_queries_are_read_only_and_settings_are_not(self):
        self.assertTrue(classify_command("VOUT1?")["read_only"])
        self.assertFalse(classify_command("VOUT1?")["state_changing"])
        self.assertFalse(classify_command("VSET1:24.000")["read_only"])
        self.assertTrue(classify_command("OUT1")["state_changing"])
        self.assertEqual(classify_command("OUT1")["pdf_page"], 50)

    def test_case_insensitivity_is_documented_and_sent_verbatim(self):
        result = classify_command("vout1?")
        self.assertEqual(result["name"], "VOUT<X>?")
        self.assertEqual(result["channel"], 1)
        self.assertEqual(result["text"], "vout1?")
        self.assertEqual(build_query("vout1?"), b"vout1?\r\n")

    def test_voltage_out_of_range(self):
        result = classify_command("VSET1:33")
        self.assertIn("value_out_of_range", result["problems"])
        self.assertEqual(classify_command("VSET1:32.000")["problems"], [])
        self.assertEqual(
            classify_command("ISET1:3.500")["problems"], ["value_out_of_range"]
        )
        self.assertEqual(classify_command("ISET1:3.200")["problems"], [])

    def test_missing_parameter_is_reported_as_malformed(self):
        result = classify_command("VSET:")
        self.assertFalse(result["known"])
        self.assertEqual(result["probable_documented_header"], "VSET<X>:<NR2>")
        self.assertIn("malformed_documented_command", result["problems"])

    def test_long_command_path_is_documented(self):
        result = classify_command("VSET1:" + "1" * (MAX_COMMAND_CHARS))
        self.assertIn("command_too_long", result["problems"])
        self.assertFalse(result["length_ok"])

    def test_long_scpi_form_is_not_documented(self):
        for text in ("SYST:ERR?", "*OPT?", "MEAS:VOLT?", "OUTPUT1 0", "OUT1?", "TRACK?"):
            with self.subTest(text=text):
                self.assertFalse(classify_command(text)["known"])

    def test_build_query_only_emits_queries(self):
        self.assertEqual(build_query("*IDN?"), b"*IDN?\r\n")
        self.assertEqual(build_query("STATUS?"), b"STATUS?\r\n")
        for text in ("OUT1", "OUT0", "VSET1:24.000", "ISET1:1.000", "TRACK1", "SAV1", "LOCAL"):
            with self.subTest(text=text):
                with self.assertRaises(ProtocolError):
                    build_query(text)

    def test_build_query_rejects_unknown(self):
        with self.assertRaises(ProtocolError):
            build_query("SYST:ERR?")

    def test_only_ch1_and_ch2_queries_are_hardware_verified(self):
        for text in ("VSET1?", "ISET2?", "VOUT2?", "IOUT1?"):
            with self.subTest(text=text):
                result = classify_command(text)
                self.assertEqual(result["evidence"], "hardware-verified")
                self.assertIsNone(result["evidence_note"])
        for text in ("VSET3?", "ISET4?", "VOUT3?", "IOUT4?"):
            with self.subTest(text=text):
                result = classify_command(text)
                self.assertEqual(result["evidence"], "documented")
                self.assertIn("CH3/CH4", result["evidence_note"])
                self.assertEqual(result["evidence_channels"], [1, 2])


class ParseResponseTests(unittest.TestCase):
    def test_identity_dispatch(self):
        artifact = parse_response(fixture("idn.txt"), "*IDN?")
        self.assertEqual(artifact["kind"], "identity")
        self.assertEqual(artifact["command"], "*IDN?")
        self.assertEqual(artifact["evidence"]["command_evidence"], "hardware-verified")

    def test_reading_dispatch_uses_the_query_quantity(self):
        artifact = parse_response(fixture("iout2-off.txt"), "IOUT2?")
        self.assertEqual(artifact["quantity"], "current_measurement")
        self.assertEqual(artifact["channel"], 2)
        self.assertEqual(artifact["value"], 0.0)

    def test_status_dispatch(self):
        artifact = parse_response(fixture("status-output-off.txt"), "STATUS?")
        self.assertEqual(artifact["kind"], "status-record")
        self.assertEqual(artifact["decoded"]["baud_bps"], 9600)

    def test_command_list_dispatch(self):
        artifact = parse_response(fixture("help-list.txt"), "HELP?")
        self.assertEqual(artifact["kind"], "command-list")

    def test_channel_scope_reaches_the_artifact(self):
        artifact = parse_response(fixture("vout3-off.txt"), "VOUT3?")
        self.assertEqual(artifact["evidence"]["command_evidence"], "documented")
        artifact = parse_response(fixture("vout2-off.txt"), "VOUT2?")
        self.assertEqual(artifact["evidence"]["command_evidence"], "hardware-verified")

    def test_non_query_is_rejected(self):
        with self.assertRaises(ProtocolError):
            parse_response(b"", "OUT1")
        with self.assertRaises(ProtocolError):
            parse_response(b"", "SYST:ERR?")


class FrameStageTests(unittest.TestCase):
    def test_metadata_payload_normalize_validate_stages(self):
        frame = read_frame(fixture("vset2.txt"))
        metadata = parse_metadata(frame, response_type="numeric")
        self.assertEqual(metadata["numeric_token"], "24.000")
        payload = extract_payload(metadata)
        self.assertEqual(payload["raw_unit"], "V")
        artifact = normalize(metadata, payload, quantity="voltage_setting", channel=2)
        self.assertEqual(artifact["status"], "COMPLETE")
        final = validate(artifact, fixture("vset2.txt"))
        self.assertEqual(final["integrity"]["status"], "COMPLETE")
        self.assertEqual(len(final["integrity"]["raw_sha256"]), 64)


class FixtureProvenanceTests(unittest.TestCase):
    def test_descriptive_fixtures_match_the_captured_bytes(self):
        pairs = {
            "idn.txt": "captures/001-IDN.raw",
            "status-output-off.txt": "captures/001-STATUS.raw",
            "vout1-off.txt": "captures/002-VOUT1.raw",
            "iout1-off.txt": "captures/003-IOUT1.raw",
            "vout2-off.txt": "captures/004-VOUT2.raw",
            "iout2-off.txt": "captures/005-IOUT2.raw",
            "help-list.txt": "captures/help-transcribed.raw",
        }
        for descriptive, captured in pairs.items():
            with self.subTest(fixture=descriptive):
                self.assertEqual(fixture(descriptive), fixture(captured))

    def test_capture_index_hashes_match_the_raw_files(self):
        lines = (FIXTURES / "captures" / "captures.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 7)
        methods = {}
        for line in lines:
            entry = json.loads(line)
            raw = (FIXTURES / "captures" / entry["raw_path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["response_sha256"])
            methods[entry["command"]] = entry.get("capture_method", "capture-dir")
        self.assertEqual(methods["HELP?"], "console-transcript")
        self.assertEqual(methods["*IDN?"], "capture-dir")

    def test_captured_and_transcribed_fixtures_end_with_crlf(self):
        for path in sorted(FIXTURES.glob("*.txt")):
            with self.subTest(fixture=path.name):
                self.assertTrue(path.read_bytes().endswith(b"\r\n"))


class CliTests(unittest.TestCase):
    def test_classify_cli_reports_state_changing(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["classify", "OUT0"])
        self.assertEqual(code, 0)
        result = json.loads(buffer.getvalue())
        self.assertTrue(result["state_changing"])
        self.assertEqual(result["value"], "0")

    def test_reading_cli_uses_the_query(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["reading", str(FIXTURES / "vset1.txt"), "--query", "VSET1?"])
        self.assertEqual(code, 0)
        result = json.loads(buffer.getvalue())
        self.assertEqual(result["value"], 24.0)
        self.assertEqual(result["channel"], 1)

    def test_status_cli_round_trip(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["status", str(FIXTURES / "status-output-off.txt")])
        self.assertEqual(code, 0)
        result = json.loads(buffer.getvalue())
        self.assertEqual(result["decoded"]["output"], "off")


class RangeConstantTests(unittest.TestCase):
    def test_documented_ranges(self):
        from gpd4303s_protocol import CURRENT_SET_RANGE, VOLTAGE_SET_RANGE

        self.assertEqual(VOLTAGE_SET_RANGE, (Decimal("0"), Decimal("32.000")))
        self.assertEqual(CURRENT_SET_RANGE, (Decimal("0"), Decimal("3.200")))


if __name__ == "__main__":
    unittest.main()
