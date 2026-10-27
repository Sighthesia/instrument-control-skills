#!/usr/bin/env python3
"""Capture SDS waveforms in one explicit TCP session.

This CLI intentionally does not reconnect, auto-retrigger, restore TRMD, or
send WFSU while reading an immutable stopped frame.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from scope_protocol import (
    ScopeProtocolError,
    ScopeSession,
    Segment,
    decide_waveform_width,
    normalize_acquisition_state,
    read_wav_segment,
    scope_assume_existing_stop,
    configure_left_aligned_trigger,
    configure_memory_depth,
    scope_prepare_capture,
    parse_wavedesc,
    save_json,
    validate_frame,
    validate_segments,
)


CHANNELS = ("C1", "C2", "C3", "C4")


def numeric_response(value):
    text = str(value).strip().replace(" ", "")
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?", text)
    if not match:
        return None
    number = float(match.group(0))
    suffix = text[match.end() :].lower()
    if suffix.startswith(("gsa/s", "gsa")):
        return number * 1e9
    if suffix.startswith(("msa/s", "msa")):
        return number * 1e6
    if suffix.startswith(("ksa/s", "ksa")):
        return number * 1e3
    if suffix.startswith(("gpts", "gpt")):
        return number * 1e9
    if suffix.startswith(("mpts", "mpt")):
        return number * 1e6
    if suffix.startswith(("kpts", "kpt")):
        return number * 1e3
    return number


def configure_default_capture(scope: ScopeSession) -> None:
    scope_prepare_capture(scope)


def wait_state(scope: ScopeSession, wanted: str, timeout_s: float, poll_s: float) -> dict:
    """Poll ``SAST?`` until the canonical state matches ``wanted``.

    Decorated replies (``SAST Ready``, mixed case, extra whitespace) are
    normalized for the decision while the raw reply is retained as evidence.
    """

    target = normalize_acquisition_state(wanted)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        observed = scope.query_state()
        state = observed.normalized
        if state == "ROLL":
            raise ScopeProtocolError(
                "scope is in Roll mode (:ACQuire:MODE ROLL); Roll never reaches Ready, "
                "so it cannot support the Ready -> Stop single-shot flow. Leave Roll "
                "(:ACQuire:MODE YT) before arming a capture"
            )
        if state == target:
            return {"wanted": target, "raw": observed.raw, "normalized": state}
        time.sleep(poll_s)
    raise ScopeProtocolError(f"timed out waiting for SAST?={wanted}")


def write_block_artifact(root: Path, channel: str, stem: str, block) -> tuple[Path, Path, Path]:
    directory = root / channel
    directory.mkdir(parents=True, exist_ok=True)
    payload_path = directory / f"{stem}.bin"
    raw_path = directory / f"{stem}.response.bin"
    prefix_path = directory / f"{stem}.prefix.bin"
    payload_path.write_bytes(block.payload)
    raw_path.write_bytes(block.raw)
    prefix_path.write_bytes(block.prefix)
    return payload_path, raw_path, prefix_path


def read_modern_segment(
    scope: ScopeSession,
    root: Path,
    channel: str,
    stem: str,
    start: int,
    count: int,
    preamble: dict,
) -> tuple[Segment, dict]:
    """Read and persist one segment; the payload length decides the point count.

    ``read_wav_segment`` has already rejected a short reply, so the metadata here
    records the verified actual count rather than echoing the request.
    """

    block = read_wav_segment(scope, start, count, preamble)
    actual_points = block.actual_points
    if actual_points != count:
        raise ScopeProtocolError(
            f"segment {start}: requested {count} points, payload holds {actual_points}; refusing to persist"
        )
    payload_path, raw_path, prefix_path = write_block_artifact(root, channel, stem, block)
    time_origin = preamble["horizontal_offset"] - preamble["timebase_s"] * 5
    segment = Segment(
        start=start,
        requested_points=count,
        payload_length=len(block.payload),
        bytes_per_point=preamble["data_width_bytes"],
        sample_interval_s=preamble["sample_interval"],
        time_origin_s=time_origin,
        sha256=block.sha256,
    )
    metadata = {
        "channel": channel,
        "requested_start": start,
        "requested_points": count,
        "scope_start": start,
        "scope_points_reported": block.reported_points,
        "scope_points_echo_is_not_evidence": True,
        "actual_payload_bytes": len(block.payload),
        "bytes_per_point": preamble["data_width_bytes"],
        "byte_offset": start * preamble["data_width_bytes"],
        "actual_points": actual_points,
        "time_start_s": segment.time_start_s,
        "time_end_s": segment.time_end_s,
        "sha256": block.sha256,
        "payload": str(payload_path),
        "raw_response": str(raw_path),
        "prefix": str(prefix_path),
        "preamble": preamble,
    }
    save_json(root / channel / f"{stem}.json", metadata)
    return segment, {**metadata, "metadata": str(root / channel / f"{stem}.json")}


def merge_segment_payloads(root: Path, channel: str, segment_files: list[dict], output_name: str) -> Path:
    output_path = root / channel / output_name
    partial_path = output_path.with_suffix(output_path.suffix + ".partial")
    digest = hashlib.sha256()
    try:
        with partial_path.open("wb") as output:
            for segment in segment_files:
                payload_path = Path(segment["payload"])
                expected_size = int(segment["actual_payload_bytes"])
                if payload_path.stat().st_size != expected_size:
                    raise ScopeProtocolError(f"segment file size changed: {payload_path}")
                segment_digest = hashlib.sha256()
                with payload_path.open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
                        segment_digest.update(chunk)
                if segment_digest.hexdigest() != segment["sha256"]:
                    raise ScopeProtocolError(f"segment SHA-256 mismatch: {payload_path}")
        expected_total = sum(int(segment["actual_payload_bytes"]) for segment in segment_files)
        if partial_path.stat().st_size != expected_total:
            raise ScopeProtocolError(f"merged file size mismatch: expected {expected_total}, got {partial_path.stat().st_size}")
        partial_path.replace(output_path)
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise
    merge_segment_payloads.last_sha256 = digest.hexdigest()
    return output_path


merge_segment_payloads.last_sha256 = None


def run_modern_probes(
    scope: ScopeSession,
    root: Path,
    channel: str,
    preamble: dict,
    max_points: int,
    probe_points: list[int],
) -> list[dict]:
    """Validate small and medium WAV reads before requesting the full record."""

    probes: list[dict] = []
    for index, requested in enumerate(probe_points):
        count = min(requested, max_points)
        if count <= 0:
            continue
        segment, metadata = read_modern_segment(
            scope,
            root,
            channel,
            f"probe-{index:02d}-{count}",
            0,
            count,
            preamble,
        )
        report = validate_segments(
            [segment],
            expected_points=count,
            sample_interval_s=preamble["sample_interval"],
            time_origin_s=preamble["horizontal_offset"] - preamble["timebase_s"] * 5,
            expected_payload_bytes=count * preamble["data_width_bytes"],
        )
        metadata["validation"] = report
        save_json(root / channel / f"probe-{index:02d}-{count}.json", metadata)
        if report["status"] != "COMPLETE":
            raise ScopeProtocolError(f"WAV probe failed at {count} points: {report['reasons']}" )
        probes.append({**metadata, "validation": report})
    return probes


def read_modern_channel(
    scope: ScopeSession,
    root: Path,
    channel: str,
    segment_points: int,
    scope_record_points=None,
    scope_record_duration_s=None,
    trigger_relative_s=None,
    probe_points: Optional[list[int]] = None,
    requested_width: str = "auto",
) -> dict:
    channel_snapshot = {}
    for suffix, key in (("VDIV?", "vdiv"), ("OFST?", "offset")):
        channel_snapshot[key] = scope.query_ascii(f"{channel}:{suffix}", allow_after_stop=True)
    for command, key in (("SARA?", "sample_rate"), ("TDIV?", "timebase"), ("TRDL?", "trigger_delay"), ("WFSU?", "waveform_setup")):
        channel_snapshot[key] = scope.query_ascii(command, allow_after_stop=True)
    scope.write(f"WAV:SOUR {channel}", allow_after_stop=True)
    scope.write("WAV:INT 1", allow_after_stop=True)
    interval_readback = int(float(scope.query_ascii("WAV:INT?", allow_after_stop=True)))
    if interval_readback != 1:
        raise ScopeProtocolError(f"requested WAV:INT 1, scope returned {interval_readback}")
    scope.write("WAV:STAR 0", allow_after_stop=True)
    initial_preamble_block = scope.query_block("WAV:PRE?", allow_after_stop=True)
    initial_preamble = parse_wavedesc(initial_preamble_block.payload)
    width_selection = decide_waveform_width(initial_preamble, requested_width)
    scope.write(f"WAV:WIDT {width_selection['width_command']}", allow_after_stop=True)
    width_readback = scope.query_ascii("WAV:WIDT?", allow_after_stop=True).strip().upper()
    if width_readback != width_selection["width_command"]:
        raise ScopeProtocolError(f"requested WAV:WIDT {width_selection['width_command']}, scope returned {width_readback!r}")
    if width_selection["bytes_per_point"] == 2:
        scope.write("WAV:BYT LSB", allow_after_stop=True)
        byte_order_readback = scope.query_ascii("WAV:BYT?", allow_after_stop=True).strip().upper()
        if byte_order_readback != "LSB":
            raise ScopeProtocolError(f"requested WAV:BYT LSB, scope returned {byte_order_readback!r}")
    else:
        byte_order_readback = "N/A"
    sparsing_readback = int(float(scope.query_ascii("WAV:INT?", allow_after_stop=True)))
    if sparsing_readback != 1:
        raise ScopeProtocolError(f"requested WAV:INT 1, scope returned {sparsing_readback}")
    preamble_block = scope.query_block("WAV:PRE?", allow_after_stop=True)
    preamble = parse_wavedesc(preamble_block.payload)
    expected_points = preamble["wave_array_count"]
    bytes_per_point = width_selection["bytes_per_point"]
    if preamble["data_width_bytes"] != bytes_per_point:
        raise ScopeProtocolError(
            f"requested {width_selection['width_command']} ({bytes_per_point} B/point), WAVEDESC reports {preamble['data_width_bytes']} B/point"
        )
    if bytes_per_point == 2 and preamble["byte_order"] != "LSB":
        raise ScopeProtocolError(f"requested LSB WORD transfer, WAVEDESC reports {preamble['byte_order']}")
    if preamble["wave_array_1_bytes"] != expected_points * bytes_per_point:
        raise ScopeProtocolError(f"WAVEDESC reports {expected_points} points but {preamble['wave_array_1_bytes']} bytes at {bytes_per_point} B/point")
    max_points_text = scope.query_ascii("WAV:MAXP?", allow_after_stop=True)
    max_points_value = numeric_response(max_points_text)
    if max_points_value is None or max_points_value <= 0:
        raise ScopeProtocolError(f"invalid WAV:MAXP? response: {max_points_text!r}")
    max_points = int(max_points_value)
    probes = run_modern_probes(scope, root, channel, preamble, max_points, probe_points or [])
    step = min(segment_points, max_points)
    if step <= 0:
        raise ScopeProtocolError(f"invalid segment step {step} from WAV:MAXP?={max_points}")
    segments: list[Segment] = []
    segment_files: list[dict] = []
    start = 0
    index = 0
    while start < expected_points:
        count = min(step, expected_points - start)
        stem = f"segment-{index:06d}"
        segment, metadata = read_modern_segment(scope, root, channel, stem, start, count, preamble)
        if segment.actual_points != count:
            raise ScopeProtocolError(
                f"segment {start}: requested {count} points, payload holds {segment.actual_points}; "
                "refusing to advance the range"
            )
        segments.append(segment)
        metadata["command_snapshot"] = channel_snapshot
        save_json(root / channel / f"{stem}.json", metadata)
        segment_files.append(metadata)
        start += segment.actual_points
        index += 1
    segment_report = validate_segments(
        segments,
        expected_points=expected_points,
        sample_interval_s=preamble["sample_interval"],
        time_origin_s=preamble["horizontal_offset"] - preamble["timebase_s"] * 5,
        expected_payload_bytes=expected_points * bytes_per_point,
    )
    frame_report = validate_frame(
        scope_points=scope_record_points,
        scope_duration_s=scope_record_duration_s,
        wavedesc_points=expected_points,
        sample_interval_s=preamble["sample_interval"],
        downloaded_points=segment_report["downloaded_points"],
        downloaded_duration_s=segment_report["downloaded_duration_s"],
        trigger_relative_s=trigger_relative_s,
        segment_report=segment_report,
        bytes_per_point=bytes_per_point,
        expected_payload_bytes=expected_points * bytes_per_point,
        downloaded_payload_bytes=segment_report["downloaded_payload_bytes"],
        byte_order=preamble["byte_order"],
        nominal_bits=preamble["nominal_bits"],
    )
    preamble_path = root / channel / "preamble.payload.bin"
    preamble_path.write_bytes(preamble_block.payload)
    preamble_raw_path = root / channel / "preamble.response.bin"
    preamble_prefix_path = root / channel / "preamble.prefix.bin"
    preamble_raw_path.write_bytes(preamble_block.raw)
    preamble_prefix_path.write_bytes(preamble_block.prefix)
    result = {"channel": channel, "mode": scope.capture_mode, "preamble": preamble, "waveform_format": {**width_selection, "width_readback": width_readback, "wav_max_point": max_points, "maxpoint_unit": "points", "sparsing_readback": sparsing_readback, "byte_order": preamble["byte_order"], "byte_order_readback": byte_order_readback, "expected_payload_bytes": expected_points * bytes_per_point}, "preamble_payload": str(preamble_path), "preamble_raw_response": str(preamble_raw_path), "preamble_prefix": str(preamble_prefix_path), "segments": segment_files, "segment_report": segment_report, "frame_report": frame_report}
    result["probes"] = probes
    result["state_evidence"] = [asdict(entry) for entry in scope.state_log]
    if segment_report["status"] == "COMPLETE":
        merged_path = merge_segment_payloads(root, channel, segment_files, "waveform.bin")
        result["merged_waveform"] = str(merged_path)
        result["merged_waveform_bytes"] = merged_path.stat().st_size
        result["merged_waveform_sha256"] = merge_segment_payloads.last_sha256
    return result


def read_legacy_channel(scope: ScopeSession, root: Path, channel: str, read_descriptor: bool) -> dict:
    # DAT2 for every requested channel is completed by the caller before DESC.
    block = scope.query_block(f"{channel}:WF? DAT2", allow_after_stop=True)
    directory = root / channel
    directory.mkdir(parents=True, exist_ok=True)
    payload_path = directory / "legacy-DAT2.payload.bin"
    raw_path = directory / "legacy-DAT2.response.bin"
    prefix_path = directory / "legacy-DAT2.prefix.bin"
    payload_path.write_bytes(block.payload)
    raw_path.write_bytes(block.raw)
    prefix_path.write_bytes(block.prefix)
    result = {"channel": channel, "mode": scope.capture_mode, "payload_points": len(block.payload), "payload": str(payload_path), "raw_response": str(raw_path), "prefix": str(prefix_path), "sha256": block.sha256}
    result["configuration_snapshot"] = {
        "vdiv": scope.query_ascii(f"{channel}:VDIV?", allow_after_stop=True),
        "offset": scope.query_ascii(f"{channel}:OFST?", allow_after_stop=True),
        "sample_rate": scope.query_ascii("SARA?", allow_after_stop=True),
        "timebase": scope.query_ascii("TDIV?", allow_after_stop=True),
        "trigger_delay": scope.query_ascii("TRDL?", allow_after_stop=True),
        "waveform_setup": scope.query_ascii("WFSU?", allow_after_stop=True),
    }
    if read_descriptor:
        result["descriptor_pending"] = True
    return result


def add_legacy_descriptors(scope: ScopeSession, root: Path, channel_results: list[dict]) -> None:
    for result in channel_results:
        channel = result["channel"]
        block = scope.query_block(f"{channel}:WF? DESC", allow_after_stop=True)
        directory = root / channel
        descriptor_path = directory / "legacy-DESC.payload.bin"
        raw_path = directory / "legacy-DESC.response.bin"
        prefix_path = directory / "legacy-DESC.prefix.bin"
        descriptor_path.write_bytes(block.payload)
        raw_path.write_bytes(block.raw)
        prefix_path.write_bytes(block.prefix)
        result["descriptor"] = parse_wavedesc(block.payload)
        result["descriptor_payload"] = str(descriptor_path)
        result["descriptor_raw_response"] = str(raw_path)
        result["descriptor_prefix"] = str(prefix_path)
        expected = result["descriptor"].get("wave_array_count")
        interval = result["descriptor"].get("sample_interval")
        result["frame_report"] = validate_frame(
            scope_points=expected,
            scope_duration_s=expected * interval if expected and interval is not None else None,
            wavedesc_points=expected,
            sample_interval_s=interval,
            downloaded_points=result["payload_points"],
        )
        result.pop("descriptor_pending", None)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.10.2")
    parser.add_argument("--port", type=int, default=5025)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--channels", nargs="+", choices=CHANNELS, default=list(CHANNELS))
    parser.add_argument("--mode", choices=("modern", "legacy"), default="modern")
    parser.add_argument("--capture-mode", choices=("immutable_capture", "configured_capture"), default=None)
    parser.add_argument("--wfsu", default=None, help="explicit WFSU command; only valid with --capture-mode configured_capture")
    parser.add_argument("--scope-record-points", type=int, default=None)
    parser.add_argument("--scope-record-duration", type=float, default=None)
    parser.add_argument("--trigger-relative-s", type=float, default=None)
    parser.add_argument("--segment-points", type=int, default=5_000_000)
    parser.add_argument("--wav-width", choices=("auto", "byte", "word"), default="auto", help="WAV transfer width; auto selects WORD when descriptor nominal bits exceed 8")
    parser.add_argument("--probe-points", default="10000,1000000", help="comma-separated preflight WAV probe sizes; use empty string to disable")
    parser.add_argument("--prepare", action="store_true", help="write the handover's capture configuration")
    parser.add_argument("--trigger", action="store_true", help="issue TRMD SINGLE and wait Ready -> Stop")
    parser.add_argument("--left-aligned-trigger", action="store_true", help="place the trigger at --trigger-margin-div from the left edge before TRMD SINGLE")
    parser.add_argument("--trigger-margin-div", type=float, default=1.0, help="pre-trigger screen divisions for --left-aligned-trigger; default 1.0")
    parser.add_argument("--memory-depth", choices=("auto", "100M", "50M", "25M"), default=None, help="explicit memory depth for a new capture; auto maps 1/2/3-4 channels to 100M/50M/25M")
    parser.add_argument("--reference-position", type=int, help="optional TIM:REF:POS percentage 0..100 for a new capture")
    parser.add_argument("--existing-stopped", action="store_true", help="read the current stopped frame without claiming a new Ready -> Stop transition")
    parser.add_argument("--read-descriptors", action="store_true", help="after all legacy DAT2 reads, explicitly read DESC")
    parser.add_argument("--ready-timeout", type=float, default=30.0)
    parser.add_argument("--stop-timeout", type=float, default=360.0)
    parser.add_argument("--poll", type=float, default=0.2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.port == 5024:
        raise SystemExit("Refusing legacy shell port 5024; use SCPI TCP port 5025")
    if args.segment_points <= 0:
        raise SystemExit("--segment-points must be positive")
    try:
        probe_points = [int(item) for item in args.probe_points.split(",") if item.strip()]
    except ValueError as exc:
        raise SystemExit("--probe-points must be comma-separated integers") from exc
    if any(item <= 0 for item in probe_points):
        raise SystemExit("--probe-points values must be positive")
    if args.capture_mode is None:
        args.capture_mode = "configured_capture" if args.mode == "modern" else "immutable_capture"
    if args.mode == "modern" and args.capture_mode != "configured_capture":
        raise SystemExit("modern WAV segmented reads require --capture-mode configured_capture")
    if args.wfsu and args.capture_mode != "configured_capture":
        raise SystemExit("--wfsu requires --capture-mode configured_capture")
    if args.trigger and args.existing_stopped:
        raise SystemExit("--trigger and --existing-stopped are mutually exclusive")
    if args.prepare and not args.trigger:
        raise SystemExit("--prepare requires --trigger so setup is applied before the new capture")
    if args.wfsu and not args.trigger:
        raise SystemExit("--wfsu requires --trigger so it is applied before the new capture")
    if args.left_aligned_trigger and not args.trigger:
        raise SystemExit("--left-aligned-trigger requires --trigger")
    if args.left_aligned_trigger and args.existing_stopped:
        raise SystemExit("--left-aligned-trigger cannot be used with --existing-stopped")
    if args.reference_position is not None and not args.trigger:
        raise SystemExit("--reference-position requires --trigger")
    if args.memory_depth is not None and not args.trigger:
        raise SystemExit("--memory-depth requires --trigger")
    if args.left_aligned_trigger and (not 0 < args.trigger_margin_div <= 5):
        raise SystemExit("--trigger-margin-div must be in the range (0, 5]")
    if args.reference_position is not None and not 0 <= args.reference_position <= 100:
        raise SystemExit("--reference-position must be in the range 0..100")
    args.out.mkdir(parents=True, exist_ok=True)
    scope = ScopeSession(args.host, args.port, args.timeout)
    scope.capture_mode = args.capture_mode
    scope.set_expected_channels(args.channels)
    manifest = {
        "host": args.host,
        "port": args.port,
        "model": "SIGLENT SDS824X HD",
        "mode": args.capture_mode,
        "channel_mapping": {"C1": "ENABLE", "C2": "nFAULT", "C3": "HOC", "C4": "P4.1/CMP"},
        "channels": args.channels,
        "command_log": [],
        "results": [],
    }
    try:
        scope.connect()
        manifest["idn"] = scope.query_ascii("*IDN?")
        from scope_protocol import scope_snapshot_configuration
        manifest["pre_capture_snapshot"] = scope_snapshot_configuration(scope, args.channels)
        if args.prepare:
            configure_default_capture(scope)
        if args.wfsu:
            scope.write(args.wfsu)
        trigger_strategy = None
        if args.left_aligned_trigger:
            trigger_strategy = configure_left_aligned_trigger(
                scope,
                margin_div=args.trigger_margin_div,
                memory_depth=None if args.memory_depth in (None, "auto") else args.memory_depth,
                reference_position=args.reference_position,
                channel_count=len(args.channels),
            )
        elif args.reference_position is not None or args.memory_depth is not None:
            trigger_strategy = {"enabled": False}
            if args.memory_depth is not None:
                trigger_strategy["memory_depth_readback"] = configure_memory_depth(
                    scope,
                    memory_depth=None if args.memory_depth == "auto" else args.memory_depth,
                    channel_count=len(args.channels),
                )
            if args.reference_position is not None:
                if not 0 <= args.reference_position <= 100:
                    raise SystemExit("--reference-position must be in the range 0..100")
                scope.write(f"TIM:REF:POS {args.reference_position}")
                reference_readback = int(float(scope.query_ascii("TIM:REF:POS?")))
                if reference_readback != args.reference_position:
                    raise ScopeProtocolError("horizontal reference position readback mismatch")
                trigger_strategy["reference_position_readback"] = reference_readback
        manifest["capture_configuration"] = scope_snapshot_configuration(scope, args.channels)
        if trigger_strategy is not None:
            manifest["capture_configuration"]["left_aligned_trigger"] = trigger_strategy
        if args.trigger:
            scope.write("TRMD SINGLE")
            manifest["ready_state"] = wait_state(scope, "READY", args.ready_timeout, args.poll)
            manifest["stop_state"] = wait_state(scope, "STOP", args.stop_timeout, args.poll)
        elif args.existing_stopped:
            existing = scope_assume_existing_stop(scope)
            manifest["existing_stop_state"] = {"raw": existing.raw, "normalized": existing.normalized}
            manifest["existing_stop_claims_new_transition"] = False
        else:
            raise SystemExit("Use --trigger for a new capture or --existing-stopped for the current stopped frame")
        manifest["state_evidence"] = [asdict(entry) for entry in scope.state_log]
        if args.mode == "modern":
            snapshot = manifest["capture_configuration"]["acquisition"]
            scope_points = args.scope_record_points
            if scope_points is None:
                points_value = numeric_response(snapshot.get("scope_record_points"))
                scope_points = int(points_value) if points_value is not None else None
            sample_rate = numeric_response(snapshot.get("sample_rate"))
            scope_duration = args.scope_record_duration
            if scope_duration is None and scope_points and sample_rate and sample_rate > 0:
                scope_duration = scope_points / sample_rate
            trigger_relative = args.trigger_relative_s
            if trigger_relative is None:
                trigger_relative = numeric_response(snapshot.get("trigger_delay"))
            for channel in args.channels:
                manifest["results"].append(read_modern_channel(scope, args.out, channel, args.segment_points, scope_points, scope_duration, trigger_relative, probe_points, args.wav_width))
        else:
            results = [read_legacy_channel(scope, args.out, channel, args.read_descriptors) for channel in args.channels]
            manifest["results"].extend(results)
            if args.read_descriptors:
                add_legacy_descriptors(scope, args.out, results)
        manifest["command_log"] = [event.__dict__ for event in scope.events]
        save_json(args.out / "manifest.json", manifest)
        return 0
    except (ScopeProtocolError, OSError, ValueError) as exc:
        manifest["command_log"] = [event.__dict__ for event in scope.events]
        manifest["error"] = str(exc)
        save_json(args.out / "manifest.failed.json", manifest)
        print(f"capture failed: {exc}", file=sys.stderr)
        return 2
    finally:
        # Closing is the explicit end of this CLI invocation; no reconnect or restore is attempted.
        scope.close()


if __name__ == "__main__":
    raise SystemExit(main())
