#!/usr/bin/env python3
"""Read SDS800X HD protocol-decode selection/protocol/result queries (read-only).

This fetches documented decode-related queries over raw SCPI TCP port 5025. It
never changes scope or decode configuration.

Firmware-scoped notes (SDS824X HD, firmware 4.8.12.1.1.6.5, SCPI TCP 5025,
observed): do not guess command names such as DEC1/DEC:A/D1; undefined queries
return 0 bytes and queue -113. LIST/BUS RESult responses are multi-line ASCII
text (not IEEE 488.2 blocks), so a single readline() would keep only the header
and desynchronize the stream. This script drains the full response with an idle
timeout after the first byte arrives (heuristic; end status is reported).
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
from typing import Any

# Read-only, documented/firmware-observed decode state queries. Keep this set
# conservative: every command is a query and targets decode/system identity/error
# diagnostics only.
DECODE_QUERIES = (
    "DEC?",  # global decode enable (firmware-observed short form)
    ":DECode:LIST?",
    ":DECode:LIST:LINE?",
    ":DECode:BUS1:PROTocol?",
    ":DECode:BUS2:PROTocol?",
    ":DECode:BUS1:RESult?",
    ":DECode:LIST1:RESult?",
    ":DECode:BUS2:RESult?",
    ":DECode:LIST2:RESult?",
)

_QUERY_RE = re.compile(r"^:?[A-Za-z][A-Za-z0-9:_-]*\?$")


class DecodeReadError(RuntimeError):
    pass


def _assert_positive(name: str, value: float) -> None:
    if not isinstance(value, (int, float)) or value <= 0:
        raise DecodeReadError(f"{name} must be > 0")


def _validate_query(command: str) -> str:
    cmd = command.strip()
    if not cmd.endswith("?"):
        raise DecodeReadError(f"read-only query required (must end with '?'): {command!r}")
    if any(ch in cmd for ch in ("\n", "\r", ";")):
        raise DecodeReadError(f"compound/multi-line commands are not allowed: {command!r}")
    # Allow the single common-status identity query used by this script; reject
    # other '*' common commands to keep the helper narrowly read-only.
    if cmd.upper() == "*IDN?":
        return cmd
    if not _QUERY_RE.match(cmd):
        raise DecodeReadError(f"unsupported query syntax: {command!r}")
    return cmd


def _decode_text(raw: bytes) -> dict[str, Any]:
    """Decode for display while reporting lossiness."""
    try:
        text = raw.decode("utf-8")
        return {"text": text, "encoding": "utf-8", "decode_errors": 0}
    except UnicodeDecodeError:
        # latin-1 preserves byte values for display fallback; raw bytes are not
        # modified. Callers should treat non-zero decode_errors as a caveat.
        text = raw.decode("utf-8", "replace")
        return {"text": text, "encoding": "utf-8(replace)", "decode_errors": text.count("\ufffd")}


def _connect(host: str, port: int, timeout: float) -> socket.socket:
    if port == 5024:
        raise DecodeReadError("port 5024 is the legacy shell channel; use SCPI TCP port 5025")
    return socket.create_connection((host, port), timeout=timeout)


def query_text(
    host: str,
    port: int,
    command: str,
    *,
    timeout: float = 4.0,
    idle: float = 0.6,
    first_byte_timeout: float | None = None,
) -> dict[str, Any]:
    """Send one read-only query and return raw bytes plus end-status metadata.

    The idle-timeout heuristic is intentional: decode LIST/BUS results are
    multi-line ASCII with no definite-length framing. ``end_reason`` and
    ``likely_complete`` make truncation visible instead of silent.
    """
    cmd = _validate_query(command)
    _assert_positive("timeout", timeout)
    _assert_positive("idle", idle)
    first_timeout = timeout if first_byte_timeout is None else first_byte_timeout
    _assert_positive("first_byte_timeout", first_timeout)

    with _connect(host, port, timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall((cmd + "\n").encode("ascii"))
        sock.settimeout(first_timeout)
        chunks: list[bytes] = []
        end_reason = "unknown"
        while True:
            try:
                data = sock.recv(65536)
            except socket.timeout:
                if chunks:
                    end_reason = "idle_timeout"
                else:
                    end_reason = "first_byte_timeout"
                break
            except (BlockingIOError, InterruptedError):
                end_reason = "recv_error"
                break
            if not data:
                end_reason = "connection_closed"
                break
            chunks.append(data)
            sock.settimeout(idle)

        raw = b"".join(chunks)
        result: dict[str, Any] = {
            "command": cmd,
            "bytes": len(raw),
            "raw": raw,
            "end_reason": end_reason,
        }
        result.update(_decode_text(raw))
        if raw:
            # Idle timeout after data is the expected end for these text results;
            # missing final newline is still reported as a truncation risk.
            result["likely_complete"] = raw.endswith(b"\n") and end_reason in {
                "idle_timeout",
                "connection_closed",
            }
            result["truncated_risk"] = not result["likely_complete"]
            if result["truncated_risk"]:
                result["warning"] = (
                    "response may be truncated (no final newline or unexpected end). "
                    "Treat as no complete decoded evidence; increase --idle/--first-byte-timeout if needed."
                )
        else:
            result["likely_complete"] = False
            result["truncated_risk"] = False
        return result


def drain_system_errors(
    host: str,
    port: int,
    *,
    timeout: float = 4.0,
    idle: float = 0.4,
    limit: int = 32,
) -> dict[str, Any]:
    """Drain SYST:ERR? on a fresh connection until 0/queue-empty or limit."""
    entries: list[str] = []
    terminated = False
    for _ in range(limit):
        item = query_text(host, port, "SYST:ERR?", timeout=timeout, idle=idle)
        text = item.get("text", "").strip()
        if re.match(r"\+?0(\D|$)", text):
            terminated = True
            break
        if not text and item.get("end_reason") == "first_byte_timeout":
            entries.append("<SYST:ERR? no response>")
            terminated = False
            break
        entries.append(text or f"<empty:{item.get('end_reason')}>")
    return {
        "entries": entries,
        "terminated": terminated,
        "not_empty_after_limit": not terminated and len(entries) >= limit,
    }


def query_text_with_diagnosis(host: str, port: int, command: str, **kwargs: Any) -> dict[str, Any]:
    result = query_text(host, port, command, **kwargs)
    # Do not ship raw bytes in the default JSON-oriented report; keep text/status.
    result.pop("raw", None)
    if result["bytes"] == 0:
        # Undefined-header queries return 0 bytes and queue -113 on this
        # firmware. Read/drain on a fresh connection to avoid buffer skew.
        try:
            result["system_error"] = drain_system_errors(
                host, port, timeout=kwargs.get("timeout", 4.0), idle=0.4
            )
        except Exception as exc:  # noqa: BLE001 - diagnostic best effort
            result["system_error_lookup_failed"] = f"{type(exc).__name__}: {exc}"
        result["warning"] = (
            "no response bytes; possible undefined header (-113) or first-byte timeout. "
            "Do not reuse a connection after an unanswered query."
        )
    return result


def fetch_decode_state(
    host: str,
    port: int,
    commands: list[str] | tuple[str, ...] = DECODE_QUERIES,
    *,
    timeout: float = 4.0,
    idle: float = 0.6,
    first_byte_timeout: float | None = None,
    include_identity: bool = True,
) -> dict[str, Any]:
    _assert_positive("timeout", timeout)
    _assert_positive("idle", idle)
    report: dict[str, Any] = {
        "host": host,
        "port": port,
        "mode": "read_only_decode_query",
        "timeout_s": timeout,
        "idle_s": idle,
        "first_byte_timeout_s": timeout if first_byte_timeout is None else first_byte_timeout,
        "queries": [],
        "notes": [
            "LIST<n>:RESult? is the preferred full decode table; parse its header (columns vary by protocol).",
            "BUS<n>:RESult? is a visible screen summary and may be incomplete when many events exist.",
            "Header-only/empty results mean no decoded evidence, not a passing protocol.",
            "Idle-timeout multiline reads are heuristic; check likely_complete/truncated_risk before analysis.",
        ],
    }
    if include_identity:
        try:
            idn = query_text(host, port, "*IDN?", timeout=timeout, idle=idle)
            report["identity"] = idn.get("text", "").strip()
            report["identity_query"] = {
                "end_reason": idn.get("end_reason"),
                "likely_complete": idn.get("likely_complete"),
            }
        except Exception as exc:  # noqa: BLE001 - best effort, still attempt decode queries
            report["identity_warning"] = f"{type(exc).__name__}: {exc}"

    report["queries"] = [
        query_text_with_diagnosis(
            host,
            port,
            command,
            timeout=timeout,
            idle=idle,
            first_byte_timeout=first_byte_timeout,
        )
        for command in commands
    ]
    return report


def _print_text(report: dict[str, Any]) -> None:
    ident = report.get("identity")
    head = f"# decode read-only {report['host']}:{report['port']}"
    print(head)
    if ident:
        print(f"identity: {ident}")
    elif report.get("identity_warning"):
        print(f"identity warning: {report['identity_warning']}")
    for item in report["queries"]:
        print(f"\n== {item['command']} ==")
        status = f"[end={item.get('end_reason')} complete={item.get('likely_complete')}]"
        if item["bytes"] == 0:
            print(f"<no response> {status}")
            err = item.get("system_error") or {}
            for entry in err.get("entries", []):
                print(f"SYST:ERR? {entry}")
            if err.get("not_empty_after_limit"):
                print("SYST:ERR? <queue not empty after limit>")
            if item.get("warning"):
                print(f"warning: {item['warning']}")
            continue
        if item.get("warning") or item.get("truncated_risk"):
            print(f"status: {status}")
        if item.get("warning"):
            print(f"warning: {item['warning']}")
        if item.get("decode_errors"):
            print(f"warning: {item['decode_errors']} UTF-8 replacement chars")
        sys.stdout.write(item.get("text", ""))
        if item.get("text") and not item["text"].endswith("\n"):
            sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.10.2")
    parser.add_argument("--port", type=int, default=5025)
    parser.add_argument("--timeout", type=float, default=4.0, help="connect/send/first-byte timeout seconds")
    parser.add_argument("--idle", type=float, default=0.6, help="idle timeout seconds after first byte")
    parser.add_argument("--first-byte-timeout", type=float, default=None, help="override first-byte timeout")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--no-idn", action="store_true", help="skip *IDN? (not recommended)")
    args = parser.parse_args(argv)

    try:
        report = fetch_decode_state(
            args.host,
            args.port,
            timeout=args.timeout,
            idle=args.idle,
            first_byte_timeout=args.first_byte_timeout,
            include_identity=not args.no_idn,
        )
    except (OSError, DecodeReadError, ValueError) as exc:
        print(f"decode read failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

