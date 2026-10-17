#!/usr/bin/env python3
"""Generate bounded, evidence-linked JSON analyses from an SDS capture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from waveform_analysis import (
    DEFAULT_CHUNK_POINTS,
    DEFAULT_EVENT_PAGE,
    DEFAULT_EVENT_SCAN_BUDGET,
    DEFAULT_JSON_BYTES,
    DEFAULT_PREVIEW_BUCKETS,
    DEFAULT_WINDOW_POINTS,
    AnalysisError,
    analyze_ringing,
    bound_json,
    error_envelope,
    find_events,
    get_window,
    load_capture,
    summarize_capture,
)


def _add_capture_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--capture", type=Path, required=True, help="capture directory or manifest.json")
    parser.add_argument("--channel", required=True, help="channel name present in the capture manifest, normally C1-C4")
    parser.add_argument("--calibration", type=Path, help="explicit calibration JSON, including independent WORD evidence")
    parser.add_argument("--vdiv", type=float, help="explicit probe-compensated physical V/div")
    parser.add_argument("--offset", type=float, help="explicit physical offset in volts")
    parser.add_argument("--max-json-bytes", type=int, default=DEFAULT_JSON_BYTES)
    parser.add_argument("--out", type=Path, help="write JSON outside the capture directory instead of stdout")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    inspect = commands.add_parser("inspect", help="validate capture integrity and describe its calibration")
    _add_capture_args(inspect)

    summary = commands.add_parser("summarize", help="full-record statistics and M4 visualization preview")
    _add_capture_args(summary)
    summary.add_argument("--chunk-points", type=int, default=DEFAULT_CHUNK_POINTS)
    summary.add_argument("--preview-buckets", type=int, default=DEFAULT_PREVIEW_BUCKETS)

    events = commands.add_parser("events", help="scan full-resolution threshold edges and pulse timing")
    _add_capture_args(events)
    threshold = events.add_mutually_exclusive_group(required=True)
    threshold.add_argument("--threshold-codes", nargs=2, type=float, metavar=("LOW", "HIGH"))
    threshold.add_argument("--threshold-volts", nargs=2, type=float, metavar=("LOW", "HIGH"))
    events.add_argument("--min-pulse-s", type=float)
    events.add_argument("--expected-period-s", type=float)
    events.add_argument("--period-tolerance", type=float, default=0.1)
    events.add_argument("--chunk-points", type=int, default=DEFAULT_CHUNK_POINTS)
    events.add_argument("--max-events-scanned", type=int, default=DEFAULT_EVENT_SCAN_BUDGET)
    events.add_argument("--limit", type=int, default=DEFAULT_EVENT_PAGE)
    events.add_argument("--cursor")
    events.add_argument("--start-time-s", "--start-time", dest="start_time_s", type=float, help="optional relative display-time scan start")
    events.add_argument("--end-time-s", "--end-time", dest="end_time_s", type=float, help="optional relative display-time scan end (exclusive)")

    window = commands.add_parser("window", help="retrieve a bounded raw sample window")
    _add_capture_args(window)
    window.add_argument("--start", type=int, help="first sample index; use with --count")
    window.add_argument("--count", type=int, help="number of samples; defaults to the bounded window size for sample-index mode")
    window.add_argument("--start-time-s", "--start-time", dest="start_time_s", type=float, help="relative display-time window start; use with --end-time-s")
    window.add_argument("--end-time-s", "--end-time", dest="end_time_s", type=float, help="relative display-time window end (exclusive); use with --start-time-s")
    window.add_argument("--max-window-points", type=int, default=DEFAULT_WINDOW_POINTS)

    ringing = commands.add_parser("ringing", help="bounded switching-edge overshoot and ring-down screening")
    _add_capture_args(ringing)
    ringing.add_argument("--start", type=int, help="first sample index; use with --count")
    ringing.add_argument("--count", type=int, help="number of samples; use with --start")
    ringing.add_argument("--start-time-s", "--start-time", dest="start_time_s", type=float, help="relative display-time window start; use with --end-time-s")
    ringing.add_argument("--end-time-s", "--end-time", dest="end_time_s", type=float, help="relative display-time window end (exclusive); use with --start-time-s")
    ringing.add_argument("--max-window-points", type=int, default=DEFAULT_WINDOW_POINTS)
    return parser


def _inspect(capture: dict[str, Any]) -> dict[str, Any]:
    preamble = capture["preamble"]
    return {
        "schema_version": "1.0",
        "tool": "inspect",
        "capture": {
            "id": capture["manifest"].get("idn", capture["manifest_path"].parent.name),
            "channel": capture["channel"],
            "path": str(capture["path"]),
            "raw_sha256": capture["raw_sha256"],
            "points": capture["points"],
            "bytes": capture["bytes"],
            "bytes_per_point": capture["width"],
            "descriptor": {
                "comm_type": preamble.get("comm_type"),
                "comm_order": preamble.get("comm_order"),
                "byte_order": preamble.get("byte_order"),
                "nominal_bits": preamble.get("nominal_bits"),
                "sparsing_factor": preamble.get("sparsing_factor"),
                "vdiv": preamble.get("vdiv"),
                "probe": preamble.get("probe"),
                "offset": preamble.get("offset"),
                "code_per_div": preamble.get("code_per_div"),
            },
        },
        "integrity": capture["integrity"],
        "sampling": {
            "interval_s": capture["sample_interval_s"],
            "rate_hz": capture["sample_rate_hz"],
            "origin_s": capture["time_origin_s"],
            "time_reference": "relative waveform/display time, not wall-clock time",
        },
        "calibration": capture["calibration"],
        "limitations": (["WORD voltage scale is not independently verified"] if capture["width"] == 2 and capture["calibration"]["status"] != "VALID" else []) + capture["calibration"].get("verification_failures", []),
    }


def _ensure_output_is_external(output: Path, capture_dir: Path) -> Path:
    output = output.expanduser().resolve()
    capture_dir = capture_dir.resolve()
    try:
        output.relative_to(capture_dir)
    except ValueError:
        return output
    raise AnalysisError("LIMIT_INVALID", "Analysis JSON must be written outside the raw capture directory")


def _emit(args: argparse.Namespace, value: dict[str, Any]) -> None:
    value = bound_json(value, args.max_json_bytes)
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)
    if args.out:
        output = _ensure_output_is_external(args.out, args.capture if args.capture.is_dir() else args.capture.parent)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)


def _run(args: argparse.Namespace) -> dict[str, Any]:
    capture = load_capture(
        args.capture,
        args.channel,
        calibration_file=args.calibration,
        vdiv_override=args.vdiv,
        offset_override=args.offset,
    )
    if args.command == "inspect":
        return _inspect(capture)
    if args.command == "summarize":
        return summarize_capture(capture, chunk_points=args.chunk_points, preview_buckets=args.preview_buckets)
    if args.command == "events":
        if args.threshold_codes:
            low, high = args.threshold_codes
            domain = "code"
        else:
            low, high = args.threshold_volts
            domain = "voltage"
        return find_events(
            capture,
            low=low,
            high=high,
            domain=domain,
            min_pulse_s=args.min_pulse_s,
            expected_period_s=args.expected_period_s,
            period_tolerance=args.period_tolerance,
            chunk_points=args.chunk_points,
            max_events_scanned=args.max_events_scanned,
            limit=args.limit,
            cursor=args.cursor,
            start_time_s=args.start_time_s,
            end_time_s=args.end_time_s,
        )
    if args.command == "window":
        sample_count = args.count
        if args.start_time_s is None and args.end_time_s is None and sample_count is None:
            sample_count = DEFAULT_WINDOW_POINTS
        return get_window(
            capture,
            args.start,
            sample_count,
            start_time_s=args.start_time_s,
            end_time_s=args.end_time_s,
            max_points=args.max_window_points,
        )
    if args.command == "ringing":
        return analyze_ringing(
            capture,
            start=args.start,
            count=args.count,
            start_time_s=args.start_time_s,
            end_time_s=args.end_time_s,
            max_points=args.max_window_points,
        )
    raise AnalysisError("LIMIT_INVALID", f"Unknown command {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _emit(args, _run(args))
        return 0
    except AnalysisError as exc:
        envelope = error_envelope(args.command, getattr(args, "channel", None), exc)
        sys.stdout.write(json.dumps(envelope, indent=2, sort_keys=True, allow_nan=False) + "\n")
        return 2
    except (OSError, ValueError, OverflowError) as exc:
        error = AnalysisError("ANALYSIS_FAILED", str(exc))
        envelope = error_envelope(args.command, getattr(args, "channel", None), error)
        sys.stdout.write(json.dumps(envelope, indent=2, sort_keys=True, allow_nan=False) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
