#!/usr/bin/env python3
"""Byte-preserving SDS waveform transport and offline validation helpers."""

from __future__ import annotations

import hashlib
import json
import re
import select
import socket
import struct
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional


class ScopeProtocolError(RuntimeError):
    """Raised when a response or capture violates the protocol contract."""


@dataclass
class IEEEBlock:
    prefix: bytes
    header: bytes
    payload: bytes
    trailing: bytes = b""

    @property
    def payload_length(self) -> int:
        return len(self.payload)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()

    @property
    def raw(self) -> bytes:
        return self.prefix + self.header + self.payload


def parse_ieee_block(raw: bytes, *, require_complete: bool = True) -> IEEEBlock:
    """Parse the first IEEE 488.2 block in arbitrary transport bytes.

    The returned prefix is retained verbatim. Bytes after the declared payload
    are returned as ``trailing`` and must not be counted as waveform samples.
    """

    marker = raw.find(b"#")
    if marker < 0:
        raise ScopeProtocolError("IEEE block marker '#' was not found")
    if len(raw) < marker + 2:
        raise ScopeProtocolError("truncated IEEE block length-of-length")
    digits_byte = raw[marker + 1 : marker + 2]
    if digits_byte < b"0" or digits_byte > b"9":
        raise ScopeProtocolError(f"invalid IEEE length-of-length: {digits_byte!r}")
    digits = digits_byte[0] - ord("0")
    if digits == 0:
        raise ScopeProtocolError("indefinite IEEE blocks are not accepted")
    length_start = marker + 2
    length_end = length_start + digits
    if len(raw) < length_end:
        raise ScopeProtocolError("truncated IEEE payload length")
    length_bytes = raw[length_start:length_end]
    if not length_bytes.isdigit():
        raise ScopeProtocolError(f"invalid IEEE payload length: {length_bytes!r}")
    payload_length = int(length_bytes)
    payload_start = length_end
    payload_end = payload_start + payload_length
    if len(raw) < payload_end:
        raise ScopeProtocolError(
            f"truncated payload: declared {payload_length}, received {len(raw) - payload_start}"
        )
    if require_complete and payload_length != len(raw[payload_start:payload_end]):
        raise ScopeProtocolError("payload length mismatch")
    return IEEEBlock(
        prefix=raw[:marker],
        header=raw[marker:payload_start],
        payload=raw[payload_start:payload_end],
        trailing=raw[payload_end:],
    )


class BufferedSocket:
    """A socket wrapper that never loses bytes between ASCII and binary reads."""

    def __init__(self, sock: socket.socket, timeout_s: float = 5.0):
        self.sock = sock
        self.timeout_s = timeout_s
        self.buffer = bytearray()

    def _recv(self, size: int = 65536) -> bytes:
        self.sock.settimeout(self.timeout_s)
        try:
            data = self.sock.recv(size)
        except socket.timeout as exc:
            raise ScopeProtocolError("socket read timed out") from exc
        if not data:
            raise ScopeProtocolError("scope closed the TCP connection")
        return data

    def _fill(self, minimum: int = 1) -> None:
        while len(self.buffer) < minimum:
            self.buffer.extend(self._recv())

    def _take(self, count: int) -> bytes:
        self._fill(count)
        data = bytes(self.buffer[:count])
        del self.buffer[:count]
        return data

    def read_ieee_block(self) -> IEEEBlock:
        """Find and read one block without interpreting prefix or payload bytes."""

        while True:
            marker = self.buffer.find(b"#")
            if marker >= 0:
                prefix = bytes(self.buffer[:marker])
                del self.buffer[: marker + 1]
                break
            self.buffer.extend(self._recv())
        digits_byte = self._take(1)
        if digits_byte < b"0" or digits_byte > b"9":
            raise ScopeProtocolError(f"invalid IEEE length-of-length: {digits_byte!r}")
        digits = digits_byte[0] - ord("0")
        if digits == 0:
            raise ScopeProtocolError("indefinite IEEE blocks are not accepted")
        length_bytes = self._take(digits)
        if not length_bytes.isdigit():
            raise ScopeProtocolError(f"invalid IEEE payload length: {length_bytes!r}")
        payload_length = int(length_bytes)
        payload = self._take(payload_length)
        return IEEEBlock(prefix=prefix, header=b"#" + digits_byte + length_bytes, payload=payload)

    def read_line(self) -> bytes:
        while True:
            newline = self.buffer.find(b"\n")
            if newline >= 0:
                line = bytes(self.buffer[: newline + 1])
                del self.buffer[: newline + 1]
                return line
            self.buffer.extend(self._recv())


@dataclass
class CommandEvent:
    command: str
    sent_at: float
    response_kind: Optional[str] = None
    response_length: Optional[int] = None
    response_sha256: Optional[str] = None


class ScopeSession:
    """One explicit TCP session. It deliberately has no reconnect method."""

    FORBIDDEN_AFTER_STOP = (
        "ARM",
        "STOP",
        "RUN",
        "TRMD",
        "WFSU",
        "TRSE",
        "TRSL",
        "TRLV",
        "TDIV",
        "VDIV",
        "OFST",
    )

    def __init__(self, host: str, port: int = 5025, timeout_s: float = 5.0):
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self.sock: Optional[socket.socket] = None
        self.io: Optional[BufferedSocket] = None
        self.events: list[CommandEvent] = []
        self.stopped = False
        self.ready_seen = False
        self.expected_channels: set[str] = {"C1", "C2", "C3", "C4"}
        self.dat2_channels: set[str] = set()
        self.capture_mode = "immutable_capture"

    def connect(self) -> None:
        if self.sock is not None:
            raise ScopeProtocolError("reconnect is forbidden within one capture session")
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout_s)
        self.io = BufferedSocket(self.sock, self.timeout_s)
        self._drain_startup_noise()

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
        self.sock = None
        self.io = None

    def _require_open(self) -> BufferedSocket:
        if self.io is None or self.sock is None:
            raise ScopeProtocolError("scope session is not connected")
        return self.io

    def _drain_startup_noise(self) -> None:
        """Record no startup bytes as a query response; 5024 may send a banner."""

        if self.sock is None or self.io is None:
            return
        self.sock.setblocking(False)
        try:
            while True:
                readable, _, _ = select.select([self.sock], [], [], 0.05)
                if not readable:
                    break
                try:
                    self.io.buffer.extend(self.sock.recv(65536))
                except BlockingIOError:
                    break
        finally:
            self.sock.setblocking(True)
            self.sock.settimeout(self.timeout_s)

    def _check_allowed(self, command: str, *, explicit_release: bool = False) -> None:
        normalized = command.strip().upper()
        if self.stopped and not explicit_release:
            query_only = normalized.endswith("?") and ";" not in normalized
            waveform_transfer_write = self.capture_mode == "configured_capture" and normalized.startswith(("WAV:SOUR ", "WAV:WIDT ", "WAV:INT ", "WAV:STAR ", "WAV:POIN ")) and ";" not in normalized
            legacy_waveform_query = ":WF? DAT2" in normalized or ":WF? DESC" in normalized
            if not (query_only or waveform_transfer_write or legacy_waveform_query):
                raise ScopeProtocolError(f"command forbidden after Stop: {command}")
        if normalized == "ARM" or normalized.startswith("ARM "):
            raise ScopeProtocolError("ARM is forbidden on SDS824X HD firmware")

    def write(self, command: str, *, allow_after_stop: bool = False, explicit_release: bool = False) -> None:
        io = self._require_open()
        self._check_allowed(command, explicit_release=explicit_release)
        wire = command.rstrip("\r\n").encode("ascii") + b"\n"
        self.sock.sendall(wire)  # type: ignore[union-attr]
        self.events.append(CommandEvent(command=command.rstrip("\r\n"), sent_at=time.time()))

    @staticmethod
    def _clean_ascii(line: bytes) -> str:
        text = line.replace(b"\x00", b"").strip()
        return text.decode("ascii", errors="replace")

    def query_ascii(self, command: str, *, allow_after_stop: bool = False) -> str:
        self.write(command, allow_after_stop=allow_after_stop)
        io = self._require_open()
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            response = self._clean_ascii(io.read_line())
            if not response or response == ">>" or response.startswith("Welcome to the SCPI instrument"):
                continue
            event = self.events[-1]
            event.response_kind = "ascii"
            event.response_length = len(response.encode("ascii", errors="replace"))
            return response
        raise ScopeProtocolError(f"no usable ASCII response for {command}")

    def query_block(self, command: str, *, allow_after_stop: bool = False) -> IEEEBlock:
        normalized = command.strip().upper()
        if ":WF? DESC" in normalized:
            missing = self.expected_channels - self.dat2_channels
            if missing:
                raise ScopeProtocolError(f"DESC is deferred until DAT2 is read for every selected channel; missing {sorted(missing)}")
        self.write(command, allow_after_stop=allow_after_stop)
        block = self._require_open().read_ieee_block()
        if ":WF? DAT2" in normalized:
            self.dat2_channels.add(normalized.split(":", 1)[0])
        event = self.events[-1]
        event.response_kind = "ieee4882"
        event.response_length = block.payload_length
        event.response_sha256 = block.sha256
        return block

    def mark_state(self, state: str) -> None:
        normalized = state.strip().upper()
        if normalized == "READY":
            self.ready_seen = True
        elif normalized == "STOP":
            if not self.ready_seen:
                raise ScopeProtocolError("Stop observed before Ready")
            self.stopped = True

    def set_expected_channels(self, channels: Iterable[str]) -> None:
        selected = {channel.upper() for channel in channels}
        if not selected or not selected.issubset({"C1", "C2", "C3", "C4"}):
            raise ScopeProtocolError("expected channels must be a non-empty subset of C1-C4")
        self.expected_channels = selected


def scope_connect(host: str = "192.168.10.2", port: int = 5025, timeout_s: float = 5.0) -> ScopeSession:
    """Open one session; callers must keep and explicitly close the result."""

    if port == 5024:
        raise ScopeProtocolError("port 5024 is the legacy shell channel; use SCPI port 5025")
    scope = ScopeSession(host, port, timeout_s)
    scope.connect()
    return scope


def scope_identify(scope: ScopeSession) -> str:
    return scope.query_ascii("*IDN?")


def scope_snapshot_configuration(scope: ScopeSession, channels: Iterable[str] = ("C1", "C2", "C3", "C4")) -> dict[str, Any]:
    """Read a snapshot without changing acquisition state."""

    snapshot: dict[str, Any] = {"acquisition": {}, "channels": {}}
    for command, key in (("TRMD?", "trigger_mode"), ("SAST?", "acquisition_state"), ("ACQ:POIN?", "scope_record_points"), ("SARA?", "sample_rate"), ("TDIV?", "timebase"), ("TRDL?", "trigger_delay"), ("WFSU?", "waveform_setup")):
        snapshot["acquisition"][key] = scope.query_ascii(command, allow_after_stop=True)
    for channel in channels:
        values: dict[str, str] = {}
        for suffix, key in (("VDIV?", "vdiv"), ("OFST?", "offset")):
            values[key] = scope.query_ascii(f"{channel}:{suffix}", allow_after_stop=True)
        snapshot["channels"][channel] = values
    return snapshot


def scope_prepare_capture(scope: ScopeSession) -> None:
    """Apply the handover's setup before a new acquisition."""

    commands = (
        "CHDR OFF",
        "C1:VDIV 2",
        "C2:VDIV 2",
        "C3:VDIV 5",
        "C4:VDIV 2",
        "C1:OFST 0",
        "C2:OFST 0",
        "C3:OFST 0",
        "C4:OFST 0",
        "TRSE EDGE,SR,C1,HT,OFF",
        "C1:TRSL POS",
        "C1:TRLV 2.5",
    )
    for command in commands:
        scope.write(command)


def scope_set_capture_mode(scope: ScopeSession, mode: str) -> None:
    if mode not in ("immutable_capture", "configured_capture"):
        raise ScopeProtocolError(f"unsupported capture mode: {mode}")
    scope.capture_mode = mode


def scope_arm_single(scope: ScopeSession) -> None:
    """The named API is retained for callers, but it never sends ARM."""

    scope.write("TRMD SINGLE")


def scope_wait_ready(scope: ScopeSession, timeout_s: float = 30.0, poll_s: float = 0.2) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = scope.query_ascii("SAST?").strip()
        scope.mark_state(state)
        if state.upper() == "READY":
            return
        time.sleep(poll_s)
    raise ScopeProtocolError("timed out waiting for Ready")


def scope_wait_stop(scope: ScopeSession, timeout_s: float = 360.0, poll_s: float = 0.2) -> None:
    if not scope.ready_seen:
        raise ScopeProtocolError("scope_wait_stop requires a previously observed Ready")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = scope.query_ascii("SAST?").strip()
        scope.mark_state(state)
        if state.upper() == "STOP":
            return
        time.sleep(poll_s)
    raise ScopeProtocolError("timed out waiting for Stop")


def scope_read_segment(scope: ScopeSession, channel: str, start: int, count: int) -> IEEEBlock:
    """Read one modern WAV segment after the caller explicitly stopped capture."""

    if start < 0 or count <= 0:
        raise ScopeProtocolError("segment start must be non-negative and count must be positive")
    if scope.capture_mode != "configured_capture":
        raise ScopeProtocolError("modern WAV segment reads require explicit configured_capture mode")
    scope.write(f"WAV:SOUR {channel}", allow_after_stop=True)
    scope.write("WAV:WIDT BYTE", allow_after_stop=True)
    scope.write("WAV:INT 1", allow_after_stop=True)
    scope.write(f"WAV:STAR {start}", allow_after_stop=True)
    scope.write(f"WAV:POIN {count}", allow_after_stop=True)
    selected_start = int(float(scope.query_ascii("WAV:STAR?", allow_after_stop=True)))
    selected_count = int(float(scope.query_ascii("WAV:POIN?", allow_after_stop=True)))
    if (selected_start, selected_count) != (start, count):
        raise ScopeProtocolError(f"scope selected {selected_start},{selected_count}; expected {start},{count}")
    block = scope.query_block("WAV:DATA?", allow_after_stop=True)
    if len(block.payload) != count:
        raise ScopeProtocolError(f"segment {start} declared {count}, received {len(block.payload)} bytes")
    return block


def scope_read_descriptor(scope: ScopeSession, channel: str) -> tuple[dict[str, Any], IEEEBlock]:
    block = scope.query_block(f"{channel}:WF? DESC", allow_after_stop=True)
    return parse_wavedesc(block.payload), block


def scope_read_immutable_frame(scope: ScopeSession, channels: Iterable[str] = ("C1", "C2", "C3", "C4")) -> dict[str, Any]:
    """Read legacy DAT2 payloads only; descriptors are deliberately not queried."""

    selected_channels = tuple(channel.upper() for channel in channels)
    if not scope.stopped:
        raise ScopeProtocolError("scope_read_immutable_frame requires a stopped frame")
    scope.set_expected_channels(selected_channels)
    result: dict[str, Any] = {
        "mode": "immutable_capture",
        "channels": {},
        "state": {"ready_seen": scope.ready_seen, "stopped": scope.stopped},
    }
    for channel in selected_channels:
        block = scope.query_block(f"{channel}:WF? DAT2", allow_after_stop=True)
        result["channels"][channel] = {
            "payload": block.payload,
            "prefix": block.prefix,
            "header": block.header,
            "payload_length": len(block.payload),
            "sha256": block.sha256,
            "integrity_report": {
                "status": "UNVERIFIED_DESCRIPTOR_PENDING",
                "downloaded_points": len(block.payload),
                "downloaded_duration_s": None,
            },
        }
    result["command_log"] = [event.__dict__ for event in scope.events]
    return result


def scope_validate_frame(**kwargs: Any) -> dict[str, Any]:
    return validate_frame(**kwargs)


def scope_assume_existing_stop(scope: ScopeSession) -> None:
    """Accept a currently stopped frame without claiming a new trigger."""

    state = scope.query_ascii("SAST?").strip()
    if state.upper() != "STOP":
        raise ScopeProtocolError(f"expected an existing stopped frame, got {state!r}")
    scope.stopped = True


def waveform_time_origin(descriptor: dict[str, Any]) -> float:
    return float(descriptor["horizontal_offset"] - descriptor["timebase_s"] * 5)


def decode_analog_byte(payload: bytes, descriptor: dict[str, Any], *, first_point: int = 0) -> list[tuple[int, float, float]]:
    if descriptor.get("data_width_bytes") != 1:
        raise ScopeProtocolError("byte decoder requires an 8-bit descriptor")
    codes_per_div = float(descriptor["code_per_div"])
    if codes_per_div == 0:
        raise ScopeProtocolError("invalid zero code_per_div in descriptor")
    interval = float(descriptor["sample_interval"])
    origin = waveform_time_origin(descriptor)
    vdiv = float(descriptor["vdiv_with_probe"])
    offset = float(descriptor["offset_with_probe"])
    return [
        (first_point + index, origin + (first_point + index) * interval, (value - 256 if value > 127 else value) * vdiv / codes_per_div - offset)
        for index, value in enumerate(payload)
    ]


def scope_restore_run_mode(scope: ScopeSession) -> None:
    """Explicit opt-in restoration; never call from capture/read helpers."""

    scope.write("TRMD AUTO", allow_after_stop=True, explicit_release=True)
    scope.stopped = False
    scope.ready_seen = False


def scope_release_capture(scope: ScopeSession) -> None:
    """Explicitly release software protection before a caller-controlled write."""

    scope.stopped = False
    scope.ready_seen = False


def scope_disconnect(scope: ScopeSession) -> None:
    scope.close()


def _unpack(payload: bytes, offset: int, fmt: str) -> Any:
    size = struct.calcsize(fmt)
    if len(payload) < offset + size:
        raise ScopeProtocolError(f"WAVEDESC is shorter than field at offset {offset}")
    return struct.unpack_from(fmt, payload, offset)[0]


TIMEBASE_ENUM = [
    200e-12,
    500e-12,
    1e-9,
    2e-9,
    5e-9,
    10e-9,
    20e-9,
    50e-9,
    100e-9,
    200e-9,
    500e-9,
    1e-6,
    2e-6,
    5e-6,
    10e-6,
    20e-6,
    50e-6,
    100e-6,
    200e-6,
    500e-6,
    1e-3,
    2e-3,
    5e-3,
    10e-3,
    20e-3,
    50e-3,
    100e-3,
    200e-3,
    500e-3,
    1,
    2,
    5,
    10,
    20,
    50,
    100,
    200,
    500,
    1000,
]


def parse_wavedesc(payload: bytes) -> dict[str, Any]:
    """Decode the common SDS800X HD WAVEDESC offsets from raw payload bytes."""

    ascii_text = payload.decode("ascii", errors="ignore")
    ascii_matches = re.findall(r"(?im)(array_count|data_length|horiz_interval|horiz_offset|trigger_position)\s*[:=]\s*([-+0-9,\.eE]+)", ascii_text)
    if ascii_matches:
        values = {key.lower(): float(value.replace(",", "")) for key, value in ascii_matches}
        result = {
            "description": "ASCII-DESC",
            "array_count": int(values["array_count"]) if "array_count" in values else None,
            "data_length": int(values["data_length"]) if "data_length" in values else None,
            "horiz_interval": values.get("horiz_interval"),
            "horiz_offset": values.get("horiz_offset"),
            "trigger_position": values.get("trigger_position"),
            "raw_sha256": hashlib.sha256(payload).hexdigest(),
            "raw_length": len(payload),
        }
        result["wave_array_count"] = result["array_count"]
        result["wave_array_1_bytes"] = result["data_length"]
        result["sample_interval"] = result["horiz_interval"]
        result["horizontal_offset"] = result["horiz_offset"]
        return result

    description = payload[0:16].split(b"\0", 1)[0].decode("ascii", errors="replace")
    timebase_index = _unpack(payload, 324, "<h")
    result: dict[str, Any] = {
        "description": description,
        "comm_type": _unpack(payload, 32, "<h"),
        "wave_array_1_bytes": _unpack(payload, 60, "<i"),
        "wave_array_count": _unpack(payload, 116, "<i"),
        "start": _unpack(payload, 132, "<i"),
        "interval": _unpack(payload, 136, "<i"),
        "vdiv": _unpack(payload, 156, "<f"),
        "offset": _unpack(payload, 160, "<f"),
        "code_per_div": _unpack(payload, 164, "<f"),
        "adc_bit": _unpack(payload, 172, "<h"),
        "sample_interval": _unpack(payload, 176, "<f"),
        "horizontal_offset": _unpack(payload, 180, "<d"),
        "timebase_index": timebase_index,
        "probe": _unpack(payload, 328, "<f"),
        "source_index": _unpack(payload, 344, "<h"),
        "raw_sha256": hashlib.sha256(payload).hexdigest(),
        "raw_length": len(payload),
    }
    if not 0 <= timebase_index < len(TIMEBASE_ENUM):
        raise ScopeProtocolError(f"unknown SDS timebase enum: {timebase_index}")
    result["timebase_s"] = TIMEBASE_ENUM[timebase_index]
    result["array_count"] = result["wave_array_count"]
    result["data_length"] = result["wave_array_1_bytes"]
    result["horiz_interval"] = result["sample_interval"]
    result["horiz_offset"] = result["horizontal_offset"]
    result["trigger_position"] = None
    result["vdiv_with_probe"] = result["vdiv"] * result["probe"]
    result["offset_with_probe"] = result["offset"] * result["probe"]
    if result["comm_type"] not in (0, 1):
        raise ScopeProtocolError(f"unknown WAVEDESC COMM_TYPE: {result['comm_type']}")
    result["data_width_bytes"] = 1 if result["comm_type"] == 0 else 2
    return result


@dataclass
class Segment:
    start: int
    requested_points: int
    payload_length: int
    bytes_per_point: int
    sample_interval_s: float
    time_origin_s: float
    sha256: str
    valid: bool = True
    error: Optional[str] = None

    @property
    def actual_points(self) -> int:
        return self.payload_length // self.bytes_per_point if self.bytes_per_point else 0

    @property
    def end_exclusive(self) -> int:
        return self.start + self.actual_points

    @property
    def time_start_s(self) -> float:
        return self.time_origin_s + self.start * self.sample_interval_s

    @property
    def time_end_s(self) -> float:
        return self.time_start_s + self.actual_points * self.sample_interval_s


def validate_segments(
    segments: Iterable[Segment],
    *,
    expected_points: Optional[int],
    sample_interval_s: float,
    time_origin_s: float,
) -> dict[str, Any]:
    ordered = sorted(segments, key=lambda item: item.start)
    reasons: list[str] = []
    cursor = 0
    total = 0
    for segment in ordered:
        segment.sample_interval_s = sample_interval_s
        segment.time_origin_s = time_origin_s
        if segment.bytes_per_point <= 0:
            segment.valid = False
            segment.error = "bytes_per_point must be positive"
            reasons.append(f"segment {segment.start}: {segment.error}")
            continue
        if segment.payload_length == 0:
            segment.valid = False
            segment.error = "empty payload"
        if segment.payload_length % segment.bytes_per_point:
            segment.valid = False
            segment.error = "payload length is not divisible by sample width"
        if segment.requested_points != segment.actual_points:
            segment.valid = False
            segment.error = f"requested {segment.requested_points}, received {segment.actual_points} points"
        if segment.start != cursor:
            segment.valid = False
            segment.error = f"range starts at {segment.start}, expected {cursor}"
        if not segment.valid:
            reasons.append(f"segment {segment.start}: {segment.error}")
        cursor = max(cursor, segment.end_exclusive)
        total += segment.actual_points
    if expected_points is not None and total != expected_points:
        reasons.append(f"downloaded {total} points, descriptor expects {expected_points}")
    if any(not segment.valid for segment in ordered):
        reasons.append("one or more segments are invalid")
    valid = not reasons and (expected_points is None or cursor == expected_points)
    return {
        "status": "COMPLETE" if valid else "INVALID",
        "expected_points": expected_points,
        "downloaded_points": total,
        "sample_interval_s": sample_interval_s,
        "downloaded_duration_s": total * sample_interval_s,
        "time_origin_s": time_origin_s,
        "time_end_s": time_origin_s + total * sample_interval_s,
        "segments": [asdict(segment) | {"actual_points": segment.actual_points, "end_exclusive": segment.end_exclusive, "time_start_s": segment.time_start_s, "time_end_s": segment.time_end_s} for segment in ordered],
        "reasons": reasons,
    }


def validate_frame(
    *,
    scope_points: Optional[int],
    scope_duration_s: Optional[float],
    wavedesc_points: Optional[int],
    sample_interval_s: Optional[float],
    downloaded_points: int,
    trigger_relative_s: Optional[float] = None,
    downloaded_duration_s: Optional[float] = None,
    segment_report: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    expected = wavedesc_points if wavedesc_points is not None else scope_points
    if scope_points is not None and wavedesc_points is not None and scope_points != wavedesc_points:
        reasons.append(f"screen record {scope_points} differs from WAVEDESC {wavedesc_points}")
    if expected is not None and downloaded_points != expected:
        reasons.append(f"downloaded {downloaded_points} points, expected {expected}")
    if scope_duration_s is not None and sample_interval_s is not None and expected is not None:
        expected_duration = expected * sample_interval_s
        if abs(scope_duration_s - expected_duration) > max(1e-12, abs(expected_duration) * 1e-6):
            reasons.append(f"scope duration {scope_duration_s} s differs from WAVEDESC duration {expected_duration} s")
    if segment_report and segment_report.get("status") != "COMPLETE":
        reasons.extend(segment_report.get("reasons", []))
    if downloaded_duration_s is None and sample_interval_s is not None:
        downloaded_duration_s = downloaded_points * sample_interval_s
    status = "COMPLETE" if not reasons else "INCOMPLETE"
    if segment_report and segment_report.get("status") != "COMPLETE":
        status = "INVALID"
    return {
        "status": status,
        "scope_record": {"points": scope_points, "duration_s": scope_duration_s},
        "wavedesc_record": {"points": wavedesc_points, "sample_interval_s": sample_interval_s},
        "downloaded": {"points": downloaded_points, "duration_s": downloaded_duration_s},
        "expected_duration_s": (expected * sample_interval_s) if expected is not None and sample_interval_s is not None else None,
        "trigger_relative_s": trigger_relative_s,
        "reasons": reasons,
        "segments": segment_report,
    }


def signed_8bit(payload: bytes) -> list[int]:
    return [value - 256 if value > 127 else value for value in payload]


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
