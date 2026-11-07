#!/usr/bin/env python3
"""Plan and apply SDS800X HD SCPI configuration with readback proof.

Every command this script sends is checked against
``scope_command_catalog.py``, the generated transcription of the vendor
programming guide. The catalog only records what the manual documents; the
scope's own readback is what decides whether a write actually took effect.

Three properties matter more than coverage:

1. **Explicit permission.** Writing is never implicit. ``apply`` is a dry run
   unless ``--write`` is given, and each risk class needs its own ``--allow``:
   ``display``, ``acquisition_context``, ``file_write``, ``destructive``.
   Commands outside the catalog additionally need ``--allow-unlisted`` plus the
   printed manual page the operator read them from.
2. **Validate everything before touching the instrument.** All steps are parsed,
   domain-checked, and permission-checked first; a single bad step aborts the
   whole plan with no bytes sent.
3. **Stop at the first sign of divergence.** After each write the error queue is
   drained and, where the manual documents a query, the value is read back and
   compared. Any queue entry or mismatch ends the run, because a session that
   has already accepted a wrong value cannot be trusted for later steps; the
   operator must open a new one.

Status vocabulary per step: ``verified`` (write + matching readback),
``unverified`` (write accepted, no documented readback), ``mismatch``,
``rejected`` (error queue non-empty). A run is ``COMPLETE`` only when every step
is ``verified``; otherwise it is ``INCOMPLETE``.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import scope_command_catalog as catalog
from scope_protocol import (
    ScopeProtocolError,
    ScopeSession,
    drain_error_queue,
    parse_scpi_number,
    scope_connect,
    scope_identify,
)

RISK_ORDER = ("display", "acquisition_context", "file_write", "destructive")

HELP_EPILOG = """\
examples:
  # what can be configured, and what each entry costs in risk
  configure_scope.py list --root :DECode
  configure_scope.py list --risk acquisition_context --queryable

  # read-only inspection of the live decode setup
  configure_scope.py show :DECode :DEC:BUS1:PROT? :DEC:BUS1:UART:BAUD?

  # dry run: validate and print the exact wire plan, send nothing
  configure_scope.py apply --allow display --set ":DECode ON" --set ":DECode:BUS1:PROTocol UART"

  # real write, decoder settings only
  configure_scope.py apply --write --allow display \\
      --set ":DECode:BUS1:PROTocol UART" --set ":DECode:BUS1:UART:BAUD 9600bps"

  # trigger setup: a second, explicit permission class
  configure_scope.py apply --write --allow acquisition_context \\
      --set ":TRIGger:TYPE RUNT" --set ":TRIGger:RUNT:SOURce C1"
"""


@dataclass
class Step:
    text: str
    command: str
    value: str | None
    canonical: str | None = None
    query: str | None = None
    risk: str = "display"
    page: int | None = None
    listed: bool = True
    kind: str = "any"
    args: tuple[str, ...] = ()
    indices: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    status: str = "planned"
    detail: str = ""
    readback: str | None = None

    @property
    def wire(self) -> str:
        return self.command if not self.value else f"{self.command} {self.value}"

    def as_json(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "value": self.value,
            "wire": self.wire,
            "canonical": self.canonical,
            "query": self.query,
            "risk": self.risk,
            "page": self.page,
            "listed": self.listed,
            "kind": self.kind,
            "indices": self.indices,
            "warnings": self.warnings,
            "status": self.status,
            "detail": self.detail,
            "readback": self.readback,
        }


class PlanError(ValueError):
    """One or more steps cannot be justified before any byte is sent."""


# --------------------------------------------------------------------------
# Parsing and pre-flight validation
# --------------------------------------------------------------------------

def split_assignment(text: str) -> tuple[str, str | None]:
    text = text.strip()
    if not text:
        raise PlanError("empty --set value")
    if not text.startswith(":"):
        raise PlanError(f"{text!r}: a command must start with ':'")
    head, _, tail = text.partition(" ")
    return head, (tail.strip() or None)


def _choice_match(token: str, choices: Sequence[str]) -> str | None:
    """Match a typed token against a documented choice, SCPI-style.

    SCPI accepts any prefix of the documented keyword down to its short form,
    so ``ALT`` and ``ALTernate`` are the same value. The reverse direction is
    allowed too, because a catalog short form such as ``A429`` is sometimes
    written out in full by the operator.
    """
    upper = token.upper()
    for choice in choices:
        if upper == choice.upper():
            return choice
    for choice in choices:
        up = choice.upper()
        if "<" in choice:
            # ``C<n>``/``D<d>``: the documented domain is a channel reference.
            if re.fullmatch(_choice_pattern(up), upper):
                return choice
            continue
        if len(upper) >= 2 and (up.startswith(upper) or upper.startswith(up)):
            return choice
    return None


def _choice_pattern(choice: str) -> str:
    """Turn ``C<N>``/``F<X>`` into a matcher for a concrete reference."""

    return re.sub(r"<[A-Z]+>", r"[0-9]+", re.escape(choice))


def _check_number(value: str, spec: catalog.CommandSpec, *, integral: bool) -> str | None:
    number = parse_scpi_number(value)
    if number is None:
        try:
            number = float(value)
        except ValueError:
            return f"{value!r} is not a number"
    if integral and not float(number).is_integer():
        return f"{value!r} is not an integer"
    if spec.minimum is not None and number < spec.minimum:
        return f"{value!r} is below the documented minimum {spec.minimum:g}"
    if spec.maximum is not None and number > spec.maximum:
        return f"{value!r} is above the documented maximum {spec.maximum:g}"
    return None


def check_value(spec: catalog.CommandSpec, value: str | None) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for one argument value."""

    if spec.kind == "action":
        return ([f"takes no argument, got {value!r}"] if value is not None else []), []
    if value is None:
        return [f"needs a value ({spec.kind})"], []

    errors: list[str] = []
    warnings: list[str] = []
    head, _, tail = value.partition(",")

    if spec.kind in ("enum", "enum_prefix"):
        matched = _choice_match(head.strip(), spec.choices)
        if matched is None:
            errors.append(
                "%r is not one of: %s" % (head.strip(), " | ".join(spec.choices))
            )
        elif matched != head.strip():
            warnings.append(f"{head.strip()!r} resolves to documented keyword {matched!r}")
        if spec.kind == "enum" and tail:
            errors.append(f"takes a single keyword, got {value!r}")
        if spec.kind == "enum_prefix" and tail:
            warnings.append("trailing argument is not pre-validated; readback decides")
    elif spec.kind in ("int", "float", "number"):
        message = _check_number(value.strip(), spec, integral=spec.kind == "int")
        if message:
            errors.append(message)
    elif spec.kind == "string":
        if not (value.startswith(('"', "'")) and value.endswith(('"', "'")) and len(value) > 1):
            errors.append(f"expects a quoted string or storage path, got {value!r}")
    elif spec.kind == "compound":
        parts = split_top_level(value)
        if len(parts) < 2:
            errors.append(
                "expects %d comma-separated arguments: %s"
                % (len(spec.args), ",".join("<%s>" % a for a in spec.args))
            )
        if value.count('"') % 2:
            errors.append("unbalanced quotes")
        warnings.append("multi-argument command: only readback can confirm the resolved shape")
    else:
        warnings.append("the manual documents no domain for this argument; readback decides")
    return errors, warnings


def split_top_level(value: str) -> list[str]:
    """Split on commas that are not inside a quoted string."""

    parts, current, quote = [], [], ""
    for char in value:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
            current.append(char)
        elif char == ",":
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    return [p for p in parts if p != ""]


def build_plan(
    assignments: Iterable[str],
    *,
    allowed: set[str],
    allow_unlisted: bool,
    manual_page: int | None,
) -> list[Step]:
    steps: list[Step] = []
    errors: list[str] = []

    for raw in assignments:
        try:
            command, value = split_assignment(raw)
        except PlanError as exc:
            errors.append(str(exc))
            continue
        resolved = catalog.lookup(command)
        if resolved is None:
            if not allow_unlisted:
                errors.append(
                    f"{command}: not in the documented catalog; pass --allow-unlisted "
                    "--manual-page N if you have the vendor page in front of you"
                )
                continue
            if manual_page is None:
                errors.append(f"{command}: --allow-unlisted also requires --manual-page N")
                continue
            steps.append(Step(
                text=raw, command=command, value=value, risk="display", page=manual_page,
                listed=False, warnings=["not in the catalog; nothing was pre-validated"],
            ))
            continue

        spec, indices = resolved
        if "<" in command or ">" in command:
            errors.append(
                f"{command}: replace the index placeholder with a concrete index "
                "(for example :DECode:BUS1:...)"
            )
            continue
        step = Step(
            text=raw,
            command=command,
            value=value,
            canonical=spec.command,
            # Use the operator's concrete spelling: the catalog's own query text
            # still carries the index placeholder.
            query=(command + "?") if spec.has_query else None,
            risk=spec.risk,
            page=spec.page,
            listed=True,
            kind=spec.kind,
            args=spec.args,
            indices=indices,
        )

        for name, captured in indices.items():
            permitted = spec.indices.get(name)
            if permitted and captured.upper() not in {p.upper() for p in permitted}:
                errors.append(
                    f"{command}: <{name}>={captured} is outside the documented "
                    f"range {'/'.join(permitted)}"
                )
            elif permitted is None and not captured.isdigit():
                errors.append(f"{command}: <{name}>={captured} must be an integer")

        value_errors, warnings = check_value(spec, value)
        errors.extend(f"{command}: {message}" for message in value_errors)
        step.warnings.extend(warnings)

        if spec.risk not in allowed:
            errors.append(
                f"{command}: {spec.risk} settings need --allow {spec.risk} "
                f"(see manual p.{spec.page})"
            )
        if not spec.has_query:
            step.warnings.append("no documented readback; the write cannot be proven")
        steps.append(step)

    if errors:
        raise PlanError("\n".join(errors))
    return steps


# --------------------------------------------------------------------------
# Readback comparison
# --------------------------------------------------------------------------

def _normalize_token(token: str) -> str:
    return token.strip().strip('"').strip("'").strip()


def _as_number(token: str) -> float | None:
    number = parse_scpi_number(token)
    if number is not None:
        return number
    try:
        return float(token)
    except ValueError:
        return None


PROTOCOL_ALIASES = {
    frozenset({"ARINC429", "A429"}): "ARINC429",
    frozenset({"MANChester", "MAN"}): "MANChester",
}


def tokens_match(expected: str, actual: str) -> bool:
    """Compare one comma-separated field, tolerating documented reply shapes.

    The firmware may answer with the short form (``ALT``), with a resolved
    number instead of a keyword (``1000000`` for ``CUSTom,1000000``), or with a
    unit-decorated quantity (``1.00E-01S``). Exact string equality would score
    all three as a failed write.
    """

    left = _normalize_token(expected)
    right = _normalize_token(actual)
    left_up, right_up = left.upper(), right.upper()
    if left_up == right_up:
        return True
    for aliases, canonical in PROTOCOL_ALIASES.items():
        if left_up in {a.upper() for a in aliases} and right_up in {a.upper() for a in aliases}:
            return True
    left_number, right_number = _as_number(left), _as_number(right)
    if left_number is not None and right_number is not None:
        return math.isclose(left_number, right_number, rel_tol=1e-6, abs_tol=1e-12)
    left_boolean, right_boolean = _boolean(left), _boolean(right)
    if left_boolean is not None and right_boolean is not None:
        return left_boolean == right_boolean
    return len(left_up) >= 2 and len(right_up) >= 2 and (
        left_up.startswith(right_up) or right_up.startswith(left_up)
    )


def _boolean(token: str) -> str | None:
    """Both ``ON``/``OFF`` and ``1``/``0`` are documented reply forms."""

    return {"ON": "ON", "1": "ON", "OFF": "OFF", "0": "OFF"}.get(token.upper())


def readback_matches(expected: str, actual: str) -> bool:
    actual_tokens = split_top_level(actual)
    expected_tokens = split_top_level(expected)
    if not actual_tokens:
        return False
    if not expected_tokens:
        return False
    if len(actual_tokens) == len(expected_tokens):
        return all(tokens_match(e, a) for e, a in zip(expected_tokens, actual_tokens))
    # A keyword that took a trailing value is answered by the value alone, and
    # vice versa; compare against the last field rather than failing outright.
    return tokens_match(expected_tokens[-1], actual_tokens[-1])


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------

def acquisition_state(session: Any) -> str:
    """Read ``SAST?`` without the Stop-before-Ready guard of ``query_state``.

    ``ScopeSession.mark_state`` raises when the first observed state is Stop,
    which is a normal starting state for a configuration run. This engine keeps
    its own guard: it asks the operator for ``--allow-after-stop`` instead of
    letting the transport decide.
    """

    raw = str(session.query_ascii("SAST?", allow_after_stop=True)).strip().upper()
    match = re.search(r"(RUN|STOP|TRIG|READY|ROLL|ARM|SING)", raw)
    return match.group(1) if match else raw


def report_stopped(session: Any) -> tuple[bool, str]:
    try:
        state = acquisition_state(session)
    except (ScopeProtocolError, OSError) as exc:
        return False, f"acquisition state unknown ({type(exc).__name__}: {exc})"
    return state.startswith("STOP"), state


def apply_steps(
    session: Any,
    steps: Sequence[Step],
    *,
    allow_after_stop: bool = False,
    stop_on_mismatch: bool = True,
) -> list[Step]:
    """Write every step, proving each one, and stop at the first divergence."""

    for index, step in enumerate(steps):
        if step.status != "planned":
            continue
        try:
            session.write(step.wire)
        except ScopeProtocolError as exc:
            step.status = "rejected"
            step.detail = f"write refused: {exc}"
            _mark_remaining(steps, index)
            return steps

        errors = drain_error_queue(session)
        if errors:
            step.status = "rejected"
            step.detail = "; ".join(errors)
            _mark_remaining(steps, index)
            return steps

        if not step.query:
            step.status = "unverified"
            step.detail = "write accepted; no documented readback"
            continue

        try:
            step.readback = str(session.query_ascii(step.query)).strip()
        except ScopeProtocolError as exc:
            step.status = "rejected"
            step.detail = (
                f"readback failed ({type(exc).__name__}: {exc}); the connection is no "
                "longer trustworthy -- close it and start a new session"
            )
            _mark_remaining(steps, index)
            return steps
        errors = drain_error_queue(session)
        if errors:
            step.status = "rejected"
            step.detail = "; ".join(errors)
            _mark_remaining(steps, index)
            return steps

        if readback_matches(step.value or "", step.readback):
            step.status = "verified"
            step.detail = "readback matches"
        else:
            step.status = "mismatch"
            step.detail = f"wrote {step.value!r}, scope reports {step.readback!r}"
            if stop_on_mismatch:
                _mark_remaining(steps, index)
                return steps
    return steps


def _mark_remaining(steps: Sequence[Step], index: int) -> None:
    for later in steps[index + 1:]:
        if later.status == "planned":
            later.status = "not_attempted"
            later.detail = "run stopped at the previous step"


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def overall_status(steps: Sequence[Step]) -> str:
    statuses = [step.status for step in steps]
    if not statuses:
        return "INCOMPLETE"
    if any(s in ("rejected", "mismatch", "not_attempted") for s in statuses):
        return "INCOMPLETE"
    if all(s == "verified" for s in statuses):
        return "COMPLETE"
    if all(s == "unverified" for s in statuses):
        return "UNVERIFIED"
    return "INCOMPLETE"


def exit_code(steps: Sequence[Step]) -> int:
    status = overall_status(steps)
    if status in ("COMPLETE",):
        return 0
    if status == "UNVERIFIED":
        return 3
    return 1


def render_steps(steps: Sequence[Step], *, dry_run: bool) -> str:
    lines = []
    for index, step in enumerate(steps, start=1):
        origin = f"p.{step.page}" if step.page else "no page"
        mark = "" if step.listed else "  UNLISTED"
        lines.append(
            "%2d. %-46s %-19s %-8s%s"
            % (index, step.wire, step.risk, origin, mark)
        )
        for warning in step.warnings:
            lines.append(f"    ! {warning}")
        if not dry_run and step.status != "planned":
            detail = f"  ({step.detail})" if step.detail else ""
            lines.append(f"    -> {step.status.upper()}{detail}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=HELP_EPILOG,
    )
    parser.add_argument("--host", default="192.168.10.2")
    parser.add_argument("--port", type=int, default=5025)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    sub = parser.add_subparsers(dest="action", required=True)

    listing = sub.add_parser("list", help="show catalog entries (offline, no connection)")
    listing.add_argument("--root", default=None, help="only entries under this root, e.g. :DECode")
    listing.add_argument("--risk", choices=RISK_ORDER, default=None)
    listing.add_argument("--queryable", action="store_true", help="only entries with a readback query")
    listing.add_argument("--grep", default=None, help="case-insensitive substring filter")
    listing.add_argument("--count", action="store_true", help="print only the number of matches")

    show = sub.add_parser("show", help="read-only readback of the given queries")
    show.add_argument("queries", nargs="+", metavar="QUERY")

    plan = sub.add_parser("plan", help="validate steps and print the wire plan")
    _add_step_arguments(plan)

    apply_cmd = sub.add_parser("apply", help="validate, then write (dry run unless --write)")
    _add_step_arguments(apply_cmd)
    apply_cmd.add_argument("--write", action="store_true", help="actually send the steps")
    apply_cmd.add_argument("--allow-after-stop", action="store_true",
                           help="permit writes while acquisition is stopped")
    apply_cmd.add_argument("--continue-on-mismatch", action="store_true",
                           help="keep going when a readback disagrees (not recommended)")
    return parser


def _add_step_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--set", dest="assignments", action="append", default=[],
                        metavar='"COMMAND [VALUE]"', help="one step; repeatable")
    parser.add_argument("--from", dest="plan_file", default=None,
                        help="read steps from a plan JSON produced by this script")
    parser.add_argument("--allow", dest="allowed", action="append", default=[],
                        choices=RISK_ORDER, help="permit one risk class; repeatable")
    parser.add_argument("--allow-unlisted", action="store_true",
                        help="permit commands outside the documented catalog")
    parser.add_argument("--manual-page", type=int, default=None,
                        help="printed manual page for every --allow-unlisted command")


def load_assignment_file(path: str) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    steps = payload.get("steps", payload)
    if not isinstance(steps, list):
        raise PlanError(f"{path}: expected a JSON object with a 'steps' list")
    assignments = []
    for entry in steps:
        if isinstance(entry, str):
            assignments.append(entry)
        elif isinstance(entry, dict) and entry.get("command"):
            value = entry.get("value")
            assignments.append(entry["command"] + (f" {value}" if value else ""))
        else:
            raise PlanError(f"{path}: unsupported step entry {entry!r}")
    return assignments


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.action == "list":
        return _list(args)

    if args.action == "show":
        return _show(args)

    assignments = list(args.assignments)
    if args.plan_file:
        try:
            assignments.extend(load_assignment_file(args.plan_file))
        except (OSError, json.JSONDecodeError, PlanError) as exc:
            print(f"plan file error: {exc}", file=sys.stderr)
            return 2
    if not assignments:
        print("nothing to do: pass --set or --from", file=sys.stderr)
        return 2

    try:
        steps = build_plan(
            assignments,
            allowed=set(args.allowed),
            allow_unlisted=args.allow_unlisted,
            manual_page=args.manual_page,
        )
    except PlanError as exc:
        print("refused before connecting:", file=sys.stderr)
        for line in str(exc).splitlines():
            print(f"  {line}", file=sys.stderr)
        return 2

    dry_run = args.action == "plan" or not args.write
    report: dict[str, Any] = {
        "action": args.action,
        "dry_run": dry_run,
        "host": args.host,
        "port": args.port,
        "steps": [step.as_json() for step in steps],
    }

    if dry_run:
        report["status"] = "PLANNED"
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"# plan only, nothing sent ({len(steps)} step(s))")
            print(render_steps(steps, dry_run=True))
        return 0

    session: ScopeSession | None = None
    try:
        session = scope_connect(args.host, args.port, args.timeout)
        report["identity"] = scope_identify(session)
        stopped, state = report_stopped(session)
        report["acquisition_state"] = state
        if stopped and not args.allow_after_stop:
            print(
                f"refused: acquisition is {state}; pass --allow-after-stop to configure a "
                "stopped scope",
                file=sys.stderr,
            )
            return 2
        apply_steps(
            session,
            steps,
            allow_after_stop=args.allow_after_stop,
            stop_on_mismatch=not args.continue_on_mismatch,
        )
    except (ScopeProtocolError, OSError) as exc:
        print(f"session failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("close the scope connection and start a new session before retrying.", file=sys.stderr)
        for step in steps:
            if step.status == "planned":
                step.status = "not_attempted"
                step.detail = "session failed before this step"
        report["steps"] = [step.as_json() for step in steps]
        report["status"] = "INCOMPLETE"
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1
    finally:
        if session is not None:
            session.close()

    report["steps"] = [step.as_json() for step in steps]
    report["status"] = overall_status(steps)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"# {report.get('identity', 'unknown instrument')}  ({args.host}:{args.port})")
        if report.get("acquisition_state"):
            print(f"acquisition: {report['acquisition_state']}")
        print(render_steps(steps, dry_run=False))
        print(f"status: {report['status']}")
        if report["status"] != "COMPLETE":
            print("rerun requires a fresh session: a diverged connection stays diverged.")
    return exit_code(steps)


def _list(args: argparse.Namespace) -> int:
    entries = []
    needle = (args.grep or "").upper()
    for key in sorted(catalog.CATALOG):
        spec = catalog.CATALOG[key]
        if args.root and not key.upper().startswith(args.root.upper()):
            continue
        if args.risk and spec.risk != args.risk:
            continue
        if args.queryable and not spec.has_query:
            continue
        if needle and needle not in key.upper():
            continue
        entries.append(spec)
    if args.count:
        print(len(entries))
        return 0
    if args.json:
        print(json.dumps(
            [
                {
                    "command": spec.command,
                    "kind": spec.kind,
                    "choices": list(spec.choices),
                    "minimum": spec.minimum,
                    "maximum": spec.maximum,
                    "args": list(spec.args),
                    "indices": {k: list(v) if v else None for k, v in spec.indices.items()},
                    "risk": spec.risk,
                    "page": spec.page,
                    "query": spec.query,
                }
                for spec in entries
            ],
            indent=2,
            ensure_ascii=False,
        ))
        return 0
    print(f"# {len(entries)} documented command(s); p.N is the printed manual page")
    for spec in entries:
        print(catalog.render(spec))
    return 0


def _show(args: argparse.Namespace) -> int:
    report: dict[str, Any] = {"action": "show", "host": args.host, "port": args.port, "queries": []}
    session: ScopeSession | None = None
    try:
        session = scope_connect(args.host, args.port, args.timeout)
        report["identity"] = scope_identify(session)
        for query in args.queries:
            text = query.strip()
            if not text.endswith("?"):
                text += "?"
            entry: dict[str, Any] = {"query": text}
            try:
                entry["response"] = str(session.query_ascii(text)).strip()
            except ScopeProtocolError as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
                entry["hint"] = (
                    "no usable reply; the connection may be desynchronised. "
                    "Close it and start a new session."
                )
                report["queries"].append(entry)
                break
            errors = drain_error_queue(session)
            if errors:
                entry["system_error"] = errors
            report["queries"].append(entry)
    except (ScopeProtocolError, OSError) as exc:
        print(f"session failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        if session is not None:
            session.close()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    print(f"# read-only {report.get('identity', 'unknown instrument')}  ({args.host}:{args.port})")
    for entry in report["queries"]:
        print(f"\n== {entry['query']} ==")
        if "response" in entry:
            print(entry["response"] if entry["response"] else "<empty response>")
        if "error" in entry:
            print(f"error: {entry['error']}")
            print(f"hint: {entry.get('hint', '')}")
        for line in entry.get("system_error", []):
            print(f"SYST:ERR? {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
