from __future__ import annotations

import base64
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gds1000b_protocol import (  # noqa: E402
    AD_FACTOR,
    MAX_LINE_BYTES,
    MAX_PAYLOAD_BYTES,
    MAX_POINTS,
    IEEEBlock,
    ProtocolError,
    encode_ieee_block,
    extract_payload,
    iter_samples,
    main,
    normalize,
    normalize_waveform,
    parse_error_queue,
    parse_identity,
    parse_ieee_block,
    parse_measurement,
    parse_metadata,
    parse_waveform,
    parse_waveform_header,
    read_frame,
    sample_value,
    validate,
    waveform_to_csv,
)


def _waveform_fixture() -> bytes:
    return (FIXTURES / "waveform-valid.bin").read_bytes()


def _header() -> bytes:
    raw = _waveform_fixture()
    marker = b"Waveform Data;"
    return raw[: raw.index(marker)]


def _with_header(header: bytes, block: bytes) -> bytes:
    return header + b"Waveform Data;" + block


class FrameTests(unittest.TestCase):
    def test_lf(self):
        frame = read_frame(b"abc\n")
        self.assertEqual(frame.content, b"abc")
        self.assertEqual(frame.terminator, b"\n")
        self.assertEqual(frame.trailing, b"")

    def test_cr(self):
        self.assertEqual(read_frame(b"abc\r").terminator, b"\r")

    def test_crlf(self):
        self.assertEqual(read_frame(b"abc\r\n").terminator, b"\r\n")

    def test_lfcr(self):
        self.assertEqual(read_frame(b"abc\n\r").terminator, b"\n\r")

    def test_empty(self):
        with self.assertRaises(ProtocolError) as ctx:
            read_frame(b"")
        self.assertEqual(ctx.exception.status, "INCOMPLETE")

    def test_missing_terminator(self):
        with self.assertRaises(ProtocolError) as ctx:
            read_frame(b"abc")
        self.assertEqual(ctx.exception.status, "INCOMPLETE")

    def test_trailing_bytes(self):
        with self.assertRaises(ProtocolError) as ctx:
            read_frame(b"abc\ndef")
        self.assertEqual(ctx.exception.status, "INVALID")

    def test_oversized_line(self):
        with self.assertRaises(ProtocolError) as ctx:
            read_frame(b"a" * (MAX_LINE_BYTES + 1) + b"\n")
        self.assertEqual(ctx.exception.status, "UNSUPPORTED")

    def test_non_bytes(self):
        with self.assertRaises(ProtocolError):
            read_frame("abc\n")  # type: ignore[arg-type]


class IdentityTests(unittest.TestCase):
    def test_valid_fixture(self):
        raw = (FIXTURES / "identity.txt").read_bytes()
        result = parse_identity(raw)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["vendor"], "GW")
        self.assertEqual(result["model"], "GDS-1102B")
        self.assertEqual(result["serial"], "P123456")
        self.assertEqual(result["firmware"], "V1.00")
        self.assertEqual(result["profile"]["channels"], 2)
        self.assertFalse(result["profile"]["ethernet"])
        self.assertTrue(result["profile"]["external_trigger"])
        self.assertEqual(base64.b64decode(result["integrity"]["raw_response_base64"]), raw)

    def test_wrong_model(self):
        result = parse_identity((FIXTURES / "identity-wrong-model.txt").read_bytes())
        self.assertEqual(result["status"], "INVALID")

    def test_missing_firmware(self):
        result = parse_identity((FIXTURES / "identity-missing-firmware.txt").read_bytes())
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_too_few_fields(self):
        result = parse_identity(b"GW,GDS-1102B\n")
        self.assertEqual(result["status"], "INVALID")

    def test_too_many_fields(self):
        result = parse_identity(b"GW,GDS-1102B,P1,V1.00,EXTRA\n")
        self.assertEqual(result["status"], "INVALID")

    def test_wrong_vendor(self):
        result = parse_identity(b"GWX,GDS-1102B,P1,V1.00\n")
        self.assertEqual(result["status"], "INVALID")

    def test_bad_serial_prefix(self):
        result = parse_identity(b"GW,GDS-1102B,X1,V1.00\n")
        self.assertEqual(result["status"], "INVALID")

    def test_bad_firmware(self):
        result = parse_identity(b"GW,GDS-1102B,P1,firmware\n")
        self.assertEqual(result["status"], "INVALID")

    def test_missing_terminator(self):
        result = parse_identity(b"GW,GDS-1102B,P1,V1.00")
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_trailing_bytes(self):
        result = parse_identity(b"GW,GDS-1102B,P1,V1.00\nEXTRA\n")
        self.assertEqual(result["status"], "INVALID")

    def test_four_channel_profile(self):
        result = parse_identity(b"GW,GDS-1104B,P9,V2.03\n")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["profile"]["channels"], 4)
        self.assertTrue(result["profile"]["ethernet"])
        self.assertTrue(result["profile"]["ethernet_dhcp_command"])

    def test_stage_composition(self):
        raw = (FIXTURES / "identity.txt").read_bytes()
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="identity")
        payload = extract_payload(metadata)
        artifact = normalize(metadata, payload)
        result = validate(artifact, raw)
        self.assertEqual(payload["model"], "GDS-1102B")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["integrity"]["status"], "COMPLETE")

    def test_auto_identity(self):
        metadata = parse_metadata(read_frame(b"GW,GDS-1074B,P2,V1.00\n"))
        self.assertEqual(metadata["response_type"], "identity")

    def test_expected_fixture(self):
        expected = json.loads((ROOT / "assets" / "expected-identity.json").read_text())
        result = parse_identity((FIXTURES / "identity.txt").read_bytes())
        self.assertEqual(result["status"], expected["status"])
        self.assertEqual(result["identity"], expected["identity"])
        self.assertEqual(result["profile"], expected["profile"])


class MeasurementTests(unittest.TestCase):
    def test_frequency(self):
        result = parse_measurement((FIXTURES / "measure-frequency.txt").read_bytes(), quantity="frequency")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["value"], 1032.0)
        self.assertEqual(result["raw_value"], 1032.0)
        self.assertEqual(result["unit"], "Hz")
        self.assertEqual(result["command"], ":MEASure:FREQuency?")

    def test_chan_off(self):
        result = parse_measurement((FIXTURES / "measure-chan-off.txt").read_bytes(), quantity="pk2pk")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIsNone(result["value"])
        self.assertIn("Chan Off", result["integrity"]["reasons"][0])

    def test_nan(self):
        result = parse_measurement(b"NaN\n", quantity="frequency")
        self.assertEqual(result["status"], "INVALID")

    def test_inf(self):
        result = parse_measurement(b"Inf\n", quantity="frequency")
        self.assertEqual(result["status"], "INVALID")

    def test_extra_bytes(self):
        result = parse_measurement(b"1.0\nextra\n", quantity="frequency")
        self.assertEqual(result["status"], "INVALID")

    def test_missing_terminator(self):
        result = parse_measurement(b"1.0", quantity="frequency")
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_unit_suffix_rejected(self):
        result = parse_measurement(b"1.0 kHz\n", quantity="frequency")
        self.assertEqual(result["status"], "INVALID")

    def test_unknown_quantity(self):
        result = parse_measurement(b"1.0\n", quantity="not-a-measurement")
        self.assertEqual(result["status"], "INVALID")

    def test_unit_override_voltage(self):
        result = parse_measurement(b"1.0\n", quantity="amplitude", unit="V")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["unit"], "V")

    def test_unit_conflict(self):
        result = parse_measurement(b"1.0\n", quantity="frequency", unit="V")
        self.assertEqual(result["status"], "INVALID")

    def test_source_dependent_unit(self):
        result = parse_measurement(b"1.0\n", quantity="amplitude")
        self.assertEqual(result["unit"], "V or A")
        self.assertEqual(result["unit_status"], "source-dependent")

    def test_area_unit(self):
        result = parse_measurement(b"1.0E-6\n", quantity="area")
        self.assertEqual(result["unit"], "V·s or A·s")

    def test_area_unit_override(self):
        result = parse_measurement(b"1.0E-6\n", quantity="area", unit="V·s")
        self.assertEqual(result["unit"], "V·s")

    def test_phase_unit(self):
        result = parse_measurement(b"4.50E+01\n", quantity="phase")
        self.assertEqual(result["unit"], "deg")

    def test_period_unit(self):
        result = parse_measurement(b"1.0E-3\n", quantity="period")
        self.assertEqual(result["unit"], "s")

    def test_count_unitless(self):
        result = parse_measurement(b"6.000E+00\n", quantity="ppulse")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertIsNone(result["unit"])
        self.assertEqual(result["unit_status"], "unitless")

    def test_count_rejects_unit(self):
        result = parse_measurement(b"6\n", quantity="ppulse", unit="V")
        self.assertEqual(result["status"], "INVALID")

    def test_alias(self):
        result = parse_measurement(b"1.0E+3\n", quantity="freq")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["quantity"], "frequency")

    def test_stage_composition(self):
        raw = (FIXTURES / "measure-frequency.txt").read_bytes()
        frame = read_frame(raw)
        metadata = parse_metadata(frame, response_type="measurement")
        payload = extract_payload(metadata)
        artifact = normalize(metadata, payload, quantity="frequency")
        result = validate(artifact, raw)
        self.assertEqual(payload["numeric_token"], "1.032E+3")
        self.assertEqual(result["value"], 1032.0)

    def test_auto_measurement(self):
        metadata = parse_metadata(read_frame(b"1.032E+3\n"))
        self.assertEqual(metadata["response_type"], "measurement")

    def test_expected_fixture(self):
        expected = json.loads((ROOT / "assets" / "expected-measurement.json").read_text())
        result = parse_measurement((FIXTURES / "measure-frequency.txt").read_bytes(), quantity="frequency")
        self.assertEqual(result["status"], expected["status"])
        self.assertEqual(result["value"], expected["value"])
        self.assertEqual(result["unit"], expected["unit"])


class ErrorQueueTests(unittest.TestCase):
    def test_none(self):
        result = parse_error_queue((FIXTURES / "error-none.txt").read_bytes())
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["message"], "No error.")
        self.assertTrue(result["quoted"])

    def test_undefined_auto_unsupported(self):
        result = parse_error_queue((FIXTURES / "error-undefined.txt").read_bytes())
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertEqual(result["code"], -113)

    def test_undefined_explicit(self):
        result = parse_error_queue(
            (FIXTURES / "error-undefined.txt").read_bytes(),
            response_type="error-queue",
        )
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["message"], "Undefined header")

    def test_overflow_auto(self):
        result = parse_error_queue((FIXTURES / "error-overflow.txt").read_bytes())
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_overflow_explicit(self):
        result = parse_error_queue(
            (FIXTURES / "error-overflow.txt").read_bytes(),
            response_type="error-queue",
        )
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_negative_overflow(self):
        result = parse_error_queue(b"-350,Queue Overflow\n", response_type="error-queue")
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_curly_quotes(self):
        raw = b"+0, \xe2\x80\x9cNo error.\xe2\x80\x9d\n"
        result = parse_error_queue(raw)
        self.assertEqual(result["status"], "COMPLETE")

    def test_unterminated_quote(self):
        result = parse_error_queue(b'-113, "Undefined header\n', response_type="error-queue")
        self.assertEqual(result["status"], "INVALID")

    def test_missing_comma(self):
        result = parse_error_queue(b'-113 "Undefined header"\n', response_type="error-queue")
        self.assertEqual(result["status"], "INVALID")

    def test_missing_terminator(self):
        result = parse_error_queue(b'+0, "No error."')
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_empty_message(self):
        result = parse_error_queue(b"-113, \n", response_type="error-queue")
        self.assertEqual(result["status"], "INVALID")

    def test_positive_overflow_preserved(self):
        result = parse_error_queue(b"+350, \"Queue overflow\"\n", response_type="error-queue")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["code"], 350)


class IeeeBlockTests(unittest.TestCase):
    def test_roundtrip(self):
        payload = b"\x01\x02\x03\x04"
        block = encode_ieee_block(payload)
        decoded = parse_ieee_block(block)
        self.assertEqual(decoded.payload, payload)
        self.assertEqual(decoded.trailing, b"")

    def test_length_digits(self):
        payload = b"\x00" * 16
        self.assertTrue(encode_ieee_block(payload).startswith(b"#216"))

    def test_parse_fixture(self):
        decoded = parse_ieee_block(b"#40008" + struct.pack(">4h", 0, 25, -25, 50))
        self.assertEqual(decoded.declared_length, 8)
        self.assertEqual(list(iter_samples(decoded.payload)), [0, 25, -25, 50])

    def test_indefinite(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_ieee_block(b"#0abc")
        self.assertEqual(ctx.exception.status, "UNSUPPORTED")

    def test_truncation(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_ieee_block(b"#40008" + b"\x00" * 4)
        self.assertEqual(ctx.exception.status, "INCOMPLETE")

    def test_trailing_rejected_by_default(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_ieee_block(b"#40002\x00\x01X")
        self.assertEqual(ctx.exception.status, "INVALID")

    def test_trailing_terminator_allowed(self):
        decoded = parse_ieee_block(b"#40002\x00\x01\n", allow_terminator=True)
        self.assertEqual(decoded.trailing, b"\n")

    def test_oversize_declared(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_ieee_block(b"#9" + f"{MAX_PAYLOAD_BYTES + 1:09d}".encode("ascii"))
        self.assertEqual(ctx.exception.status, "UNSUPPORTED")

    def test_empty_encode(self):
        with self.assertRaises(ProtocolError):
            encode_ieee_block(b"")

    def test_odd_payload_iter(self):
        with self.assertRaises(ProtocolError):
            list(iter_samples(b"\x00\x01\x02"))


class SampleConversionTests(unittest.TestCase):
    def test_manual_example_with_scale_half(self):
        self.assertEqual(sample_value(28, 0.5), 0.56)

    def test_codes(self):
        self.assertEqual(sample_value(0, 0.5), 0.0)
        self.assertEqual(sample_value(25, 0.5), 0.5)
        self.assertEqual(sample_value(-25, 0.5), -0.5)
        self.assertEqual(sample_value(50, 0.5), 1.0)

    def test_ad_factor_default(self):
        self.assertEqual(AD_FACTOR, 25)

    def test_bad_code_type(self):
        with self.assertRaises(ProtocolError):
            sample_value(1.0, 0.5)  # type: ignore[arg-type]

    def test_out_of_range_code(self):
        with self.assertRaises(ProtocolError):
            sample_value(32768, 0.5)

    def test_bad_ad_factor(self):
        with self.assertRaises(ProtocolError):
            sample_value(1, 0.5, ad_factor=0)

    def test_bad_scale(self):
        with self.assertRaises(ProtocolError):
            sample_value(1, -0.5)


class WaveformTests(unittest.TestCase):
    def test_valid(self):
        raw = _waveform_fixture()
        result = parse_waveform(raw)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["kind"], "waveform")
        self.assertEqual(result["points"], 4)
        self.assertEqual(result["point_count"], 4)
        self.assertEqual(result["bytes_per_point"], 2)
        self.assertEqual(result["block_length"], 8)
        self.assertEqual(result["header"]["Memory Length"], "4")
        self.assertEqual(result["header"]["Vertical Scale"], "5.000E-01")
        self.assertEqual(result["calibration"]["status"], "UNVERIFIED")
        self.assertEqual(result["calibration"]["vertical_scale"], 0.5)
        self.assertEqual(result["analysis_allowed"], "code-domain-only")
        self.assertEqual(result["payload_sha256"], hashlib.sha256(struct.pack(">4h", 0, 25, -25, 50)).hexdigest())

    def test_samples_are_opt_in(self):
        result = parse_waveform(_waveform_fixture())
        self.assertNotIn("samples", result)

    def test_codes_and_endianness(self):
        result = parse_waveform(_waveform_fixture(), include_samples=True)
        self.assertEqual(result["samples"], [0, 25, -25, 50])
        self.assertEqual(result["sample_voltages_documented"], [0.0, 0.5, -0.5, 1.0])

    def test_headerless_unverified(self):
        result = parse_waveform((FIXTURES / "waveform-headerless.bin").read_bytes())
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertFalse(result["header_present"])
        self.assertEqual(result["points"], 4)
        self.assertIsNone(result["calibration"]["vertical_scale"])
        self.assertIn("headerless_block_has_no_scale_or_units", result["integrity"]["reasons"])

    def test_truncated(self):
        result = parse_waveform((FIXTURES / "waveform-truncated.bin").read_bytes())
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_length_mismatch(self):
        result = parse_waveform((FIXTURES / "waveform-length-mismatch.bin").read_bytes())
        self.assertEqual(result["status"], "INVALID")

    def test_missing_marker(self):
        result = parse_waveform((FIXTURES / "waveform-bad-header.bin").read_bytes())
        self.assertEqual(result["status"], "INVALID")

    def test_empty(self):
        result = parse_waveform(b"")
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_odd_payload(self):
        raw = _with_header(_header(), b"#3003\x00\x01\x02")
        result = parse_waveform(raw)
        self.assertEqual(result["status"], "INVALID")

    def test_indefinite_block(self):
        raw = _with_header(_header(), b"#0abc")
        result = parse_waveform(raw)
        self.assertEqual(result["status"], "UNSUPPORTED")

    def test_oversize_declared(self):
        raw = _with_header(_header(), b"#9" + f"{MAX_PAYLOAD_BYTES + 1:09d}".encode("ascii"))
        result = parse_waveform(raw)
        self.assertEqual(result["status"], "UNSUPPORTED")

    def test_trailing_non_terminator(self):
        raw = _waveform_fixture() + b"X"
        result = parse_waveform(raw)
        self.assertEqual(result["status"], "INVALID")

    def test_trailing_lf(self):
        result = parse_waveform(_waveform_fixture() + b"\n")
        self.assertEqual(result["status"], "COMPLETE")

    def test_header_parse(self):
        info = parse_waveform_header(_waveform_fixture())
        self.assertTrue(info["header_present"])
        self.assertEqual(info["marker"], "Waveform Data;")
        self.assertEqual(info["block"].declared_length, 8)
        self.assertEqual(info["points"], 4)
        self.assertEqual(info["separator"], b"")

    def test_headerless_parse(self):
        info = parse_waveform_header((FIXTURES / "waveform-headerless.bin").read_bytes())
        self.assertFalse(info["header_present"])
        self.assertTrue(info["headerless"])
        self.assertEqual(info["block"].declared_length, 8)

    def test_missing_memory_length(self):
        header = _header().replace(b"Memory Length,4;", b"")
        raw = _with_header(header, b"#40008" + struct.pack(">4h", 0, 25, -25, 50))
        result = parse_waveform(raw)
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_missing_vertical_scale(self):
        header = _header().replace(b"Vertical Scale,5.000E-01;", b"")
        raw = _with_header(header, b"#40008" + struct.pack(">4h", 0, 25, -25, 50))
        result = parse_waveform(raw)
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertIsNone(result["calibration"]["vertical_scale"])
        self.assertIn("vertical_scale_missing", result["integrity"]["reasons"])

    def test_manual_scale_inconsistency_is_not_repaired(self):
        header = _header().replace(b"Vertical Scale,5.000E-01;", b"Vertical Scale,5.000E+00;")
        raw = _with_header(header, b"#40008" + struct.pack(">4h", 0, 25, -25, 50))
        result = parse_waveform(raw)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["calibration"]["vertical_scale"], 5.0)
        self.assertEqual(result["calibration"]["status"], "UNVERIFIED")
        self.assertAlmostEqual(sample_value(28, result["calibration"]["vertical_scale"]), 5.6)

    def test_duplicate_header_field(self):
        header = _header() + b"Memory Length,4;"
        raw = _with_header(header, b"#40008" + struct.pack(">4h", 0, 25, -25, 50))
        result = parse_waveform(raw)
        self.assertEqual(result["status"], "INVALID")

    def test_header_field_without_comma(self):
        header = b"Format,2.0E;BadField;Memory Length,4;"
        raw = _with_header(header, b"#40008" + struct.pack(">4h", 0, 25, -25, 50))
        result = parse_waveform(raw)
        self.assertEqual(result["status"], "INVALID")

    def test_failure_preserves_raw_sha(self):
        raw = (FIXTURES / "waveform-truncated.bin").read_bytes()
        result = parse_waveform(raw)
        self.assertEqual(result["integrity"]["raw_sha256"], hashlib.sha256(raw).hexdigest())

    def test_inline_sample_limit(self):
        points = 1_000_001
        payload = b"\x00" * (points * 2)
        huge = encode_ieee_block(payload)
        raw = _with_header(
            _header().replace(b"Memory Length,4", f"Memory Length,{points}".encode("ascii")),
            huge,
        )
        result = parse_waveform(raw, include_samples=True)
        self.assertEqual(result["status"], "UNSUPPORTED")

    def test_expected_fixture(self):
        expected = json.loads((ROOT / "assets" / "expected-waveform.json").read_text())
        result = parse_waveform(_waveform_fixture(), include_samples=True)
        self.assertEqual(result["status"], expected["status"])
        self.assertEqual(result["points"], expected["points"])
        self.assertEqual(result["block_length"], expected["block_length"])
        self.assertEqual(result["payload_sha256"], expected["payload_sha256"])
        self.assertEqual(result["samples"], expected["samples"])
        self.assertEqual(result["calibration"]["status"], expected["calibration"]["status"])


class CsvTests(unittest.TestCase):
    def test_valid_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wave.csv"
            result = waveform_to_csv(_waveform_fixture(), out)
            lines = out.read_text().splitlines()
            self.assertEqual(result["rows"], 4)
            self.assertEqual(lines[0], "index,code,voltage_documented,voltage_unit")
            self.assertEqual(lines[1], "0,0,0,V")
            self.assertEqual(lines[4], "3,50,1,V")
            self.assertEqual(result["calibration_status"], "UNVERIFIED")
            self.assertEqual(result["csv_sha256"], hashlib.sha256(out.read_bytes()).hexdigest())

    def test_headerless_csv_has_empty_voltage(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wave.csv"
            waveform_to_csv((FIXTURES / "waveform-headerless.bin").read_bytes(), out)
            lines = out.read_text().splitlines()
            self.assertEqual(lines[1], "0,0,, " .rstrip())

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wave.csv"
            out.write_text("operator data\n")
            with self.assertRaises(FileExistsError):
                waveform_to_csv(_waveform_fixture(), out)
            self.assertEqual(out.read_text(), "operator data\n")

    def test_overwrite_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wave.csv"
            out.write_text("operator data\n")
            result = waveform_to_csv(_waveform_fixture(), out, overwrite=True)
            self.assertEqual(result["rows"], 4)
            self.assertTrue(out.read_text().startswith("index,code"))


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

    def test_measure(self):
        code, result = self._run(
            ["measure", str(FIXTURES / "measure-frequency.txt"), "--quantity", "frequency"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(result["value"], 1032.0)

    def test_error_queue(self):
        code, result = self._run(["error-queue", str(FIXTURES / "error-undefined.txt"), "--response-type", "error-queue"])
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_waveform(self):
        code, result = self._run(["waveform", str(FIXTURES / "waveform-valid.bin")])
        self.assertEqual(code, 0)
        self.assertNotIn("samples", result)

    def test_waveform_samples(self):
        code, result = self._run(["waveform", str(FIXTURES / "waveform-valid.bin"), "--samples"])
        self.assertEqual(code, 0)
        self.assertEqual(result["samples"], [0, 25, -25, 50])

    def test_waveform_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wave.csv"
            code, result = self._run(
                ["waveform", str(FIXTURES / "waveform-valid.bin"), "--csv-out", str(out)]
            )
            self.assertEqual(code, 0)
            self.assertEqual(result["csv"]["rows"], 4)
            self.assertTrue(out.exists())

    def test_waveform_header(self):
        code, result = self._run(["waveform-header", str(FIXTURES / "waveform-valid.bin")])
        self.assertEqual(code, 0)
        self.assertEqual(result["block_header"], "#40008")

    def test_invalid_exit(self):
        code, _ = self._run(["measure", str(FIXTURES / "measure-chan-off.txt"), "--quantity", "pk2pk"])
        self.assertEqual(code, 1)

    def test_truncated_exit(self):
        code, _ = self._run(["waveform", str(FIXTURES / "waveform-truncated.bin")])
        self.assertEqual(code, 1)


class ManifestTests(unittest.TestCase):
    def test_manifest_hash(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        raw = (ROOT / manifest["data"]["raw_path"]).read_bytes()
        self.assertEqual(manifest["data"]["raw_sha256"], hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
