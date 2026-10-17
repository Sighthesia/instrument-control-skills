#!/usr/bin/env python3
"""Discover Siglent SDS800X HD instruments without changing instrument state.

The script performs only transport-level discovery and ``*IDN?`` identity
checks. It never configures LAN settings, mounts network storage, starts an
acquisition, or writes a file to the instrument.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable, Optional


DEFAULT_PORT = 5025
DEFAULT_TIMEOUT_S = 0.5
DEFAULT_MAX_HOSTS = 256
DEFAULT_WORKERS = 32
TARGET_VENDOR = "siglent"


def parse_idn(response: str) -> dict[str, str]:
    """Parse an IEEE 488.2 identification response conservatively."""

    text = response.replace("\x00", "").strip()
    fields = [field.strip() for field in text.split(",", 3)]
    return {
        "raw": text,
        "manufacturer": fields[0] if fields else "",
        "model": fields[1] if len(fields) > 1 else "",
        "serial": fields[2] if len(fields) > 2 else "",
        "firmware": fields[3] if len(fields) > 3 else "",
    }


def is_target_idn(idn: dict[str, str]) -> bool:
    """Return true for a Siglent SDS model, including SDS800X HD variants."""

    return TARGET_VENDOR in idn["manufacturer"].lower() and "sds" in idn["model"].lower()


def _read_idn(sock: socket.socket, *, max_bytes: int = 4096) -> str:
    """Read a text response while tolerating banners and empty lines."""

    data = bytearray()
    while len(data) < max_bytes:
        chunk = sock.recv(min(1024, max_bytes - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        lines = data.replace(b"\r", b"").split(b"\n")
        for line in lines[:-1]:
            text = line.replace(b"\x00", b"").decode("ascii", errors="replace").strip()
            if not text or text == ">>" or text.startswith("Welcome to the SCPI instrument"):
                continue
            return text
    text = data.replace(b"\x00", b"").decode("ascii", errors="replace").strip()
    if text and text != ">>" and not text.startswith("Welcome to the SCPI instrument"):
        return text.splitlines()[-1].strip()
    raise ValueError("no usable ASCII response to *IDN?")


def probe_lan_host(host: str, *, port: int = DEFAULT_PORT, timeout_s: float = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """Probe one raw-SCPI endpoint and always return a JSON-safe result."""

    result: dict[str, Any] = {"transport": "lan-socket", "host": host, "port": port}
    try:
        with socket.create_connection((host, port), timeout=timeout_s) as sock:
            sock.settimeout(timeout_s)
            sock.sendall(b"*IDN?\n")
            idn = parse_idn(_read_idn(sock))
        result.update({"status": "ok", "idn": idn, "target": is_target_idn(idn)})
    except (OSError, TimeoutError, ValueError) as exc:
        result.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
    return result


def discover_lan(
    network: str,
    *,
    port: int = DEFAULT_PORT,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_hosts: int = DEFAULT_MAX_HOSTS,
    workers: int = DEFAULT_WORKERS,
) -> dict[str, Any]:
    """Probe a bounded IPv4 network concurrently and retain successful hosts."""

    parsed = ipaddress.ip_network(network, strict=False)
    hosts = list(parsed.hosts())
    if len(hosts) > max_hosts:
        raise ValueError(f"network contains {len(hosts)} hosts; max_hosts is {max_hosts}")
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(max(1, workers), max(1, len(hosts)))) as pool:
        futures = [pool.submit(probe_lan_host, str(host), port=port, timeout_s=timeout_s) for host in hosts]
        for future in as_completed(futures):
            result = future.result()
            if result["status"] == "ok":
                results.append(result)
            elif len(errors) < 20:
                errors.append(result)
    results.sort(key=lambda item: item["host"])
    return {"transport": "lan-socket", "network": network, "scanned": len(hosts), "results": results, "errors": errors, "error_count": len(hosts) - len(results)}


def discover_ips(
    hosts: Iterable[str], *, port: int = DEFAULT_PORT, timeout_s: float = DEFAULT_TIMEOUT_S
) -> dict[str, Any]:
    """Probe explicitly supplied addresses without expanding a network."""

    results = [probe_lan_host(host, port=port, timeout_s=timeout_s) for host in hosts]
    return {
        "transport": "lan-socket",
        "scanned": len(results),
        "results": [result for result in results if result["status"] == "ok"],
        "errors": [result for result in results if result["status"] != "ok"],
        "error_count": sum(result["status"] != "ok" for result in results),
    }


def discover_usb(*, timeout_ms: int = 1000) -> dict[str, Any]:
    """Enumerate USBTMC VISA resources, returning a dependency error if absent."""

    try:
        import pyvisa  # type: ignore[import-not-found]
    except ImportError as exc:
        return {"transport": "usb-visa", "status": "error", "error": "PyVISA is not installed", "detail": str(exc)}

    manager = None
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    try:
        manager = pyvisa.ResourceManager()
        resources = manager.list_resources("USB?*INSTR")
        for resource_name in resources:
            instrument = None
            try:
                instrument = manager.open_resource(resource_name)
                instrument.timeout = timeout_ms
                idn = parse_idn(instrument.query("*IDN?"))
                results.append({"transport": "usb-visa", "resource": resource_name, "status": "ok", "idn": idn, "target": is_target_idn(idn)})
            except Exception as exc:  # VISA backends expose several exception types.
                errors.append({"transport": "usb-visa", "resource": resource_name, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
            finally:
                if instrument is not None:
                    instrument.close()
        return {"transport": "usb-visa", "status": "ok", "scanned": len(resources), "results": results, "errors": errors}
    except Exception as exc:  # Backend/driver failures are actionable, not an empty scan.
        return {"transport": "usb-visa", "status": "error", "error": f"{type(exc).__name__}: {exc}", "results": results, "errors": errors}
    finally:
        if manager is not None:
            manager.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usb", action="store_true", help="enumerate USBTMC VISA resources")
    parser.add_argument("--lan", metavar="CIDR", help="probe a bounded IPv4 network, for example 192.168.1.0/24")
    parser.add_argument("--ip", action="append", default=[], help="probe one IPv4 address; repeat for multiple addresses")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="per-host LAN timeout in seconds")
    parser.add_argument("--usb-timeout-ms", type=int, default=1000)
    parser.add_argument("--max-hosts", type=int, default=DEFAULT_MAX_HOSTS)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--all", action="store_true", help="retain non-Siglent/non-SDS successful LAN and USB responses")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not (args.usb or args.lan or args.ip):
        raise SystemExit("choose at least one of --usb, --lan, or --ip")
    if args.port == 5024:
        raise SystemExit("refusing legacy shell port 5024; use SCPI TCP port 5025")
    if args.timeout <= 0 or args.max_hosts <= 0 or args.workers <= 0:
        raise SystemExit("timeout, max-hosts, and workers must be positive")

    report: dict[str, Any] = {"schema_version": "1.0", "tool": "discover_scope", "results": []}
    if args.usb:
        report["usb"] = discover_usb(timeout_ms=args.usb_timeout_ms)
        report["results"].extend(report["usb"].get("results", []))
    if args.lan:
        report["lan"] = discover_lan(args.lan, port=args.port, timeout_s=args.timeout, max_hosts=args.max_hosts, workers=args.workers)
        report["results"].extend(report["lan"]["results"])
    if args.ip:
        report["explicit_ips"] = discover_ips(args.ip, port=args.port, timeout_s=args.timeout)
        report["results"].extend(report["explicit_ips"]["results"])
    if not args.all:
        report["results"] = [result for result in report["results"] if result.get("target")]
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
