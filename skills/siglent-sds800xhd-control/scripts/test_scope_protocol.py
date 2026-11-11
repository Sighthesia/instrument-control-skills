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
    configure_acquisition_context,
    decide_waveform_width,
    configure_left_aligned_trigger,
    configure_memory_depth,
    drain_error_queue,
    largest_standard_timebase_step,
    max_timebase_for_context,
    read_wav_segment,
    normalize_acquisition_state,
    parse_ieee_block,
    parse_wavedesc,
    representable_code_limit,
    decode_analog_byte,
    read_trigger_configuration,
    scope_prepare_capture,
    scope_snapshot_configuration,
    signed_8bit,
    validate_frame,
    validate_segments,
    write_and_verify,
)
from capture_scope import numeric_response
from capture_scope import merge_segment_payloads


def block(payload: bytes, prefix: bytes = b"\x00DAT2,") -> bytes:
    length = str(len(payload)).encode("ascii")
    return prefix + b"#" + str(len(length)).encode("ascii") + length + payload


def wavedesc_bytes(comm_type: int, vertical_code_field: float, *, points: int = 10, adc_bit: int = 16) -> bytes:
    """Build a minimal 346-byte WAVEDESC with the given transfer layout."""

    raw = bytearray(346)
    raw[:8] = b"WAVEDESC"
    struct.pack_into("<h", raw, 32, comm_type)
    struct.pack_into("<h", raw, 34, 0)
    struct.pack_into("<i", raw, 36, 346)
    struct.pack_into("<i", raw, 60, points * (1 if comm_type == 0 else 2))
    struct.pack_into("<i", raw, 116, points)
    struct.pack_into("<f", raw, 156, 2.0)
    struct.pack_into("<f", raw, 164, vertical_code_field)
    struct.pack_into("<h", raw, 172, adc_bit)
    struct.pack_into("<h", raw, 324, 28)
    return bytes(raw)


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

    def test_word_wavedesc_publishes_word_code_domain(self):
        parsed = parse_wavedesc(wavedesc_bytes(comm_type=1, vertical_code_field=7680.0, adc_bit=16))
        self.assertEqual(parsed["data_width_bytes"], 2)
        self.assertEqual(parsed["nominal_bits"], 16)
        self.assertEqual(parsed["transfer_width"], "word")
        self.assertEqual(parsed["code_domain"], "word")
        self.assertEqual(parsed["code_per_div"], 7680.0)
        self.assertEqual(parsed["codes_per_div_byte"], 30.0)
        self.assertEqual(parsed["codes_per_div_word"], 7680.0)
        self.assertEqual(parsed["max_value"], 7680.0)

    def test_legacy_byte_wavedesc_keeps_byte_code_domain(self):
        parsed = parse_wavedesc(wavedesc_bytes(comm_type=0, vertical_code_field=30.0, adc_bit=8))
        self.assertEqual(parsed["data_width_bytes"], 1)
        self.assertEqual(parsed["transfer_width"], "byte")
        self.assertEqual(parsed["code_domain"], "byte")
        self.assertEqual(parsed["code_per_div"], 30.0)
        self.assertEqual(parsed["codes_per_div_byte"], 30.0)
        self.assertEqual(parsed["codes_per_div_word"], 7680.0)
        self.assertEqual(parsed["max_value"], 7680.0)

    def test_representable_code_limit_tracks_transfer_width(self):
        self.assertEqual(representable_code_limit(2), 32767)
        self.assertEqual(representable_code_limit(1), 127)
        with self.assertRaises(ScopeProtocolError):
            representable_code_limit(4)

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

    def test_screen_record_is_separate_from_descriptor_integrity(self):
        # ACQ:POINts? counts the on-screen waveform (manual printed p. 21); the
        # WAVEDESC wave_array_count is the waveform record (printed p. 388). A
        # complete 20 M-point descriptor/download is not disproven by a 5 M
        # screen readback, and the screen range stays unverified.
        report = validate_frame(
            scope_points=5_000_000,
            scope_duration_s=1.0,
            wavedesc_points=20_000_000,
            sample_interval_s=2e-7,
            downloaded_points=20_000_000,
            downloaded_payload_bytes=20_000_000,
            expected_payload_bytes=20_000_000,
            scope_points_semantics="screen",
        )
        self.assertEqual(report["status"], "COMPLETE")
        self.assertEqual(report["reasons"], [])
        self.assertEqual(report["screen_record"]["points"], 5_000_000)
        self.assertEqual(report["screen_record"]["semantics"], "screen_display_record")
        self.assertEqual(report["scope_record"]["semantics"], "screen")
        self.assertEqual(report["range_correspondence"]["status"], "UNVERIFIED")
        self.assertFalse(report["range_correspondence"]["point_counts_equal"])
        self.assertTrue(any("differs" in reason for reason in report["range_correspondence"]["reasons"]))
        self.assertIn("not whole screen or memory extent", report["status_meaning"])

    def test_screen_record_never_justifies_a_short_descriptor(self):
        # Descriptor says 20 M, only 5 M arrived: the screen readback must not
        # become the expected count and turn the transfer complete.
        report = validate_frame(
            scope_points=20_000_000,
            scope_duration_s=5.0,
            wavedesc_points=20_000_000,
            sample_interval_s=2e-7,
            downloaded_points=5_000_000,
            downloaded_payload_bytes=5_000_000,
            expected_payload_bytes=20_000_000,
            scope_points_semantics="screen",
        )
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertTrue(any("downloaded 5000000 points" in reason for reason in report["reasons"]))

    def test_screen_record_cannot_replace_a_missing_descriptor(self):
        report = validate_frame(
            scope_points=5_000_000,
            scope_duration_s=1.0,
            wavedesc_points=None,
            sample_interval_s=2e-7,
            downloaded_points=5_000_000,
            scope_points_semantics="screen",
        )
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertTrue(any("cannot stand in for descriptor integrity" in reason for reason in report["reasons"]))
        self.assertEqual(report["range_correspondence"]["status"], "UNVERIFIED")

    def test_equal_screen_and_descriptor_counts_still_leave_time_unverified(self):
        report = validate_frame(
            scope_points=5_000_000,
            scope_duration_s=1.0,
            wavedesc_points=5_000_000,
            sample_interval_s=2e-7,
            downloaded_points=5_000_000,
            scope_points_semantics="screen",
        )
        self.assertEqual(report["status"], "COMPLETE")
        self.assertIs(report["range_correspondence"]["point_counts_equal"], True)
        self.assertEqual(report["range_correspondence"]["status"], "UNVERIFIED")
        self.assertTrue(any("do not prove" in reason for reason in report["range_correspondence"]["reasons"]))

    def test_same_record_semantics_keeps_rejecting_a_screen_mismatch(self):
        report = validate_frame(
            scope_points=5_000_000,
            scope_duration_s=1.0,
            wavedesc_points=25_000_000,
            sample_interval_s=2e-7,
            downloaded_points=25_000_000,
            scope_points_semantics="same_record",
        )
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertTrue(any("screen record 5000000 differs from WAVEDESC 25000000" in reason for reason in report["reasons"]))
        self.assertNotIn("range_correspondence", report)

    def test_screen_frame_rejects_invalid_numbers_including_segment_fallback(self):
        arguments = dict(
            scope_points=5, scope_duration_s=0.05, wavedesc_points=20,
            sample_interval_s=0.01, downloaded_points=20,
            scope_points_semantics="screen", bytes_per_point=2,
            expected_payload_bytes=40, downloaded_payload_bytes=40,
        )
        for changes in (
            {"wavedesc_points": 0}, {"wavedesc_points": 2.5},
            {"sample_interval_s": float("nan")}, {"sample_interval_s": 0},
            {"downloaded_points": -1}, {"bytes_per_point": 3},
            {"expected_payload_bytes": None, "downloaded_payload_bytes": None,
             "segment_report": {"status": "COMPLETE", "expected_payload_bytes": -2,
                                "downloaded_payload_bytes": -2}},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_frame(**(arguments | changes))
        missing_interval = validate_frame(**(arguments | {"sample_interval_s": None}))
        self.assertEqual(missing_interval["status"], "INCOMPLETE")
        mismatched_bytes = validate_frame(**(arguments | {"downloaded_payload_bytes": 38}))
        self.assertEqual(mismatched_bytes["status"], "INCOMPLETE")
        mismatched_duration = validate_frame(**(arguments | {"downloaded_duration_s": 0.01}))
        self.assertEqual(mismatched_duration["status"], "INCOMPLETE")

    def test_unknown_scope_points_semantics_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_frame(
                scope_points=1,
                scope_duration_s=1.0,
                wavedesc_points=1,
                sample_interval_s=1.0,
                downloaded_points=1,
                scope_points_semantics="memory_depth",
            )

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

    def test_prepare_writes_only_commands_that_can_be_read_back(self):
        # The handover block wrote TRSE EDGE,SR,C1,HT,OFF + C1:TRSL + C1:TRLV.
        # HT is defined nowhere in the programming guide and no per-channel
        # trigger slope/level command exists, so that block asserts a slope it
        # never proves. The documented long form is readback-verified instead.
        from scope_protocol import ScopeSession

        class FakeScope(ScopeSession):
            def __init__(self):
                super().__init__("example.invalid")
                self.written = []
                self.answers = {
                    ":TRIGger:TYPE?": "EDGE",
                    ":TRIGger:EDGE:SOURce?": "C1",
                    ":TRIGger:EDGE:SLOPe?": "RISing",
                    ":TRIGger:EDGE:LEVel?": "2.50E+00",
                    ":TRIGger:EDGE:COUPling?": "DC",
                    ":TRIGger:EDGE:HOLDoff?": "OFF",
                    ":TRIGger:EDGE:NREJect?": "OFF",
                    ":TRIGger:EDGE:IMPedance?": "ONEMeg",
                    "SYST:ERR?": '0,"No error"',
                }
                self.stopped = True

            def write(self, command, **kwargs):
                self.written.append(command)

            def query_ascii(self, command, **kwargs):
                return self.answers[command]

        scope = FakeScope()
        evidence = scope_prepare_capture(scope)
        joined = " | ".join(scope.written)
        for forbidden in ("TRSE", "TRSL", "TRLV", "HT"):
            self.assertNotIn(forbidden, joined)
        self.assertIn(":TRIGger:EDGE:SLOPe RISing", scope.written)
        self.assertIn(":TRIGger:EDGE:SOURce C1", scope.written)
        self.assertEqual(evidence["readback"]["trigger_slope"], "RISing")
        self.assertEqual(evidence["readback"]["trigger_source"], "C1")
        self.assertEqual(evidence["requested"]["trigger_slope"], "RISing")

    def test_trigger_configuration_is_snapshot_evidence(self):
        from scope_protocol import ScopeSession

        class FakeScope(ScopeSession):
            def __init__(self):
                super().__init__("example.invalid")
                self.stopped = True
                self.answers = {
                    "TRMD?": "TRMD SINGle",
                    "SAST?": "SAST Stop",
                    "ACQ:POIN?": "2.00E+07",
                    "ACQ:MDEP?": "25.0 Mpts",
                    "SARA?": "SARA 1.00E+08Sa/s",
                    "TDIV?": "2.00E-02S",
                    "TRDL?": "TRDL -8.00E-02S",
                    "TIM:SCAL?": "2.00E-02",
                    "TIM:DEL?": "8.00E-02",
                    "TIM:REF:POS?": "5.00E+01",
                    "WFSU?": "WFSU SP,1,NP,0,FP,0",
                    "C1:VDIV?": "C1:VDIV 5.00E+00V",
                    "C1:OFST?": "C1:OFST 0.00E+00V",
                    ":TRIGger:TYPE?": "EDGE",
                    ":TRIGger:EDGE:SOURce?": "C2",
                    ":TRIGger:EDGE:SLOPe?": "RISing",
                    ":TRIGger:EDGE:LEVel?": "1.50E+00",
                    ":TRIGger:EDGE:COUPling?": "DC",
                    ":TRIGger:EDGE:HOLDoff?": "OFF",
                    ":TRIGger:EDGE:NREJect?": "OFF",
                    ":TRIGger:EDGE:IMPedance?": "ONEMeg",
                }

            def query_ascii(self, command, **kwargs):
                return self.answers[command]

        snapshot = scope_snapshot_configuration(FakeScope(), ("C1",))
        self.assertEqual(snapshot["trigger"]["trigger_slope"], "RISing")
        self.assertEqual(snapshot["trigger"]["trigger_source"], "C2")
        self.assertEqual(snapshot["trigger"]["trigger_level"], "1.50E+00")

    def test_read_trigger_configuration_covers_all_eight_fields(self):
        from scope_protocol import ScopeSession

        class FakeScope(ScopeSession):
            def __init__(self):
                super().__init__("example.invalid")
                self.stopped = True
                self.answers = {
                    ":TRIGger:TYPE?": "EDGE",
                    ":TRIGger:EDGE:SOURce?": "C1",
                    ":TRIGger:EDGE:SLOPe?": "FALLing",
                    ":TRIGger:EDGE:LEVel?": "-5.00E-01",
                    ":TRIGger:EDGE:COUPling?": "AC",
                    ":TRIGger:EDGE:HOLDoff?": "TIME",
                    ":TRIGger:EDGE:NREJect?": "ON",
                    ":TRIGger:EDGE:IMPedance?": "FIFTy",
                }

            def query_ascii(self, command, **kwargs):
                return self.answers[command]

        config = read_trigger_configuration(FakeScope())
        self.assertEqual(set(config), {
            "trigger_type", "trigger_source", "trigger_slope", "trigger_level",
            "trigger_coupling", "trigger_holdoff", "trigger_noise_reject", "trigger_impedance",
        })
        self.assertEqual(config["trigger_slope"], "FALLing")
        self.assertEqual(config["trigger_impedance"], "FIFTy")

    def test_numeric_response_reads_the_value_not_the_command_echo(self):
        # The old left-to-right digit scan returned 1.0 for every vertical
        # channel reply because it matched the "1" in "C1".
        self.assertEqual(numeric_response("C1:VDIV 5.00E+00V"), 5.0)
        self.assertEqual(numeric_response("C2:VDIV 2.00E+00V"), 2.0)
        self.assertEqual(numeric_response("C1:OFST -8.00E-01V"), -0.8)
        self.assertEqual(numeric_response("C4:ATTN 10"), 10.0)
        self.assertEqual(numeric_response("SARA 1.00E+07Sa/s"), 10_000_000.0)
        self.assertIsNone(numeric_response("C1:VDIV"))
        self.assertIsNone(numeric_response("garbage"))
        # "M" is milli in SI and million in memory depth, so it is never guessed.
        self.assertIsNone(numeric_response("25M"))
        self.assertEqual(numeric_response("25.0 Mpts"), 25_000_000.0)

    def test_one_parser_serves_capture_and_analysis_paths(self):
        from scope_protocol import parse_scpi_number
        from waveform_analysis import parse_scpi_number as analysis_parser

        self.assertIs(analysis_parser, parse_scpi_number)
        for reply in ("C1:VDIV 5.00E+00V", "2.00E-01S", "ACQ:POIN? 20000000", "0.2"):
            self.assertEqual(numeric_response(reply), parse_scpi_number(reply))

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

    def test_capture_channel_mapping_defaults_to_unknown(self):
        from capture_scope import channel_mapping_declaration

        declaration = channel_mapping_declaration(None)
        self.assertIsNone(declaration["channel_mapping"])
        self.assertEqual(declaration["channel_mapping_source"], "unknown")

    def test_capture_channel_mapping_records_caller_declaration(self):
        from capture_scope import channel_mapping_declaration

        declaration = channel_mapping_declaration("C1=ENABLE, c4=P4.1/CMP")
        self.assertEqual(declaration["channel_mapping"], {"C1": "ENABLE", "C4": "P4.1/CMP"})
        self.assertEqual(declaration["channel_mapping_source"], "user-supplied")

    def test_capture_channel_mapping_rejects_unusable_entries(self):
        from capture_scope import channel_mapping_declaration

        for text in ("C1", "C5=SIGNAL", "C1=", "C1=A,C1=B", " , "):
            with self.subTest(text=text), self.assertRaises(SystemExit):
                channel_mapping_declaration(text)

    def test_capture_cli_accepts_channel_mapping(self):
        from capture_scope import parse_args
        import sys
        from unittest.mock import patch

        with patch.object(sys, "argv", ["capture_scope.py", "--out", "/tmp/capture", "--existing-stopped", "--channel-mapping", "C2=nFAULT"]):
            args = parse_args()
        self.assertEqual(args.channel_mapping, "C2=nFAULT")

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


class SilentWriteTests(unittest.TestCase):
    """Regression guards for the silent-failure modes found on firmware 4.8.12.1.1.6.5.

    Every case here was reproduced on the instrument: a rejected or inapplicable
    write changes nothing and queues no error, so a readback comparison is the
    only general detector. The fake returns one queued answer per query, so a
    test states the readback it wants before and after the write instead of
    modelling the firmware's reply formatting.
    """

    @staticmethod
    def fake_scope(answers, errors_on_write=None, trmd_leaves_stop=True):
        """``answers`` maps a query to either one reply or a list consumed in order.

        ``trmd_leaves_stop=False`` models an instrument that acknowledges
        ``TRMD AUTO`` but keeps reporting ``Stop``, which must abort configuration.
        """

        from scope_protocol import ScopeSession

        class FakeScope(ScopeSession):
            def __init__(self):
                super().__init__("example.invalid")
                self.written = []
                self.replies = {
                    key: (list(value) if isinstance(value, list) else [value])
                    for key, value in answers.items()
                }
                self.errors_on_write = dict(errors_on_write or {})
                self.queue = []

            def write(self, command, **kwargs):
                # Drive the real gate: a permissive fake hides the very bug this
                # class exists to catch (a config helper that cannot configure a
                # stopped scope because FORBIDDEN_AFTER_STOP still blocks it).
                self._check_allowed(command, explicit_release=kwargs.get("explicit_release", False))
                self.written.append(command)
                if command in self.errors_on_write:
                    self.queue.append(self.errors_on_write[command])
                if command == "TRMD AUTO" and trmd_leaves_stop:
                    self.replies["SAST?"] = ["SAST Ready"]

            def query_ascii(self, command, **kwargs):
                if command == "SYST:ERR?":
                    return self.queue.pop(0) if self.queue else '0,"No error"'
                queued = self.replies.get(command)
                if not queued:
                    raise KeyError(command)
                return queued.pop(0) if len(queued) > 1 else queued[0]

        return FakeScope()

    def test_drain_error_queue_loops_past_stale_backlog(self):
        scope = self.fake_scope({})
        scope.queue = [
            '-113,"Undefined header;TRSL RIS"',
            '-224,"Illegal parameter value"',
            '0,"No error"',
        ]
        entries = drain_error_queue(scope)
        self.assertEqual(len(entries), 2)
        self.assertIn("Undefined header", entries[0])
        self.assertEqual(drain_error_queue(scope), [])

    def test_drain_error_queue_marks_an_exhausted_budget(self):
        # An exhausted budget must not look like an empty queue, or the next
        # caller attributes this backlog to its own write.
        scope = self.fake_scope({})
        scope.queue = ['-113,"Undefined header;A"'] * 5
        entries = drain_error_queue(scope, limit=3)
        self.assertEqual(len(entries), 4)
        self.assertIn("not empty after 3 reads", entries[-1])

    def test_write_and_verify_reports_silent_no_op(self):
        # Acquisition context written while Stop: value unchanged, no error.
        scope = self.fake_scope({"SARA?": ["SARA 2.00E+07Sa/s", "SARA 2.00E+07Sa/s"]})
        result = write_and_verify(scope, "ACQuire:SRATe 1.00E+06", "SARA?")
        self.assertFalse(result["applied"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["before"], result["after"])

    def test_write_and_verify_detects_applied_change(self):
        scope = self.fake_scope({"TDIV?": ["1.00E-01S", "2.00E-02S"]})
        result = write_and_verify(scope, "TIMebase:SCALe 2.00E-02", "TDIV?")
        self.assertTrue(result["applied"])
        self.assertEqual(result["after"], "2.00E-02S")

    def test_write_and_verify_honours_explicit_expectation(self):
        # A no-op write of the value already set is still an applied setting.
        scope = self.fake_scope({"ACQ:MMAN?": ["FSRate", "FSRate"]})
        result = write_and_verify(
            scope, "ACQuire:MMANagement FSRate", "ACQ:MMAN?", expect="FSRate"
        )
        self.assertTrue(result["applied"])

    def test_write_and_verify_accepts_query_echoing_reply(self):
        # Real firmware mixes bare and echoing replies for the same value.
        scope = self.fake_scope({"ACQ:MMAN?": ["AUTO", "ACQ:MMAN FSRate"]})
        result = write_and_verify(
            scope, "ACQuire:MMANagement FSRate", "ACQ:MMAN?", expect="FSRate"
        )
        self.assertTrue(result["applied"])

    def test_write_and_verify_surfaces_rejection_error(self):
        # C4:TRSL RIS is -224 Illegal parameter value on the instrument.
        scope = self.fake_scope(
            {"C4:TRSL?": ["C4:TRSL POSitive", "C4:TRSL POSitive"]},
            errors_on_write={"C4:TRSL RIS": '-224,"Illegal parameter value"'},
        )
        result = write_and_verify(scope, "C4:TRSL RIS", "C4:TRSL?")
        self.assertFalse(result["applied"])
        self.assertEqual(result["errors"], ['-224,"Illegal parameter value"'])

    def test_max_timebase_follows_the_window_conservation_law(self):
        # The bound is necessary but not achievable: s/div is quantized, so the
        # reproduced instrument values are settled values, not the bound.
        self.assertAlmostEqual(max_timebase_for_context(25e6, 500e6), 5e-3)
        self.assertAlmostEqual(max_timebase_for_context(25e6, 20e6), 0.125)
        self.assertAlmostEqual(max_timebase_for_context(1e6, 1e6), 1e-1)
        self.assertAlmostEqual(max_timebase_for_context(10e6, 10e6), 1e-1)
        for bad in (0, -1):
            with self.assertRaises(ScopeProtocolError):
                max_timebase_for_context(bad, 1e6)
            with self.assertRaises(ScopeProtocolError):
                max_timebase_for_context(1e6, bad)

    def test_standard_step_is_one_step_below_a_125ms_bound(self):
        # 25 Mpts at 20 MSa/s bounds TDIV at 125 ms yet settled at 100 ms/div.
        self.assertAlmostEqual(largest_standard_timebase_step(0.125), 0.1)
        self.assertAlmostEqual(largest_standard_timebase_step(5e-3), 5e-3)
        self.assertAlmostEqual(largest_standard_timebase_step(1.0), 1.0)
        self.assertIsNone(largest_standard_timebase_step(0))

    def test_context_rejects_unreachable_timebase_before_writing(self):
        scope = self.fake_scope({"SAST?": "SAST Ready"})
        with self.assertRaises(ScopeProtocolError) as caught:
            configure_acquisition_context(
                scope, sample_rate=500e6, timebase_s_per_div=1e-1, memory_depth="25M"
            )
        self.assertIn("unreachable", str(caught.exception))
        self.assertEqual(scope.written, [])

    def test_context_escapes_stop_before_writing_acquisition(self):
        scope = self.fake_scope(
            {
                "SAST?": ["SAST Stop", "SAST Ready"],
                "ACQ:MMAN?": ["FSRate"],
                "ACQ:MDEP?": ["25.0 Mpts"],
                "SARA?": ["SARA 2.00E+07Sa/s"],
                "TDIV?": ["1.00E-01S"],
                "ACQ:POIN?": ["2.00E+07"],
                "*IDN?": "Siglent Technologies,SDS824X HD,SDS08A0Q909185,4.8.12.1.1.6.5",
            }
        )
        scope.stopped = True
        result = configure_acquisition_context(
            scope,
            sample_rate=20e6,
            timebase_s_per_div=1e-1,
            memory_depth="25M",
            release_from_stop=True,
        )
        self.assertTrue(result["released_from_stop"])
        self.assertEqual(scope.written[0], "TRMD AUTO")
        self.assertIn("ACQuire:SRATe 2.000000E+07", scope.written)
        self.assertEqual(result["unapplied"], [])
        self.assertEqual(result["release_errors"], [])
        self.assertTrue(result["observed"]["points_per_second_consistent"])

    def test_context_refuses_to_release_a_stopped_frame_by_default(self):
        # Leaving Stop with TRMD AUTO overwrites the single-shot record, so the
        # helper must not do it unless the caller says the frame is expendable.
        scope = self.fake_scope({"SAST?": "SAST Stop"})
        with self.assertRaises(ScopeProtocolError) as caught:
            configure_acquisition_context(scope, sample_rate=20e6, timebase_s_per_div=1e-1)
        self.assertIn("stopped", str(caught.exception).lower())
        self.assertEqual(scope.written, [])

    def test_context_raises_when_release_does_not_leave_stop(self):
        scope = self.fake_scope(
            {
                "SAST?": ["SAST Stop", "SAST Stop"],
                "ACQ:MMAN?": ["FSRate"],
                "ACQ:MDEP?": ["25M"],
                "SARA?": ["SARA 2.00E+07Sa/s"],
                "TDIV?": ["1.00E-01S"],
                "ACQ:POIN?": ["2.00E+07"],
            },
            trmd_leaves_stop=False,
        )
        scope.stopped = True
        with self.assertRaises(ScopeProtocolError) as caught:
            configure_acquisition_context(
                scope,
                sample_rate=20e6,
                timebase_s_per_div=1e-1,
                release_from_stop=True,
            )
        self.assertIn("did not leave Stop", str(caught.exception))

    def test_context_rejects_depth_unavailable_at_this_channel_count(self):
        scope = self.fake_scope({"SAST?": "SAST Ready"})
        with self.assertRaises(ScopeProtocolError) as caught:
            configure_acquisition_context(
                scope,
                sample_rate=1e6,
                timebase_s_per_div=1e-1,
                memory_depth="100M",
                channel_count=4,
            )
        self.assertIn("unavailable", str(caught.exception))
        self.assertEqual(scope.written, [])

    def test_context_accepts_decorated_mpts_depth_readback(self):
        # The firmware answers ACQ:MDEP? with "25.0 Mpts", which a string
        # comparison against "25M" scores as a failure for an accepted write.
        scope = self.fake_scope(
            {
                "SAST?": "SAST Ready",
                "ACQ:MMAN?": ["FSRate"],
                "ACQ:MDEP?": ["25.0 Mpts"],
                "SARA?": ["SARA 2.00E+07Sa/s"],
                "TDIV?": ["1.00E-01S"],
                "ACQ:POIN?": ["2.00E+07"],
            }
        )
        result = configure_acquisition_context(
            scope, sample_rate=20e6, timebase_s_per_div=1e-1, memory_depth="25M"
        )
        self.assertEqual(result["unapplied"], [])

    def test_context_clears_the_stop_latch_so_configuration_is_allowed(self):
        # ScopeSession.stopped is a latch that only mark_state sets. A config
        # helper that releases the instrument must clear it, otherwise every
        # following write raises "command forbidden after Stop" and the helper
        # cannot configure anything.
        scope = self.fake_scope(
            {
                "SAST?": ["SAST Stop", "SAST Ready"],
                "ACQ:MMAN?": ["FSRate"],
                "ACQ:MDEP?": ["25.0 Mpts"],
                "SARA?": ["SARA 2.00E+07Sa/s"],
                "TDIV?": ["1.00E-01S"],
                "ACQ:POIN?": ["2.00E+07"],
                "*IDN?": "Siglent Technologies,SDS824X HD,SDS08A0Q909185,4.8.12.1.1.6.5",
            }
        )
        scope.mark_state("SAST Ready")
        scope.mark_state("SAST Stop")
        self.assertTrue(scope.stopped)
        configure_acquisition_context(
            scope, sample_rate=20e6, timebase_s_per_div=1e-1, release_from_stop=True
        )
        self.assertFalse(scope.stopped)
        # Clearing only ``stopped`` is not enough: a stale ``ready_seen`` lets the
        # next capture claim a Ready -> Stop transition it never observed.
        self.assertFalse(scope.ready_seen)
        self.assertFalse(scope.roll_seen)

    def test_context_orders_sample_rate_before_timebase(self):
        scope = self.fake_scope(
            {
                "SAST?": "SAST Ready",
                "ACQ:MMAN?": ["FSRate"],
                "ACQ:MDEP?": ["25.0 Mpts"],
                "SARA?": ["SARA 2.00E+07Sa/s"],
                "TDIV?": ["1.00E-01S"],
                "ACQ:POIN?": ["2.00E+07"],
            }
        )
        configure_acquisition_context(scope, sample_rate=20e6, timebase_s_per_div=1e-1)
        rate_at = next(i for i, c in enumerate(scope.written) if c.startswith("ACQuire:SRATe"))
        tdiv_at = next(i for i, c in enumerate(scope.written) if c.startswith("TIMebase:SCALe"))
        self.assertLess(rate_at, tdiv_at)

    def test_context_reports_a_quantized_timebase_as_unapplied(self):
        # 25 Mpts at 20 MSa/s bounds s/div at 125 ms, but the settled value
        # observed on the instrument is 100 ms/div: reachable, still clamped by
        # the s/div step table, and it must be reported rather than assumed.
        scope = self.fake_scope(
            {
                "SAST?": "SAST Ready",
                "ACQ:MMAN?": ["FSRate"],
                "ACQ:MDEP?": ["25.0 Mpts"],
                "SARA?": ["SARA 2.00E+07Sa/s"],
                "TDIV?": ["1.25E-01S", "1.00E-01S"],
                "ACQ:POIN?": ["2.00E+07"],
            }
        )
        result = configure_acquisition_context(
            scope, sample_rate=20e6, timebase_s_per_div=0.125, memory_depth="25M"
        )
        self.assertIn("TIMebase:SCALe 1.250000E-01", result["unapplied"])
        self.assertAlmostEqual(result["largest_standard_step_s_per_div"], 0.1)

    def test_prepare_reasserts_source_after_level_write(self):
        # A per-channel level write retargets the trigger to that channel, so the
        # source must be asserted last and verified.
        scope = self.fake_scope(
            {
                ":TRIGger:TYPE?": "EDGE",
                ":TRIGger:EDGE:SOURce?": ["C1"],
                ":TRIGger:EDGE:SLOPe?": "RISing",
                ":TRIGger:EDGE:LEVel?": "2.50E+00",
                ":TRIGger:EDGE:COUPling?": "DC",
                ":TRIGger:EDGE:HOLDoff?": "OFF",
                ":TRIGger:EDGE:NREJect?": "OFF",
                ":TRIGger:EDGE:IMPedance?": "ONEMeg",
            }
        )
        scope_prepare_capture(scope)
        self.assertEqual(scope.written[-1], ":TRIGger:EDGE:SOURce C1")

    def test_prepare_raises_when_source_did_not_stick(self):
        scope = self.fake_scope(
            {
                ":TRIGger:TYPE?": "EDGE",
                ":TRIGger:EDGE:SOURce?": ["C3"],
                ":TRIGger:EDGE:SLOPe?": "RISing",
                ":TRIGger:EDGE:LEVel?": "2.50E+00",
                ":TRIGger:EDGE:COUPling?": "DC",
                ":TRIGger:EDGE:HOLDoff?": "OFF",
                ":TRIGger:EDGE:NREJect?": "OFF",
                ":TRIGger:EDGE:IMPedance?": "ONEMeg",
            }
        )
        with self.assertRaises(ScopeProtocolError):
            scope_prepare_capture(scope)


if __name__ == "__main__":
    unittest.main()
