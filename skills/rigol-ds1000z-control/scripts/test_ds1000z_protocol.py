from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "assets" / "fixtures"
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from ds1000z_protocol import (  # noqa: E402
    CURSOR_FAMILY_QUERIES,
    MAX_BLOCK_BYTES,
    MAX_LINE_BYTES,
    NO_RESULT_SENTINEL,
    NORM_SCREEN_POINTS,
    PREAMBLE_FIELDS,
    ProtocolError,
    encode_ieee_block,
    extract_payload,
    is_command_error,
    iter_codes,
    main,
    normalize,
    normalize_preamble,
    parse_block,
    parse_bmp_header,
    parse_cursor,
    parse_cursor_readout,
    parse_error_queue,
    parse_identity,
    parse_ieee_block,
    parse_measurement,
    parse_metadata,
    parse_preamble,
    parse_screenshot,
    parse_waveform,
    read_frame,
    sample_time,
    sample_voltage,
    summarize_codes,
    validate,
    waveform_to_csv,
)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def expected(name: str) -> dict:
    return json.loads((ROOT / "assets" / name).read_text())


def check_names(result: dict) -> dict[str, dict]:
    return {check["name"]: check for check in result["integrity"]["checks"]}


class FrameTests(unittest.TestCase):
    def test_lf(self):
        frame = read_frame(b"abc\n")
        self.assertEqual(frame.content, b"abc")
        self.assertEqual(frame.terminator, b"\n")
        self.assertEqual(frame.trailing, b"")

    def test_crlf_accepted(self):
        frame = read_frame(b"abc\r\n")
        self.assertEqual(frame.content, b"abc")
        self.assertEqual(frame.terminator, b"\r\n")

    def test_cr_inside_content_rejected(self):
        # Measured: responses terminate with LF and contain no CR.
        with self.assertRaises(ProtocolError) as ctx:
            read_frame(b"ab\rc\n")
        self.assertEqual(ctx.exception.status, "INVALID")
        self.assertEqual(ctx.exception.reason, "unexpected_cr")

    def test_empty(self):
        with self.assertRaises(ProtocolError) as ctx:
            read_frame(b"")
        self.assertEqual(ctx.exception.status, "INCOMPLETE")

    def test_missing_terminator(self):
        with self.assertRaises(ProtocolError) as ctx:
            read_frame(b"abc")
        self.assertEqual(ctx.exception.status, "INCOMPLETE")
        self.assertEqual(ctx.exception.reason, "missing_terminator")

    def test_trailing_bytes(self):
        with self.assertRaises(ProtocolError) as ctx:
            read_frame(b"abc\ndef")
        self.assertEqual(ctx.exception.status, "INVALID")
        self.assertEqual(ctx.exception.reason, "trailing_bytes")

    def test_trailing_bytes_kept_when_allowed(self):
        frame = read_frame(b"abc\ndef", allow_trailing=True)
        self.assertEqual(frame.trailing, b"def")

    def test_oversized_line(self):
        with self.assertRaises(ProtocolError) as ctx:
            read_frame(b"a" * (MAX_LINE_BYTES + 1) + b"\n")
        self.assertEqual(ctx.exception.status, "UNSUPPORTED")

    def test_binary_block_is_not_a_line(self):
        with self.assertRaises(ProtocolError) as ctx:
            read_frame(b"#40002\x00\x01")
        self.assertEqual(ctx.exception.status, "UNSUPPORTED")
        self.assertEqual(ctx.exception.reason, "binary_block_not_line")

    def test_non_bytes(self):
        with self.assertRaises(ProtocolError):
            read_frame("abc\n")  # type: ignore[arg-type]

    def test_command_error_has_no_terminator(self):
        self.assertTrue(is_command_error(b"command error"))
        self.assertTrue(is_command_error(b"command error\n"))
        self.assertFalse(is_command_error(b"command erro"))
        with self.assertRaises(ProtocolError) as ctx:
            read_frame(b"command error")
        self.assertEqual(ctx.exception.status, "UNSUPPORTED")
        self.assertEqual(ctx.exception.reason, "instrument_command_error")

    def test_command_error_with_terminator(self):
        with self.assertRaises(ProtocolError) as ctx:
            read_frame(b"command error\n")
        self.assertEqual(ctx.exception.status, "UNSUPPORTED")


class IdentityTests(unittest.TestCase):
    def test_valid_fixture(self):
        raw = fixture("identity.txt")
        result = parse_identity(raw)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["vendor"], "RIGOL TECHNOLOGIES")
        self.assertEqual(result["model"], "DS1074Z")
        self.assertEqual(result["serial"], "DS1ZA171004155")
        self.assertEqual(result["firmware"], "00.04.02.SP4")
        self.assertEqual(result["profile"]["channels"], 4)
        self.assertEqual(result["profile"]["bandwidth_mhz"], 70)
        self.assertEqual(result["integrity"]["raw_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["integrity"]["support_level"], "firmware-scoped")

    def test_stage_composition(self):
        raw = fixture("identity.txt")
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="identity")
        payload = extract_payload(metadata)
        artifact = normalize(metadata, payload)
        result = validate(artifact, raw)
        self.assertEqual(payload["model"], "DS1074Z")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["integrity"]["status"], "COMPLETE")

    def test_auto_classification(self):
        metadata = parse_metadata(read_frame(fixture("identity.txt")))
        self.assertEqual(metadata["response_type"], "identity")

    def test_missing_firmware_is_incomplete(self):
        result = parse_identity(fixture("identity-missing-firmware.txt"))
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIn("identity_firmware_missing", result["integrity"]["reasons"])

    def test_wrong_vendor(self):
        self.assertEqual(parse_identity(fixture("identity-wrong-vendor.txt"))["status"], "INVALID")

    def test_five_fields(self):
        result = parse_identity(b"RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,00.04.02.SP4,EXTRA\n")
        self.assertEqual(result["status"], "INVALID")

    def test_two_fields(self):
        self.assertEqual(parse_identity(b"RIGOL TECHNOLOGIES,DS1074Z\n")["status"], "INVALID")

    def test_unknown_model(self):
        result = parse_identity(b"RIGOL TECHNOLOGIES,DS9999Z,DS1ZA171004155,00.04.02.SP4\n")
        self.assertEqual(result["status"], "INVALID")

    def test_family_model_without_profile_is_unverified(self):
        result = parse_identity(b"RIGOL TECHNOLOGIES,MSO1104Z,DS1ZA171004155,00.04.02.SP4\n")
        self.assertEqual(result["status"], "COMPLETE")

    def test_bad_serial(self):
        self.assertEqual(parse_identity(b"RIGOL TECHNOLOGIES,DS1074Z,XYZ,00.04.02.SP4\n")["status"], "INVALID")

    def test_bad_firmware(self):
        self.assertEqual(
            parse_identity(b"RIGOL TECHNOLOGIES,DS1074Z,DS1ZA171004155,firmware\n")["status"], "INVALID"
        )

    def test_missing_terminator(self):
        self.assertEqual(parse_identity(fixture("identity.txt")[:-1])["status"], "INCOMPLETE")

    def test_trailing_bytes(self):
        self.assertEqual(parse_identity(fixture("identity.txt") + b"EXTRA\n")["status"], "INVALID")

    def test_expected_fixture(self):
        spec = expected("expected-identity.json")
        result = parse_identity(fixture("identity.txt"))
        self.assertEqual(result["status"], spec["status"])
        self.assertEqual(result["identity"], spec["identity"])
        self.assertEqual(result["profile"], spec["profile"])
        self.assertEqual(result["integrity"]["raw_bytes"], spec["raw_bytes"])
        for name, variant in spec["variants"].items():
            self.assertEqual(parse_identity(fixture(name))["status"], variant["status"])


class MeasurementTests(unittest.TestCase):
    def test_vpp(self):
        result = parse_measurement(fixture("measurement-vpp.txt"), quantity="vpp")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["value"], 3.04)
        self.assertEqual(result["numeric_token"], "3.040000e+00")
        self.assertEqual(result["unit"], "V")
        self.assertEqual(result["command"], ":MEASure:VPP?")

    def test_frequency(self):
        result = parse_measurement(fixture("measurement-frequency.txt"), quantity="frequency")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertAlmostEqual(result["value"], 999.9999)
        self.assertEqual(result["unit"], "Hz")

    def test_no_result_sentinel_is_not_a_value(self):
        result = parse_measurement(fixture("measurement-no-result.txt"), quantity="vpp")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIsNone(result["value"])
        self.assertIsNone(result["raw_value"])
        self.assertEqual(result["sentinel"], "9.9E37")
        self.assertEqual(result["numeric_token"], "9.9E37")
        self.assertIn("no_measurement_result_sentinel", result["integrity"]["reasons"])

    def test_sentinel_with_explicit_exponent(self):
        result = parse_measurement(b"9.900000e+37\n", quantity="vpp")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIsNone(result["value"])

    def test_sentinel_constant(self):
        self.assertEqual(str(NO_RESULT_SENTINEL), "9.9E+37")

    def test_command_error_is_not_a_number(self):
        result = parse_measurement(fixture("command-error.bin"), quantity="rtime")
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertIsNone(result["value"])
        self.assertTrue(result["command_error"])
        self.assertEqual(result["integrity"]["reasons"], ["instrument_command_error"])

    def test_empty_response(self):
        self.assertEqual(parse_measurement(b"", quantity="vpp")["status"], "INCOMPLETE")

    def test_blank_line(self):
        self.assertEqual(parse_measurement(b"\n", quantity="vpp")["status"], "INCOMPLETE")

    def test_bad_nr3(self):
        self.assertEqual(parse_measurement(fixture("measurement-syntax-error.txt"), quantity="vpp")["status"],
                         "INVALID")

    def test_nan(self):
        self.assertEqual(parse_measurement(b"NaN\n", quantity="vpp")["status"], "INVALID")

    def test_inf(self):
        self.assertEqual(parse_measurement(b"Inf\n", quantity="vpp")["status"], "INVALID")

    def test_unit_suffix_rejected(self):
        self.assertEqual(parse_measurement(b"3.04 V\n", quantity="vpp")["status"], "INVALID")

    def test_unknown_quantity(self):
        self.assertEqual(parse_measurement(b"3.04\n", quantity="nope")["status"], "INVALID")

    def test_alias(self):
        result = parse_measurement(b"3.04\n", quantity="pk2pk")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["quantity"], "vpp")

    def test_rtime_uses_item_query(self):
        result = parse_measurement(b"9.9E37\n", quantity="rtime")
        self.assertEqual(result["command"], ":MEASure:ITEM? RTIMe")
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_trailing_bytes(self):
        self.assertEqual(parse_measurement(b"1.0\nextra\n", quantity="vpp")["status"], "INVALID")

    def test_stage_composition(self):
        raw = fixture("measurement-vpp.txt")
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="measurement")
        payload = extract_payload(metadata)
        artifact = normalize(metadata, payload, quantity="vpp")
        result = validate(artifact, raw)
        self.assertEqual(payload["numeric_token"], "3.040000e+00")
        self.assertEqual(result["value"], 3.04)

    def test_auto_classification(self):
        metadata = parse_metadata(read_frame(fixture("measurement-vpp.txt")))
        self.assertEqual(metadata["response_type"], "measurement")

    def test_expected_fixture(self):
        spec = expected("expected-measurement.json")
        result = parse_measurement(fixture("measurement-vpp.txt"), quantity=spec["quantity"])
        self.assertEqual(result["status"], spec["status"])
        self.assertEqual(result["value"], spec["value"])
        self.assertEqual(result["unit"], spec["unit"])
        no_result = parse_measurement(fixture(spec["no_result"]["fixture"]), quantity="vpp")
        self.assertEqual(no_result["status"], spec["no_result"]["status"])
        self.assertIsNone(no_result["value"])
        command_error = parse_measurement(fixture(spec["command_error"]["fixture"]), quantity="vpp")
        self.assertEqual(command_error["status"], spec["command_error"]["status"])
        self.assertTrue(command_error["command_error"])


class ErrorQueueTests(unittest.TestCase):
    def test_undefined_header(self):
        result = parse_error_queue(fixture("error-queue-undefined.txt"))
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["code"], -113)
        self.assertEqual(result["message"], "Undefined header; keyword cannot be found")
        self.assertEqual(result["error_class"], "command")
        self.assertTrue(result["quoted"])

    def test_empty_queue(self):
        result = parse_error_queue(fixture("error-queue-none.txt"))
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["error_class"], "none")

    def test_overflow(self):
        result = parse_error_queue(fixture("error-queue-overflow.txt"))
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["code"], -350)
        self.assertIn("instrument_error_queue_overflow", result["integrity"]["reasons"])

    def test_parameter_error(self):
        result = parse_error_queue(b'-220,"Parameter error"\n')
        self.assertEqual(result["code"], -220)
        self.assertEqual(result["error_class"], "execution")
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_unquoted_message(self):
        result = parse_error_queue(b"-350,Queue overflow\n")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertFalse(result["quoted"])

    def test_unterminated_quote(self):
        self.assertEqual(parse_error_queue(b'-113, "Undefined header\n')["status"], "INVALID")

    def test_missing_comma(self):
        # Auto mode cannot classify a two-token line without a comma; the
        # explicit mode reports the malformed shape as INVALID.
        self.assertEqual(parse_error_queue(b'-113 "Undefined header"\n')["status"], "UNSUPPORTED")
        self.assertEqual(
            parse_error_queue(b'-113 "Undefined header"\n', response_type="error-queue")["status"],
            "INVALID",
        )

    def test_empty_message(self):
        self.assertEqual(parse_error_queue(b"-113, \n")["status"], "INVALID")

    def test_missing_terminator(self):
        self.assertEqual(parse_error_queue(fixture("error-queue-none.txt")[:-1])["status"], "INCOMPLETE")

    def test_explicit_and_auto_agree(self):
        raw = fixture("error-queue-undefined.txt")
        self.assertEqual(
            parse_error_queue(raw)["integrity"]["reasons"],
            parse_error_queue(raw, response_type="error-queue")["integrity"]["reasons"],
        )

    def test_expected_fixture(self):
        spec = expected("expected-error-queue.json")
        result = parse_error_queue(fixture(spec["fixture"]))
        self.assertEqual(result["status"], spec["status"])
        self.assertEqual(result["code"], spec["code"])
        self.assertEqual(result["message"], spec["message"])
        self.assertEqual(parse_error_queue(fixture(spec["empty"]["fixture"]))["status"], spec["empty"]["status"])
        self.assertEqual(parse_error_queue(fixture(spec["overflow"]["fixture"]))["status"],
                         spec["overflow"]["status"])


class PreambleTests(unittest.TestCase):
    def test_norm(self):
        result = parse_preamble(fixture("preamble-norm.txt"))
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["format"], 0)
        self.assertEqual(result["format_name"], "BYTE")
        self.assertEqual(result["bytes_per_point"], 1)
        self.assertEqual(result["mode"], 0)
        self.assertEqual(result["mode_name"], "NORM")
        self.assertEqual(result["points"], 1200)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["xincrement"], 2.0e-06)
        self.assertEqual(result["xorigin"], -1.2e-03)
        self.assertEqual(result["yincrement"], 0.02)
        self.assertEqual(result["yorigin"], -76)
        self.assertEqual(result["yreference"], 127)
        self.assertEqual(result["zero_code"], 51)

    def test_raw(self):
        result = parse_preamble(fixture("preamble-raw.txt"))
        self.assertEqual(result["mode_name"], "RAW")
        self.assertEqual(result["points"], 4000)
        self.assertEqual(result["yincrement"], 0.0209375)
        self.assertEqual(result["zero_code"], 49)

    def test_max(self):
        result = parse_preamble(fixture("preamble-max.txt"))
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["mode"], 1)
        self.assertEqual(result["mode_name"], "MAX")
        self.assertEqual(result["points"], 240000)

    def test_truncated_field_list(self):
        result = parse_preamble(fixture("preamble-truncated.txt"))
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("preamble_field_count", result["integrity"]["reasons"])

    def test_stale_window_contradiction(self):
        result = parse_preamble(fixture("preamble-stale-window.txt"))
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("norm_mode_point_count_contradicts_window", result["integrity"]["reasons"])
        failing = check_names(result)["preamble_mode_points"]
        self.assertEqual(failing["status"], "fail")
        self.assertEqual(failing["evidence"]["expected_points"], NORM_SCREEN_POINTS)

    def test_auto_classification(self):
        metadata = parse_metadata(read_frame(fixture("preamble-raw.txt")))
        self.assertEqual(metadata["response_type"], "preamble")
        self.assertEqual(metadata["field_count"], len(PREAMBLE_FIELDS))

    def test_field_not_numeric(self):
        fields = fixture("preamble-norm.txt").decode().strip().split(",")
        fields[7] = "abc"
        result = parse_preamble((",".join(fields) + "\n").encode())
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("preamble_field_not_numeric", result["integrity"]["reasons"])

    def test_unknown_mode(self):
        fields = fixture("preamble-norm.txt").decode().strip().split(",")
        fields[1] = "7"
        result = parse_preamble((",".join(fields) + "\n").encode())
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("preamble_mode_unknown", result["integrity"]["reasons"])

    def test_word_format_is_unsupported(self):
        fields = fixture("preamble-norm.txt").decode().strip().split(",")
        fields[0] = "1"
        result = parse_preamble((",".join(fields) + "\n").encode())
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertIn("waveform_format_not_supported", result["integrity"]["reasons"])

    def test_zero_code_out_of_range(self):
        fields = fixture("preamble-norm.txt").decode().strip().split(",")
        fields[8] = "-2000"
        result = parse_preamble((",".join(fields) + "\n").encode())
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("preamble_zero_code_out_of_range", result["integrity"]["reasons"])

    def test_average_count_above_one_is_legal(self):
        fields = fixture("preamble-norm.txt").decode().strip().split(",")
        fields[3] = "16"
        result = parse_preamble((",".join(fields) + "\n").encode())
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["count"], 16)

    def test_negative_xincrement(self):
        fields = fixture("preamble-norm.txt").decode().strip().split(",")
        fields[4] = "-2.000000e-06"
        result = parse_preamble((",".join(fields) + "\n").encode())
        self.assertEqual(result["status"], "INVALID")

    def test_normalize_preamble_direct(self):
        artifact = normalize_preamble(fixture("preamble-norm.txt").decode().strip().split(","))
        self.assertEqual(artifact["zero_code"], 51)
        self.assertEqual(artifact["zero_volts_formula"], "(code - yorigin - yreference) * yincrement")


class IEEEBlockTests(unittest.TestCase):
    def test_roundtrip(self):
        payload = b"\x01\x02\x03\x04"
        block = encode_ieee_block(payload)
        self.assertTrue(block.startswith(b"#9000000004"))
        decoded = parse_ieee_block(block)
        self.assertEqual(decoded.payload, payload)
        self.assertEqual(decoded.declared_length, 4)
        self.assertEqual(decoded.trailing, b"")

    def test_measured_header_shape(self):
        block = encode_ieee_block(b"\x00" * 1200)
        self.assertTrue(block.startswith(b"#9000001200"))

    def test_indefinite(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_ieee_block(b"#0abc")
        self.assertEqual(ctx.exception.status, "UNSUPPORTED")

    def test_missing_marker(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_ieee_block(b"1200")
        self.assertEqual(ctx.exception.reason, "block_marker_missing")

    def test_non_numeric_length(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_ieee_block(b"#9" + b"abcdefghi")
        self.assertEqual(ctx.exception.status, "INVALID")

    def test_truncated(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_ieee_block(b"#9000000008" + b"\x00\x00")
        self.assertEqual(ctx.exception.status, "INCOMPLETE")

    def test_oversize_declared(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_ieee_block(b"#9" + str(MAX_BLOCK_BYTES + 1).encode().rjust(9, b"0"))
        self.assertEqual(ctx.exception.status, "UNSUPPORTED")

    def test_trailing_rejected_when_disallowed(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_ieee_block(b"#9000000002\x00\x01X", allow_trailing=False)
        self.assertEqual(ctx.exception.status, "INVALID")

    def test_block_description(self):
        result = parse_block(fixture("waveform-norm-block.bin"))
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["declared_bytes"], 1200)
        self.assertEqual(result["payload_bytes"], 1200)
        self.assertEqual(result["trailing_hex"], "0a")
        self.assertEqual(check_names(result)["trailing_bytes"]["status"], "pass")

    def test_unknown_trailing(self):
        result = parse_block(fixture("block-unknown-trailing.bin"))
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("unexpected_trailing_bytes", result["integrity"]["reasons"])


class CodeConversionTests(unittest.TestCase):
    def test_manual_formula(self):
        # Manual p. 2-221: (0x8E - YORigin - YREFerence) x YINCrement.
        self.assertEqual(
            sample_voltage(0x8E, yorigin=-76, yreference=127, yincrement=0.02),
            (0x8E - (-76) - 127) * 0.02,
        )

    def test_zero_code_is_zero_volts(self):
        self.assertEqual(sample_voltage(51, yorigin=-76, yreference=127, yincrement=0.02), 0.0)

    def test_norm_extremes_match_measurements(self):
        self.assertAlmostEqual(sample_voltage(49, yorigin=-76, yreference=127, yincrement=0.02), -0.04)
        self.assertAlmostEqual(sample_voltage(201, yorigin=-76, yreference=127, yincrement=0.02), 3.0)

    def test_bad_code(self):
        for code in (-1, 256, 1.0, True):
            with self.assertRaises(ProtocolError):
                sample_voltage(code, yorigin=0, yreference=0, yincrement=1)  # type: ignore[arg-type]

    def test_bad_scale(self):
        with self.assertRaises(ProtocolError):
            sample_voltage(1, yorigin=0, yreference=0, yincrement=0)

    def test_sample_time(self):
        self.assertAlmostEqual(sample_time(0, xorigin=-1.2e-3, xincrement=2e-6), -1.2e-3)
        self.assertAlmostEqual(sample_time(1199, xorigin=-1.2e-3, xincrement=2e-6), 1.198e-3)

    def test_bad_index(self):
        with self.assertRaises(ProtocolError):
            sample_time(-1, xorigin=0, xincrement=1)

    def test_summarize(self):
        summary = summarize_codes(bytes([49, 51, 201]), yorigin=-76, yreference=127, yincrement=0.02)
        self.assertEqual(summary["points"], 3)
        self.assertEqual(summary["min_code"], 49)
        self.assertEqual(summary["max_code"], 201)
        self.assertAlmostEqual(summary["vpp_volts"], 3.04)

    def test_iter_codes(self):
        self.assertEqual(list(iter_codes(b"\x00\xff")), [0, 255])


class WaveformTests(unittest.TestCase):
    def test_norm_complete(self):
        result = parse_waveform(fixture("waveform-norm-ch1.bin"))
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["points"], 1200)
        self.assertEqual(result["bytes_per_point"], 1)
        self.assertEqual(result["declared_block_bytes"], 1200)
        self.assertEqual(result["mode"], "NORM")
        self.assertEqual(result["zero_code"], 51)
        self.assertEqual(result["codes"]["min_code"], 49)
        self.assertEqual(result["codes"]["max_code"], 201)
        self.assertAlmostEqual(result["codes"]["vpp_volts"], 3.04)
        self.assertEqual(result["calibration"]["status"], "UNVERIFIED")
        self.assertEqual(result["analysis_allowed"], "code-domain-only")

    def test_norm_matches_measurements(self):
        # One screen, one signal: the decoded codes reproduce VMIN/VMAX/VPP.
        result = parse_waveform(fixture("waveform-norm-ch1.bin"))
        self.assertAlmostEqual(result["codes"]["min_volts"], -0.04)
        self.assertAlmostEqual(result["codes"]["max_volts"], 3.0)
        self.assertAlmostEqual(result["codes"]["vpp_volts"], 3.04)

    def test_block_only_is_unverified(self):
        result = parse_waveform(fixture("waveform-norm-block.bin"))
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertFalse(result["preamble_present"])
        self.assertIsNone(result["mode"])
        self.assertIn("preamble_missing", result["integrity"]["reasons"])
        self.assertEqual(result["points"], 1200)

    def test_samples_are_opt_in(self):
        self.assertNotIn("samples", parse_waveform(fixture("waveform-norm-ch1.bin")))
        result = parse_waveform(fixture("waveform-norm-ch1.bin"), include_samples=True)
        self.assertEqual(len(result["samples"]), 1200)
        self.assertEqual(result["samples"][0], 55)
        self.assertAlmostEqual(result["sample_voltages"][0], 0.08)

    def test_raw_uses_its_own_yincrement(self):
        result = parse_waveform(fixture("waveform-raw-ch1.bin"))
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["mode"], "RAW")
        self.assertEqual(result["points"], 4000)
        self.assertEqual(result["yincrement"], 0.0209375)
        self.assertNotEqual(result["yincrement"], 0.02)
        self.assertEqual(result["zero_code"], 49)
        self.assertAlmostEqual(result["codes"]["min_volts"], 0.0)
        self.assertAlmostEqual(result["codes"]["max_volts"], 0.08375)

    def test_separate_preamble_argument(self):
        result = parse_waveform(
            fixture("waveform-norm-block.bin"),
            preamble_raw=fixture("preamble-norm.txt"),
        )
        self.assertEqual(result["status"], "COMPLETE")
        self.assertTrue(result["preamble_present"])

    def test_prefixed_block_and_separate_preamble_agree(self):
        combined = parse_waveform(fixture("waveform-norm-ch1.bin"))
        separate = parse_waveform(
            fixture("waveform-norm-block.bin"), preamble_raw=fixture("preamble-norm.txt")
        )
        self.assertEqual(combined["payload_sha256"], separate["payload_sha256"])
        self.assertEqual(combined["codes"], separate["codes"])

    def test_length_short(self):
        result = parse_waveform(fixture("waveform-length-short.bin"))
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIn("block_payload_truncated", result["integrity"]["reasons"])

    def test_length_extra(self):
        result = parse_waveform(fixture("waveform-length-extra.bin"))
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("unexpected_trailing_bytes", result["integrity"]["reasons"])

    def test_points_mismatch(self):
        result = parse_waveform(fixture("waveform-points-mismatch.bin"))
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("declared_points_do_not_match_payload", result["integrity"]["reasons"])
        failing = check_names(result)["declared_points"]
        self.assertEqual(failing["evidence"], {"declared_points": 1200, "observed_points": 1000})

    def test_stale_norm_preamble_invalidates_waveform(self):
        stale = fixture("preamble-stale-window.txt") + encode_ieee_block(b"\x33" * 240001) + b"\n"
        result = parse_waveform(stale)
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("norm_mode_point_count_contradicts_window", result["integrity"]["reasons"])

    def test_window_consistency_pass(self):
        result = parse_waveform(fixture("waveform-raw-ch1.bin"), window_start=1, window_stop=4000)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(check_names(result)["window_consistency"]["status"], "pass")

    def test_window_consistency_fail(self):
        result = parse_waveform(fixture("waveform-raw-ch1.bin"), window_start=1, window_stop=100)
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("window_points_do_not_match_payload", result["integrity"]["reasons"])

    def test_window_requires_both_bounds(self):
        with self.assertRaises(ProtocolError):
            parse_waveform(fixture("waveform-raw-ch1.bin"), window_start=1)

    def test_window_not_checked_without_bounds(self):
        result = parse_waveform(fixture("waveform-raw-ch1.bin"))
        self.assertEqual(check_names(result)["window_consistency"]["status"], "not_checked")

    def test_empty(self):
        self.assertEqual(parse_waveform(b"")["status"], "INCOMPLETE")

    def test_no_block_marker(self):
        self.assertEqual(parse_waveform(b"nothing here\n")["status"], "INVALID")

    def test_trailing_lf_allowed(self):
        raw = fixture("waveform-norm-ch1.bin")
        self.assertEqual(parse_waveform(raw + b"\n")["status"], "INVALID")
        block_without_terminator = fixture("waveform-norm-block.bin")[:-1]
        self.assertEqual(parse_waveform(block_without_terminator + b"\r\n")["status"], "UNVERIFIED")
        self.assertEqual(parse_waveform(block_without_terminator)["status"], "UNVERIFIED")

    def test_malformed_preamble_argument(self):
        result = parse_waveform(
            fixture("waveform-norm-block.bin"),
            preamble_raw=fixture("preamble-truncated.txt"),
        )
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("preamble_field_count", result["integrity"]["reasons"])
        self.assertIsNone(result["codes"])
        self.assertEqual(result["analysis_allowed"], "none")

    def test_word_format_payload_is_counted_in_two_byte_points(self):
        preamble = fixture("preamble-raw.txt").replace(b"0,2,4000,", b"1,2,2000,")
        block = encode_ieee_block(b"\x33\x00" * 2000) + b"\n"
        result = parse_waveform(block, preamble_raw=preamble)
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertEqual(result["bytes_per_point"], 2)
        self.assertEqual(result["points"], 2000)
        self.assertIsNone(result["codes"])

    def test_inline_sample_limit(self):
        big = encode_ieee_block(b"\x33" * (1_000_001))
        raw = fixture("preamble-raw.txt").replace(b"0,2,4000,", b"0,2,1000001,") + big + b"\n"
        result = parse_waveform(raw, include_samples=True)
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertIn("inline_samples_too_large", result["integrity"]["reasons"])

    def test_failure_preserves_raw_hash(self):
        raw = fixture("waveform-length-short.bin")
        result = parse_waveform(raw)
        self.assertEqual(result["integrity"]["raw_sha256"], hashlib.sha256(raw).hexdigest())

    def test_expected_norm_fixture(self):
        spec = expected("expected-waveform-norm.json")
        result = parse_waveform(fixture(spec["fixture"]))
        self.assertEqual(result["status"], spec["status"])
        self.assertEqual(result["points"], spec["points"])
        self.assertEqual(result["mode"], spec["mode"])
        self.assertEqual(result["yincrement"], spec["yincrement"])
        self.assertEqual(result["zero_code"], spec["zero_code"])
        self.assertEqual(result["codes"], spec["codes"])
        self.assertEqual(result["payload_sha256"], spec["payload_sha256"])
        self.assertEqual(result["calibration"]["status"], spec["calibration"])
        block_only = parse_waveform(fixture(spec["block_only"]["fixture"]))
        self.assertEqual(block_only["status"], spec["block_only"]["status"])

    def test_expected_raw_fixture(self):
        spec = expected("expected-waveform-raw.json")
        result = parse_waveform(fixture(spec["fixture"]))
        self.assertEqual(result["status"], spec["status"])
        self.assertEqual(result["points"], spec["points"])
        self.assertEqual(result["yincrement"], spec["yincrement"])
        self.assertEqual(result["zero_code"], spec["zero_code"])
        self.assertEqual(result["codes"], spec["codes"])


class CsvTests(unittest.TestCase):
    def test_norm_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wave.csv"
            result = waveform_to_csv(fixture("waveform-norm-ch1.bin"), out)
            lines = out.read_text().splitlines()
            self.assertEqual(result["rows"], 1200)
            self.assertEqual(lines[0], "index,t_seconds,code,voltage,voltage_unit")
            self.assertEqual(lines[1], "0,-0.0012,55,0.08,V")
            self.assertEqual(lines[1200], "1199,0.001198,196,2.9,V")
            self.assertEqual(result["csv_sha256"], hashlib.sha256(out.read_bytes()).hexdigest())
            self.assertEqual(result["calibration_status"], "UNVERIFIED")

    def test_block_only_csv_has_empty_axes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wave.csv"
            waveform_to_csv(fixture("waveform-norm-block.bin"), out)
            self.assertEqual(out.read_text().splitlines()[1], "0,,55,,")

    def test_separate_preamble(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wave.csv"
            result = waveform_to_csv(
                fixture("waveform-norm-block.bin"), out, preamble_raw=fixture("preamble-norm.txt")
            )
            self.assertTrue(result["preamble_present"])
            self.assertEqual(out.read_text().splitlines()[1], "0,-0.0012,55,0.08,V")

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wave.csv"
            out.write_text("operator data\n")
            with self.assertRaises(FileExistsError):
                waveform_to_csv(fixture("waveform-norm-ch1.bin"), out)
            self.assertEqual(out.read_text(), "operator data\n")

    def test_overwrite_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wave.csv"
            out.write_text("operator data\n")
            result = waveform_to_csv(fixture("waveform-norm-ch1.bin"), out, overwrite=True)
            self.assertEqual(result["rows"], 1200)

    def test_invalid_waveform_not_exported(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProtocolError):
                waveform_to_csv(fixture("waveform-length-short.bin"), Path(tmp) / "w.csv")


def _bmp(width: int, height: int) -> bytes:
    row = ((width * 24 + 31) // 32) * 4
    pixels = bytes(range(row % 256)) * (height * row // max(row % 256, 1) + 1)
    pixels = pixels[: height * row]
    header = struct.pack("<2sIHHI", b"BM", 54 + len(pixels), 0, 0, 54)
    dib = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(pixels), 2835, 2835, 0, 0)
    return header + dib + pixels


class ScreenshotTests(unittest.TestCase):
    def test_compact_fixture(self):
        result = parse_screenshot(fixture("screenshot-compact.bin"))
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["declared_bytes"], 102)
        self.assertEqual(result["payload_bytes"], 102)
        self.assertEqual(result["trailing_bytes"], 3)
        self.assertEqual(result["trailing_hex"], "3b300a")
        self.assertEqual(result["panel"], [4, 4])
        self.assertEqual(result["bits_per_pixel"], 24)
        self.assertIn("firmware_trailing_bytes_after_block", result["integrity"]["reasons"])
        self.assertIn("panel_geometry_differs_from_800x480", result["integrity"]["limitations"])

    def test_real_header_is_truncated(self):
        result = parse_screenshot(fixture("screenshot-color-head.bin"))
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIn("block_payload_truncated", result["integrity"]["reasons"])

    def test_bad_signature(self):
        result = parse_screenshot(fixture("screenshot-bad-signature.bin"))
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("bmp_signature_missing", result["integrity"]["reasons"])

    def test_size_mismatch(self):
        result = parse_screenshot(fixture("screenshot-size-mismatch.bin"))
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("bmp_file_size_mismatch", result["integrity"]["reasons"])

    def test_trailing_quirk_trimmed_on_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "shot.bmp"
            result = parse_screenshot(fixture("screenshot-compact.bin"), out=out)
            written = out.read_bytes()
            self.assertEqual(len(written), 102)
            self.assertFalse(written.endswith(b";0\n"))
            self.assertEqual(written[:2], b"BM")
            self.assertEqual(result["written"]["sha256"], result["trimmed_bmp_sha256"])
            self.assertEqual(written, parse_ieee_block(fixture("screenshot-compact.bin")).payload)

    def test_write_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "shot.bmp"
            out.write_bytes(b"operator data")
            with self.assertRaises(FileExistsError):
                parse_screenshot(fixture("screenshot-compact.bin"), out=out)
            self.assertEqual(out.read_bytes(), b"operator data")

    def test_unknown_trailing_bytes_invalid(self):
        raw = encode_ieee_block(_bmp(4, 4)) + b"junk"
        self.assertEqual(parse_screenshot(raw)["status"], "INVALID")

    def test_bmp_header(self):
        header = parse_bmp_header(_bmp(800, 480))
        self.assertEqual(header["width"], 800)
        self.assertEqual(header["height"], 480)
        self.assertTrue(header["matches_scope_panel"])
        self.assertEqual(header["pixel_bytes"], 800 * 480 * 3)

    def test_empty(self):
        self.assertEqual(parse_screenshot(b"")["status"], "INCOMPLETE")

    def test_expected_fixture(self):
        spec = expected("expected-screenshot.json")
        result = parse_screenshot(fixture(spec["fixture"]))
        self.assertEqual(result["status"], spec["status"])
        self.assertEqual(result["declared_bytes"], spec["declared_bytes"])
        self.assertEqual(result["trailing_hex"], spec["trailing_hex"])
        self.assertEqual(result["trimmed_bmp_sha256"], spec["trimmed_bmp_sha256"])
        real = parse_screenshot(fixture(spec["real_frame"]["fixture"]))
        self.assertEqual(real["status"], spec["real_frame"]["status"])


def cursor_replies(name: str, family: str) -> dict[str, bytes]:
    """Split one replay container into the family's replies, in query order."""

    lines = fixture(name).splitlines(keepends=True)
    keys = CURSOR_FAMILY_QUERIES[family]
    if len(lines) != len(keys):
        raise AssertionError(f"{name}: {len(lines)} replies for {len(keys)} queries")
    return dict(zip(keys, lines))


class CursorReadingTests(unittest.TestCase):
    def test_manual_position_is_a_pixel(self):
        result = parse_cursor(b"100\n", quantity="manual_ax")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["value"], 100)
        self.assertEqual(result["unit"], "pixel")
        self.assertEqual(result["value_kind"], "pixel")
        self.assertEqual(result["command"], ":CURSor:MANual:AX?")
        self.assertEqual(result["integrity"]["raw_sha256"], hashlib.sha256(b"100\n").hexdigest())

    def test_manual_value_is_physical(self):
        result = parse_cursor(fixture("cursor-no-result.txt"), quantity="manual_ayvalue")
        self.assertEqual(result["value_kind"], "nr3")
        self.assertEqual(result["numeric_token"], "9.9E37")

    def test_units_follow_the_unit_tokens(self):
        value = parse_cursor(b"1.600000e-03\n", quantity="manual_xdelta", t_unit="S")
        self.assertEqual(value["unit"], "s")
        inverse = parse_cursor(b"6.250000e+02\n", quantity="manual_ixdelta", t_unit="S")
        self.assertEqual(inverse["unit"], "Hz")
        # VUNit SOUR means "whatever :CHANnel<n>:UNITs is", which is not queried.
        volts = parse_cursor(b"2.520000e+00\n", quantity="manual_ayvalue", v_unit="SOUR")
        self.assertIsNone(volts["unit"])
        percent = parse_cursor(b"5.200000e+01\n", quantity="manual_ayvalue", v_unit="PERC")
        self.assertEqual(percent["unit"], "%")

    def test_no_result_sentinel_is_not_a_number(self):
        result = parse_cursor(fixture("cursor-no-result.txt"), quantity="manual_ayvalue")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIsNone(result["value"])
        self.assertEqual(result["sentinel"], "9.9E37")
        self.assertEqual(result["integrity"]["reasons"], ["no_cursor_result"])

    def test_position_unset_sentinel_is_not_a_number(self):
        result = parse_cursor(fixture("cursor-position-unset.txt"), quantity="auto_ay")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIsNone(result["value"])
        self.assertEqual(result["sentinel"], "4294967295")
        self.assertEqual(result["integrity"]["reasons"], ["cursor_position_unset"])

    def test_position_unset_sentinel_in_a_delta(self):
        # Manual p. 2-23: :CURSor:MANual:YDELta? answers 4294967295 for an LA
        # source. Same uint32 -1 sentinel, different meaning.
        result = parse_cursor(b"4294967295\n", quantity="manual_ydelta")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIsNone(result["value"])
        self.assertEqual(result["integrity"]["reasons"], ["cursor_value_unset"])

    def test_command_error_is_unsupported(self):
        result = parse_cursor(fixture("cursor-command-error.bin"), quantity="manual_ax")
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertTrue(result["command_error"])
        self.assertIsNone(result["value"])

    def test_empty_and_blank_replies_are_incomplete(self):
        self.assertEqual(parse_cursor(b"", quantity="manual_ax")["status"], "INCOMPLETE")
        self.assertEqual(parse_cursor(b"\n", quantity="manual_ax")["status"], "INCOMPLETE")

    def test_unknown_quantity(self):
        result = parse_cursor(b"1\n", quantity="manual_nope")
        self.assertEqual(result["status"], "INVALID")
        self.assertEqual(result["integrity"]["reasons"], ["quantity_unknown"])

    def test_pixel_and_value_never_cross(self):
        # A physical value is not a pixel and a pixel is not a physical value.
        self.assertEqual(parse_cursor(b"12.5\n", quantity="manual_ax")["status"], "INVALID")
        self.assertEqual(parse_cursor(b"three\n", quantity="manual_axvalue")["status"], "INVALID")
        self.assertEqual(parse_cursor(b"1,2\n", quantity="manual_ax")["status"], "INVALID")

    def test_position_outside_documented_range(self):
        result = parse_cursor(b"700\n", quantity="manual_ax")
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["integrity"]["reasons"], ["cursor_position_out_of_documented_range"])

    def test_enum_setting(self):
        self.assertEqual(parse_cursor(fixture("cursor-mode-track.txt"), quantity="mode")["value"], "TRAC")
        self.assertEqual(parse_cursor(b"X\n", quantity="manual_type")["status"], "COMPLETE")
        unexpected = parse_cursor(b"Z\n", quantity="manual_type")
        self.assertEqual(unexpected["status"], "UNVERIFIED")
        self.assertEqual(unexpected["integrity"]["reasons"], ["cursor_setting_unexpected"])


class CursorReadoutTests(unittest.TestCase):
    def test_manual_family(self):
        replies = cursor_replies("cursor-manual-values.txt", "manual")
        replies["mode"] = fixture("cursor-mode-man.txt")
        result = parse_cursor_readout(replies["mode"], replies)
        self.assertEqual(result["kind"], "cursor-readout")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["mode"], "MAN")
        self.assertEqual(result["family"], "manual")
        self.assertEqual((result["type"], result["source"]), ("X", "CHAN1"))
        self.assertEqual((result["t_unit"], result["v_unit"]), ("S", "SOUR"))
        self.assertEqual(result["positions"], {"ax": 100, "bx": 500, "ay": 100, "by": 300})
        self.assertEqual(result["deltas"]["ixdelta"], 625.0)
        self.assertEqual(result["units"]["position"]["ax"], "pixel")
        self.assertEqual(result["units"]["delta"]["ixdelta"], "Hz")
        checks = {check["name"]: check["status"] for check in result["integrity"]["checks"]}
        self.assertEqual(checks["cursor_mode"], "pass")
        self.assertEqual(checks["cursor_field_count"], "pass")
        self.assertEqual(checks["cursor_numeric"], "pass")
        self.assertEqual(checks["cursor_result_present"], "pass")
        self.assertEqual(checks["cursor_position_set"], "pass")
        # Every reading keeps its own hash and repr.
        for reading in result["readings"]:
            self.assertEqual(len(reading["raw"]["sha256"]), 64)
            self.assertIsNotNone(reading["raw"]["repr"])

    def test_track_family(self):
        replies = cursor_replies("cursor-track-values.txt", "track")
        replies["mode"] = fixture("cursor-mode-track.txt")
        result = parse_cursor_readout(fixture("cursor-mode-track.txt"), replies)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["family"], "track")
        self.assertEqual(result["sources"], {"a": "CHAN1", "b": "CHAN1"})
        self.assertEqual(result["positions"], {"ax": 299, "bx": 301, "ay": 352, "by": 76})
        self.assertEqual(result["units"]["value"]["ax"], "s")

    def test_auto_family_reports_both_sentinels(self):
        replies = cursor_replies("cursor-auto-unset.txt", "auto")
        replies["mode"] = fixture("cursor-mode-auto.txt")
        result = parse_cursor_readout(fixture("cursor-mode-auto.txt"), replies)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["item"], "ITEM5")
        self.assertEqual(result["positions"]["ax"], 50)
        self.assertIsNone(result["positions"]["ay"])
        self.assertIsNone(result["values"]["ay"])
        self.assertEqual(
            sorted(result["integrity"]["reasons"]), ["cursor_position_unset", "no_cursor_result"]
        )
        checks = {check["name"]: check["status"] for check in result["integrity"]["checks"]}
        self.assertEqual(checks["cursor_position_set"], "fail")
        self.assertEqual(checks["cursor_result_present"], "fail")

    def test_xy_family_readings(self):
        lines = fixture("cursor-xy-values.txt").splitlines(keepends=True)
        keys = CURSOR_FAMILY_QUERIES["xy"]
        replies = dict(zip(keys, lines))
        self.assertEqual(parse_cursor(replies["xy_ax"], quantity="xy_ax")["value"], 100)
        self.assertEqual(parse_cursor(replies["xy_by"], quantity="xy_by")["value"], 300)
        self.assertEqual(
            parse_cursor(replies["xy_axvalue"], quantity="xy_axvalue")["status"], "INCOMPLETE"
        )

    def test_missing_field_is_incomplete(self):
        replies = cursor_replies("cursor-manual-values.txt", "manual")
        replies.pop("manual_ydelta")
        result = parse_cursor_readout("MAN", replies)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["integrity"]["reasons"], ["cursor_field_missing"])
        self.assertIsNone(result["deltas"]["ydelta"])
        checks = {check["name"]: check for check in result["integrity"]["checks"]}
        self.assertEqual(checks["cursor_field_count"]["evidence"]["missing"], ["manual_ydelta"])

    def test_missing_mode(self):
        result = parse_cursor_readout(None, {})
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["integrity"]["reasons"], ["cursor_mode_missing"])

    def test_disabled_and_unknown_modes(self):
        off = parse_cursor_readout("OFF", {})
        self.assertEqual(off["status"], "INCOMPLETE")
        self.assertEqual(off["integrity"]["reasons"], ["cursor_disabled"])
        self.assertIsNone(off["family"])
        unknown = parse_cursor_readout("BOGUS", {})
        self.assertEqual(unknown["status"], "UNSUPPORTED")
        self.assertEqual(unknown["integrity"]["reasons"], ["cursor_mode_unknown"])

    def test_other_family_readings_are_listed_not_used(self):
        replies = cursor_replies("cursor-manual-values.txt", "manual")
        replies["auto_ax"] = b"50\n"
        result = parse_cursor_readout("MAN", replies)
        self.assertEqual(result["ignored_readings"], ["auto_ax"])
        self.assertEqual(result["positions"]["ax"], 100)

    def test_command_error_field_is_unsupported(self):
        replies = cursor_replies("cursor-manual-values.txt", "manual")
        replies["manual_ax"] = fixture("cursor-command-error.bin")
        result = parse_cursor_readout("MAN", replies)
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertIn("instrument_command_error", result["integrity"]["reasons"])

    def test_expected_fixture(self):
        spec = expected("expected-cursor.json")
        containers = spec["replay_containers"]
        manual = containers["manual"]
        replies = cursor_replies(manual["fixture"], manual["family"])
        replies["mode"] = fixture(manual["mode_fixture"])
        result = parse_cursor_readout(replies["mode"], replies)
        self.assertEqual(result["status"], manual["status"])
        self.assertEqual(result["mode"], manual["mode"])
        self.assertEqual(result["type"], manual["type"])
        self.assertEqual(result["source"], manual["source"])
        self.assertEqual(result["t_unit"], manual["t_unit"])
        self.assertEqual(result["v_unit"], manual["v_unit"])
        self.assertEqual(result["positions"], manual["positions"])
        for key, value in manual["values"].items():
            self.assertAlmostEqual(result["values"][key], value, places=12)
        for key, value in manual["deltas"].items():
            self.assertAlmostEqual(result["deltas"][key], value, places=12)

        auto = containers["auto"]
        replies = cursor_replies(auto["fixture"], auto["family"])
        replies["mode"] = fixture(auto["mode_fixture"])
        result = parse_cursor_readout(replies["mode"], replies)
        self.assertEqual(result["status"], auto["status"])
        self.assertEqual(result["positions"], auto["positions"])
        self.assertEqual(sorted(result["integrity"]["reasons"]), sorted(auto["reasons"]))

        for name in ("no_result", "position_unset", "command_error"):
            single = spec["single_replies"][name]
            result = parse_cursor(fixture(single["fixture"]), quantity=single["quantity"])
            self.assertEqual(result["status"], single["status"], name)
            self.assertIsNone(result["value"], name)
            self.assertEqual(result["integrity"]["reasons"], single["reasons"], name)

        empty = spec["single_replies"]["empty"]
        result = parse_cursor(b"", quantity=empty["quantity"])
        self.assertEqual(result["status"], empty["status"])
        self.assertEqual(result["integrity"]["reasons"], empty["reasons"])


class IsolationTests(unittest.TestCase):
    def test_no_socket_import(self):
        tree = ast.parse((SCRIPTS / "ds1000z_protocol.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertNotIn("socket", [alias.name for alias in node.names])
            if isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "socket")


class CliTests(unittest.TestCase):
    def _run(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(argv)
        return code, json.loads(buffer.getvalue())

    def test_identity(self):
        code, result = self._run(["identity", str(FIXTURES / "identity.txt")])
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "COMPLETE")

    def test_measurement(self):
        code, result = self._run(["measurement", str(FIXTURES / "measurement-vpp.txt"), "--quantity", "vpp"])
        self.assertEqual(code, 0)
        self.assertEqual(result["value"], 3.04)

    def test_measurement_no_result_exit(self):
        code, result = self._run(["measurement", str(FIXTURES / "measurement-no-result.txt"), "--quantity", "vpp"])
        self.assertEqual(code, 1)
        self.assertIsNone(result["value"])

    def test_cursor_bundle_manual(self):
        code, result = self._run(["cursor", str(FIXTURES / "cursor-manual-values.txt"), "--mode", "MAN"])
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["positions"], {"ax": 100, "bx": 500, "ay": 100, "by": 300})
        self.assertAlmostEqual(result["values"]["ax"], -8e-4)

    def test_cursor_bundle_track(self):
        code, result = self._run(["cursor", str(FIXTURES / "cursor-track-values.txt"), "--mode", "TRAC"])
        self.assertEqual(code, 0)
        self.assertEqual(result["family"], "track")
        self.assertAlmostEqual(result["values"]["by"], 2.76)

    def test_cursor_bundle_sentinels_are_incomplete(self):
        code, result = self._run(["cursor", str(FIXTURES / "cursor-auto-unset.txt"), "--mode", "AUTO"])
        self.assertEqual(code, 1)
        self.assertIsNone(result["positions"]["ay"])
        self.assertIsNone(result["values"]["ay"])
        self.assertIn("cursor_position_unset", result["integrity"]["reasons"])

    def test_cursor_bundle_length_mismatch_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "short.txt"
            path.write_bytes(b"X\nCHAN1\n")
            buffer, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(err):
                code = main(["cursor", str(path), "--mode", "MAN"])
        self.assertEqual(code, 2)
        self.assertIn("cursor_bundle_length", err.getvalue())

    def test_error_queue(self):
        code, result = self._run(["error-queue", str(FIXTURES / "error-queue-undefined.txt")])
        self.assertEqual(code, 0)
        self.assertEqual(result["code"], -113)

    def test_preamble(self):
        code, result = self._run(["preamble", str(FIXTURES / "preamble-stale-window.txt")])
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "INVALID")

    def test_waveform_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wave.csv"
            code, result = self._run(
                ["waveform", str(FIXTURES / "waveform-norm-ch1.bin"), "--csv-out", str(out)]
            )
            self.assertEqual(code, 0)
            self.assertEqual(result["csv"]["rows"], 1200)
            self.assertTrue(out.exists())

    def test_waveform_separate_preamble(self):
        code, result = self._run(
            [
                "waveform",
                str(FIXTURES / "waveform-norm-block.bin"),
                "--preamble",
                str(FIXTURES / "preamble-norm.txt"),
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "COMPLETE")

    def test_screenshot_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "shot.bmp"
            code, result = self._run(["screenshot", str(FIXTURES / "screenshot-compact.bin"), "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertEqual(out.read_bytes()[:2], b"BM")
            self.assertEqual(result["written"]["bytes"], 102)

    def test_block(self):
        code, result = self._run(["block", str(FIXTURES / "waveform-norm-block.bin")])
        self.assertEqual(code, 0)
        self.assertEqual(result["declared_bytes"], 1200)

    def test_truncated_exit(self):
        code, _ = self._run(["waveform", str(FIXTURES / "waveform-length-short.bin")])
        self.assertEqual(code, 1)


class ManifestTests(unittest.TestCase):
    def test_manifest_hash_and_fields(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        self.assertEqual(manifest["schema_version"], "artifact-envelope-v1")
        self.assertEqual(manifest["instrument"]["firmware"], "00.04.02.SP4")
        self.assertEqual(manifest["instrument"]["serial"], "DS1ZA171004155")
        self.assertEqual(manifest["support"]["level"], "firmware-scoped")
        self.assertTrue(manifest["support"]["hardware_verified"])
        raw = (ROOT / manifest["data"]["raw_path"]).read_bytes()
        self.assertEqual(manifest["data"]["raw_sha256"], hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
