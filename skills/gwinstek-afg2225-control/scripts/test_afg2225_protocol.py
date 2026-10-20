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

from afg2225_protocol import (  # noqa: E402
    MAX_ARB_POINTS,
    ProtocolError,
    build_arb_artifact,
    build_data_dac_ascii,
    build_data_dac_binary,
    decode_ieee_block,
    encode_ieee_block,
    load_arb_csv,
    main,
    parse_error_queue,
    parse_identity,
    parse_numeric,
    read_frame,
    scale_normalized,
    validate_arb_samples,
)


class FrameTests(unittest.TestCase):
    def test_lf(self):
        f = read_frame(b"abc\n")
        self.assertEqual(f.content, b"abc")
        self.assertEqual(f.terminator, b"\n")
        self.assertEqual(f.trailing, b"")

    def test_cr(self):
        f = read_frame(b"abc\r")
        self.assertEqual(f.terminator, b"\r")

    def test_crlf(self):
        f = read_frame(b"abc\r\n")
        self.assertEqual(f.terminator, b"\r\n")

    def test_lfcr(self):
        f = read_frame(b"abc\n\r")
        self.assertEqual(f.terminator, b"\n\r")

    def test_empty(self):
        with self.assertRaises(ProtocolError):
            read_frame(b"")

    def test_missing_terminator(self):
        with self.assertRaises(ProtocolError):
            read_frame(b"abc")

    def test_trailing_bytes(self):
        with self.assertRaises(ProtocolError):
            read_frame(b"abc\ndef")


class IdentityTests(unittest.TestCase):
    def test_valid(self):
        raw = (FIXTURES / "identity.txt").read_bytes()
        r = parse_identity(raw)
        self.assertEqual(r["status"], "COMPLETE")
        self.assertEqual(r["vendor"], "GW INSTEK")
        self.assertEqual(r["model"], "AFG-2225")
        self.assertEqual(r["serial"], "AFG2225000001")
        self.assertEqual(r["firmware"], "V1.23")
        self.assertEqual(r["integrity"]["status"], "COMPLETE")
        self.assertEqual(base64.b64decode(r["integrity"]["raw_response_base64"]), raw)

    def test_wrong_model(self):
        raw = (FIXTURES / "identity-wrong-model.txt").read_bytes()
        r = parse_identity(raw)
        self.assertEqual(r["status"], "INVALID")

    def test_missing_firmware(self):
        raw = (FIXTURES / "identity-missing-firmware.txt").read_bytes()
        r = parse_identity(raw)
        self.assertEqual(r["status"], "INCOMPLETE")

    def test_malformed(self):
        r = parse_identity(b"GW INSTEK,AFG-2225,SN:ABC\n")
        self.assertEqual(r["status"], "INCOMPLETE")
        r2 = parse_identity(b"garbage\n")
        self.assertEqual(r2["status"], "INVALID")

    def test_missing_terminator(self):
        r = parse_identity(b"GW INSTEK,AFG-2225,SN:AFG1,V1.23")
        self.assertEqual(r["status"], "INCOMPLETE")

    def test_trailing_bytes(self):
        r = parse_identity(b"GW INSTEK,AFG-2225,SN:AFG1,V1.23\nEXTRA\n")
        self.assertEqual(r["status"], "INVALID")

    def test_expected_fixture(self):
        expected = json.loads((ROOT / "assets" / "expected-identity.json").read_text())
        raw = (FIXTURES / "identity.txt").read_bytes()
        r = parse_identity(raw)
        self.assertEqual(r["status"], expected["status"])
        self.assertEqual(r["identity"], expected["identity"])


class NumericTests(unittest.TestCase):
    def test_unitless_frequency(self):
        raw = (FIXTURES / "frequency.txt").read_bytes()
        r = parse_numeric(raw, quantity="frequency", unit="Hz")
        self.assertEqual(r["status"], "COMPLETE")
        self.assertEqual(r["value"], 1000000.0)
        self.assertEqual(r["unit"], "Hz")

    def test_nan(self):
        raw = (FIXTURES / "frequency-bad.txt").read_bytes()
        r = parse_numeric(raw, quantity="frequency")
        self.assertEqual(r["status"], "INVALID")

    def test_suffixed(self):
        r = parse_numeric(b"+1.0E+03 Hz\n", quantity="frequency")
        self.assertEqual(r["status"], "COMPLETE")
        self.assertEqual(r["value"], 1000.0)
        self.assertEqual(r["unit"], "Hz")

    def test_bad_unit(self):
        r = parse_numeric(b"1.0 foo\n", quantity="frequency")
        self.assertEqual(r["status"], "INVALID")

    def test_inf(self):
        r = parse_numeric(b"Inf\n", quantity="frequency")
        self.assertEqual(r["status"], "INVALID")

    def test_extra_bytes(self):
        r = parse_numeric(b"1.0\nextra\n", quantity="frequency")
        self.assertEqual(r["status"], "INVALID")

    def test_missing_terminator(self):
        r = parse_numeric(b"1.0", quantity="frequency")
        self.assertEqual(r["status"], "INCOMPLETE")

    def test_suffix_normalized_to_base_unit(self):
        r = parse_numeric(b"1kHz\n", quantity="frequency")
        self.assertEqual(r["status"], "COMPLETE")
        self.assertEqual(r["value"], 1000.0)
        self.assertEqual(r["unit"], "Hz")
        self.assertEqual(r["raw_value"], 1.0)
        self.assertEqual(r["raw_unit"], "kHz")

    def test_time_suffix_normalized(self):
        r = parse_numeric(b"1ms\n", quantity="time")
        self.assertEqual(r["status"], "COMPLETE")
        self.assertAlmostEqual(r["value"], 0.001)

    def test_unit_conflict(self):
        r = parse_numeric(b"1V\n", quantity="frequency")
        self.assertEqual(r["status"], "INVALID")

    def test_amplitude_unit_family(self):
        for raw, expected_unit in ((b"1Vpp\n", "Vpp"), (b"1Vrms\n", "Vrms"), (b"1dBm\n", "dBm")):
            r = parse_numeric(raw, quantity="amplitude")
            self.assertEqual(r["status"], "COMPLETE")
            self.assertEqual(r["unit"], expected_unit)
        r = parse_numeric(b"1V\n", quantity="amplitude")
        self.assertEqual(r["status"], "INVALID")

    def test_unitless_count(self):
        r = parse_numeric(b"5\n", quantity="count")
        self.assertEqual(r["status"], "COMPLETE")
        self.assertIsNone(r["unit"])


class ErrorQueueTests(unittest.TestCase):
    def test_none(self):
        raw = (FIXTURES / "error-none.txt").read_bytes()
        r = parse_error_queue(raw)
        self.assertEqual(r["status"], "COMPLETE")
        self.assertEqual(r["code"], 0)

    def test_suffix_auto_unsupported(self):
        raw = (FIXTURES / "error-suffix.txt").read_bytes()
        r = parse_error_queue(raw)
        self.assertEqual(r["status"], "UNSUPPORTED")

    def test_suffix_explicit(self):
        raw = (FIXTURES / "error-suffix.txt").read_bytes()
        r = parse_error_queue(raw, response_type="error-queue")
        self.assertEqual(r["status"], "UNVERIFIED")
        self.assertEqual(r["code"], -138)

    def test_overflow(self):
        raw = (FIXTURES / "error-overflow.txt").read_bytes()
        r = parse_error_queue(raw, response_type="error-queue")
        self.assertEqual(r["status"], "INCOMPLETE")

    def test_bare_no_error(self):
        r = parse_error_queue(b"No error\n")
        self.assertEqual(r["status"], "COMPLETE")
        self.assertEqual(r["code"], 0)

    def test_negative_overflow(self):
        r = parse_error_queue(b"-350,Queue Overflow\n", response_type="error-queue")
        self.assertEqual(r["status"], "INCOMPLETE")

    def test_auto_overflow(self):
        r = parse_error_queue(b"-350 Queue overflow\n")
        self.assertEqual(r["status"], "INCOMPLETE")

    def test_auto_suffix_explicit_classify(self):
        # comma variant
        r = parse_error_queue(b"-138,Suffix not allowed\n", response_type="error-queue")
        self.assertEqual(r["code"], -138)

    def test_missing_terminator(self):
        r = parse_error_queue(b"0 No error")
        self.assertEqual(r["status"], "INCOMPLETE")


class CsvTests(unittest.TestCase):
    def test_valid(self):
        vals = load_arb_csv(FIXTURES / "arb-valid.csv")
        self.assertEqual(vals, [-511, 0, 511, 256, -256, 128, -128, 0])

    def test_out_of_range(self):
        vals = load_arb_csv(FIXTURES / "arb-out-of-range.csv")
        v = validate_arb_samples(vals)
        self.assertEqual(v["status"], "INVALID")

    def test_too_many(self):
        vals = load_arb_csv(FIXTURES / "arb-too-many.csv")
        v = validate_arb_samples(vals)
        self.assertEqual(v["status"], "INVALID")

    def test_non_integer(self):
        with self.assertRaises(ProtocolError):
            load_arb_csv(FIXTURES / "arb-non-integer.csv")

    def test_comments(self):
        text = "# c\n1, 2\n3 # trailing\n"
        self.assertEqual(load_arb_csv(text), [1, 2, 3])

    def test_float_rejected(self):
        with self.assertRaises(ProtocolError):
            load_arb_csv("1.0\n")


class ScalingTests(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(scale_normalized([0.0, 1.0, -1.0], 511), [0, 511, -511])

    def test_rounding(self):
        self.assertEqual(scale_normalized([0.5], 511), [256])

    def test_no_clamp(self):
        with self.assertRaises(ProtocolError):
            scale_normalized([1.0000001])

    def test_out_of_range(self):
        with self.assertRaises(ProtocolError):
            scale_normalized([1.1])

    def test_full_scale_cannot_exceed_dac_range(self):
        with self.assertRaises(ProtocolError):
            scale_normalized([1.0], full_scale=1024)


class IeeeTests(unittest.TestCase):
    def test_roundtrip(self):
        payload = b"\x01\x02\x03\x04"
        block = encode_ieee_block(payload)
        dec = decode_ieee_block(block)
        self.assertEqual(dec.payload, payload)
        self.assertEqual(dec.trailing, b"")

    def test_length_digits(self):
        payload = b"\x00" * 16
        block = encode_ieee_block(payload)
        self.assertTrue(block.startswith(b"#216"))

    def test_indefinite(self):
        with self.assertRaises(ProtocolError):
            decode_ieee_block(b"#0abc")

    def test_truncation(self):
        with self.assertRaises(ProtocolError):
            decode_ieee_block(b"#216" + b"\x00" * 10)

    def test_trailing_preserved(self):
        payload = b"\xaa\xbb"
        block = encode_ieee_block(payload)
        raw = block + b"TRAIL"
        dec = decode_ieee_block(raw)
        self.assertEqual(dec.payload, payload)
        self.assertEqual(dec.trailing, b"TRAIL")

    def test_empty_encode(self):
        with self.assertRaises(ProtocolError):
            encode_ieee_block(b"")


class AsciiCommandTests(unittest.TestCase):
    def test_exact_bytes(self):
        cmd = build_data_dac_ascii(0, [-511, 0, 511])
        self.assertEqual(cmd, b"DATA:DAC VOLATILE,0,-511,0,511")

    def test_negative_start_rejected(self):
        with self.assertRaises(ProtocolError):
            build_data_dac_ascii(-1, [1])

    def test_start_plus_points_rejected(self):
        with self.assertRaises(ProtocolError):
            build_data_dac_ascii(4095, [1, 2])

    def test_start_at_limit_allowed(self):
        self.assertEqual(
            build_data_dac_ascii(4095, [1]),
            b"DATA:DAC VOLATILE,4095,1",
        )

    def test_binary_roundtrip_both_orders(self):
        vals = [-511, 0, 511]
        for order in ("little", "big"):
            cmd = build_data_dac_binary(0, vals, byte_order=order)
            self.assertTrue(cmd.startswith(b"DATA:DAC VOLATILE,0,#"))
            # decode block
            block_bytes = cmd.split(b",", 2)[2]
            dec = decode_ieee_block(block_bytes)
            self.assertEqual(len(dec.payload), 6)
            import struct

            endian = "<" if order == "little" else ">"
            unpacked = list(struct.unpack(endian + "hhh", dec.payload))
            self.assertEqual(unpacked, vals)

    def test_binary_requires_byte_order(self):
        with self.assertRaises(TypeError):
            build_data_dac_binary(0, [1, 2])  # missing required keyword


class ArbValidationTests(unittest.TestCase):
    def test_empty(self):
        v = validate_arb_samples([])
        self.assertEqual(v["status"], "INVALID")

    def test_too_many(self):
        v = validate_arb_samples([1] * (MAX_ARB_POINTS + 1))
        self.assertEqual(v["status"], "INVALID")

    def test_non_int(self):
        v = validate_arb_samples([1.0])
        self.assertEqual(v["status"], "INVALID")

    def test_out_of_range(self):
        v = validate_arb_samples([512])
        self.assertEqual(v["status"], "INVALID")

    def test_valid(self):
        v = validate_arb_samples([-511, 0, 511])
        self.assertEqual(v["status"], "COMPLETE")
        self.assertEqual(v["min"], -511)
        self.assertEqual(v["max"], 511)


class ArbArtifactTests(unittest.TestCase):
    def test_ascii(self):
        vals = load_arb_csv(FIXTURES / "arb-valid.csv")
        art = build_arb_artifact(vals, start=0, data_format="ascii", source="x")
        self.assertEqual(art["points"], 8)
        self.assertEqual(art["format"], "ascii")
        self.assertEqual(art["integrity"]["status"], "COMPLETE")
        self.assertEqual(base64.b64decode(art["command_bytes_base64"]), build_data_dac_ascii(0, vals))

    def test_binary_unverified(self):
        vals = [1, 2, 3]
        art = build_arb_artifact(vals, data_format="binary", byte_order="little")
        self.assertEqual(art["integrity"]["status"], "UNVERIFIED")
        self.assertEqual(art["byte_order"], "little")

    def test_binary_requires_byte_order(self):
        with self.assertRaises(ProtocolError):
            build_arb_artifact([1, 2], data_format="binary")

    def test_expected_fixture(self):
        expected = json.loads((ROOT / "assets" / "expected-arb-ascii.json").read_text())
        vals = load_arb_csv(FIXTURES / "arb-valid.csv")
        art = build_arb_artifact(vals, start=0, data_format="ascii", source="assets/fixtures/arb-valid.csv")
        self.assertEqual(art["points"], expected["points"])
        self.assertEqual(art["command_bytes_base64"], expected["command_bytes_base64"])


class CliTests(unittest.TestCase):
    def test_identity_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "idn.txt"
            p.write_bytes((FIXTURES / "identity.txt").read_bytes())
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(["identity", str(p)])
            self.assertEqual(code, 0)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["status"], "COMPLETE")

    def test_numeric_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "freq.txt"
            p.write_bytes((FIXTURES / "frequency.txt").read_bytes())
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(["numeric", str(p), "--quantity", "frequency", "--unit", "Hz"])
            self.assertEqual(code, 0)

    def test_error_queue_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "err.txt"
            p.write_bytes((FIXTURES / "error-suffix.txt").read_bytes())
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(["error-queue", str(p), "--response-type", "error-queue"])
            self.assertEqual(code, 0)

    def test_arb_cli(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["arb", "--csv", str(FIXTURES / "arb-valid.csv"), "--format", "ascii"])
        self.assertEqual(code, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["points"], 8)

    def test_invalid_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.txt"
            p.write_bytes(b"NaN\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(["numeric", str(p), "--quantity", "frequency"])
            self.assertEqual(code, 1)


class ManifestHashTests(unittest.TestCase):
    def test_manifest_hash(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        raw = (ROOT / manifest["data"]["raw_path"]).read_bytes()
        self.assertEqual(manifest["data"]["raw_sha256"], hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
