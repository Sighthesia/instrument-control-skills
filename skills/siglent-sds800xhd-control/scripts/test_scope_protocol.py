#!/usr/bin/env python3
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from scope_protocol import (
    ScopeProtocolError,
    BufferedSocket,
    Segment,
    decide_waveform_width,
    configure_left_aligned_trigger,
    configure_memory_depth,
    read_wav_segment,
    normalize_acquisition_state,
    parse_ieee_block,
    parse_wavedesc,
    decode_analog_byte,
    signed_8bit,
    validate_frame,
    validate_segments,
)
from capture_scope import numeric_response
from capture_scope import merge_segment_payloads


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
        self.assertEqual(parsed["byte_order"], "LSB")
        self.assertEqual(parsed["descriptor_length"], 0)

    def test_word_wavedesc_and_width_decision(self):
        raw = bytearray(346)
        raw[:8] = b"WAVEDESC"
        struct.pack_into("<i", raw, 36, 346)
        struct.pack_into("<h", raw, 32, 1)
        struct.pack_into("<h", raw, 34, 0)
        struct.pack_into("<i", raw, 60, 20)
        struct.pack_into("<i", raw, 116, 10)
        struct.pack_into("<i", raw, 136, 1)
        struct.pack_into("<h", raw, 172, 12)
        struct.pack_into("<h", raw, 324, 28)
        parsed = parse_wavedesc(bytes(raw))
        self.assertEqual(parsed["data_width_bytes"], 2)
        self.assertEqual(parsed["wave_array_1_bytes"], 20)
        self.assertEqual(parsed["byte_order"], "LSB")
        self.assertEqual(decide_waveform_width(parsed, "auto")["width_command"], "WORD")
        self.assertEqual(decide_waveform_width(parsed, "byte")["precision"], "lossy_8bit")
        self.assertEqual(decide_waveform_width(parsed, "auto")["voltage_decode"], "unverified_for_WORD")

        initial_byte_descriptor = dict(parsed, comm_type=0, data_width_bytes=1)
        self.assertEqual(decide_waveform_width(initial_byte_descriptor, "auto")["width_command"], "WORD")

        eight_bit_descriptor = dict(parsed, comm_type=0, data_width_bytes=1, nominal_bits=8)
        self.assertEqual(decide_waveform_width(eight_bit_descriptor, "auto")["width_command"], "BYTE")

    def test_decorated_acquisition_state_is_normalized(self):
        from scope_protocol import ScopeSession, scope_assume_existing_stop, scope_wait_ready, scope_wait_stop

        self.assertEqual(normalize_acquisition_state("  SAST Stop\r\n"), "STOP")
        self.assertEqual(normalize_acquisition_state(":TRIGger:STATus? Ready"), "READY")

        class FakeScope(ScopeSession):
            def __init__(self, responses):
                super().__init__("example.invalid")
                self.responses = iter(responses)
                self.stopped = False

            def query_ascii(self, command, **kwargs):
                self.assert_command = command
                return next(self.responses)

        existing = FakeScope(["SAST Stop"])
        observed = scope_assume_existing_stop(existing)
        self.assertEqual(observed.normalized, "STOP")
        self.assertEqual(observed.raw, "SAST Stop")
        self.assertTrue(existing.stopped)

        capture = FakeScope(["SAST Ready", "SAST Stop"])
        ready = scope_wait_ready(capture, timeout_s=1.0, poll_s=0.0)
        stop = scope_wait_stop(capture, timeout_s=1.0, poll_s=0.0)
        self.assertEqual(ready.normalized, "READY")
        self.assertEqual(stop.normalized, "STOP")
        self.assertEqual([entry.raw for entry in capture.state_log], ["SAST Ready", "SAST Stop"])

    def test_word_segment_payload_is_two_bytes_per_point(self):
        from scope_protocol import IEEEBlock, ScopeSession

        class FakeScope(ScopeSession):
            def __init__(self, payload):
                super().__init__("example.invalid")
                self.stopped = True
                self.capture_mode = "configured_capture"
                self.payload = payload

            def write(self, command, **kwargs):
                return None

            def query_ascii(self, command, **kwargs):
                return {"WAV:STAR?": "10", "WAV:POIN?": "3"}[command]

            def query_block(self, command, **kwargs):
                return IEEEBlock(b"", b"#", self.payload)

        preamble = {"data_width_bytes": 2}
        block_result = read_wav_segment(FakeScope(b"\x00\x01" * 3), 10, 3, preamble)
        self.assertEqual(len(block_result.payload), 6)
        with self.assertRaises(ScopeProtocolError):
            read_wav_segment(FakeScope(b"\x01" * 3), 10, 3, preamble)

        class EchoingTruncation(FakeScope):
            def query_block(self, command, **kwargs):
                return IEEEBlock(b"", b"#", b"\x00\x01" * 2)

        with self.assertRaisesRegex(ScopeProtocolError, "not evidence"):
            read_wav_segment(EchoingTruncation(b""), 10, 3, preamble)
        with self.assertRaises(ScopeProtocolError):
            read_wav_segment(FakeScope(b"\x00" * 5), 10, 3, preamble)

    def test_invalid_word_descriptor_fields_fail(self):
        raw = bytearray(346)
        raw[:8] = b"WAVEDESC"
        struct.pack_into("<h", raw, 32, 1)
        struct.pack_into("<h", raw, 34, 2)
        struct.pack_into("<i", raw, 60, 20)
        struct.pack_into("<i", raw, 116, 10)
        struct.pack_into("<h", raw, 172, 12)
        struct.pack_into("<h", raw, 324, 28)
        with self.assertRaises(ScopeProtocolError):
            parse_wavedesc(bytes(raw))

    def test_segment_validation_detects_gap_and_short_payload(self):
        segments = [
            Segment(0, 5, 5, 1, 1.0, 0.0, "a"),
            Segment(6, 4, 3, 1, 1.0, 0.0, "b"),
        ]
        report = validate_segments(segments, expected_points=10, sample_interval_s=1.0, time_origin_s=-2.0)
        self.assertEqual(report["status"], "INVALID")
        self.assertTrue(report["reasons"])

    def test_word_segment_report_counts_payload_bytes(self):
        report = validate_segments(
            [Segment(0, 3, 6, 2, 1e-6, 0.0, "word")],
            expected_points=3,
            expected_payload_bytes=6,
            sample_interval_s=1e-6,
            time_origin_s=0.0,
        )
        self.assertEqual(report["status"], "COMPLETE")
        self.assertEqual(report["downloaded_payload_bytes"], 6)
        mismatch = validate_segments(
            [Segment(0, 3, 3, 2, 1e-6, 0.0, "short")],
            expected_points=3,
            expected_payload_bytes=6,
            sample_interval_s=1e-6,
            time_origin_s=0.0,
        )
        self.assertEqual(mismatch["status"], "INVALID")

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
        scope._check_allowed("WAV:BYT LSB")

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
        panel_points = decode_analog_byte(bytes([30]), descriptor, panel_vdiv=5.0, panel_offset=0.0)
        self.assertEqual(panel_points[0][2], 5.0)

    def test_numeric_response_understands_scope_units(self):
        self.assertEqual(numeric_response("5.00 MSa/s"), 5_000_000.0)
        self.assertEqual(numeric_response("25.0 Mpts"), 25_000_000.0)
        self.assertEqual(numeric_response("-2 s"), -2.0)

    def test_left_aligned_trigger_sets_delay_and_memory_before_single(self):
        from scope_protocol import ScopeSession

        class FakeScope(ScopeSession):
            def __init__(self):
                super().__init__("example.invalid")
                self.commands = []
                self.responses = {
                    "TIM:SCAL?": "1.00E-04",
                    "TIM:DEL?": "4.00E-04",
                    "ACQ:MDEP?": "25M",
                    "ACQ:MODE?": "YT",
                    "TIM:REF:POS?": "10",
                }

            def write(self, command, **kwargs):
                self.commands.append(command)

            def query_ascii(self, command, **kwargs):
                return self.responses[command]

        scope = FakeScope()
        configuration = configure_left_aligned_trigger(
            scope,
            margin_div=1.0,
            reference_position=10,
            channel_count=3,
        )
        self.assertAlmostEqual(configuration["delay_s"], 4e-4)
        self.assertAlmostEqual(configuration["pre_trigger_s"], 1e-4)
        self.assertAlmostEqual(configuration["post_trigger_s"], 9e-4)
        self.assertEqual(configuration["memory_depth_readback"], "25M")
        self.assertEqual(configuration["reference_position_readback"], 10)
        self.assertEqual(scope.commands[0], "TIM:DEL 4.000000000E-04")
        self.assertEqual(scope.commands[1], "ACQ:MDEP 25M")
        self.assertEqual(scope.commands[2], "TIM:REF:POS 10")
        self.assertNotIn("ARM", [command.upper() for command in scope.commands])

    def test_left_aligned_trigger_rejects_invalid_margin_before_io(self):
        from scope_protocol import ScopeSession

        class FakeScope(ScopeSession):
            def __init__(self):
                super().__init__("example.invalid")
                self.commands = []

            def query_ascii(self, command, **kwargs):
                self.commands.append(command)
                return "1"

        scope = FakeScope()
        with self.assertRaises(ScopeProtocolError):
            configure_left_aligned_trigger(scope, margin_div=0)
        self.assertEqual(scope.commands, [])

    def test_memory_depth_readback_mismatch_fails_closed(self):
        from scope_protocol import ScopeSession

        class FakeScope(ScopeSession):
            def __init__(self):
                super().__init__("example.invalid")
                self.commands = []

            def write(self, command, **kwargs):
                self.commands.append(command)

            def query_ascii(self, command, **kwargs):
                return "50M"

        with self.assertRaises(ScopeProtocolError):
            configure_memory_depth(FakeScope(), memory_depth="100M", channel_count=1)

    def test_left_aligned_trigger_rejects_roll_mode_before_writing(self):
        from scope_protocol import ScopeSession

        class FakeScope(ScopeSession):
            def __init__(self):
                super().__init__("example.invalid")
                self.commands = []

            def write(self, command, **kwargs):
                self.commands.append(command)

            def query_ascii(self, command, **kwargs):
                if command == "TIM:SCAL?":
                    return "1.00E-01"
                if command == "ACQ:MODE?":
                    return "ROLL"
                raise AssertionError(f"unexpected query after Roll detection: {command}")

        scope = FakeScope()
        with self.assertRaises(ScopeProtocolError) as caught:
            configure_left_aligned_trigger(scope, margin_div=1.0)
        self.assertIn("ROLL", str(caught.exception))
        self.assertEqual(scope.commands, [])

    def test_wait_ready_fails_fast_in_roll_mode(self):
        from scope_protocol import ScopeSession, scope_wait_ready

        class FakeScope(ScopeSession):
            def __init__(self):
                super().__init__("example.invalid")

            def query_ascii(self, command, **kwargs):
                return "Roll"

        scope = FakeScope()
        with self.assertRaises(ScopeProtocolError) as caught:
            scope_wait_ready(scope, timeout_s=5.0, poll_s=0.0)
        self.assertIn("Roll mode", str(caught.exception))
        self.assertTrue(scope.roll_seen)
        self.assertFalse(scope.ready_seen)

    def test_roll_state_is_recorded_without_claiming_ready(self):
        from scope_protocol import ScopeSession

        scope = ScopeSession("example.invalid")
        scope.mark_state("Roll")
        self.assertTrue(scope.roll_seen)
        self.assertFalse(scope.ready_seen)
        with self.assertRaises(ScopeProtocolError):
            scope.mark_state("Stop")

    def test_capture_cli_rejects_left_aligned_options_without_trigger(self):
        from capture_scope import parse_args
        import sys
        from unittest.mock import patch

        with patch.object(sys, "argv", ["capture_scope.py", "--out", "/tmp/capture", "--existing-stopped", "--left-aligned-trigger"]):
            args = parse_args()
        self.assertTrue(args.left_aligned_trigger)

    def test_merge_segment_payloads_preserves_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            channel = "C4"
            channel_dir = root / channel
            channel_dir.mkdir()
            first = channel_dir / "segment-000000.bin"
            second = channel_dir / "segment-000001.bin"
            first.write_bytes(b"abc")
            second.write_bytes(b"def")
            first_hash = hashlib.sha256(b"abc").hexdigest()
            second_hash = hashlib.sha256(b"def").hexdigest()
            output = merge_segment_payloads(
                root,
                channel,
                [
                    {"payload": str(first), "actual_payload_bytes": 3, "sha256": first_hash},
                    {"payload": str(second), "actual_payload_bytes": 3, "sha256": second_hash},
                ],
                "waveform.bin",
            )
            self.assertEqual(output.read_bytes(), b"abcdef")
            self.assertFalse((channel_dir / "waveform.bin.partial").exists())
            second.write_bytes(b"bad")
            with self.assertRaises(ScopeProtocolError):
                merge_segment_payloads(
                    root,
                    channel,
                    [
                        {"payload": str(first), "actual_payload_bytes": 3, "sha256": first_hash},
                        {"payload": str(second), "actual_payload_bytes": 3, "sha256": second_hash},
                    ],
                    "waveform-bad.bin",
                )
            self.assertFalse((channel_dir / "waveform-bad.bin").exists())
            self.assertFalse((channel_dir / "waveform-bad.bin.partial").exists())


if __name__ == "__main__":
    unittest.main()
