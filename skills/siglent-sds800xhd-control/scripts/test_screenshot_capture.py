#!/usr/bin/env python3
"""Offline tests for the headerless :PRINt? PNG reader.

No test imports or runs anything that opens a real socket: every session uses
a fake socket that hands out pre-fragmented bytes.
"""

import hashlib
import io
import json
import socket
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

import capture_scope
import screenshot_capture
from capture_scope import capture_optional_screenshot
from scope_protocol import BufferedSocket, ScopeProtocolError, ScopeSession
from screenshot_capture import (
    PNG_MIN_BYTES,
    PNG_QUERY,
    PNG_SIGNATURE,
    capture_png_on_session,
    validate_bounds,
    write_connection_failure_record,
)


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def png_bytes(*, width: int = 8, height: int = 4, bit_depth: int = 8, color_type: int = 2, image_data: bytes = b"#\nIEND\xaeB`\x82\n", palette: bytes | None = None) -> bytes:
    """Build a structurally valid PNG whose IDAT contains ``#`` and LF."""

    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)
    chunks = [png_chunk(b"IHDR", ihdr)]
    if palette is not None:
        chunks.append(png_chunk(b"PLTE", palette))
    chunks.append(png_chunk(b"IDAT", image_data))
    chunks.append(png_chunk(b"IEND", b""))
    return PNG_SIGNATURE + b"".join(chunks) + b"\n"


class FakeSocket:
    """A socket double; ``recv`` returns only the bytes the caller asked for."""

    def __init__(self, chunks, *, timeout=5.0, clock=None, advance_per_recv=0.0, fail_restore=False):
        self.chunks = list(chunks)
        self.timeout = timeout
        self.initial_timeout = timeout
        self.clock = clock
        self.advance_per_recv = advance_per_recv
        self.fail_restore = fail_restore
        self.sent = []
        self.timeouts = []

    def settimeout(self, value):
        if self.fail_restore and value == self.initial_timeout:
            raise OSError("socket already closed")
        self.timeout = value
        self.timeouts.append(value)

    def gettimeout(self):
        return self.timeout

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, size):
        if self.clock is not None:
            self.clock.now += self.advance_per_recv
        if not self.chunks:
            return b""
        item = self.chunks.pop(0)
        if isinstance(item, BaseException):
            raise item
        if len(item) > size:
            self.chunks.insert(0, item[size:])
            return item[:size]
        return item

    def close(self):
        pass


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def fake_session(sock, *, stopped=True, timeout_s=5.0, buffer=b""):
    scope = ScopeSession("example.invalid", timeout_s=timeout_s)
    scope.sock = sock
    scope.io = BufferedSocket(sock, timeout_s)
    scope.stopped = stopped
    scope.io.buffer.extend(buffer)
    return scope


class PngCaptureTests(unittest.TestCase):
    def test_capture_complete_png_from_fragmented_stream(self):
        png = png_bytes()
        fragments = [png[:1], png[1:4], png[4:9], png[9:21], png[21:37], png[37:]]
        sock = FakeSocket(fragments)
        scope = fake_session(sock)
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            metadata_path = Path(tmp) / "shot.png.json"
            record = capture_png_on_session(scope, raw_path, metadata_path)

            self.assertEqual(record["status"], "COMPLETE")
            self.assertTrue(record["container_valid"])
            self.assertEqual(record["image_decode_status"], "UNVERIFIED")
            self.assertTrue(record["image_decode_reasons"])
            self.assertTrue(record["raw_file_created"])
            self.assertEqual(record["raw_bytes"], len(png))
            self.assertEqual(record["sha256"], hashlib.sha256(png).hexdigest())
            self.assertEqual((record["width"], record["height"]), (8, 4))
            self.assertEqual((record["bit_depth"], record["color_type"]), (8, 2))
            self.assertEqual(record["idat_bytes"], len(b"#\nIEND\xaeB`\x82\n"))
            self.assertEqual(record["chunks"], 3)
            self.assertEqual(record["crc_checked"], 3)
            self.assertEqual(record["terminator"], "IEND+LF")
            self.assertEqual(record["frame_association"]["status"], "UNVERIFIED")
            self.assertEqual(raw_path.read_bytes(), png)
            stored = json.loads(metadata_path.read_text())
            self.assertEqual(stored["sha256"], record["sha256"])
            self.assertEqual(stored["command"], PNG_QUERY)
            self.assertEqual(stored["command_log"][-1]["response_kind"], "png_raw")
            self.assertEqual(stored["command_log"][-1]["response_length"], len(png))
            self.assertEqual(sock.sent, [PNG_QUERY.encode("ascii") + b"\n"])

    def test_ancillary_chunk_after_idat_is_accepted(self):
        ihdr = struct.pack(">IIBBBBB", 4, 2, 8, 2, 0, 0, 0)
        body = (
            PNG_SIGNATURE
            + png_chunk(b"IHDR", ihdr)
            + png_chunk(b"IDAT", b"\x00")
            + png_chunk(b"tEXt", b"note")
            + png_chunk(b"IEND", b"")
            + b"\n"
        )
        sock = FakeSocket([body])
        with tempfile.TemporaryDirectory() as tmp:
            record = capture_png_on_session(fake_session(sock), Path(tmp) / "a.png", Path(tmp) / "a.png.json")
        self.assertEqual(record["status"], "COMPLETE")
        self.assertEqual(record["chunks"], 4)

    def test_crc_mismatch_is_invalid_and_raw_prefix_is_kept(self):
        png = bytearray(png_bytes())
        png[29] ^= 0xFF  # inside the IHDR CRC
        sock = FakeSocket([bytes(png)])
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            record = capture_png_on_session(fake_session(sock), raw_path, Path(tmp) / "shot.png.json")
            self.assertEqual(record["status"], "INVALID")
            self.assertEqual(record["error_code"], "png_crc_mismatch")
            self.assertFalse(record["container_valid"])
            self.assertEqual(record["image_decode_status"], "UNVERIFIED")
            self.assertTrue(record["raw_file_created"])
            self.assertEqual(raw_path.read_bytes(), bytes(png[:33]))
            self.assertEqual(record["raw_bytes"], 33)

    def test_truncated_stream_is_incomplete_and_raw_prefix_is_kept(self):
        png = png_bytes()
        sock = FakeSocket([png[:20]])
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            record = capture_png_on_session(fake_session(sock), raw_path, Path(tmp) / "shot.png.json")
            self.assertEqual(record["status"], "INCOMPLETE")
            self.assertEqual(record["error_code"], "connection_closed")
            self.assertEqual(raw_path.read_bytes(), png[:20])
            self.assertEqual(record["raw_bytes"], 20)

    def test_non_png_response_is_invalid_and_raw_is_kept(self):
        banner = b"Welcome to the SCPI instrument 'Siglent SDS824X HD'\r\n>>"
        sock = FakeSocket([banner])
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            record = capture_png_on_session(fake_session(sock), raw_path, Path(tmp) / "shot.png.json")
            self.assertEqual(record["status"], "INVALID")
            self.assertEqual(record["error_code"], "png_signature_invalid")
            self.assertEqual(raw_path.read_bytes(), banner[:8])

    def test_byte_limit_is_enforced_and_partial_raw_is_kept(self):
        png = png_bytes()
        max_bytes = len(png) - 1
        sock = FakeSocket([png])
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            record = capture_png_on_session(
                fake_session(sock), raw_path, Path(tmp) / "shot.png.json", max_bytes=max_bytes
            )
            self.assertEqual(record["status"], "INCOMPLETE")
            self.assertEqual(record["error_code"], "byte_limit_exceeded")
            self.assertEqual(raw_path.read_bytes(), png[:max_bytes])
            self.assertEqual(record["raw_bytes"], max_bytes)

    def test_socket_timeout_is_reported_as_read_timeout(self):
        sock = FakeSocket([socket.timeout()])
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            record = capture_png_on_session(fake_session(sock), raw_path, Path(tmp) / "shot.png.json", max_seconds=2.0)
            self.assertEqual(record["status"], "INCOMPLETE")
            self.assertEqual(record["error_code"], "read_timeout")
            self.assertEqual(raw_path.read_bytes(), b"")

    def test_elapsed_time_limit_is_enforced(self):
        clock = Clock()
        sock = FakeSocket([socket.timeout()], clock=clock, advance_per_recv=3.0)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(screenshot_capture, "time", mock.Mock(monotonic=clock)):
                record = capture_png_on_session(
                    fake_session(sock), Path(tmp) / "shot.png", Path(tmp) / "shot.png.json", max_seconds=2.0
                )
        self.assertEqual(record["status"], "INCOMPLETE")
        self.assertEqual(record["error_code"], "duration_limit_exceeded")

    def test_trailing_buffered_bytes_after_terminator_are_invalid(self):
        png = png_bytes()
        sock = FakeSocket([])
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            record = capture_png_on_session(fake_session(sock, buffer=png + b"EXTRA"), raw_path, Path(tmp) / "shot.png.json")
            self.assertEqual(record["status"], "INVALID")
            self.assertEqual(record["error_code"], "png_trailing_bytes")
            self.assertEqual(raw_path.read_bytes(), png + b"EXTRA")

    def test_oversized_dimensions_are_rejected(self):
        sock = FakeSocket([png_bytes(width=100_000)])
        with tempfile.TemporaryDirectory() as tmp:
            record = capture_png_on_session(fake_session(sock), Path(tmp) / "a.png", Path(tmp) / "a.png.json")
        self.assertEqual(record["status"], "INVALID")
        self.assertEqual(record["error_code"], "png_dimensions_out_of_bounds")

    def test_missing_idat_is_rejected(self):
        ihdr = struct.pack(">IIBBBBB", 4, 2, 8, 2, 0, 0, 0)
        body = PNG_SIGNATURE + png_chunk(b"IHDR", ihdr) + png_chunk(b"IEND", b"") + b"\n"
        sock = FakeSocket([body])
        with tempfile.TemporaryDirectory() as tmp:
            record = capture_png_on_session(fake_session(sock), Path(tmp) / "a.png", Path(tmp) / "a.png.json")
        self.assertEqual(record["status"], "INVALID")
        self.assertEqual(record["error_code"], "png_idat_missing")

    def test_empty_or_random_idat_is_container_valid_but_not_an_image_claim(self):
        for image_data in (b"", b"\x00\xff\x10not-a-zlib-stream"):
            with self.subTest(image_data=image_data):
                sock = FakeSocket([png_bytes(image_data=image_data)])
                with tempfile.TemporaryDirectory() as tmp:
                    record = capture_png_on_session(fake_session(sock), Path(tmp) / "a.png", Path(tmp) / "a.png.json")
                self.assertEqual(record["status"], "COMPLETE")
                self.assertTrue(record["container_valid"])
                self.assertEqual(record["idat_bytes"], len(image_data))
                self.assertEqual(record["image_decode_status"], "UNVERIFIED")
                self.assertTrue(record["image_decode_reasons"])

    def test_invalid_bit_depth_color_combination_is_rejected(self):
        for bit_depth, color_type in ((4, 2), (16, 3), (2, 6), (8, 5)):
            with self.subTest(bit_depth=bit_depth, color_type=color_type):
                sock = FakeSocket([png_bytes(bit_depth=bit_depth, color_type=color_type)])
                with tempfile.TemporaryDirectory() as tmp:
                    record = capture_png_on_session(fake_session(sock), Path(tmp) / "a.png", Path(tmp) / "a.png.json")
                self.assertEqual(record["status"], "INVALID")
                self.assertEqual(record["error_code"], "png_ihdr_encoding_invalid")

    def test_indexed_color_requires_a_palette_before_idat(self):
        sock = FakeSocket([png_bytes(bit_depth=8, color_type=3)])
        with tempfile.TemporaryDirectory() as tmp:
            record = capture_png_on_session(fake_session(sock), Path(tmp) / "a.png", Path(tmp) / "a.png.json")
        self.assertEqual(record["status"], "INVALID")
        self.assertEqual(record["error_code"], "png_palette_missing")

    def test_indexed_color_with_a_palette_is_container_valid(self):
        sock = FakeSocket([png_bytes(bit_depth=8, color_type=3, palette=b"\x00\x00\x00\xff\xff\xff")])
        with tempfile.TemporaryDirectory() as tmp:
            record = capture_png_on_session(fake_session(sock), Path(tmp) / "a.png", Path(tmp) / "a.png.json")
        self.assertEqual(record["status"], "COMPLETE")
        self.assertEqual(record["palette_entries"], 2)
        self.assertEqual(record["image_decode_status"], "UNVERIFIED")

    def test_palette_entries_must_fit_the_index_range(self):
        sock = FakeSocket([png_bytes(bit_depth=1, color_type=3, palette=b"\x01\x02\x03" * 3)])
        with tempfile.TemporaryDirectory() as tmp:
            record = capture_png_on_session(fake_session(sock), Path(tmp) / "a.png", Path(tmp) / "a.png.json")
        self.assertEqual(record["status"], "INVALID")
        self.assertEqual(record["error_code"], "png_palette_invalid")

    def test_palette_after_idat_is_rejected(self):
        ihdr = struct.pack(">IIBBBBB", 4, 2, 8, 3, 0, 0, 0)
        body = (
            PNG_SIGNATURE
            + png_chunk(b"IHDR", ihdr)
            + png_chunk(b"PLTE", b"\x00\x00\x00")
            + png_chunk(b"IDAT", b"\x00")
            + png_chunk(b"PLTE", b"\x00\x00\x00")
            + png_chunk(b"IEND", b"")
            + b"\n"
        )
        sock = FakeSocket([body])
        with tempfile.TemporaryDirectory() as tmp:
            record = capture_png_on_session(fake_session(sock), Path(tmp) / "a.png", Path(tmp) / "a.png.json")
        self.assertEqual(record["status"], "INVALID")
        self.assertEqual(record["error_code"], "png_palette_after_idat")

    def test_unknown_critical_chunk_is_rejected(self):
        ihdr = struct.pack(">IIBBBBB", 4, 2, 8, 2, 0, 0, 0)
        body = (
            PNG_SIGNATURE
            + png_chunk(b"IHDR", ihdr)
            + png_chunk(b"ZZZZ", b"x")
            + png_chunk(b"IDAT", b"\x00")
            + png_chunk(b"IEND", b"")
            + b"\n"
        )
        sock = FakeSocket([body])
        with tempfile.TemporaryDirectory() as tmp:
            record = capture_png_on_session(fake_session(sock), Path(tmp) / "a.png", Path(tmp) / "a.png.json")
        self.assertEqual(record["status"], "INVALID")
        self.assertEqual(record["error_code"], "png_critical_chunk_unknown")

    def test_unknown_ancillary_chunk_is_accepted(self):
        ihdr = struct.pack(">IIBBBBB", 4, 2, 8, 2, 0, 0, 0)
        body = (
            PNG_SIGNATURE
            + png_chunk(b"IHDR", ihdr)
            + png_chunk(b"zzZz", b"x")
            + png_chunk(b"IDAT", b"\x00")
            + png_chunk(b"IEND", b"")
            + b"\n"
        )
        sock = FakeSocket([body])
        with tempfile.TemporaryDirectory() as tmp:
            record = capture_png_on_session(fake_session(sock), Path(tmp) / "a.png", Path(tmp) / "a.png.json")
        self.assertEqual(record["status"], "COMPLETE")

    def test_non_contiguous_idat_is_rejected(self):
        ihdr = struct.pack(">IIBBBBB", 4, 2, 8, 2, 0, 0, 0)
        body = (
            PNG_SIGNATURE
            + png_chunk(b"IHDR", ihdr)
            + png_chunk(b"IDAT", b"\x00")
            + png_chunk(b"tEXt", b"note")
            + png_chunk(b"IDAT", b"\x01")
            + png_chunk(b"IEND", b"")
            + b"\n"
        )
        sock = FakeSocket([body])
        with tempfile.TemporaryDirectory() as tmp:
            record = capture_png_on_session(fake_session(sock), Path(tmp) / "a.png", Path(tmp) / "a.png.json")
        self.assertEqual(record["status"], "INVALID")
        self.assertEqual(record["error_code"], "png_idat_not_contiguous")

    def test_original_socket_timeout_is_restored(self):
        png = png_bytes()
        sock = FakeSocket([png], timeout=7.5)
        with tempfile.TemporaryDirectory() as tmp:
            record = capture_png_on_session(fake_session(sock), Path(tmp) / "a.png", Path(tmp) / "a.png.json")
        self.assertEqual(record["status"], "COMPLETE")
        self.assertEqual(sock.gettimeout(), 7.5)
        self.assertNotIn("timeout_restore_error", record)
        self.assertTrue(any(value != 7.5 for value in sock.timeouts))

    def test_timeout_restore_failure_keeps_the_original_failure_and_writes_json(self):
        png = png_bytes()
        sock = FakeSocket([png[:20]], timeout=7.5, fail_restore=True)
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "a.png"
            metadata_path = Path(tmp) / "a.png.json"
            record = capture_png_on_session(fake_session(sock), raw_path, metadata_path)
            self.assertEqual(record["status"], "INCOMPLETE")
            self.assertEqual(record["error_code"], "connection_closed")
            self.assertIn("socket already closed", record["timeout_restore_error"])
            self.assertEqual(raw_path.read_bytes(), png[:20])
            stored = json.loads(metadata_path.read_text())
            self.assertEqual(stored["error_code"], "connection_closed")
            self.assertEqual(stored["timeout_restore_error"], record["timeout_restore_error"])

    def test_existing_raw_artifact_is_never_overwritten(self):
        sock = FakeSocket([png_bytes()])
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            metadata_path = Path(tmp) / "shot.png.json"
            raw_path.write_bytes(b"previous capture")
            with self.assertRaises(FileExistsError):
                capture_png_on_session(fake_session(sock), raw_path, metadata_path)
            self.assertEqual(raw_path.read_bytes(), b"previous capture")
            self.assertFalse(metadata_path.exists())
            self.assertEqual(sock.sent, [])

    def test_existing_metadata_rolls_back_the_reserved_raw_file(self):
        sock = FakeSocket([png_bytes()])
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            metadata_path = Path(tmp) / "shot.png.json"
            metadata_path.write_text("previous record")
            with self.assertRaises(FileExistsError):
                capture_png_on_session(fake_session(sock), raw_path, metadata_path)
            self.assertEqual(metadata_path.read_text(), "previous record")
            self.assertFalse(raw_path.exists())
            self.assertEqual(sock.sent, [])

    def test_invalid_bounds_are_rejected_before_any_artifact_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            metadata_path = Path(tmp) / "shot.png.json"
            for max_bytes, max_seconds in (
                (PNG_MIN_BYTES - 1, 1.0),
                (1024, float("nan")),
                (1024, float("inf")),
                (1024, 0.0),
                (1024, -1.0),
                (1024.5, 1.0),
            ):
                with self.subTest(max_bytes=max_bytes, max_seconds=max_seconds):
                    with self.assertRaises(ValueError):
                        validate_bounds(max_bytes, max_seconds)
                    with self.assertRaises(ValueError):
                        capture_png_on_session(
                            fake_session(FakeSocket([])),
                            raw_path,
                            metadata_path,
                            max_bytes=max_bytes,
                            max_seconds=max_seconds,
                        )
                    self.assertFalse(raw_path.exists())
                    self.assertFalse(metadata_path.exists())


class ConnectionFailureRecordTests(unittest.TestCase):
    def test_connection_failure_writes_json_without_a_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            metadata_path = Path(tmp) / "shot.png.json"
            error = ConnectionRefusedError(111, "connection refused")
            record = write_connection_failure_record(raw_path, metadata_path, error)
            self.assertFalse(raw_path.exists())
            stored = json.loads(metadata_path.read_text())
            self.assertEqual(stored["status"], "INCOMPLETE")
            self.assertEqual(stored["error_code"], "connection_failed")
            self.assertIn("ConnectionRefusedError", stored["error"])
            self.assertFalse(stored["container_valid"])
            self.assertEqual(stored["image_decode_status"], "UNVERIFIED")
            self.assertFalse(stored["raw_file_created"])
            self.assertEqual(stored["raw_bytes"], 0)
            self.assertEqual(stored["frame_association"]["status"], "UNVERIFIED")
            self.assertEqual(stored, json.loads(json.dumps(record)))

    def test_connection_failure_does_not_overwrite_an_existing_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            metadata_path = Path(tmp) / "shot.png.json"
            metadata_path.write_text("previous record")
            with self.assertRaises(FileExistsError):
                write_connection_failure_record(raw_path, metadata_path, OSError("boom"))
            self.assertEqual(metadata_path.read_text(), "previous record")
            self.assertFalse(raw_path.exists())


class StoppedSessionAllowlistTests(unittest.TestCase):
    def test_only_the_exact_png_query_is_allowed_after_stop(self):
        scope = ScopeSession("example.invalid")
        scope.stopped = True
        scope._check_allowed(PNG_QUERY)
        for command in (
            ":PRINt? BMP",
            ":PRINt? PNG,NORM",
            ":PRINt?  PNG",
            ":PRINt? PNG;:SYSTem:REMote ON",
            ':SAVe:IMAGe "local/a.png",PNG,ON,MOFf',
            "TRMD AUTO",
            "STOP",
        ):
            with self.subTest(command=command):
                with self.assertRaises(ScopeProtocolError):
                    scope._check_allowed(command)


class FakeCliSession(ScopeSession):
    """A ScopeSession double; ``connect`` never opens a real socket."""

    connect_error = None
    fragments = []
    clock = None
    connect_seconds = 0.0
    instances = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.closed = False
        type(self).instances.append(self)

    def connect(self):
        if type(self).clock is not None:
            type(self).clock.now += type(self).connect_seconds
        if type(self).connect_error is not None:
            raise type(self).connect_error
        sock = FakeSocket(list(type(self).fragments))
        self.sock = sock
        self.io = BufferedSocket(sock, self.timeout_s)

    def close(self):
        self.closed = True
        super().close()


class StandaloneCliTests(unittest.TestCase):
    def setUp(self):
        FakeCliSession.connect_error = None
        FakeCliSession.fragments = []
        FakeCliSession.clock = None
        FakeCliSession.connect_seconds = 0.0
        FakeCliSession.instances = []

    def tearDown(self):
        FakeCliSession.connect_error = None
        FakeCliSession.fragments = []
        FakeCliSession.clock = None
        FakeCliSession.connect_seconds = 0.0
        FakeCliSession.instances = []

    def test_cli_writes_png_and_metadata_without_a_real_socket(self):
        png = png_bytes()
        FakeCliSession.fragments = [png[:10], png[10:]]
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            stdout = io.StringIO()
            with mock.patch.object(screenshot_capture, "ScopeSession", FakeCliSession):
                with mock.patch.object(sys, "stdout", stdout):
                    code = screenshot_capture.main(["--host", "example.invalid", "--out", str(raw_path)])
            self.assertEqual(code, 0)
            self.assertEqual(raw_path.read_bytes(), png)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "COMPLETE")
            self.assertTrue((Path(tmp) / "shot.png.json").exists())

    def test_cli_records_connection_failure_with_exit_code_2(self):
        FakeCliSession.connect_error = ConnectionRefusedError(111, "refused")
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            stdout = io.StringIO()
            with mock.patch.object(screenshot_capture, "ScopeSession", FakeCliSession):
                with mock.patch.object(sys, "stdout", stdout):
                    code = screenshot_capture.main(["--host", "example.invalid", "--out", str(raw_path)])
            self.assertEqual(code, 2)
            self.assertFalse(raw_path.exists())
            stored = json.loads((Path(tmp) / "shot.png.json").read_text())
            self.assertEqual(stored["error_code"], "connection_failed")

    def test_cli_rejects_invalid_bounds_before_connecting(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            with mock.patch.object(screenshot_capture, "ScopeSession", FakeCliSession):
                for arguments in (["--max-seconds", "nan"], ["--max-seconds", "inf"], ["--max-bytes", "10"]):
                    with self.subTest(arguments=arguments):
                        with self.assertRaises(SystemExit):
                            screenshot_capture.main(["--host", "example.invalid", "--out", str(raw_path), *arguments])
            self.assertFalse(raw_path.exists())

    def test_cli_caps_the_session_timeout_at_max_seconds_and_keeps_the_request(self):
        FakeCliSession.fragments = [png_bytes()]
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            with mock.patch.object(screenshot_capture, "ScopeSession", FakeCliSession):
                with mock.patch.object(sys, "stdout", io.StringIO()):
                    code = screenshot_capture.main(
                        ["--host", "example.invalid", "--out", str(raw_path), "--timeout", "9", "--max-seconds", "2"]
                    )
            self.assertEqual(code, 0)
            self.assertEqual(FakeCliSession.instances[0].timeout_s, 2.0)
            stored = json.loads((Path(tmp) / "shot.png.json").read_text())
            self.assertEqual(stored["session_timeout_s"], 2.0)
            self.assertEqual(stored["requested_timeout_s"], 9.0)

    def test_cli_keeps_a_smaller_requested_timeout(self):
        FakeCliSession.fragments = [png_bytes()]
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            with mock.patch.object(screenshot_capture, "ScopeSession", FakeCliSession):
                with mock.patch.object(sys, "stdout", io.StringIO()):
                    code = screenshot_capture.main(
                        ["--host", "example.invalid", "--out", str(raw_path), "--timeout", "1", "--max-seconds", "5"]
                    )
            self.assertEqual(code, 0)
            self.assertEqual(FakeCliSession.instances[0].timeout_s, 1.0)
            stored = json.loads((Path(tmp) / "shot.png.json").read_text())
            self.assertEqual((stored["requested_timeout_s"], stored["session_timeout_s"]), (1.0, 1.0))

    def test_connection_failure_record_keeps_both_timeout_values(self):
        FakeCliSession.connect_error = ConnectionRefusedError(111, "refused")
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            with mock.patch.object(screenshot_capture, "ScopeSession", FakeCliSession):
                with mock.patch.object(sys, "stdout", io.StringIO()):
                    code = screenshot_capture.main(
                        ["--host", "example.invalid", "--out", str(raw_path), "--timeout", "9", "--max-seconds", "2"]
                    )
            self.assertEqual(code, 2)
            stored = json.loads((Path(tmp) / "shot.png.json").read_text())
            self.assertEqual(stored["session_timeout_s"], 2.0)
            self.assertEqual(stored["requested_timeout_s"], 9.0)

    def test_connect_time_counts_against_the_total_time_bound(self):
        clock = Clock()
        FakeCliSession.clock = clock
        FakeCliSession.connect_seconds = 5.0
        FakeCliSession.fragments = [png_bytes()]
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "shot.png"
            with mock.patch.object(screenshot_capture, "time", mock.Mock(monotonic=clock)):
                with mock.patch.object(screenshot_capture, "ScopeSession", FakeCliSession):
                    with mock.patch.object(sys, "stdout", io.StringIO()):
                        code = screenshot_capture.main(
                            ["--host", "example.invalid", "--out", str(raw_path), "--max-seconds", "5"]
                        )
            self.assertEqual(code, 2)
            self.assertEqual(raw_path.read_bytes(), b"")
            self.assertTrue((Path(tmp) / "shot.png.json").exists())
            stored = json.loads((Path(tmp) / "shot.png.json").read_text())
            self.assertEqual(stored["error_code"], "command_or_transport_error")
            self.assertIn("TimeoutError", stored["error"])
            self.assertEqual(stored["command_log"], [])
            self.assertEqual(stored["raw_bytes"], 0)


class CaptureScopeIntegrationTests(unittest.TestCase):
    def test_screenshot_is_opt_in(self):
        with mock.patch.object(sys, "argv", ["capture_scope.py", "--out", "unused", "--existing-stopped"]):
            self.assertFalse(capture_scope.parse_args().screenshot)
        with mock.patch.object(sys, "argv", ["capture_scope.py", "--out", "unused", "--existing-stopped", "--screenshot"]):
            self.assertTrue(capture_scope.parse_args().screenshot)

    def test_screenshot_after_capture_keeps_association_unverified(self):
        png = png_bytes()
        sock = FakeSocket([png])
        scope = fake_session(sock)
        with tempfile.TemporaryDirectory() as tmp:
            record = capture_optional_screenshot(scope, Path(tmp))
            self.assertEqual(record["status"], "COMPLETE")
            self.assertEqual(record["frame_association"]["status"], "UNVERIFIED")
            self.assertEqual((Path(tmp) / "screenshot.png").read_bytes(), png)
            self.assertEqual(sock.sent, [PNG_QUERY.encode("ascii") + b"\n"])

    def test_failed_screenshot_does_not_raise_and_never_requeries(self):
        sock = FakeSocket([socket.timeout()])
        scope = fake_session(sock)
        with tempfile.TemporaryDirectory() as tmp:
            record = capture_optional_screenshot(scope, Path(tmp))
            self.assertEqual(record["status"], "INCOMPLETE")
            self.assertFalse(record["container_valid"])
            self.assertEqual(len(sock.sent), 1)
            second = capture_optional_screenshot(scope, Path(tmp))
            self.assertEqual(second["error_code"], "artifact_exists")
            self.assertFalse(second["container_valid"])
            self.assertEqual(len(sock.sent), 1)


if __name__ == "__main__":
    unittest.main()
