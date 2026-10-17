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
from pathlib import Path
from typing import Optional

from scope_protocol import (
    ScopeProtocolError,
    ScopeSession,
    Segment,
    scope_assume_existing_stop,
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


def wait_state(scope: ScopeSession, wanted: str, timeout_s: float, poll_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = scope.query_ascii("SAST?").strip()
        normalized = state.upper()
        if normalized == "READY":
            scope.mark_state("Ready")
        elif normalized == "STOP":
            scope.mark_state("Stop")
        if normalized == wanted.upper():
            return
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
    scope.write(f"WAV:STAR {start}", allow_after_stop=True)
    scope.write(f"WAV:POIN {count}", allow_after_stop=True)
    actual_start = int(float(scope.query_ascii("WAV:STAR?", allow_after_stop=True)))
    actual_count = int(float(scope.query_ascii("WAV:POIN?", allow_after_stop=True)))
    if actual_start != start or actual_count != count:
        raise ScopeProtocolError(f"scope selected {actual_start},{actual_count}; expected {start},{count}")
    block = scope.query_block("WAV:DATA?", allow_after_stop=True)
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
        "scope_start": actual_start,
        "scope_points": actual_count,
        "actual_payload_bytes": len(block.payload),
        "actual_points": segment.actual_points,
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
    with partial_path.open("wb") as output:
        for segment in segment_files:
            output.write(Path(segment["payload"]).read_bytes())
    partial_path.replace(output_path)
    return output_path


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
) -> dict:
    channel_snapshot = {}
    for suffix, key in (("VDIV?", "vdiv"), ("OFST?", "offset")):
        channel_snapshot[key] = scope.query_ascii(f"{channel}:{suffix}", allow_after_stop=True)
    for command, key in (("SARA?", "sample_rate"), ("TDIV?", "timebase"), ("TRDL?", "trigger_delay"), ("WFSU?", "waveform_setup")):
        channel_snapshot[key] = scope.query_ascii(command, allow_after_stop=True)
    scope.write(f"WAV:SOUR {channel}", allow_after_stop=True)
    scope.write("WAV:WIDT BYTE", allow_after_stop=True)
    scope.write("WAV:INT 1", allow_after_stop=True)
    scope.write("WAV:STAR 0", allow_after_stop=True)
    scope.write("WAV:POIN 0", allow_after_stop=True)
    preamble_block = scope.query_block("WAV:PRE?", allow_after_stop=True)
    preamble = parse_wavedesc(preamble_block.payload)
    expected_points = preamble["wave_array_count"]
    if preamble["data_width_bytes"] != 1:
        raise ScopeProtocolError("modern capture requested BYTE but preamble reports non-byte data")
    if preamble["wave_array_1_bytes"] != expected_points:
        raise ScopeProtocolError(
            f"BYTE preamble reports {expected_points} points but {preamble['wave_array_1_bytes']} data bytes"
        )
    max_points_text = scope.query_ascii("WAV:MAXP?", allow_after_stop=True)
    max_points = int(float(max_points_text))
    probes = run_modern_probes(scope, root, channel, preamble, max_points, probe_points or [])
    step = min(segment_points, max_points) if max_points > 0 else segment_points
    segments: list[Segment] = []
    segment_files: list[dict] = []
    start = 0
    index = 0
    while start < expected_points:
        count = min(step, expected_points - start)
        stem = f"segment-{index:06d}"
        segment, metadata = read_modern_segment(scope, root, channel, stem, start, count, preamble)
        segments.append(segment)
        metadata["command_snapshot"] = channel_snapshot
        save_json(root / channel / f"{stem}.json", metadata)
        segment_files.append(metadata)
        start += count
        index += 1
    segment_report = validate_segments(
        segments,
        expected_points=expected_points,
        sample_interval_s=preamble["sample_interval"],
        time_origin_s=preamble["horizontal_offset"] - preamble["timebase_s"] * 5,
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
    )
    preamble_path = root / channel / "preamble.payload.bin"
    preamble_path.write_bytes(preamble_block.payload)
    preamble_raw_path = root / channel / "preamble.response.bin"
    preamble_prefix_path = root / channel / "preamble.prefix.bin"
    preamble_raw_path.write_bytes(preamble_block.raw)
    preamble_prefix_path.write_bytes(preamble_block.prefix)
    result = {"channel": channel, "mode": scope.capture_mode, "preamble": preamble, "preamble_payload": str(preamble_path), "preamble_raw_response": str(preamble_raw_path), "preamble_prefix": str(preamble_prefix_path), "segments": segment_files, "segment_report": segment_report, "frame_report": frame_report}
    result["probes"] = probes
    if segment_report["status"] == "COMPLETE":
        merged_path = merge_segment_payloads(root, channel, segment_files, "waveform.bin")
        result["merged_waveform"] = str(merged_path)
        result["merged_waveform_bytes"] = merged_path.stat().st_size
        result["merged_waveform_sha256"] = hashlib.sha256(merged_path.read_bytes()).hexdigest()
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
    parser.add_argument("--probe-points", default="10000,1000000", help="comma-separated preflight WAV probe sizes; use empty string to disable")
    parser.add_argument("--prepare", action="store_true", help="write the handover's capture configuration")
    parser.add_argument("--trigger", action="store_true", help="issue TRMD SINGLE and wait Ready -> Stop")
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
        manifest["capture_configuration"] = scope_snapshot_configuration(scope, args.channels)
        if args.trigger:
            scope.write("TRMD SINGLE")
            wait_state(scope, "READY", args.ready_timeout, args.poll)
            wait_state(scope, "STOP", args.stop_timeout, args.poll)
        elif args.existing_stopped:
            scope_assume_existing_stop(scope)
        else:
            raise SystemExit("Use --trigger for a new capture or --existing-stopped for the current stopped frame")
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
                manifest["results"].append(read_modern_channel(scope, args.out, channel, args.segment_points, scope_points, scope_duration, trigger_relative, probe_points))
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
