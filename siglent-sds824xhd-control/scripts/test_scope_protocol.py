#!/usr/bin/env python3
import hashlib
import struct
import unittest
from unittest.mock import Mock

from scope_protocol import (
    ScopeProtocolError,
    BufferedSocket,
    Segment,
    parse_ieee_block,
    parse_wavedesc,
    decode_analog_byte,
    signed_8bit,
    validate_frame,
    validate_segments,
)
from capture_scope import numeric_response


def block(payload: bytes, prefix: bytes = b"\x00DAT2,") -> bytes:
    length = str(len(payload)).encode("ascii")
    return prefix + b"#" + str(len(length)).encode("ascii") + length + payload


class ProtocolTests(unittest.TestCase):
    def test_ieee_block_preserves_prefix_nul_and_payload(self):
        payload = b"\x00#\xff\nDATA"
        parsed = parse_ieee_block(block(payload) + b"\r\n")
        self.assertEqual(parsed.prefix, b"\x00DAT2,")
        self.assertEqual(parsed.payload, payload)
        self.assertEqual(parsed.trailing, b"\r\n")
        self.assertEqual(parsed.sha256, hashlib.sha256(payload).hexdigest())

    def test_ieee_block_rejects_truncation_and_bad_header(self):
        with self.assertRaises(ScopeProtocolError):
            parse_ieee_block(b"banner#4100short")
        with self.assertRaises(ScopeProtocolError):
            parse_ieee_block(b"#A10payload")

    def test_wavedesc_fields(self):
        raw = bytearray(346)
        raw[:8] = b"WAVEDESC"
        struct.pack_into("<i", raw, 60, 25_000_000)
        struct.pack_into("<i", raw, 116, 25_000_000)
        struct.pack_into("<i", raw, 132, 0)
        struct.pack_into("<i", raw, 136, 1)
        struct.pack_into("<h", raw, 32, 0)
        struct.pack_into("<f", raw, 156, 2.0)
        struct.pack_into("<f", raw, 160, 0.0)
        struct.pack_into("<f", raw, 164, 30.0)
        struct.pack_into("<h", raw, 172, 8)
        struct.pack_into("<f", raw, 176, 2e-7)
        struct.pack_into("<d", raw, 180, -2.0)
        struct.pack_into("<h", raw, 324, 28)
        struct.pack_into("<f", raw, 328, 10.0)
        struct.pack_into("<h", raw, 344, 0)
        parsed = parse_wavedesc(bytes(raw))
        self.assertEqual(parsed["wave_array_count"], 25_000_000)
        self.assertEqual(parsed["wave_array_1_bytes"], 25_000_000)
        self.assertEqual(parsed["timebase_s"], 0.5)
        self.assertEqual(parsed["data_width_bytes"], 1)
        self.assertEqual(parsed["vdiv_with_probe"], 20.0)

    def test_segment_validation_detects_gap_and_short_payload(self):
        segments = [
            Segment(0, 5, 5, 1, 1.0, 0.0, "a"),
            Segment(6, 4, 3, 1, 1.0, 0.0, "b"),
        ]
        report = validate_segments(segments, expected_points=10, sample_interval_s=1.0, time_origin_s=-2.0)
        self.assertEqual(report["status"], "INVALID")
        self.assertTrue(report["reasons"])

    def test_25m_record_rejects_5m_download(self):
        report = validate_frame(
            scope_points=25_000_000,
            scope_duration_s=5.0,
            wavedesc_points=25_000_000,
            sample_interval_s=2e-7,
            downloaded_points=5_000_000,
        )
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["downloaded"]["duration_s"], 1.0)

    def test_duration_mismatch_is_reported(self):
        report = validate_frame(
            scope_points=25_000_000,
            scope_duration_s=4.0,
            wavedesc_points=25_000_000,
            sample_interval_s=2e-7,
            downloaded_points=25_000_000,
        )
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertTrue(any("duration" in reason for reason in report["reasons"]))

    def test_signed_8bit(self):
        self.assertEqual(signed_8bit(bytes([0, 127, 128, 255])), [0, 127, -128, -1])

    def test_buffered_reader_handles_banner_and_split_binary_block(self):
        fake_socket = Mock()
        chunks = iter([b"Welcome to the SCPI instrument 'Siglent SDS824X HD'\r\n>>\x00DA", b"T2,#", b"13", b"\x00#\xff"])
        fake_socket.recv.side_effect = lambda _size: next(chunks)
        reader = BufferedSocket(fake_socket, timeout_s=0.1)
        parsed = reader.read_ieee_block()
        self.assertEqual(parsed.prefix, b"Welcome to the SCPI instrument 'Siglent SDS824X HD'\r\n>>\x00DAT2,")
        self.assertEqual(parsed.payload, b"\x00#\xff")

    def test_stop_state_blocks_state_changes_but_allows_queries(self):
        from scope_protocol import ScopeSession

        scope = ScopeSession("example.invalid")
        scope.stopped = True
        with self.assertRaises(ScopeProtocolError):
            scope._check_allowed("WFSU SP,1,NP,0,FP,0")
        scope._check_allowed("WFSU?")
        with self.assertRaises(ScopeProtocolError):
            scope._check_allowed("WAV:STAR 0")
        with self.assertRaises(ScopeProtocolError):
            scope._check_allowed("ARM")
        scope.capture_mode = "configured_capture"
        scope._check_allowed("WAV:STAR 0")
        with self.assertRaises(ScopeProtocolError):
            scope._check_allowed("WFSU SP,1,NP,0,FP,0")

    def test_descriptor_query_is_gated_until_selected_dat2_reads_complete(self):
        from scope_protocol import ScopeSession

        scope = ScopeSession("example.invalid")
        scope.set_expected_channels(("C1", "C2"))
        with self.assertRaises(ScopeProtocolError):
            scope.query_block("C1:WF? DESC")

    def test_ascii_descriptor_fields(self):
        descriptor = parse_wavedesc(
            b"array_count=25000000\ndata_length=25000000\nhoriz_interval=2e-7\nhoriz_offset=-2\ntrigger_position=2\n"
        )
        self.assertEqual(descriptor["wave_array_count"], 25_000_000)
        self.assertEqual(descriptor["sample_interval"], 2e-7)
        self.assertEqual(descriptor["trigger_position"], 2.0)

    def test_analog_decoder_uses_codes_per_div_and_probe(self):
        descriptor = {
            "data_width_bytes": 1,
            "code_per_div": 30.0,
            "sample_interval": 2e-7,
            "horizontal_offset": -2.0,
            "timebase_s": 0.5,
            "vdiv_with_probe": 20.0,
            "offset_with_probe": 0.0,
        }
        points = decode_analog_byte(bytes([30, 255]), descriptor)
        self.assertEqual(points[0][2], 20.0)
        self.assertAlmostEqual(points[1][2], -20.0 / 30.0)

    def test_numeric_response_understands_scope_units(self):
        self.assertEqual(numeric_response("5.00 MSa/s"), 5_000_000.0)
        self.assertEqual(numeric_response("25.0 Mpts"), 25_000_000.0)
        self.assertEqual(numeric_response("-2 s"), -2.0)


if __name__ == "__main__":
    unittest.main()
