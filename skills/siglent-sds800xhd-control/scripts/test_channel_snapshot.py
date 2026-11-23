#!/usr/bin/env python3
"""Offline tests for the read-only per-channel snapshot.

No test opens a socket: every session is a scripted ScopeSession double. The
suite pins the failure modes that produced a wrong "no signal" verdict: a
measurement reply that is not a number must stay UNVERIFIED, a value may be
attributed only to the channel named by the simple-measurement source readback,
and a transport failure must stop every later query.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import channel_snapshot
from channel_snapshot import (
    SCHEMA,
    attribute_measurements,
    build_snapshot,
    format_table,
    parse_measurement_source,
    parse_scalar_reply,
)
from scope_protocol import ScopeProtocolError, ScopeSession


IDN = "Siglent Technologies,SDS824X HD,SDS08A0Q909185,4.8.12.1.1.6.5"


def channel_answers(channel: str) -> dict:
    number = channel[1:]
    return {
        f":CHANnel{number}:SWITch?": "ON",
        f"C{number}:VDIV?": "2.00E+00V",
        f"C{number}:OFST?": "0.00E+00V",
        f":CHANnel{number}:COUPling?": "DC",
    }


class ScriptedScope(ScopeSession):
    """A ScopeSession double: answers by command, records every send."""

    def __init__(self, answers: dict):
        super().__init__("example.invalid", timeout_s=0.01)
        self.answers = {
            key: (list(value) if isinstance(value, list) else [value])
            for key, value in answers.items()
        }
        self.failures: dict[str, BaseException] = {}
        self.sent: list[str] = []

    def connect(self):
        return None

    def close(self):
        return None

    def query_ascii(self, command: str, *, allow_after_stop: bool = False) -> str:
        self.sent.append(command)
        self._check_allowed(command)
        failure = self.failures.get(command)
        if failure is not None:
            raise failure
        if command not in self.answers:
            raise AssertionError(f"unscripted query: {command}")
        replies = self.answers[command]
        return replies.pop(0) if len(replies) > 1 else replies[0]

    def query_block(self, command: str, *, allow_after_stop: bool = False):
        raise AssertionError(f"snapshot must not request a block: {command}")


def snapshot_scope(*, channels=("C1", "C2", "C3"), source=("C1", "C1"), metrics=None, unit="V", model=IDN):
    answers: dict = {
        "*IDN?": model,
        "SAST?": "Stop",
        "TRMD?": "SINGle",
        ":TRIGger:TYPE?": "EDGE",
        ":TRIGger:EDGE:SOURce?": "C1",
        ":TRIGger:EDGE:SLOPe?": "RISing",
        ":TRIGger:EDGE:LEVel?": "2.50E+00",
        ":MEASure:SIMPle:SOURce?": list(source),
        ":MEASure:SIMPle:VALue? PKPK": "3.30000E+00",
        ":MEASure:SIMPle:VALue? MAX": "3.30000E+00",
        ":MEASure:SIMPle:VALue? MIN": "0.00E+00",
    }
    for channel in channels:
        answers.update(channel_answers(channel))
        answers[f":CHANnel{channel[1:]}:UNIT?"] = unit
    answers.update(metrics or {})
    return ScriptedScope(answers)


class ReplyParsingTests(unittest.TestCase):
    def test_strict_scalar_accepts_nr3_and_rejects_error_text(self):
        self.assertEqual(parse_scalar_reply("3.04167E+00"), (3.04167, None, None))
        self.assertEqual(parse_scalar_reply("2.00E-01V"), (0.2, "V", None))
        self.assertEqual(parse_scalar_reply("3.3 V"), (3.3, "V", None))
        self.assertEqual(
            parse_scalar_reply("C1:VDIV 5.00E+00V", allowed_echoes={"C1:VDIV"}),
            (5.0, "V", "C1:VDIV"),
        )
        for raw in ("***", "****", "", "  ", "nan", "inf", "1E999", "-1E999", "1.0,2.0", "-113,\"Undefined header;X\"", "C1", "ERROR 0"):
            with self.subTest(raw=raw):
                value, unit, echo = parse_scalar_reply(raw, allowed_echoes={"C1:VDIV"})
                self.assertIsNone(value)
                self.assertIsNone(unit)
        # A header that is not the expected one is not an echo, even if the tail
        # is a valid scalar; only the query's own documented/observed header is.
        for raw in ("C2:VDIV 5.00E+00V", "ERROR C1:VDIV 5.00E+00V", "CHAN2:SCAL 5.00E+00V"):
            with self.subTest(raw=raw):
                value, _unit, _echo = parse_scalar_reply(raw, allowed_echoes={"C1:VDIV", ":CHANnel1:SCALe"})
                self.assertIsNone(value)

    def test_measurement_source_parser_keeps_only_documented_tokens(self):
        self.assertEqual(parse_measurement_source("C2"), "C2")
        self.assertEqual(parse_measurement_source(":MEAS:SIMP:SOUR? C3"), "C3")
        self.assertEqual(parse_measurement_source(":MEASure:SIMPle:SOURce? C4"), "C4")
        for raw in ("***", "", "-113,\"Undefined header;MEAS:SOUR?\"", "C5", "PAVA", "ERROR C1", "OTHER C1"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_measurement_source(raw))


class SnapshotTests(unittest.TestCase):
    def test_only_the_matching_source_channel_receives_values(self):
        scope = snapshot_scope(source=("C2", "C2"))
        snapshot = build_snapshot(scope, ["C1", "C2", "C3"])

        self.assertEqual(snapshot["status"], "COMPLETE")
        c2 = snapshot["channels"]["C2"]
        self.assertEqual(c2["measurement"]["source_attribution"], "verified-simple-source-readback")
        self.assertEqual(c2["measurement"]["pkpk"]["value"], 3.3)
        self.assertEqual(c2["measurement"]["pkpk"]["unit"], "V")
        self.assertEqual(c2["measurement"]["pkpk"]["status"], "OBSERVED")
        for channel in ("C1", "C3"):
            row = snapshot["channels"][channel]
            self.assertEqual(row["measurement"]["source_attribution"], "other-source")
            self.assertEqual(row["measurement"]["pkpk"]["status"], "UNVERIFIED")
            self.assertIsNone(row["measurement"]["pkpk"]["value"])
            self.assertEqual(row["measurement"]["pkpk"]["raw"], "3.30000E+00")
            self.assertIn("C2", row["measurement"]["pkpk"]["reason"])
        self.assertEqual(snapshot["measurement"]["source_before"]["raw"], "C2")
        self.assertEqual(snapshot["measurement"]["source_after"]["raw"], "C2")

    def test_unreadable_replies_are_unverified_and_never_zero(self):
        metrics = {
            ":MEASure:SIMPle:VALue? PKPK": "***",
            ":MEASure:SIMPle:VALue? MAX": "****",
            ":MEASure:SIMPle:VALue? MIN": "",
        }
        scope = snapshot_scope(metrics=metrics)
        snapshot = build_snapshot(scope, ["C1"])

        for metric in ("pkpk", "max", "min"):
            entry = snapshot["channels"]["C1"]["measurement"][metric]
            with self.subTest(metric=metric):
                self.assertEqual(entry["status"], "UNVERIFIED")
                self.assertIsNone(entry["value"])
                self.assertNotEqual(entry["value"], 0.0)
                self.assertIn("not a readable finite NR3 scalar", entry["reason"])
        self.assertEqual(snapshot["channels"]["C1"]["measurement"]["pkpk"]["raw"], "***")
        self.assertEqual(snapshot["channels"]["C1"]["measurement"]["max"]["raw"], "****")

    def test_error_text_and_non_scalar_replies_do_not_become_numbers(self):
        metrics = {
            ":MEASure:SIMPle:VALue? PKPK": "-113,\"Undefined header;MEAS:SOUR?\"",
            ":MEASure:SIMPle:VALue? MAX": "C1,C2",
            ":MEASure:SIMPle:VALue? MIN": "V",
        }
        scope = snapshot_scope(metrics=metrics)
        snapshot = build_snapshot(scope, ["C1"])

        for metric in ("pkpk", "max", "min"):
            entry = snapshot["channels"]["C1"]["measurement"][metric]
            self.assertEqual(entry["status"], "UNVERIFIED")
            self.assertIsNone(entry["value"])

    def test_switch_coupling_and_unit_echoes_are_strict(self):
        scope = snapshot_scope(channels=("C1",))
        scope.answers[":CHANnel1:SWITch?"] = ["CHAN1:SWIT ON"]
        scope.answers[":CHANnel1:COUPling?"] = ["CHAN1:COUP DC"]
        scope.answers[":CHANnel1:UNIT?"] = ["CHAN1:UNIT V"]
        scope.answers["C1:VDIV?"] = ["C1:VDIV 2.00E+00V"]
        snapshot = build_snapshot(scope, ["C1"])
        row = snapshot["channels"]["C1"]
        self.assertEqual(row["switch"]["state"], "ON")
        self.assertEqual(row["coupling"]["state"], "DC")
        self.assertEqual(row["unit"]["unit"], "V")
        self.assertEqual(row["vdiv"]["value"], 2.0)

        for query, raw in (
            (":CHANnel1:SWITch?", "ERROR ON"),
            (":CHANnel1:COUPling?", "ERROR DC"),
            (":CHANnel1:UNIT?", "ERROR V"),
            (":CHANnel1:SWITch?", "CHAN2:SWIT ON"),
        ):
            scope = snapshot_scope(channels=("C1",))
            scope.answers[query] = [raw]
            if query == ":CHANnel1:UNIT?":
                scope.answers["C1:VDIV?"] = ["2.00E+00"]
                scope.answers["C1:OFST?"] = ["0.00E+00"]
            snapshot = build_snapshot(scope, ["C1"])
            row = snapshot["channels"]["C1"]
            with self.subTest(query=query, raw=raw):
                if query == ":CHANnel1:SWITch?":
                    self.assertEqual(row["switch"]["status"], "UNVERIFIED")
                elif query == ":CHANnel1:COUPling?":
                    self.assertEqual(row["coupling"]["status"], "UNVERIFIED")
                else:
                    self.assertEqual(row["unit"]["status"], "UNVERIFIED")
                    self.assertIsNone(row["vdiv"]["unit"])
                    self.assertNotEqual(row["vdiv"]["unit_status"], "BOUND")

    def test_trigger_placeholders_are_unverified_and_unreadable_type_skips_edge(self):
        answers = {
            "*IDN?": IDN,
            "SAST?": "Stop",
            "TRMD?": "ERROR SINGle",
            ":TRIGger:TYPE?": "ERROR EDGE",
            **channel_answers("C1"),
            ":CHANnel1:UNIT?": "V",
            ":MEASure:SIMPle:SOURce?": ["C1", "C1"],
            ":MEASure:SIMPle:VALue? PKPK": "1.0",
            ":MEASure:SIMPle:VALue? MAX": "1.0",
            ":MEASure:SIMPle:VALue? MIN": "0.0",
        }
        scope = ScriptedScope(answers)
        snapshot = build_snapshot(scope, ["C1"])
        self.assertEqual(snapshot["trigger"]["mode"]["status"], "UNVERIFIED")
        self.assertEqual(snapshot["trigger"]["type"]["status"], "UNVERIFIED")
        self.assertIsNone(snapshot["trigger"]["type"]["type"])
        self.assertFalse(any(":TRIGger:EDGE:" in command for command in scope.sent))
        for key in ("source", "slope", "level"):
            self.assertEqual(snapshot["trigger"][key]["status"], "UNVERIFIED")
            self.assertIn("unreadable", snapshot["trigger"][key]["reason"])

        edge_answers = dict(answers)
        edge_answers.update(
            {
                "TRMD?": "SINGle",
                ":TRIGger:TYPE?": "EDGE",
                ":TRIGger:EDGE:SOURce?": "ERROR C1",
                ":TRIGger:EDGE:SLOPe?": "ERROR RISing",
                ":TRIGger:EDGE:LEVel?": "1E999",
            }
        )
        edge = ScriptedScope(edge_answers)
        snapshot = build_snapshot(edge, ["C1"])
        self.assertEqual(snapshot["trigger"]["source"]["status"], "UNVERIFIED")
        self.assertEqual(snapshot["trigger"]["slope"]["status"], "UNVERIFIED")
        self.assertEqual(snapshot["trigger"]["level"]["status"], "UNVERIFIED")

    def test_all_unreadable_metrics_keep_query_flow_complete_but_evidence_unverified(self):
        metrics = {
            ":MEASure:SIMPle:VALue? PKPK": "***",
            ":MEASure:SIMPle:VALue? MAX": "****",
            ":MEASure:SIMPle:VALue? MIN": "",
        }
        scope = snapshot_scope(metrics=metrics)
        snapshot = build_snapshot(scope, ["C1"])
        measurement = snapshot["channels"]["C1"]["measurement"]
        self.assertEqual(measurement["query_status"], "COMPLETE")
        self.assertEqual(measurement["status"], "UNVERIFIED")
        self.assertEqual(measurement["usable_metrics"], [])
        self.assertIsNone(snapshot["channels"]["C1"]["triage"])
        self.assertEqual(snapshot["status"], "COMPLETE")
        self.assertEqual(snapshot["evidence_status"], "UNVERIFIED")

    def test_negative_pkpk_is_not_a_level(self):
        scope = snapshot_scope(metrics={":MEASure:SIMPle:VALue? PKPK": "-1.50E+00"})
        snapshot = build_snapshot(scope, ["C1"])
        pkpk = snapshot["channels"]["C1"]["measurement"]["pkpk"]
        self.assertIsNone(pkpk["value"])
        self.assertEqual(pkpk["status"], "UNVERIFIED")
        self.assertIn("magnitude", pkpk["reason"])

    def test_true_zero_is_observed_with_variation_semantics_and_triage(self):
        metrics = {
            ":MEASure:SIMPle:VALue? PKPK": "0.00E+00",
            ":MEASure:SIMPle:VALue? MAX": "0.00E+00",
            ":MEASure:SIMPle:VALue? MIN": "0.00E+00",
        }
        scope = snapshot_scope(metrics=metrics)
        snapshot = build_snapshot(scope, ["C1"])

        pkpk = snapshot["channels"]["C1"]["measurement"]["pkpk"]
        self.assertEqual(pkpk["value"], 0.0)
        self.assertEqual(pkpk["status"], "OBSERVED")
        self.assertIn("no variation", pkpk["zero_semantics"])
        triage = snapshot["channels"]["C1"]["triage"]
        self.assertEqual(triage["conclusion"], "UNVERIFIED")
        causes = {cause["cause"]: cause["status"] for cause in triage["causes"]}
        self.assertEqual(causes["channel disabled"], "EXCLUDED")
        self.assertEqual(causes["GND coupling disconnects the input"], "EXCLUDED")
        self.assertEqual(causes["probe ground on a different board reference"], "UNVERIFIED")
        self.assertEqual(snapshot["limits"]["no_signal_verdict"], "NOT_SUPPORTED_BY_THIS_SNAPSHOT")

    def test_a_positive_amplitude_needs_no_zero_triage(self):
        scope = snapshot_scope()
        snapshot = build_snapshot(scope, ["C1"])
        self.assertIsNone(snapshot["channels"]["C1"]["triage"])

    def test_ready_and_stop_are_recorded_as_context_not_a_capture_claim(self):
        for state, expected in (
            ("Ready", ("waiting for a trigger", "not a completed frame")),
            ("Stop", ("current stopped state", "proves no new frame")),
        ):
            with self.subTest(state=state):
                answers = {"*IDN?": IDN, "SAST?": state, "TRMD?": "SINGle", ":TRIGger:TYPE?": "PULSE"}
                for channel in ("C1",):
                    answers.update(channel_answers(channel))
                answers.update(
                    {
                        ":MEASure:SIMPle:SOURce?": ["C1", "C1"],
                        ":MEASure:SIMPle:VALue? PKPK": "1.0",
                        ":MEASure:SIMPle:VALue? MAX": "1.0",
                        ":MEASure:SIMPle:VALue? MIN": "0.0",
                        ":CHANnel1:UNIT?": "V",
                    }
                )
                snapshot = build_snapshot(ScriptedScope(answers), ["C1"])
                acquisition = snapshot["acquisition"]
                self.assertEqual(acquisition["raw"], state)
                for phrase in expected:
                    self.assertIn(phrase, acquisition["meaning"])

    def test_edge_queries_are_sent_only_for_an_edge_trigger(self):
        scope = ScriptedScope(
            {
                "*IDN?": IDN,
                "SAST?": "Stop",
                "TRMD?": "SINGle",
                ":TRIGger:TYPE?": "PULSE",
                **channel_answers("C1"),
                ":MEASure:SIMPle:SOURce?": ["C1", "C1"],
                ":MEASure:SIMPle:VALue? PKPK": "1.0",
                ":MEASure:SIMPle:VALue? MAX": "1.0",
                ":MEASure:SIMPle:VALue? MIN": "0.0",
                ":CHANnel1:UNIT?": "V",
            }
        )
        snapshot = build_snapshot(scope, ["C1"])
        self.assertFalse(any(":TRIGger:EDGE:" in command for command in scope.sent))
        self.assertEqual(snapshot["trigger"]["source"]["status"], "NOT_APPLICABLE")
        self.assertIn("PULSE", snapshot["trigger"]["source"]["reason"])

        edge = snapshot_scope(channels=("C1",))
        build_snapshot(edge, ["C1"])
        for command in (":TRIGger:EDGE:SOURce?", ":TRIGger:EDGE:SLOPe?", ":TRIGger:EDGE:LEVel?"):
            self.assertIn(command, edge.sent)

    def test_snapshot_sends_only_queries_and_claims_no_state_change(self):
        scope = snapshot_scope(channels=("C1", "C2"))
        # Exercise the real frozen-frame gate: every command must remain a
        # read-only query even when the session is latched after Stop.
        scope.stopped = True
        build_snapshot(scope, ["C1", "C2"])
        self.assertTrue(scope.sent)
        for command in scope.sent:
            # Argument-bearing queries do not end in '?', so require a query
            # marker and exclude every write spelling the frozen-frame rule names.
            self.assertIn("?", command)
            for forbidden in ("ARM", "STOP", "RUN", "TRMD SINGLE", "WFSU", "MEAS:SIMP:SOUR C"):
                self.assertNotIn(forbidden, command.upper())
        self.assertNotIn("ARM", scope.sent)
        self.assertEqual(scope.state_log, [])
        self.assertTrue(scope.stopped)
        self.assertFalse(scope.armed_single_shot)

    def test_transport_failure_stops_every_later_query_and_keeps_completed_rows(self):
        scope = snapshot_scope(channels=("C1", "C2"))
        scope.failures["C1:VDIV?"] = ScopeProtocolError("no usable ASCII response for C1:VDIV?")
        snapshot = build_snapshot(scope, ["C1", "C2"])

        self.assertEqual(snapshot["status"], "INCOMPLETE")
        self.assertEqual(snapshot["transport_failure"]["query"], "C1:VDIV?")
        self.assertEqual(scope.sent[-1], "C1:VDIV?")
        c1 = snapshot["channels"]["C1"]
        self.assertEqual(c1["switch"]["status"], "OBSERVED")
        self.assertEqual(c1["switch"]["raw"], "ON")
        self.assertEqual(c1["vdiv"]["status"], "NOT_ATTEMPTED")
        self.assertEqual(c1["measurement"]["status"], "INCOMPLETE")
        self.assertEqual(c1["measurement"]["query_status"], "INCOMPLETE")
        self.assertEqual(snapshot["channels"]["C2"]["status"], "NOT_ATTEMPTED")
        self.assertNotIn(":MEASure:SIMPle:SOURce?", scope.sent)

    def test_measurement_timeout_stops_before_the_second_source_check(self):
        scope = snapshot_scope(channels=("C1",))
        scope.failures[":MEASure:SIMPle:VALue? PKPK"] = TimeoutError("timed out")
        snapshot = build_snapshot(scope, ["C1"])

        self.assertEqual(snapshot["status"], "INCOMPLETE")
        self.assertEqual(snapshot["transport_failure"]["query"], ":MEASure:SIMPle:VALue? PKPK")
        measurement = snapshot["channels"]["C1"]["measurement"]
        self.assertEqual(measurement["source_raw_before"], "C1")
        self.assertEqual(measurement["pkpk"]["status"], "NOT_ATTEMPTED")
        self.assertEqual(measurement["max"]["status"], "NOT_ATTEMPTED")
        self.assertEqual(scope.sent.count(":MEASure:SIMPle:SOURce?"), 1)
        # The channel row's unit read happened before the measurement block; no
        # query follows the failing metric.
        self.assertEqual(scope.sent.count(":CHANnel1:UNIT?"), 1)
        self.assertLess(scope.sent.index(":CHANnel1:UNIT?"), scope.sent.index(":MEASure:SIMPle:VALue? PKPK"))

    def test_a_source_change_between_readbacks_invalidates_every_value(self):
        scope = snapshot_scope(channels=("C1",), source=("C1", "C2"))
        snapshot = build_snapshot(scope, ["C1"])
        measurement = snapshot["channels"]["C1"]["measurement"]
        self.assertFalse(measurement["source_stable"])
        self.assertIsNone(measurement["pkpk"]["value"])
        self.assertEqual(measurement["pkpk"]["status"], "UNVERIFIED")
        self.assertIn("source", measurement["reason"].lower())
        self.assertIsNone(snapshot["measurement"]["metrics"]["PKPK"]["value"])
        self.assertEqual(snapshot["measurement"]["metrics"]["PKPK"]["raw"], "3.30000E+00")

    def test_unknown_source_leaves_every_value_unverified_and_unparsed(self):
        scope = snapshot_scope(channels=("C1",), source=("***", "***"))
        snapshot = build_snapshot(scope, ["C1"])
        self.assertFalse(any(command.startswith(":MEASure:SIMPle:VALue?") for command in scope.sent))
        measurement = snapshot["channels"]["C1"]["measurement"]
        self.assertIsNone(measurement["source"])
        self.assertEqual(measurement["pkpk"]["status"], "NOT_ATTEMPTED")
        self.assertIsNone(measurement["pkpk"]["value"])

    def test_channel_unit_is_bound_only_from_evidence(self):
        ampere = snapshot_scope(channels=("C1",), unit="A")
        snapshot = build_snapshot(ampere, ["C1"])
        pkpk = snapshot["channels"]["C1"]["measurement"]["pkpk"]
        self.assertEqual(pkpk["unit"], "A")
        self.assertEqual(pkpk["unit_status"], "BOUND")

        unreadable = snapshot_scope(channels=("C1",), unit="***")
        snapshot = build_snapshot(unreadable, ["C1"])
        pkpk = snapshot["channels"]["C1"]["measurement"]["pkpk"]
        self.assertIsNone(pkpk["unit"])
        self.assertEqual(pkpk["unit_status"], "UNVERIFIED")
        self.assertIsNone(pkpk["value"])
        self.assertEqual(pkpk["status"], "UNVERIFIED")
        self.assertEqual(pkpk["raw"], "3.30000E+00")
        # The top-level block must not retain a consumable number either.
        self.assertIsNone(snapshot["measurement"]["metrics"]["PKPK"]["value"])
        self.assertEqual(snapshot["measurement"]["metrics"]["PKPK"]["raw"], "3.30000E+00")

    def test_model_channel_count_is_conservative(self):
        two_channel = snapshot_scope(
            channels=("C1", "C2"),
            model="Siglent,SDS802X HD,SDS1,4.8.12.1.1.6.5",
        )
        snapshot = build_snapshot(two_channel, ["C1", "C2", "C3"])
        self.assertEqual(snapshot["instrument"]["channel_count"], 2)
        self.assertEqual(snapshot["instrument"]["channel_count_source"], "series-minimum")
        self.assertEqual(snapshot["channels"]["C3"]["status"], "UNSUPPORTED")
        self.assertFalse(any("CHANnel3" in command for command in two_channel.sent))
        self.assertEqual(snapshot["status"], "INCOMPLETE")

        # A documented four-channel model still needs the caller's declaration:
        # the model suffix alone is not evidence of four channels here.
        unconfirmed = snapshot_scope(
            channels=("C1",),
            model="Siglent,SDS804X HD,SDS1,4.8.12.1.1.6.5",
        )
        snapshot = build_snapshot(unconfirmed, ["C1", "C4"])
        self.assertEqual(snapshot["instrument"]["channel_count"], 2)
        self.assertEqual(snapshot["channels"]["C4"]["status"], "UNSUPPORTED")
        self.assertFalse(any("CHANnel4" in command for command in unconfirmed.sent))

        unknown = ScriptedScope({"*IDN?": "Siglent,OTHERMODEL,SDS1,4.8.12.1.1.6.5"})
        snapshot = build_snapshot(unknown, ["C1", "C2"])
        self.assertEqual(snapshot["status"], "UNSUPPORTED")
        self.assertIsNone(snapshot["instrument"]["channel_count"])
        self.assertEqual(unknown.sent, ["*IDN?"])

        declared = ScriptedScope(
            {
                "*IDN?": "Siglent,OTHERMODEL,SDS1,4.8.12.1.1.6.5",
                "SAST?": "Stop",
                "TRMD?": "SINGle",
                ":TRIGger:TYPE?": "PULSE",
                **channel_answers("C1"),
                ":MEASure:SIMPle:SOURce?": ["C1", "C1"],
                ":MEASure:SIMPle:VALue? PKPK": "1.0",
                ":MEASure:SIMPle:VALue? MAX": "1.0",
                ":MEASure:SIMPle:VALue? MIN": "0.0",
                ":CHANnel1:UNIT?": "V",
            }
        )
        snapshot = build_snapshot(declared, ["C1"], declared_channel_count=2)
        self.assertEqual(snapshot["instrument"]["channel_count_source"], "user-supplied")
        self.assertEqual(snapshot["status"], "COMPLETE")

    def test_a_screenshot_can_never_supply_the_verdict(self):
        scope = snapshot_scope(channels=("C1",))
        snapshot = build_snapshot(scope, ["C1"])
        self.assertFalse(any("PRINt" in command.upper() for command in scope.sent))
        self.assertIn("never per-channel presence or absence", snapshot["limits"]["screenshot"])
        self.assertEqual(snapshot["limits"]["no_signal_verdict"], "NOT_SUPPORTED_BY_THIS_SNAPSHOT")
        # Every per-channel evidence statement cites a query and a raw reply.
        for row in snapshot["channels"].values():
            self.assertTrue(row["measurement"]["pkpk"]["source_query"].endswith("PKPK"))
            self.assertIsNotNone(row["measurement"]["pkpk"]["raw"])

    def test_attribute_measurements_keeps_unmatched_rows_unverified(self):
        block = {
            "source": "C2",
            "source_stable": True,
            "queried_at": "2026-11-23T00:00:00Z",
            "source_before": {"raw": "C2"},
            "source_after": {"raw": "C2"},
            "transport_failure": None,
            "metrics": {
                "PKPK": {
                    "query": ":MEASure:SIMPle:VALue? PKPK",
                    "raw": "3.3E+00",
                    "metric": "PKPK",
                    "value": 3.3,
                    "unit": "V",
                    "unit_status": "BOUND",
                    "status": "OBSERVED",
                }
            },
        }
        attributed = attribute_measurements(block, ["C2", "C3"])
        self.assertEqual(attributed["C2"]["pkpk"]["value"], 3.3)
        self.assertIsNone(attributed["C3"]["pkpk"]["value"])
        self.assertEqual(attributed["C3"]["pkpk"]["status"], "UNVERIFIED")

    def test_table_lists_each_channel_and_raw_replies(self):
        snapshot = build_snapshot(snapshot_scope(channels=("C1", "C2"), source=("C1", "C1")), ["C1", "C2"])
        table = format_table(snapshot)
        self.assertIn("C1:", table)
        self.assertIn("C2:", table)
        self.assertIn("source='C1'", table)
        self.assertIn("PKPK", table)
        self.assertIn("snapshot status: COMPLETE", table)


class CliTests(unittest.TestCase):
    def test_cli_writes_json_and_prints_the_table(self):
        scope = snapshot_scope(channels=("C1",))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "snapshot.json"
            with mock.patch.object(channel_snapshot, "ScopeSession", lambda *args, **kwargs: scope):
                with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                    code = channel_snapshot.main(
                        ["--host", "example.invalid", "--channels", "C1", "--out", str(out)]
                    )
            self.assertEqual(code, 0)
            stored = json.loads(out.read_text())
            self.assertEqual(stored["schema"], SCHEMA)
            self.assertEqual(stored["status"], "COMPLETE")
            self.assertIn("C1:", stdout.getvalue())

    def test_cli_json_mode_is_machine_readable(self):
        scope = snapshot_scope(channels=("C1",))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "snapshot.json"
            with mock.patch.object(channel_snapshot, "ScopeSession", lambda *args, **kwargs: scope):
                with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                    code = channel_snapshot.main(
                        ["--host", "example.invalid", "--channels", "C1", "--json"]
                    )
            self.assertEqual(code, 0)
            stored = json.loads(stdout.getvalue())
            self.assertEqual(stored["schema"], SCHEMA)
            self.assertEqual(stored["channels"]["C1"]["measurement"]["pkpk"]["value"], 3.3)

    def test_cli_requires_an_explicit_channel_list_and_host(self):
        with mock.patch("sys.stderr", new_callable=io.StringIO):
            with mock.patch.object(sys, "argv", ["channel_snapshot.py", "--host", "example.invalid"]):
                with self.assertRaises(SystemExit):
                    channel_snapshot.parse_args()
            with mock.patch.object(sys, "argv", ["channel_snapshot.py", "--channels", "C1"]):
                with self.assertRaises(SystemExit):
                    channel_snapshot.parse_args()

    def test_cli_rejects_the_legacy_shell_port_and_bad_timeouts_before_connecting(self):
        with mock.patch.object(channel_snapshot, "ScopeSession") as session:
            with mock.patch("sys.stderr", new_callable=io.StringIO):
                for arguments in (
                    ["--host", "example.invalid", "--channels", "C1", "--port", "5024"],
                    ["--host", "example.invalid", "--channels", "C1", "--timeout", "0"],
                    ["--host", "example.invalid", "--channels", "C1", "--timeout", "nan"],
                    ["--host", "example.invalid", "--channels", "C1", "--timeout", "inf"],
                ):
                    with self.subTest(arguments=arguments):
                        with self.assertRaises(SystemExit):
                            channel_snapshot.parse_args(arguments)
            session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
