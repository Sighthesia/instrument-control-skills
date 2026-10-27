#!/usr/bin/env python3
"""Byte-preserving SDS waveform transport and offline validation helpers."""

from __future__ import annotations

import hashlib
import json
import math
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


ACQUISITION_STATE_ALIASES = {
    "ARM": "ARM",
    "ARMED": "ARM",
    "READY": "READY",
    "AUTO": "AUTO",
    "TRIGD": "TRIGD",
    "TRIG'D": "TRIGD",
    "TRIGGED": "TRIGD",
    "TRIGGERED": "TRIGD",
    "STOP": "STOP",
    "STOPPED": "STOP",
    "ROLL": "ROLL",
    "ROLLING": "ROLL",
    "WAIT": "WAIT",
    "RUN": "RUN",
}


def normalize_acquisition_state(response: Any) -> str:
    """Reduce a decorated ``SAST?`` reply to one canonical state token.

    Firmware may answer with a bare state (``Stop``) or repeat the query as a
    prefix (``SAST Stop``, ``:TRIGger:STATus? Stop``) in any case and with
    surrounding whitespace or quoting. Only the trailing token is a state; the
    raw reply stays available through :class:`AcquisitionState` so the evidence
    is never rewritten by this normalization.
    """

    text = str(response).strip()
    if not text:
        raise ScopeProtocolError("empty acquisition-state response")
    tokens = [token for token in re.split(r"[\s,;]+", text) if token]
    token = tokens[-1].strip("\"'<>[]()").strip().upper()
    canonical = ACQUISITION_STATE_ALIASES.get(token)
    if canonical is None:
        raise ScopeProtocolError(f"unrecognized acquisition state: {text!r}")
    return canonical


@dataclass(frozen=True)
class AcquisitionState:
    """One ``SAST?`` reply: raw bytes-as-text plus its canonical state."""

    raw: str
    normalized: str


def _optional_int(value: Any) -> Optional[int]:
    """Parse a decorated integer readback, returning ``None`` when absent."""

    match = re.search(r"[-+]?\d+", str(value))
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


@dataclass
class IEEEBlock:
    prefix: bytes
    header: bytes
    payload: bytes
    trailing: bytes = b""
    bytes_per_point: Optional[int] = None
    requested_points: Optional[int] = None
    reported_points: Optional[int] = None
    slices: Optional[list[dict[str, Any]]] = None

    @property
    def payload_length(self) -> int:
        return len(self.payload)

    @property
    def actual_points(self) -> Optional[int]:
        if not self.bytes_per_point:
            return None
        return len(self.payload) // self.bytes_per_point

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
        self.roll_seen = False
        self.expected_channels: set[str] = {"C1", "C2", "C3", "C4"}
        self.dat2_channels: set[str] = set()
        self.capture_mode = "immutable_capture"
        self.state_log: list[AcquisitionState] = []

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
            waveform_transfer_write = self.capture_mode == "configured_capture" and normalized.startswith(("WAV:SOUR ", "WAV:WIDT ", "WAV:BYT ", "WAV:INT ", "WAV:STAR ", "WAV:POIN ")) and ";" not in normalized
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

    def mark_state(self, state: str) -> AcquisitionState:
        """Record one observed acquisition state without trusting its decoration."""

        normalized = normalize_acquisition_state(state)
        observed = AcquisitionState(raw=str(state), normalized=normalized)
        self.state_log.append(observed)
        if normalized == "READY":
            self.ready_seen = True
        elif normalized == "ROLL":
            self.roll_seen = True
        elif normalized == "STOP":
            if not self.ready_seen:
                raise ScopeProtocolError("Stop observed before Ready")
            self.stopped = True
        return observed

    def query_state(self) -> AcquisitionState:
        """Query ``SAST?``, record it, and keep both raw reply and canonical state."""

        return self.mark_state(self.query_ascii("SAST?", allow_after_stop=True))

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
    for command, key in (("TRMD?", "trigger_mode"), ("SAST?", "acquisition_state"), ("ACQ:POIN?", "scope_record_points"), ("ACQ:MDEP?", "memory_depth"), ("SARA?", "sample_rate"), ("TDIV?", "timebase"), ("TRDL?", "trigger_delay"), ("TIM:SCAL?", "horizontal_scale"), ("TIM:DEL?", "horizontal_delay"), ("TIM:REF:POS?", "horizontal_reference_position"), ("WFSU?", "waveform_setup")):
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


def configure_left_aligned_trigger(
    scope: ScopeSession,
    *,
    margin_div: float = 1.0,
    memory_depth: Optional[str] = None,
    reference_position: Optional[int] = None,
    channel_count: int = 1,
) -> dict[str, Any]:
    """Configure a new trigger-following capture before TRMD SINGLE.

    The trigger is placed ``margin_div`` divisions from the left edge by
    setting positive horizontal delay. This is intentionally opt-in.
    """

    try:
        margin = float(margin_div)
    except (TypeError, ValueError) as exc:
        raise ScopeProtocolError("margin_div must be numeric") from exc
    if not math.isfinite(margin) or margin <= 0 or margin > 5:
        raise ScopeProtocolError("margin_div must be finite and in the range (0, 5]")
    if channel_count not in (1, 2, 3, 4):
        raise ScopeProtocolError("channel_count must be between 1 and 4")
    timebase = _parse_numeric(scope.query_ascii("TIM:SCAL?"), "TIM:SCAL?")
    if timebase <= 0:
        raise ScopeProtocolError("TIM:SCAL? must return a positive timebase")
    acquire_mode = scope.query_ascii("ACQ:MODE?").strip().upper()
    if acquire_mode != "YT":
        raise ScopeProtocolError(
            f"left-aligned trigger needs YT acquisition mode, scope reports {acquire_mode!r}; "
            "ROLL ignores horizontal delay and never reaches Ready"
        )
    delay = (5.0 - margin) * timebase
    scope.write(f"TIM:DEL {delay:.9E}")
    normalized_depth = configure_memory_depth(scope, memory_depth=memory_depth, channel_count=channel_count)
    if reference_position is not None:
        if not isinstance(reference_position, int) or not 0 <= reference_position <= 100:
            raise ScopeProtocolError("reference_position must be an integer in the range 0..100")
        scope.write(f"TIM:REF:POS {reference_position}")

    actual_timebase = _parse_numeric(scope.query_ascii("TIM:SCAL?"), "TIM:SCAL? readback")
    actual_delay = _parse_numeric(scope.query_ascii("TIM:DEL?"), "TIM:DEL? readback")
    if not math.isclose(actual_timebase, timebase, rel_tol=1e-6, abs_tol=max(1e-15, timebase * 1e-9)):
        raise ScopeProtocolError(f"timebase changed during left-aligned setup: requested {timebase}, read {actual_timebase}")
    if not math.isclose(actual_delay, delay, rel_tol=1e-6, abs_tol=max(1e-15, delay * 1e-9)):
        raise ScopeProtocolError(f"delay readback mismatch: requested {delay}, read {actual_delay}")
    actual_depth = scope.query_ascii("ACQ:MDEP?").strip().upper()
    if normalized_depth not in actual_depth:
        raise ScopeProtocolError(f"memory depth readback mismatch: requested {normalized_depth}, read {actual_depth!r}")
    actual_reference = None
    if reference_position is not None:
        actual_reference = int(float(scope.query_ascii("TIM:REF:POS?")))
        if actual_reference != reference_position:
            raise ScopeProtocolError(f"reference position readback mismatch: requested {reference_position}, read {actual_reference}")
    return {
        "enabled": True,
        "margin_div": margin,
        "timebase_s_per_div": actual_timebase,
        "delay_s": actual_delay,
        "pre_trigger_s": margin * actual_timebase,
        "post_trigger_s": (10.0 - margin) * actual_timebase,
        "total_window_s": 10.0 * actual_timebase,
        "memory_depth_requested": normalized_depth,
        "memory_depth_readback": actual_depth,
        "reference_position_requested": reference_position,
        "reference_position_readback": actual_reference,
    }


def configure_memory_depth(
    scope: ScopeSession,
    *,
    memory_depth: Optional[str] = None,
    channel_count: int = 1,
) -> str:
    if channel_count not in (1, 2, 3, 4):
        raise ScopeProtocolError("channel_count must be between 1 and 4")
    if memory_depth is None:
        memory_depth = {1: "100M", 2: "50M", 3: "25M", 4: "25M"}[channel_count]
    normalized_depth = str(memory_depth).strip().upper()
    if normalized_depth not in {"100M", "50M", "25M"}:
        raise ScopeProtocolError("memory_depth must be one of 100M, 50M, or 25M")
    scope.write(f"ACQ:MDEP {normalized_depth}")
    actual_depth = scope.query_ascii("ACQ:MDEP?").strip().upper()
    if normalized_depth not in actual_depth:
        raise ScopeProtocolError(f"memory depth readback mismatch: requested {normalized_depth}, read {actual_depth!r}")
    return actual_depth


def _parse_numeric(value: Any, label: str) -> float:
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?", str(value).replace(" ", ""))
    if not match:
        raise ScopeProtocolError(f"{label} did not return a numeric value: {value!r}")
    parsed = float(match.group(0))
    if not math.isfinite(parsed):
        raise ScopeProtocolError(f"{label} returned a non-finite value: {value!r}")
    return parsed


def scope_set_capture_mode(scope: ScopeSession, mode: str) -> None:
    if mode not in ("immutable_capture", "configured_capture"):
        raise ScopeProtocolError(f"unsupported capture mode: {mode}")
    scope.capture_mode = mode


def scope_arm_single(scope: ScopeSession) -> None:
    """The named API is retained for callers, but it never sends ARM."""

    scope.write("TRMD SINGLE")


def scope_wait_ready(scope: ScopeSession, timeout_s: float = 30.0, poll_s: float = 0.2) -> AcquisitionState:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = scope.query_state()
        if state.normalized == "ROLL":
            raise ScopeProtocolError(
                "scope is in Roll mode (:ACQuire:MODE ROLL); Roll never reaches Ready, "
                "so it cannot support the Ready -> Stop single-shot flow. Leave Roll "
                "(:ACQuire:MODE YT) before arming a capture"
            )
        if state.normalized == "READY":
            return state
        time.sleep(poll_s)
    raise ScopeProtocolError("timed out waiting for Ready")


def scope_wait_stop(scope: ScopeSession, timeout_s: float = 360.0, poll_s: float = 0.2) -> AcquisitionState:
    if not scope.ready_seen:
        raise ScopeProtocolError("scope_wait_stop requires a previously observed Ready")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = scope.query_state()
        if state.normalized == "STOP":
            return state
        time.sleep(poll_s)
    raise ScopeProtocolError("timed out waiting for Stop")


def scope_read_segment(scope: ScopeSession, channel: str, start: int, count: int) -> IEEEBlock:
    """Read one modern WAV segment after the caller explicitly stopped capture.

    The caller supplies the requested segment size. The payload must hold
    exactly that many points; a short reply aborts the read.
    """

    if start < 0 or count <= 0:
        raise ScopeProtocolError("segment start must be non-negative and count must be positive")
    if scope.capture_mode != "configured_capture":
        raise ScopeProtocolError("modern WAV segment reads require explicit configured_capture mode")
    scope.write(f"WAV:SOUR {channel}", allow_after_stop=True)
    scope.write("WAV:INT 1", allow_after_stop=True)
    interval_readback = _optional_int(scope.query_ascii("WAV:INT?", allow_after_stop=True))
    if interval_readback != 1:
        raise ScopeProtocolError(f"requested WAV:INT 1, scope returned {interval_readback!r}")
    scope.write("WAV:STAR 0", allow_after_stop=True)
    initial = parse_wavedesc(scope.query_block("WAV:PRE?", allow_after_stop=True).payload)
    selection = decide_waveform_width(initial, "auto")
    scope.write(f"WAV:WIDT {selection['width_command']}", allow_after_stop=True)
    if selection["bytes_per_point"] == 2:
        scope.write("WAV:BYT LSB", allow_after_stop=True)
        if scope.query_ascii("WAV:BYT?", allow_after_stop=True).strip().upper() != "LSB":
            raise ScopeProtocolError("scope did not accept WAV:BYT LSB")
    preamble = parse_wavedesc(scope.query_block("WAV:PRE?", allow_after_stop=True).payload)
    if preamble["data_width_bytes"] != selection["bytes_per_point"]:
        raise ScopeProtocolError("scope WAVEDESC width differs from requested width")
    return read_wav_segment(scope, start, count, preamble)


def read_wav_segment(
    scope: ScopeSession,
    start: int,
    count: int,
    preamble: dict[str, Any],
) -> IEEEBlock:
    """Read one segment; the returned payload length is the point-count authority.

    ``WAV:POIN?`` may echo the requested value even when the device silently
    truncates the transfer, so it is kept as advisory evidence only. The actual
    point count is ``len(payload) // bytes_per_point`` and must equal the
    request exactly; anything else fails closed before the payload is saved or
    merged.
    """

    if start < 0 or count <= 0:
        raise ScopeProtocolError("segment start must be non-negative and count must be positive")
    bytes_per_point = int(preamble["data_width_bytes"])
    if bytes_per_point <= 0:
        raise ScopeProtocolError("preamble bytes_per_point must be positive")
    expected_bytes = count * bytes_per_point
    scope.write(f"WAV:STAR {start}", allow_after_stop=True)
    scope.write(f"WAV:POIN {count}", allow_after_stop=True)
    reported_start = _optional_int(scope.query_ascii("WAV:STAR?", allow_after_stop=True))
    reported_count = _optional_int(scope.query_ascii("WAV:POIN?", allow_after_stop=True))
    if reported_start is not None and reported_start != start:
        raise ScopeProtocolError(f"scope selected start {reported_start}; expected {start}")
    block = scope.query_block("WAV:DATA?", allow_after_stop=True)
    actual_bytes = len(block.payload)
    if actual_bytes % bytes_per_point:
        raise ScopeProtocolError(
            f"segment {start}: payload {actual_bytes} bytes is not divisible by {bytes_per_point} B/point"
        )
    actual_points = actual_bytes // bytes_per_point
    if actual_bytes != expected_bytes:
        raise ScopeProtocolError(
            f"segment {start}: requested {count} points ({expected_bytes} bytes), received {actual_points} points "
            f"({actual_bytes} bytes); WAV:POIN? reported {reported_count!r} and is not evidence of the returned count"
        )
    block.bytes_per_point = bytes_per_point
    block.requested_points = count
    block.reported_points = reported_count
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
        "state": {"ready_seen": scope.ready_seen, "roll_seen": scope.roll_seen, "stopped": scope.stopped},
        "state_evidence": [asdict(entry) for entry in scope.state_log],
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


def scope_assume_existing_stop(scope: ScopeSession) -> AcquisitionState:
    """Accept a stopped frame without claiming a new Ready -> Stop transition."""

    raw = scope.query_ascii("SAST?", allow_after_stop=True)
    normalized = normalize_acquisition_state(raw)
    state = AcquisitionState(raw=str(raw), normalized=normalized)
    scope.state_log.append(state)
    if normalized != "STOP":
        raise ScopeProtocolError(f"expected an existing stopped frame, got {state.raw!r}")
    scope.stopped = True
    return state


def waveform_time_origin(descriptor: dict[str, Any]) -> float:
    return float(descriptor["horizontal_offset"] - descriptor["timebase_s"] * 5)


def decode_analog_byte(
    payload: bytes,
    descriptor: dict[str, Any],
    *,
    first_point: int = 0,
    panel_vdiv: Optional[float] = None,
    panel_offset: Optional[float] = None,
) -> list[tuple[int, float, float]]:
    """Decode byte samples, preferring live panel VDIV/OFST when supplied."""

    if descriptor.get("data_width_bytes") != 1:
        raise ScopeProtocolError("byte decoder requires an 8-bit descriptor")
    codes_per_div = float(descriptor["code_per_div"])
    if codes_per_div == 0:
        raise ScopeProtocolError("invalid zero code_per_div in descriptor")
    interval = float(descriptor["sample_interval"])
    origin = waveform_time_origin(descriptor)
    vdiv = float(panel_vdiv if panel_vdiv is not None else descriptor["vdiv_with_probe"])
    offset = float(panel_offset if panel_offset is not None else descriptor["offset_with_probe"])
    return [
        (first_point + index, origin + (first_point + index) * interval, (value - 256 if value > 127 else value) * vdiv / codes_per_div - offset)
        for index, value in enumerate(payload)
    ]


def scope_restore_run_mode(scope: ScopeSession) -> None:
    """Explicit opt-in restoration; never call from capture/read helpers."""

    scope.write("TRMD AUTO", allow_after_stop=True, explicit_release=True)
    scope.stopped = False
    scope.ready_seen = False
    scope.roll_seen = False


def scope_release_capture(scope: ScopeSession) -> None:
    """Explicitly release software protection before a caller-controlled write."""

    scope.stopped = False
    scope.ready_seen = False
    scope.roll_seen = False


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

    if len(payload) < 346:
        raise ScopeProtocolError(f"WAVEDESC is shorter than 346 bytes: {len(payload)}")
    description = payload[0:16].split(b"\0", 1)[0].decode("ascii", errors="replace")
    if not description.startswith("WAVEDESC"):
        raise ScopeProtocolError(f"invalid WAVEDESC description: {description!r}")
    descriptor_length = _unpack(payload, 36, "<i")
    if descriptor_length not in (0, 346):
        raise ScopeProtocolError(f"unexpected WAVEDESC length: {descriptor_length}")
    timebase_index = _unpack(payload, 324, "<h")
    result: dict[str, Any] = {
        "description": description,
        "descriptor_length": descriptor_length,
        "comm_type": _unpack(payload, 32, "<h"),
        "comm_order": _unpack(payload, 34, "<h"),
        "wave_array_1_bytes": _unpack(payload, 60, "<i"),
        "wave_array_count": _unpack(payload, 116, "<i"),
        "start": _unpack(payload, 132, "<i"),
        "sparsing_factor": _unpack(payload, 136, "<i"),
        "vdiv": _unpack(payload, 156, "<f"),
        "offset": _unpack(payload, 160, "<f"),
        "vertical_code_field": _unpack(payload, 164, "<f"),
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
    result["interval"] = result["sparsing_factor"]
    result["nominal_bits"] = result["adc_bit"]
    result["horiz_interval"] = result["sample_interval"]
    result["horiz_offset"] = result["horizontal_offset"]
    result["trigger_position"] = None
    result["vdiv_with_probe"] = result["vdiv"] * result["probe"]
    result["offset_with_probe"] = result["offset"] * result["probe"]
    if result["comm_type"] not in (0, 1):
        raise ScopeProtocolError(f"unknown WAVEDESC COMM_TYPE: {result['comm_type']}")
    if result["comm_order"] not in (0, 1):
        raise ScopeProtocolError(f"unknown WAVEDESC COMM_ORDER: {result['comm_order']}")
    result["byte_order"] = "MSB" if result["comm_order"] == 1 else "LSB"
    # SDS824X HD firmware reports MAX_VALUE=7680 at this legacy descriptor
    # offset, while the handover confirms codes_per_div=30. Older descriptors
    # may put codes_per_div directly here, so preserve both interpretations.
    if abs(result["vertical_code_field"]) > 256:
        result["max_value"] = result["vertical_code_field"]
        result["code_per_div"] = result["vertical_code_field"] / 256.0
    else:
        result["code_per_div"] = result["vertical_code_field"]
        result["max_value"] = result["vertical_code_field"] * 256.0
    result["data_width_bytes"] = 1 if result["comm_type"] == 0 else 2
    if result["wave_array_1_bytes"] != result["wave_array_count"] * result["data_width_bytes"]:
        raise ScopeProtocolError(
            f"WAVEDESC byte/point mismatch: {result['wave_array_1_bytes']} bytes for {result['wave_array_count']} points at {result['data_width_bytes']} B/point"
        )
    return result


def decide_waveform_width(preamble: dict[str, Any], requested: str = "auto") -> dict[str, Any]:
    if requested not in ("auto", "byte", "word"):
        raise ScopeProtocolError(f"unsupported waveform width: {requested}")
    nominal_bits = int(preamble.get("nominal_bits", preamble.get("adc_bit", 0)))
    if requested == "auto":
        width = 2 if nominal_bits > 8 or preamble.get("comm_type") == 1 else 1
    else:
        width = 1 if requested == "byte" else 2
    return {
        "requested": requested,
        "bytes_per_point": width,
        "width_command": "WORD" if width == 2 else "BYTE",
        "precision": "lossy_8bit" if width == 1 and nominal_bits > 8 else ("word_container_unscaled" if width == 2 else "8bit"),
        "nominal_bits": nominal_bits,
        "voltage_decode": "unverified_for_WORD" if width == 2 else "signed_8bit",
    }


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
    expected_payload_bytes: Optional[int] = None,
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
    downloaded_bytes = sum(segment.payload_length for segment in ordered)
    if expected_points is not None and total != expected_points:
        reasons.append(f"downloaded {total} points, descriptor expects {expected_points}")
    if expected_payload_bytes is not None and downloaded_bytes != expected_payload_bytes:
        reasons.append(f"downloaded {downloaded_bytes} bytes, expected {expected_payload_bytes}")
    if any(not segment.valid for segment in ordered):
        reasons.append("one or more segments are invalid")
    valid = not reasons and (expected_points is None or cursor == expected_points)
    return {
        "status": "COMPLETE" if valid else "INVALID",
        "expected_points": expected_points,
        "downloaded_points": total,
        "expected_payload_bytes": expected_payload_bytes,
        "downloaded_payload_bytes": downloaded_bytes,
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
    bytes_per_point: Optional[int] = None,
    expected_payload_bytes: Optional[int] = None,
    downloaded_payload_bytes: Optional[int] = None,
    byte_order: Optional[str] = None,
    nominal_bits: Optional[int] = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    expected = wavedesc_points if wavedesc_points is not None else scope_points
    if scope_points is not None and wavedesc_points is not None and scope_points != wavedesc_points:
        reasons.append(f"screen record {scope_points} differs from WAVEDESC {wavedesc_points}")
    if expected is not None and downloaded_points != expected:
        reasons.append(f"downloaded {downloaded_points} points, expected {expected}")
    if downloaded_payload_bytes is None and segment_report is not None:
        downloaded_payload_bytes = segment_report.get("downloaded_payload_bytes")
    if expected_payload_bytes is None and segment_report is not None:
        expected_payload_bytes = segment_report.get("expected_payload_bytes")
    if expected_payload_bytes is not None and downloaded_payload_bytes != expected_payload_bytes:
        reasons.append(f"downloaded {downloaded_payload_bytes} bytes, expected {expected_payload_bytes}")
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
        "waveform_format": {"bytes_per_point": bytes_per_point, "expected_payload_bytes": expected_payload_bytes, "downloaded_payload_bytes": downloaded_payload_bytes, "byte_order": byte_order, "nominal_bits": nominal_bits},
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
