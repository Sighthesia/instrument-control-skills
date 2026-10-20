#!/usr/bin/env python3
"""Optional live transport for the Keithley Model 2000 over RS-232.

The module imports pyserial lazily. ``--dry-run`` records the exact bytes that
would be sent and never opens a serial port. Commands are written one at a time
with a CR terminator, and every query consumes exactly one CR/LF-terminated
response before the next command is sent.

Safety defaults:

* ``read``/``walk`` refuse current functions unless ``--allow-current`` is given,
  because the AMPS path must already be wired in series by the operator.
* ``walk`` requires ``--confirm-open-input`` because it assumes disconnected
  leads and reports overflow as expected behaviour.
* reset/clear/calibration writes are refused unless ``--allow-state-change`` is
  given; no subcommand needs them for a normal measurement.
* ``config`` changes only the requested NPLC/digits/filter/REL values, reads
  them back, and drains the error queue; ``constants`` is query-only.
* A non-blocking ``flock`` prevents two sessions from sharing the port; a second
  concurrent command fails instead of interleaving responses.

The guard list is a prefix match on the command text, not a security boundary:
an abbreviation that does not match the listed prefixes will be forwarded.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keithley2000_protocol import (  # noqa: E402
    default_unit,
    normalize_function,
    parse_config,
    parse_error_queue,
    parse_identity,
    sense_path,
)
from keithley2000_scalar import parse_response  # noqa: E402

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 9600
DEFAULT_TIMEOUT = 3.0
MAX_RESPONSE_BYTES = 65_536
MAX_QUEUE_DRAIN = 12

FORBIDDEN_WRITES = (
    "*RST",
    "*CLS",
    "*TRG",
    ":SYSTem:PRESet",
    ":SYST:PRES",
    ":CALibration",
    ":CAL:PROT",
    ":SYSTem:AZERo:STATe",
    ":SYST:AZER",
    ":INITiate:CONTinuous",  # allowed only through explicit restore flows
    ":INIT:CONT",
)

CURRENT_FUNCTIONS = {"CURR:DC", "CURR:AC"}
NPLC_FUNCTIONS = {"VOLT:DC", "VOLT:AC", "CURR:DC", "CURR:AC", "RES", "FRES", "TEMP"}
DIGITS_FUNCTIONS = {"VOLT:DC", "VOLT:AC", "CURR:DC", "CURR:AC", "RES", "FRES",
                    "FREQ", "PER", "TEMP"}
FILTER_FUNCTIONS = {"VOLT:DC", "VOLT:AC", "CURR:DC", "CURR:AC", "RES", "FRES", "TEMP"}
REFERENCE_FUNCTIONS = {"VOLT:DC", "VOLT:AC", "CURR:DC", "CURR:AC", "RES", "FRES",
                       "FREQ", "PER", "TEMP"}
REFERENCE_LIMITS = {
    "VOLT:DC": (-1010.0, 1010.0),
    "VOLT:AC": (-757.5, 757.5),
    "CURR:DC": (-3.1, 3.1),
    "CURR:AC": (-3.1, 3.1),
    "RES": (0.0, 120e6),
    "FRES": (0.0, 120e6),
    "FREQ": (0.0, 1.5e7),
    "PER": (0.0, 1.0),
    "TEMP": (-200.0, 1372.0),
}

CONSTANT_QUERIES = (
    ("identity", "*IDN?"),
    ("options", "*OPT?"),
    ("scpi_version", ":SYSTem:VERSion?"),
    ("line_frequency", ":SYSTem:LFRequency?"),
    ("front_rear_switch", ":SYSTem:FRSWitch?"),
    ("power_on_setup", ":SYSTem:POSetup?"),
    ("autozero", ":SYSTem:AZERo:STATe?"),
    ("calibration_count", ":CAL:PROT:COUN?"),
    ("calibration_date", ":CAL:PROT:DATE?"),
    ("calibration_due", ":CAL:PROT:NDUE?"),
    ("calibration_lock", ":CAL:PROT:LOCK?"),
)

WALK_FUNCTIONS = (
    ("VOLTage:DC", "voltage-dc"),
    ("VOLTage:AC", "voltage-ac"),
    ("CURRent:DC", "current-dc"),
    ("CURRent:AC", "current-ac"),
    ("RESistance", "resistance-2w"),
    ("FRESistance", "resistance-4w"),
    ("FREQuency", "frequency"),
    ("PERiod", "period"),
    ("CONTinuity", "continuity"),
    ("DIODe", "diode"),
    ("TEMPerature", "temperature"),
)


class SessionError(RuntimeError):
    """A transport, ordering, or safety failure."""


def _serial_module():
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise SessionError(
            "pyserial is required for RS-232 transport; install it or use --dry-run"
        ) from exc
    return serial


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Session:
    """One RS-232 session: CR framing, one query -> one response."""

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baud: int = DEFAULT_BAUD,
        timeout: float = DEFAULT_TIMEOUT,
        dry_run: bool = False,
        allow_state_change: bool = False,
    ) -> None:
        if not 1200 <= baud <= 115200:
            raise SessionError("baud must be in 1200..115200")
        if timeout <= 0:
            raise SessionError("timeout must be positive")
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.dry_run = dry_run
        self.allow_state_change = allow_state_change
        self.sent: list[bytes] = []
        self.exchange: list[dict[str, Any]] = []
        self._connection = None
        self._buffer = bytearray()
        self._desynced = False

    # -- transport ---------------------------------------------------------
    def _open(self) -> None:
        if self._connection is not None or self.dry_run:
            return
        serial = _serial_module()
        self._connection = serial.Serial(
            self.port,
            self.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        self._connection.reset_input_buffer()
        self._connection.reset_output_buffer()
        try:
            import fcntl
        except ImportError:  # non-POSIX host; no advisory lock available
            fcntl = None
        if fcntl is not None:
            try:
                fcntl.flock(self._connection.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, AttributeError) as exc:
                self._connection.close()
                self._connection = None
                raise SessionError(
                    "serial port is already open by another session; "
                    "close it before starting a second command"
                ) from exc

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _recv(self) -> bytes:
        assert self._connection is not None
        data = self._connection.read(1)
        if not data:
            raise SessionError("response timed out before a line terminator arrived")
        return data

    def _read_response(self) -> bytes:
        while True:
            positions = [index for index in (self._buffer.find(b"\r"), self._buffer.find(b"\n"))
                         if index >= 0]
            if positions:
                start = min(positions)
                first = bytes(self._buffer[start : start + 1])
                second = bytes(self._buffer[start + 1 : start + 2])
                length = 2 if (first, second) in {(b"\r", b"\n"), (b"\n", b"\r")} else 1
                data = bytes(self._buffer[: start + length])
                del self._buffer[: start + length]
                return data
            if len(self._buffer) > MAX_RESPONSE_BYTES:
                self._desynced = True
                raise SessionError("response exceeds the session size limit")
            self._buffer.extend(self._recv())

    def _guard(self, command: str) -> None:
        upper = command.strip().upper()
        if upper.endswith("?"):
            return  # queries never change state
        if self.allow_state_change:
            return
        for prefix in FORBIDDEN_WRITES:
            if upper.startswith(prefix.upper()):
                raise SessionError(
                    f"refusing state-changing command {command!r}; "
                    "rerun with --allow-state-change when that is intended"
                )

    # -- commands ----------------------------------------------------------
    def write(self, command: str) -> None:
        self._guard(command)
        payload = command.encode("ascii") + b"\r"
        self.sent.append(payload)
        self.exchange.append({"direction": "tx", "command": command,
                              "raw_hex": payload.hex(), "timestamp_utc": _now()})
        if self.dry_run:
            print(f"DRY-RUN SEND: {payload!r}")
            return
        if self._desynced:
            raise SessionError("session is out of sync after an earlier timeout")
        self._open()
        assert self._connection is not None
        self._connection.write(payload)
        self._connection.flush()

    def query(self, command: str) -> bytes:
        self.write(command)
        if self.dry_run:
            return b""
        if self._desynced:
            raise SessionError("session is out of sync after an earlier timeout")
        try:
            raw = self._read_response()
        except SessionError:
            self._desynced = True
            raise
        self.exchange.append({
            "direction": "rx",
            "command": command,
            "raw_hex": raw.hex(),
            "raw_ascii": raw.decode("latin-1"),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "timestamp_utc": _now(),
        })
        return raw

    def unblock(self) -> bytes:
        """Send a device clear (0x03) and verify the link with ``*IDN?``.

        An armed trigger (for example ``:TRIGger:SOURce BUS`` followed by
        ``:INITiate``) leaves a pending ``:FETCh?``/``:READ?`` in the output
        queue. Later queries then time out until the operation is cleared; the
        device clear is the only recovery this helper performs.
        """

        if self.dry_run:
            print("DRY-RUN SEND-BYTES: b'\\x03'")
            self.sent.append(b"\x03")
            self.exchange.append({"direction": "tx", "command": "<device-clear 0x03>",
                                  "raw_hex": "03", "timestamp_utc": _now()})
            return b""
        self._desynced = False
        self._buffer.clear()
        self._open()
        assert self._connection is not None
        self._connection.write(b"\x03")
        self._connection.flush()
        time.sleep(0.2)
        reset = getattr(self._connection, "reset_input_buffer", None)
        if callable(reset):
            reset()
        return self.query("*IDN?")

    def drain_errors(self) -> dict[str, Any]:
        """Drain ``:SYSTem:ERRor?`` until ``0,No error`` and parse the blobs."""

        blobs: list[bytes] = []
        for _ in range(MAX_QUEUE_DRAIN):
            raw = self.query(":SYSTem:ERRor?")
            if not raw:
                break
            blobs.append(raw)
            if raw.strip().lower() == b'0,"no error"':
                break
        return parse_error_queue(b"".join(blobs))

    def save_log(self, path: Path) -> Path:
        payload = {
            "schema_version": "keithley2000-session-log-v1",
            "port": self.port,
            "baud": self.baud,
            "framing": "8N1",
            "flow_control": "none",
            "tx_terminator": "CR (0x0D)",
            "dry_run": self.dry_run,
            "sent": [payload.hex() for payload in self.sent],
            "exchange": self.exchange,
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path


# -- command helpers -------------------------------------------------------
def _function_token(function: str) -> str:
    token = normalize_function(function)
    if token is None:
        raise SessionError(f"unknown function {function!r}")
    return token


def _range_targets(token: str, path: str) -> dict[str, str | None]:
    """Per-function command names for the range/threshold readback.

    Only voltage, current, and resistance use ``:RANGe[:UPPer]``; frequency and
    period use the threshold voltage range, continuity a resistance threshold,
    diode a current range, and temperature has no range at all.
    """

    if token in {"FREQ", "PER"}:
        return {"range": f":SENSe:{path}:THReshold:VOLTage:RANGe",
                "autorange": None}
    if token == "CONT":
        return {"range": ":SENSe:CONTinuity:THReshold", "autorange": None}
    if token == "DIOD":
        return {"range": ":SENSe:DIODe:CURRent:RANGe", "autorange": None}
    if token == "TEMP":
        return {"range": None, "autorange": None}
    return {"range": f":SENSe:{path}:RANGe",
            "autorange": f":SENSe:{path}:RANGe:AUTO"}


def _configure(session: Session, function: str, args: argparse.Namespace,
               apply: bool = True) -> dict[str, Any]:
    token = _function_token(function)
    configure_command = f":CONFigure:{function.strip()}"
    path = sense_path(token)
    assert path is not None
    targets = _range_targets(token, path)
    if args.range is not None and targets["range"] is None:
        raise SessionError(f"{token} has no selectable range")
    if args.autorange is not None and targets["autorange"] is None:
        raise SessionError(f"{token} has no autorange setting")
    if args.nplc is not None:
        if token not in NPLC_FUNCTIONS:
            raise SessionError(f"{token} does not support NPLC")
        if not 0.01 <= args.nplc <= 10:
            raise SessionError("NPLC must be in 0.01..10")
    if getattr(args, "digits", None) is not None:
        if token not in DIGITS_FUNCTIONS:
            raise SessionError(f"{token} does not support DIGits")
        if not 4 <= args.digits <= 7:
            raise SessionError("DIGits must be in 4..7")
    commands: list[str] = []

    def setting(command: str) -> None:
        if apply:
            session.write(command)
            commands.append(command)

    if apply:
        session.write(configure_command)
        commands.append(configure_command)
    if args.elements:
        setting(f":FORMat:ELEments {args.elements}")
    if args.nplc is not None:
        setting(f":SENSe:{path}:NPLCycles {args.nplc:g}")
    if getattr(args, "digits", None) is not None:
        setting(f":SENSe:{path}:DIGits {args.digits}")
    if args.range is not None:
        setting(f"{targets['range']} {args.range}")
    if args.autorange is not None:
        setting(f"{targets['autorange']} {'ON' if args.autorange else 'OFF'}")

    configuration: dict[str, Any] = {"applied": apply, "commands": commands, "readbacks": {}}
    queries = [":FUNCtion?"]
    if targets["range"]:
        queries.append(f"{targets['range']}?")
    if targets["autorange"]:
        queries.append(f"{targets['autorange']}?")
    if args.nplc is not None:
        queries.append(f":SENSe:{path}:NPLCycles?")
    if getattr(args, "digits", None) is not None:
        queries.append(f":SENSe:{path}:DIGits?")
    if token == "TEMP":
        queries.append(":SENSe:TEMPerature:TCouple:TYPE?")
        queries.append(":UNIT:TEMPerature?")

    if args.dry_run:
        for query in queries:
            session.query(query)
        return configuration

    for query in queries:
        raw = session.query(query)
        configuration["readbacks"][query] = parse_config(raw, query=query)
    return configuration


def _temperature_unit(configuration: dict[str, Any]) -> str | None:
    readback = configuration.get("readbacks", {}).get(":UNIT:TEMPerature?")
    if not readback:
        return None
    value = str(readback["configuration"]["value"]).strip().upper()
    return {"C": "C", "CEL": "C", "CELSIUS": "C",
            "F": "F", "FAR": "F", "FAHRENHEIT": "F", "K": "K"}.get(value)


def _read_once(session: Session, function: str, args: argparse.Namespace,
               index: int, unit: str | None = None) -> dict[str, Any]:
    raw = session.query(":READ?")
    unit = args.unit or unit or default_unit(function)
    context = {"function": function, "query": ":READ?", "acquisition_complete": True}
    if unit:
        context["unit"] = unit
        if not args.unit:
            context["unit_provenance"] = "function_default"
    artifact = parse_response(raw, context=context)
    if args.dry_run:
        artifact = {"raw": raw.hex(), "note": "dry-run: no response read"}
    artifact["index"] = index
    return artifact


def _apply_assessment(reading: dict[str, Any], verdict: dict[str, Any]) -> None:
    """Downgrade a structurally complete reading when the queue contradicts it."""

    integrity = reading.get("integrity")
    if not integrity:
        return
    if "init_ignored" in verdict["flags"] and integrity["status"] == "COMPLETE":
        integrity["status"] = "UNVERIFIED"
        integrity.setdefault("reasons", []).append("not_newly_triggered")


def _save_raw(directory: Path, name: str, artifact: dict[str, Any]) -> None:
    blob = artifact.get("integrity", {}).get("raw_response_base64")
    if not blob:
        return
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.txt").write_bytes(base64.b64decode(blob))


def _config_queries(token: str, path: str) -> dict[str, str]:
    queries = {"function": ":FUNCtion?"}
    if token in NPLC_FUNCTIONS:
        queries["nplc"] = f":SENSe:{path}:NPLCycles?"
    if token in DIGITS_FUNCTIONS:
        queries["digits"] = f":SENSe:{path}:DIGits?"
    if token in FILTER_FUNCTIONS:
        queries["filter_state"] = f":SENSe:{path}:AVERage:STATe?"
        queries["filter_type"] = f":SENSe:{path}:AVERage:TCONtrol?"
        queries["filter_count"] = f":SENSe:{path}:AVERage:COUNt?"
    if token in REFERENCE_FUNCTIONS:
        queries["reference"] = f":SENSe:{path}:REFerence?"
        queries["reference_state"] = f":SENSe:{path}:REFerence:STATe?"
    return queries


def _flag(artifact: dict[str, Any]) -> bool:
    value = artifact["configuration"].get("value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    return str(value).strip().upper() in {"1", "ON"}


def _filter_type(value: Any) -> str:
    text = str(value).strip().upper()
    return {"MOV": "moving", "MOVING": "moving", "REP": "repeat", "REPEAT": "repeat"}.get(text, text.lower())


def _settings_from_readbacks(readbacks: dict[str, Any]) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    if "function" in readbacks:
        configuration = readbacks["function"]["configuration"]
        settings["function"] = configuration.get("function") or configuration.get("value")
    if "nplc" in readbacks:
        settings["nplc"] = float(readbacks["nplc"]["configuration"]["value"])
    if "digits" in readbacks:
        settings["digits"] = int(round(float(readbacks["digits"]["configuration"]["value"])))
    if "filter_state" in readbacks:
        settings["filter"] = {
            "enabled": _flag(readbacks["filter_state"]),
            "type": _filter_type(readbacks["filter_type"]["configuration"]["value"]),
            "count": int(float(readbacks["filter_count"]["configuration"]["value"])),
        }
    if "reference" in readbacks:
        settings["rel"] = {
            "enabled": _flag(readbacks["reference_state"]),
            "reference": float(readbacks["reference"]["configuration"]["value"]),
        }
    return settings


def _print_settings(settings: dict[str, Any]) -> None:
    print(f"function: {settings.get('function')}")
    print(f"NPLC    : {settings.get('nplc', '-')}")
    print(f"digits  : {settings.get('digits', '-')}")
    filt = settings.get("filter")
    if filt:
        print(f"filter  : {'on' if filt['enabled'] else 'off'} "
              f"({filt['type']}, count {filt['count']})")
    else:
        print("filter  : -")
    rel = settings.get("rel")
    if rel:
        print(f"REL     : {'on' if rel['enabled'] else 'off'} "
              f"(reference {rel['reference']:g})")
    else:
        print("REL     : -")


def cmd_config(session: Session, args: argparse.Namespace) -> int:
    if args.function:
        token = _function_token(args.function)
        if token in CURRENT_FUNCTIONS and not args.allow_current:
            raise SessionError(
                "selecting a current function requires --allow-current and the front "
                "AMPS/INPUT LO path already wired in series"
            )
    else:
        if args.dry_run:
            raise SessionError("config --dry-run requires --function to plan the queries")
        raw = session.query(":FUNCtion?")
        artifact = parse_config(raw, query=":FUNCtion?")
        token = artifact["configuration"].get("function")
        if token is None:
            raise SessionError(f"cannot determine the active function from {raw!r}")
    path = sense_path(token)
    if path is None:
        raise SessionError(f"unknown function {token!r}")

    if args.nplc is not None:
        if token not in NPLC_FUNCTIONS:
            raise SessionError(f"{token} does not support NPLC")
        if not 0.01 <= args.nplc <= 10:
            raise SessionError("NPLC must be in 0.01..10")
    if args.digits is not None:
        if token not in DIGITS_FUNCTIONS:
            raise SessionError(f"{token} does not support DIGits")
        if not 4 <= args.digits <= 7:
            raise SessionError("DIGits must be in 4..7")
    if args.filter is not None or args.filter_type is not None or args.filter_count is not None:
        if token not in FILTER_FUNCTIONS:
            raise SessionError(f"{token} has no averaging filter")
    if args.filter_count is not None and not 1 <= args.filter_count <= 100:
        raise SessionError("filter count must be in 1..100")
    if args.rel is not None or args.rel_reference is not None or args.rel_acquire:
        if token not in REFERENCE_FUNCTIONS:
            raise SessionError(f"{token} has no REL/reference function")
    if args.rel_acquire and args.rel is None:
        raise SessionError("--rel-acquire requires --rel on or --rel off")
    if args.rel_reference is not None:
        low, high = REFERENCE_LIMITS[token]
        if not low <= args.rel_reference <= high:
            raise SessionError(f"reference must be in {low:g}..{high:g} for {token}")

    requested = {
        key: value for key, value in {
            "function": token if args.function else None,
            "nplc": args.nplc,
            "digits": args.digits,
            "filter": args.filter,
            "filter_type": args.filter_type,
            "filter_count": args.filter_count,
            "rel": args.rel,
            "rel_reference": args.rel_reference,
            "rel_acquire": args.rel_acquire or None,
        }.items() if value is not None
    }

    commands: list[str] = []

    def apply(command: str) -> None:
        session.write(command)
        commands.append(command)

    if args.function:
        apply(f':FUNCtion "{token}"')
    if args.nplc is not None:
        apply(f":SENSe:{path}:NPLCycles {args.nplc:g}")
    if args.digits is not None:
        apply(f":SENSe:{path}:DIGits {args.digits}")
    if args.filter_type is not None:
        apply(f":SENSe:{path}:AVERage:TCONtrol {args.filter_type}")
    if args.filter_count is not None:
        apply(f":SENSe:{path}:AVERage:COUNt {args.filter_count}")
    if args.filter is not None:
        apply(f":SENSe:{path}:AVERage:STATe {'ON' if args.filter == 'on' else 'OFF'}")
    if args.rel_reference is not None:
        apply(f":SENSe:{path}:REFerence {args.rel_reference:g}")
    if args.rel_acquire:
        # ACQuire captures the displayed reading, so REL must be off first.
        apply(f":SENSe:{path}:REFerence:STATe OFF")
        apply(f":SENSe:{path}:REFerence:ACQuire")
        if args.rel == "on":
            apply(f":SENSe:{path}:REFerence:STATe ON")
    elif args.rel is not None:
        apply(f":SENSe:{path}:REFerence:STATe {'ON' if args.rel == 'on' else 'OFF'}")

    readbacks: dict[str, Any] = {}
    for label, query in _config_queries(token, path).items():
        raw = session.query(query)
        if args.dry_run:
            continue
        readbacks[label] = parse_config(raw, query=query)
    if args.dry_run:
        return 0

    settings = _settings_from_readbacks(readbacks)
    queue = session.drain_errors()
    envelope = {
        "schema_version": "keithley2000-config-v1",
        "requested": requested,
        "commands": commands,
        "settings": settings,
        "readbacks": readbacks,
        "error_queue": queue,
    }
    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        session.save_log(out / "session.json")
        (out / "config.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    if args.json:
        json.dump(envelope, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _print_settings(settings)
        if any(record["code"] != 0 for record in queue["records"]):
            print(f"error queue: {[(r['code'], r['message']) for r in queue['records']]}")
    return 0


def _constant_text(raw: bytes) -> str:
    return raw.decode("ascii", "replace").strip().rstrip("\r")


def _calibration_due_in_past(text: str, today: date | None = None) -> bool | None:
    try:
        year, month, day = [int(part) for part in text.split(",")]
        due = date(year, month, day)
    except (TypeError, ValueError):
        return None
    return due < (today or date.today())


def _interpret_constants(raw_map: dict[str, bytes]) -> dict[str, Any]:
    text = {label: _constant_text(raw) for label, raw in raw_map.items()}
    identity = parse_identity(raw_map["identity"]).get("identity", {})
    options = text["options"]
    due_in_past = _calibration_due_in_past(text["calibration_due"])
    try:
        calibration_count: int | None = int(float(text["calibration_count"]))
    except ValueError:
        calibration_count = None
    try:
        line_frequency: float | None = float(text["line_frequency"])
    except ValueError:
        line_frequency = None
    return {
        "identity": identity,
        "options": options,
        "options_interpretation": ("no scanner option reported" if options == "0,0"
                                    else "see raw response"),
        "scpi_version": text["scpi_version"],
        "line_frequency_hz": line_frequency,
        "input_switch": {"1": "front", "0": "rear"}.get(text["front_rear_switch"],
                                                        text["front_rear_switch"]),
        "power_on_setup": text["power_on_setup"],
        "autozero": text["autozero"] in {"1", "ON"},
        "calibration": {
            "count": calibration_count,
            "date": text["calibration_date"],
            "due": text["calibration_due"],
            "due_in_past": due_in_past,
            "lock": {"0": "locked", "1": "unlocked"}.get(text["calibration_lock"],
                                                         text["calibration_lock"]),
        },
    }


def cmd_constants(session: Session, args: argparse.Namespace) -> int:
    raw_map: dict[str, bytes] = {}
    for label, query in CONSTANT_QUERIES:
        raw_map[label] = session.query(query)
    if args.dry_run:
        return 0
    constants = _interpret_constants(raw_map)
    readbacks = {
        label: {"query": query, "raw": _constant_text(raw_map[label]),
                **parse_config(raw_map[label], query=query)}
        for label, query in CONSTANT_QUERIES if label != "identity"
    }
    queue = session.drain_errors()
    envelope = {
        "schema_version": "keithley2000-constants-v1",
        "constants": constants,
        "readbacks": readbacks,
        "error_queue": queue,
    }
    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        session.save_log(out / "session.json")
        (out / "constants.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    if args.json:
        json.dump(envelope, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        ident = constants["identity"]
        print(f"vendor   : {ident.get('vendor')}")
        print(f"model    : {ident.get('model')}")
        print(f"serial   : {ident.get('serial')}")
        print(f"firmware : {ident.get('firmware_digital')} / {ident.get('firmware_display')}")
        print(f"options  : {constants['options']} ({constants['options_interpretation']})")
        print(f"SCPI     : {constants['scpi_version']}")
        print(f"line     : {constants['line_frequency_hz']:g} Hz"
              if constants["line_frequency_hz"] is not None else "line     : -")
        print(f"inputs   : {constants['input_switch']}")
        print(f"power-on : {constants['power_on_setup']}")
        print(f"autozero : {'on' if constants['autozero'] else 'off'}")
        cal = constants["calibration"]
        print(f"cal count: {cal['count']}")
        print(f"cal date : {cal['date']}")
        due_note = " (overdue)" if cal["due_in_past"] else ""
        print(f"cal due  : {cal['due']}{due_note}")
        print(f"cal lock : {cal['lock']}")
        if any(record["code"] != 0 for record in queue["records"]):
            print(f"error queue: {[(r['code'], r['message']) for r in queue['records']]}")
    return 0


def cmd_identify(session: Session, args: argparse.Namespace) -> int:
    raw = session.query("*IDN?")
    identity = parse_identity(raw) if raw else {"note": "dry-run"}
    if args.json:
        json.dump(identity, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    if raw:
        fields = identity.get("identity", {})
        print(f"vendor : {fields.get('vendor')}")
        print(f"model  : {fields.get('model')}")
        print(f"serial : {fields.get('serial')}")
        print(f"firmware: {fields.get('firmware_digital')} / {fields.get('firmware_display')}")
        print(f"matches recorded capture: {identity['verified_scope']['matches_recorded_capture']}")
    return 0


def cmd_query(session: Session, args: argparse.Namespace) -> int:
    command = args.query_command
    raw = session.query(command)
    if not raw:
        return 0
    print(f"raw: {raw!r}")
    parsed = parse_config(raw, query=command)
    print(f"parsed: {parsed['configuration']['value']!r} "
          f"({parsed['configuration']['value_type']}, {parsed['integrity']['status']})")
    return 0


def cmd_write(session: Session, args: argparse.Namespace) -> int:
    session.write(args.write_command)
    print(f"sent: {args.write_command}")
    return 0


def cmd_unblock(session: Session, args: argparse.Namespace) -> int:
    raw = session.unblock()
    if raw:
        print(f"link restored: {raw!r}")
    return 0 if raw or args.dry_run else 2


def cmd_errors(session: Session, args: argparse.Namespace) -> int:
    queue = session.drain_errors()
    if args.json:
        json.dump(queue, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    for record in queue.get("records", []):
        print(f"{record['code']}: {record['message']}")
    print(f"status: {queue['integrity']['status']} drained={queue.get('drained')}")
    return 0


def cmd_read(session: Session, args: argparse.Namespace) -> int:
    token = _function_token(args.function)
    if token in CURRENT_FUNCTIONS and not args.allow_current:
        raise SessionError(
            "current functions require --allow-current and the front AMPS/INPUT LO "
            "path already wired in series; this tool will not assume that wiring"
        )
    identity = None
    if not args.dry_run:
        identity = parse_identity(session.query("*IDN?"))
        before = session.drain_errors()
    else:
        before = {"note": "dry-run"}

    configuration = _configure(session, args.function, args,
                               apply=not args.no_configure)
    if args.dry_run:
        for _ in range(args.count):
            session.query(":READ?")
        return 0
    extra_unit = _temperature_unit(configuration) if token == "TEMP" else None
    readings = [_read_once(session, args.function, args, index, extra_unit)
                for index in range(1, args.count + 1)]
    after = session.drain_errors() if not args.dry_run else {"note": "dry-run"}

    envelope = {
        "schema_version": "keithley2000-session-v1",
        "identity": identity,
        "configuration": configuration,
        "readings": readings,
        "error_queue_before": before,
        "error_queue_after": after,
    }
    if not args.dry_run:
        from keithley2000_protocol import assess_reading

        envelope["assessment"] = []
        for reading in readings:
            verdict = assess_reading(reading, after, args.function)
            _apply_assessment(reading, verdict)
            envelope["assessment"].append(verdict)
        if args.output:
            out = Path(args.output)
            for reading in readings:
                _save_raw(out, f"reading-{reading['index']}", reading)
            session.save_log(out / "session.json")
            (out / "envelope.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")

    if args.json:
        json.dump(envelope, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for reading, verdict in zip(readings, envelope.get("assessment", [])):
            measurement = reading.get("measurement", {})
            token = measurement.get("numeric_token")
            status = reading.get("integrity", {}).get("status")
            print(f"reading {reading['index']}: {token} {measurement.get('unit') or ''} [{status}] "
                  f"flags={verdict['flags']} freshness={verdict['freshness']}")
    return 0


def cmd_walk(session: Session, args: argparse.Namespace) -> int:
    if not args.dry_run and not args.confirm_open_input:
        raise SessionError(
            "walk assumes all leads are disconnected; rerun with --confirm-open-input"
        )
    if not args.dry_run:
        session.drain_errors()
    results = []
    out = Path(args.output) if args.output else None
    for function, tag in WALK_FUNCTIONS:
        token = _function_token(function)
        config_args = copy.copy(args)
        if token not in NPLC_FUNCTIONS:
            config_args.nplc = None
        if token not in DIGITS_FUNCTIONS:
            config_args.digits = None
        configuration = _configure(session, function, config_args)
        extra_unit = _temperature_unit(configuration) if token == "TEMP" else None
        reading = _read_once(session, function, args, 1, extra_unit)
        queue = session.drain_errors() if not args.dry_run else {"note": "dry-run"}
        verdict = None
        if not args.dry_run:
            from keithley2000_protocol import assess_reading

            verdict = assess_reading(reading, queue, function)
            _apply_assessment(reading, verdict)
        results.append({"function": function, "tag": tag, "configuration": configuration,
                        "reading": reading, "error_queue": queue, "assessment": verdict})
        if out is not None:
            _save_raw(out, tag, reading)
        if not args.dry_run:
            measurement = reading.get("measurement", {})
            print(f"{function:12s} {measurement.get('numeric_token'):>18s} "
                  f"{measurement.get('reading_status')}")
    if out is not None and not args.dry_run:
        session.save_log(out / "session-walk.json")
        payload = {"schema_version": "keithley2000-walk-v1", "results": results}
        (out / "walk.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.json:
        json.dump(results, sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 0


def _add_common_options(parser: argparse.ArgumentParser, suppress: bool = False) -> None:
    missing = argparse.SUPPRESS if suppress else None
    parser.add_argument("--port", default=missing if suppress else DEFAULT_PORT)
    parser.add_argument("--baud", type=int, default=missing if suppress else DEFAULT_BAUD)
    parser.add_argument("--timeout", type=float, default=missing if suppress else DEFAULT_TIMEOUT)
    parser.add_argument("--dry-run", action="store_true",
                        default=argparse.SUPPRESS if suppress else False,
                        help="record the exact bytes without opening the port")
    parser.add_argument("--allow-state-change", action="store_true",
                        default=argparse.SUPPRESS if suppress else False,
                        help="permit reset/clear/autozero/continuous writes")
    parser.add_argument("--json", action="store_true",
                        default=argparse.SUPPRESS if suppress else False,
                        help="emit JSON artifacts")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    _add_common_options(parser)

    common = argparse.ArgumentParser(add_help=False)
    _add_common_options(common, suppress=True)

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("identify", parents=[common], help="query *IDN? and parse it")

    constants = sub.add_parser("constants", parents=[common],
                               help="read-only identity, options, and calibration metadata")
    constants.add_argument("--output")

    config = sub.add_parser("config", parents=[common],
                            help="read or change NPLC, digits, filter, and REL")
    config.add_argument("--function", help="select this function before configuring")
    config.add_argument("--nplc", type=float)
    config.add_argument("--digits", type=int)
    config.add_argument("--filter", choices=("on", "off"))
    config.add_argument("--filter-type", dest="filter_type", choices=("moving", "repeat"))
    config.add_argument("--filter-count", dest="filter_count", type=int)
    config.add_argument("--rel", choices=("on", "off"),
                        help="final REL state; required with --rel-acquire")
    rel_group = config.add_mutually_exclusive_group()
    rel_group.add_argument("--rel-reference", dest="rel_reference", type=float)
    rel_group.add_argument("--rel-acquire", dest="rel_acquire", action="store_true",
                           help="capture the latest raw reading as the reference")
    config.add_argument("--allow-current", action="store_true",
                        help="confirm the AMPS/INPUT LO path is already wired in series")
    config.add_argument("--output")

    query = sub.add_parser("query", parents=[common],
                           help="send one query and show the raw response")
    query.add_argument("query_command", metavar="COMMAND")

    write = sub.add_parser("write", parents=[common],
                           help="send one command without reading a response")
    write.add_argument("write_command", metavar="COMMAND")

    sub.add_parser("unblock", parents=[common],
                   help="device clear (0x03) after a timeout or armed trigger")
    sub.add_parser("errors", parents=[common],
                   help="drain and parse :SYSTem:ERRor?")

    read = sub.add_parser("read", parents=[common],
                          help="configure, read one or more samples, assess")
    read.add_argument("--function", required=True,
                      help="VOLT:DC, VOLT:AC, CURR:DC, CURR:AC, RES, FRES, FREQ, "
                           "PER, CONT, DIOD, TEMP or the full command name")
    read.add_argument("--count", type=int, default=1)
    read.add_argument("--range", dest="range", type=float)
    read.add_argument("--nplc", type=float)
    read.add_argument("--digits", type=int)
    read.add_argument("--unit")
    read.add_argument("--elements", help="e.g. READ,CHAN,UNIT")
    read.add_argument("--autorange", dest="autorange", action="store_true", default=None)
    read.add_argument("--no-autorange", dest="autorange", action="store_false")
    read.add_argument("--output", help="directory for raw bytes and session log")
    read.add_argument("--allow-current", action="store_true",
                      help="confirm the AMPS/INPUT LO path is already wired in series")
    read.add_argument("--no-configure", action="store_true",
                      help="read the current setup without :CONFigure or setting writes")

    walk = sub.add_parser("walk", parents=[common],
                          help="configure and read every function (open inputs)")
    walk.add_argument("--output", help="directory for raw bytes and walk summary")
    walk.add_argument("--confirm-open-input", action="store_true")
    walk.add_argument("--elements", help="e.g. READ,CHAN,UNIT")
    walk.add_argument("--unit")
    walk.add_argument("--nplc", type=float)
    walk.add_argument("--digits", type=int)
    walk.add_argument("--range", dest="range", type=float)
    walk.add_argument("--autorange", dest="autorange", action="store_true", default=None)
    walk.add_argument("--no-autorange", dest="autorange", action="store_false")
    walk.add_argument("--allow-current", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    session = Session(port=args.port, baud=args.baud, timeout=args.timeout,
                      dry_run=args.dry_run, allow_state_change=args.allow_state_change)
    try:
        if args.command == "identify":
            return cmd_identify(session, args)
        if args.command == "constants":
            return cmd_constants(session, args)
        if args.command == "config":
            return cmd_config(session, args)
        if args.command == "query":
            return cmd_query(session, args)
        if args.command == "write":
            return cmd_write(session, args)
        if args.command == "unblock":
            return cmd_unblock(session, args)
        if args.command == "errors":
            return cmd_errors(session, args)
        if args.command == "read":
            return cmd_read(session, args)
        if args.command == "walk":
            return cmd_walk(session, args)
        raise SessionError(f"unknown command {args.command}")
    except SessionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
