#!/usr/bin/env python3
"""Bounded reader for the SDS800X HD headerless PNG screenshot response.

``:PRINt? PNG`` answers with raw PNG bytes and no IEEE 488.2 block header, so
``scope_protocol.query_block()`` must not be used. This reader validates the
PNG container only: signature, legal IHDR bit-depth/colour-type combination,
chunk order and framing, one CRC per chunk, ``IEND`` followed by exactly one
``LF``. It deliberately does not decode image data: ``image_decode_status`` is
always ``UNVERIFIED``, so an empty or random ``IDAT`` payload with correct CRCs
still yields ``container_valid = true`` and proves nothing about a viewable
image. Container validity also never proves that the image shows the same
acquisition as a downloaded waveform, so that association stays ``UNVERIFIED``.

The reader is validated offline against fragmented fake sockets. It has not
been exercised against a physical SDS800X HD.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import socket
import struct
import sys
import time
import zlib
from pathlib import Path
from typing import Any, BinaryIO

from scope_protocol import BufferedSocket, ScopeProtocolError, ScopeSession

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_QUERY = ":PRINt? PNG"
FRAMING = "raw_png_chunks_through_iend_plus_lf_not_ieee4882"
SCHEMA_VERSION = "screenshot-evidence-v1"
DEFAULT_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_SECONDS = 15.0
RECV_CHUNK = 65536
MAX_DIMENSION = 16384
MAX_PIXELS = 100_000_000
MAX_CHUNK_BYTES = 0x7FFFFFFF
# Signature, the 13-byte IHDR chunk, one IDAT chunk, one IEND chunk, one LF.
PNG_MIN_BYTES = len(PNG_SIGNATURE) + (12 + 13) + 12 + 12 + 1
# PNG bit-depth/colour-type combinations (spec section 11.2.2).
VALID_BIT_DEPTHS = {
    0: (1, 2, 4, 8, 16),
    2: (8, 16),
    3: (1, 2, 4, 8),
    4: (8, 16),
    6: (8, 16),
}
CRITICAL_CHUNKS = (b"IHDR", b"PLTE", b"IDAT", b"IEND")
# No decoder runs here, so decoded pixels and image usability are never claimed.
IMAGE_DECODE_STATUS = "UNVERIFIED"
IMAGE_DECODE_REASONS = ["no PNG decoder ran; chunk framing and CRCs prove container structure only"]


class _PngReadFailure(Exception):
    def __init__(self, status: str, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


def frame_association() -> dict[str, Any]:
    """Return the unchanged association verdict for every screenshot record."""

    return {
        "status": "UNVERIFIED",
        "reasons": ["no shared frame identifier or pixel-to-sample mapping was recorded"],
    }


def validate_bounds(max_bytes: Any, max_seconds: Any, *, timeout_s: Any = None) -> None:
    """Reject non-finite or too-small bounds before any artifact is created."""

    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
        raise ValueError("max_bytes must be an integer byte bound")
    if max_bytes < PNG_MIN_BYTES:
        raise ValueError(f"max_bytes must be at least {PNG_MIN_BYTES} bytes")
    if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)):
        raise ValueError("max_seconds must be a finite positive number of seconds")
    if not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("max_seconds must be a finite positive number of seconds")
    if timeout_s is not None:
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
            raise ValueError("timeout must be a finite positive number of seconds")
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout must be a finite positive number of seconds")


def _read_png_stream(
    buffered: BufferedSocket,
    output: BinaryIO,
    *,
    max_bytes: int,
    max_seconds: float,
    started_at: float,
) -> dict[str, Any]:
    """Read one PNG response into ``output``; never raise a transport failure.

    Every byte actually read is written to ``output`` before the status is
    returned, so a partial or invalid response is still on disk. ``max_bytes``
    and ``max_seconds`` are hard: the reader stops and reports ``INCOMPLETE``
    rather than reading past either bound. Bounds must already be validated by
    :func:`validate_bounds`.
    """

    sock = buffered.sock
    deadline = started_at + max_seconds
    digest = hashlib.sha256()
    observed = 0
    dimensions: tuple[int, int] | None = None
    bit_depth_value: int | None = None
    color_type_value: int | None = None
    palette_entries: int | None = None
    palette_seen = False
    idat_bytes = 0
    chunk_count = 0
    crc_checked = 0
    saw_idat = False
    idat_finished = False
    saw_iend = False

    def result(status: str, *, error_code: str | None = None, error: str | None = None, terminator: str | None = None) -> dict[str, Any]:
        return {
            "status": status,
            "container_valid": status == "COMPLETE",
            "image_decode_status": IMAGE_DECODE_STATUS,
            "image_decode_reasons": list(IMAGE_DECODE_REASONS),
            "error_code": error_code,
            "error": error,
            "raw_bytes": observed,
            "sha256": digest.hexdigest(),
            "width": dimensions[0] if dimensions else None,
            "height": dimensions[1] if dimensions else None,
            "bit_depth": bit_depth_value,
            "color_type": color_type_value,
            "palette_entries": palette_entries,
            "idat_bytes": idat_bytes,
            "chunks": chunk_count,
            "crc_checked": crc_checked,
            "duration_s": round(time.monotonic() - started_at, 6),
            "terminator": terminator,
        }

    def take(count: int) -> bytes:
        """Return 1..count bytes, honouring both the byte and the time bound."""

        nonlocal observed
        remaining_time = deadline - time.monotonic()
        if remaining_time <= 0:
            raise _PngReadFailure("INCOMPLETE", "duration_limit_exceeded", f"PNG read exceeded {max_seconds} seconds")
        budget = max_bytes - observed
        if budget <= 0:
            raise _PngReadFailure("INCOMPLETE", "byte_limit_exceeded", f"PNG exceeded {max_bytes} bytes")
        if buffered.buffer:
            take_count = min(count, len(buffered.buffer), budget)
            data = bytes(buffered.buffer[:take_count])
            del buffered.buffer[:take_count]
        else:
            sock.settimeout(min(float(buffered.timeout_s), remaining_time))
            try:
                data = sock.recv(min(count, RECV_CHUNK, budget))
            except socket.timeout as exc:
                if time.monotonic() >= deadline:
                    raise _PngReadFailure("INCOMPLETE", "duration_limit_exceeded", f"PNG read exceeded {max_seconds} seconds") from exc
                raise _PngReadFailure("INCOMPLETE", "read_timeout", "PNG response read timed out") from exc
            except OSError as exc:
                raise _PngReadFailure("INCOMPLETE", "transport_error", f"PNG transport failed: {exc}") from exc
            if not data:
                raise _PngReadFailure("INCOMPLETE", "connection_closed", "connection closed before PNG IEND and LF")
        output.write(data)
        digest.update(data)
        observed += len(data)
        return data

    def read_exact(count: int) -> bytes:
        parts: list[bytes] = []
        remaining = count
        while remaining > 0:
            data = take(remaining)
            parts.append(data)
            remaining -= len(data)
        return b"".join(parts)

    try:
        if read_exact(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
            raise _PngReadFailure("INVALID", "png_signature_invalid", "response does not begin with the PNG signature")

        while not saw_iend:
            length, kind = struct.unpack(">I4s", read_exact(8))
            if not all(65 <= byte <= 90 or 97 <= byte <= 122 for byte in kind):
                raise _PngReadFailure("INVALID", "png_chunk_type_invalid", f"invalid PNG chunk type {kind!r}")
            if length > MAX_CHUNK_BYTES:
                raise _PngReadFailure("INVALID", "png_chunk_length_invalid", f"PNG chunk length {length} is out of range")
            if chunk_count == 0 and kind != b"IHDR":
                raise _PngReadFailure("INVALID", "png_ihdr_missing", "IHDR must be the first PNG chunk")
            if kind == b"IHDR" and (chunk_count != 0 or length != 13):
                raise _PngReadFailure("INVALID", "png_ihdr_invalid", "PNG must contain one 13-byte IHDR first")
            if kind == b"IEND" and length != 0:
                raise _PngReadFailure("INVALID", "png_iend_invalid", "IEND must have an empty payload")
            if kind[:1].isupper() and kind not in CRITICAL_CHUNKS:
                raise _PngReadFailure("INVALID", "png_critical_chunk_unknown", f"unknown critical PNG chunk {kind!r}")
            if kind == b"PLTE":
                if saw_idat:
                    raise _PngReadFailure("INVALID", "png_palette_after_idat", "PLTE must precede all IDAT chunks")
                if palette_seen:
                    raise _PngReadFailure("INVALID", "png_palette_duplicate", "PNG must contain at most one PLTE chunk")
            if kind == b"IDAT":
                if idat_finished:
                    raise _PngReadFailure("INVALID", "png_idat_not_contiguous", "IDAT chunks must be contiguous")
                if color_type_value == 3 and not palette_seen:
                    raise _PngReadFailure("INVALID", "png_palette_missing", "indexed-color PNG has no PLTE before IDAT")
                saw_idat = True
            elif saw_idat:
                idat_finished = True

            crc = zlib.crc32(kind)
            payload = bytearray()
            remaining = length
            while remaining > 0:
                part = take(remaining)
                crc = zlib.crc32(part, crc)
                payload.extend(part)
                remaining -= len(part)
            expected_crc = struct.unpack(">I", read_exact(4))[0]
            if crc & 0xFFFFFFFF != expected_crc:
                raise _PngReadFailure("INVALID", "png_crc_mismatch", f"CRC mismatch in {kind.decode('ascii', 'replace')} chunk")
            crc_checked += 1
            chunk_count += 1

            if kind == b"IHDR":
                width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
                if width <= 0 or height <= 0 or width > MAX_DIMENSION or height > MAX_DIMENSION or width * height > MAX_PIXELS:
                    raise _PngReadFailure("INVALID", "png_dimensions_out_of_bounds", f"PNG dimensions {width}x{height} exceed validation bounds")
                if color_type not in VALID_BIT_DEPTHS or bit_depth not in VALID_BIT_DEPTHS[color_type]:
                    raise _PngReadFailure(
                        "INVALID",
                        "png_ihdr_encoding_invalid",
                        f"bit depth {bit_depth} is not legal for PNG colour type {color_type}",
                    )
                if compression != 0 or filtering != 0 or interlace not in (0, 1):
                    raise _PngReadFailure("INVALID", "png_ihdr_method_invalid", "invalid PNG compression, filter, or interlace method")
                dimensions = (width, height)
                bit_depth_value = bit_depth
                color_type_value = color_type
            elif kind == b"PLTE":
                entries = len(payload) // 3
                if not payload or len(payload) % 3 or entries > 256:
                    raise _PngReadFailure("INVALID", "png_palette_invalid", f"PLTE holds {len(payload)} bytes")
                if color_type_value in (0, 4):
                    raise _PngReadFailure("INVALID", "png_palette_forbidden", "grayscale PNG must not carry PLTE")
                if color_type_value == 3 and entries > (1 << int(bit_depth_value or 0)):
                    raise _PngReadFailure("INVALID", "png_palette_invalid", f"{entries} PLTE entries exceed the {bit_depth_value}-bit index range")
                palette_entries = entries
                palette_seen = True
            elif kind == b"IDAT":
                idat_bytes += length
            elif kind == b"IEND":
                saw_iend = True

        if not saw_idat:
            raise _PngReadFailure("INVALID", "png_idat_missing", "PNG has no image-data chunk")
        if read_exact(1) != b"\n":
            raise _PngReadFailure("INVALID", "png_terminator_invalid", "PNG IEND must be followed by one LF")
        if buffered.buffer:
            buffered_bytes = len(buffered.buffer)
            trailing = bytes(buffered.buffer[: max(0, max_bytes - observed)])
            del buffered.buffer[: len(trailing)]
            if trailing:
                output.write(trailing)
                digest.update(trailing)
                observed += len(trailing)
            raise _PngReadFailure("INVALID", "png_trailing_bytes", f"unexpected {buffered_bytes} buffered bytes follow the PNG terminator")
    except _PngReadFailure as exc:
        return result(exc.status, error_code=exc.code, error=str(exc))

    return result("COMPLETE", terminator="IEND+LF")


def _hash_stream(stream: BinaryIO) -> str:
    position = stream.tell()
    stream.seek(0)
    digest = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
    stream.seek(position)
    return digest.hexdigest()


def _write_json(stream: BinaryIO, value: dict[str, Any]) -> None:
    stream.write(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))
    stream.write(b"\n")
    stream.flush()


def screenshot_failure_record(
    *,
    raw_path: Path,
    metadata_path: Path,
    error_code: str,
    error: str,
    raw_bytes: int = 0,
    sha256: str | None = None,
    raw_file_created: bool = False,
    max_bytes: int | None = None,
    max_seconds: float | None = None,
    session_timeout_s: float | None = None,
    requested_timeout_s: float | None = None,
    duration_s: float = 0.0,
) -> dict[str, Any]:
    """Build the record for a screenshot that produced no validated container."""

    return {
        "schema_version": SCHEMA_VERSION,
        "command": PNG_QUERY,
        "framing": FRAMING,
        "raw_path": str(raw_path),
        "metadata_path": str(metadata_path),
        "max_bytes": max_bytes,
        "max_seconds": max_seconds,
        "session_timeout_s": session_timeout_s,
        "requested_timeout_s": requested_timeout_s,
        "status": "INCOMPLETE",
        "container_valid": False,
        "image_decode_status": IMAGE_DECODE_STATUS,
        "image_decode_reasons": list(IMAGE_DECODE_REASONS),
        "raw_file_created": raw_file_created,
        "error_code": error_code,
        "error": error,
        "raw_bytes": raw_bytes,
        "sha256": sha256,
        "width": None,
        "height": None,
        "bit_depth": None,
        "color_type": None,
        "palette_entries": None,
        "idat_bytes": 0,
        "chunks": 0,
        "crc_checked": 0,
        "duration_s": round(duration_s, 6),
        "terminator": None,
        "frame_association": frame_association(),
    }


def capture_png_on_session(
    scope: ScopeSession,
    raw_path: Path,
    metadata_path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    started_at: float | None = None,
    requested_timeout_s: float | None = None,
) -> dict[str, Any]:
    """Capture one PNG on an already connected session without reconnecting.

    The raw response is written for every outcome, including a partial or
    invalid stream. Neither artifact path may already exist. The socket timeout
    in force before the call is restored afterwards; a failure to restore it is
    recorded beside the original outcome instead of replacing it. ``status``
    and ``container_valid`` describe PNG container structure only; no decoder
    runs, so ``image_decode_status`` always stays ``UNVERIFIED``.
    """

    validate_bounds(max_bytes, max_seconds)
    raw_path = raw_path.expanduser().resolve()
    metadata_path = metadata_path.expanduser().resolve()
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    attempt_started = time.monotonic() if started_at is None else started_at
    buffered = scope._require_open()
    sock = scope.sock
    if sock is None:
        raise ScopeProtocolError("scope session is not connected")
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "command": PNG_QUERY,
        "framing": FRAMING,
        "raw_path": str(raw_path),
        "metadata_path": str(metadata_path),
        "max_bytes": max_bytes,
        "max_seconds": max_seconds,
        "session_timeout_s": round(float(scope.timeout_s), 6),
        "requested_timeout_s": requested_timeout_s,
    }

    raw_file = raw_path.open("x+b")
    try:
        metadata_file = metadata_path.open("xb")
    except BaseException:
        raw_file.close()
        raw_path.unlink(missing_ok=True)
        raise
    original_timeout = sock.gettimeout()
    restore_error: str | None = None
    try:
        try:
            remaining = max_seconds - (time.monotonic() - attempt_started)
            if remaining <= 0:
                raise TimeoutError(f"screenshot attempt exceeded {max_seconds} seconds before the query")
            sock.settimeout(min(float(scope.timeout_s), remaining))
            # No bypass flag: ``:PRINt? PNG`` is allowlisted by ScopeSession
            # itself while stopped, and every other write stays forbidden.
            scope.write(PNG_QUERY)
            result = _read_png_stream(
                buffered,
                raw_file,
                max_bytes=max_bytes,
                max_seconds=max_seconds,
                started_at=attempt_started,
            )
        except Exception as exc:
            result = {
                "status": "INCOMPLETE",
                "container_valid": False,
                "image_decode_status": IMAGE_DECODE_STATUS,
                "image_decode_reasons": list(IMAGE_DECODE_REASONS),
                "error_code": "command_or_transport_error",
                "error": f"{type(exc).__name__}: {exc}",
                "raw_bytes": 0,
                "sha256": None,
                "width": None,
                "height": None,
                "bit_depth": None,
                "color_type": None,
                "palette_entries": None,
                "idat_bytes": 0,
                "chunks": 0,
                "crc_checked": 0,
                "duration_s": round(time.monotonic() - attempt_started, 6),
                "terminator": None,
            }
        finally:
            # A restore failure must not replace the attempt result or block
            # the metadata JSON that records the original failure.
            try:
                sock.settimeout(original_timeout)
            except (OSError, ValueError) as exc:
                restore_error = f"{type(exc).__name__}: {exc}"
        raw_file.flush()
        result["raw_bytes"] = raw_file.tell()
        result["sha256"] = _hash_stream(raw_file)
        result["raw_file_created"] = True
        if restore_error is not None:
            result["timeout_restore_error"] = restore_error
        if scope.events and scope.events[-1].command == PNG_QUERY:
            event = scope.events[-1]
            event.response_kind = "png_raw"
            event.response_length = result["raw_bytes"]
            event.response_sha256 = result["sha256"]
        record = {
            **base,
            **result,
            "frame_association": frame_association(),
            "command_log": [event.__dict__.copy() for event in scope.events],
        }
        _write_json(metadata_file, record)
        return record
    finally:
        raw_file.close()
        metadata_file.close()


def write_connection_failure_record(
    raw_path: Path,
    metadata_path: Path,
    error: BaseException,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    started_at: float | None = None,
    session_timeout_s: float | None = None,
    requested_timeout_s: float | None = None,
) -> dict[str, Any]:
    """Record a failed connect as JSON without creating or replacing a PNG."""

    validate_bounds(max_bytes, max_seconds)
    raw_path = raw_path.expanduser().resolve()
    metadata_path = metadata_path.expanduser().resolve()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    record = screenshot_failure_record(
        raw_path=raw_path,
        metadata_path=metadata_path,
        error_code="connection_failed",
        error=f"{type(error).__name__}: {error}",
        max_bytes=max_bytes,
        max_seconds=max_seconds,
        session_timeout_s=session_timeout_s,
        requested_timeout_s=requested_timeout_s,
        duration_s=0.0 if started_at is None else time.monotonic() - started_at,
    )
    with metadata_path.open("xb") as metadata_file:
        _write_json(metadata_file, record)
    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.10.2")
    parser.add_argument("--port", type=int, default=5025)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--max-seconds", type=float, default=DEFAULT_MAX_SECONDS)
    parser.add_argument("--out", type=Path, required=True, help="PNG output path; a .json metadata sidecar is created")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.port == 5024:
        raise SystemExit("Refusing legacy shell port 5024; use SCPI TCP port 5025")
    try:
        validate_bounds(args.max_bytes, args.max_seconds, timeout_s=args.timeout)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    raw_path = args.out.expanduser().resolve()
    metadata_path = raw_path.with_suffix(raw_path.suffix + ".json")
    # The whole attempt, including connect(), must fit inside --max-seconds, so
    # one socket operation may not be allowed to outlast that budget. The
    # caller's --timeout is kept as requested_timeout_s in every record.
    requested_timeout = args.timeout
    session_timeout = min(args.timeout, args.max_seconds)
    scope = ScopeSession(args.host, args.port, session_timeout)
    attempt_started = time.monotonic()
    try:
        scope.connect()
    except (OSError, ScopeProtocolError) as exc:
        try:
            record = write_connection_failure_record(
                raw_path,
                metadata_path,
                exc,
                max_bytes=args.max_bytes,
                max_seconds=args.max_seconds,
                started_at=attempt_started,
                session_timeout_s=session_timeout,
                requested_timeout_s=requested_timeout,
            )
        except FileExistsError as collision:
            print(f"screenshot failed without overwriting artifacts: {collision.filename}", file=sys.stderr)
            return 2
        print(json.dumps(record, sort_keys=True, separators=(",", ":")))
        return 2
    try:
        record = capture_png_on_session(
            scope,
            raw_path,
            metadata_path,
            max_bytes=args.max_bytes,
            max_seconds=args.max_seconds,
            started_at=attempt_started,
            requested_timeout_s=requested_timeout,
        )
    except FileExistsError as collision:
        print(f"screenshot failed without overwriting artifacts: {collision.filename}", file=sys.stderr)
        return 2
    finally:
        scope.close()
    print(json.dumps(record, sort_keys=True, separators=(",", ":")))
    return 0 if record["container_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
