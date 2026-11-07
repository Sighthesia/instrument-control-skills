#!/usr/bin/env python3
"""Offline tests for the configuration engine and its documented catalog.

Nothing here talks to an instrument: the fake session records every byte the
engine would send, so the tests can assert both the wire plan and the refusal
paths without a scope on the network.
"""

import json
import tempfile
import unittest
from pathlib import Path

import scope_command_catalog as catalog
from configure_scope import (
    PlanError,
    Step,
    apply_steps,
    build_plan,
    check_value,
    exit_code,
    load_assignment_file,
    main,
    overall_status,
    readback_matches,
    split_assignment,
    split_top_level,
)


class FakeSession:
    """Minimal stand-in for ``ScopeSession`` with an echo-style readback."""

    def __init__(self, resolve=None, fail_on=None, state="RUN"):
        self.values = {}
        self.writes = []
        self.queries = []
        self.state = state
        self.resolve = resolve or (lambda command, value: value)
        self.fail_on = set(fail_on or ())
        self.pending_errors = []

    def write(self, command, **kwargs):
        self.writes.append(command)
        name, _, value = command.partition(" ")
        if name in self.fail_on:
            self.pending_errors.append('-113,"Undefined header"')
        self.values[name.upper() + "?"] = self.resolve(name, value)

    def query_ascii(self, command, **kwargs):
        self.queries.append(command)
        if command.upper() == "SYST:ERR?":
            return self.pending_errors.pop(0) if self.pending_errors else "0"
        return self.values.get(command.upper(), "0")


def plan_for(assignments, allowed=("display",), **kwargs):
    return build_plan(
        assignments,
        allowed=set(allowed),
        allow_unlisted=kwargs.pop("allow_unlisted", False),
        manual_page=kwargs.pop("manual_page", None),
    )


class CatalogIntegrity(unittest.TestCase):
    def test_every_entry_resolves_to_itself(self):
        for key, spec in catalog.CATALOG.items():
            resolved = catalog.lookup(key)
            self.assertIsNotNone(resolved, key)
            self.assertEqual(resolved[0].command, key)
            self.assertEqual(spec.kind in (
                "enum", "enum_prefix", "int", "float", "number", "string",
                "compound", "action", "any",
            ), True, key)
            self.assertIn(spec.risk, {
                "display", "acquisition_context", "file_write", "destructive",
            })
            self.assertGreater(spec.page, 0, key)

    def test_short_forms_and_indices_resolve(self):
        resolved = catalog.lookup("dec:bus2:uart:baud")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[0].command, ":DECode:BUS<n>:UART:BAUD")
        self.assertEqual(resolved[1], {"n": "2"})

        resolved = catalog.lookup(":FUNC1:FFT:MODE")
        self.assertEqual(resolved[0].command, ":FUNCtion<x>:FFT:MODE")
        self.assertEqual(resolved[1], {"x": "1"})

    def test_manual_defects_are_corrected(self):
        self.assertEqual(
            list(catalog.CATALOG[":TRIGger:SPI:BITorder"].choices), ["LSB", "MSB"]
        )
        self.assertIn("ARINC429", catalog.CATALOG[":DECode:BUS<n>:PROTocol"].choices)
        self.assertIn(":TRIGger:RUNT:HLDTime", catalog.CATALOG)
        self.assertNotIn(":TRIGger:RUNt:HLDTime", catalog.CATALOG)

    def test_unknown_command_is_not_invented(self):
        self.assertIsNone(catalog.lookup(":DECode:BUS1:NOTACommand"))


class AssignmentParsing(unittest.TestCase):
    def test_split_keeps_quoted_arguments_whole(self):
        self.assertEqual(
            split_assignment(':SAVE:IMAGe "U-disk0/a b.png",PNG,OFF'),
            (":SAVE:IMAGe", '"U-disk0/a b.png",PNG,OFF'),
        )

    def test_split_requires_colon(self):
        with self.assertRaises(PlanError):
            split_assignment("DECode ON")

    def test_top_level_split_respects_quotes(self):
        self.assertEqual(
            split_top_level('"local/a,b.xml",EXTernal'),
            ['"local/a,b.xml"', "EXTernal"],
        )


class PlanValidation(unittest.TestCase):
    def test_valid_decoder_plan(self):
        steps = plan_for([
            ":DECode ON",
            ":DEC:BUS1:PROT UART",
            ":DECode:BUS1:UART:BAUD 9600bps",
        ])
        self.assertEqual([step.wire for step in steps], [
            ":DECode ON", ":DEC:BUS1:PROT UART", ":DECode:BUS1:UART:BAUD 9600bps",
        ])
        self.assertEqual(steps[1].canonical, ":DECode:BUS<n>:PROTocol")
        self.assertEqual(steps[1].indices, {"n": "1"})

    def test_out_of_range_index_is_refused(self):
        with self.assertRaises(PlanError) as ctx:
            plan_for([":DECode:BUS3:FORMat HEX"])
        self.assertIn("<n>=3", str(ctx.exception))

    def test_undocumented_keyword_is_refused(self):
        with self.assertRaises(PlanError) as ctx:
            plan_for([":DECode:BUS1:FORMat OCTal"])
        self.assertIn("OCTal", str(ctx.exception))

    def test_numeric_range_is_refused(self):
        with self.assertRaises(PlanError) as ctx:
            plan_for([":TRIGger:UART:DLENgth 9"], allowed=("acquisition_context",))
        self.assertIn("maximum", str(ctx.exception))

    def test_missing_permission_is_refused(self):
        with self.assertRaises(PlanError) as ctx:
            plan_for([":TRIGger:SPI:BITorder LSB"])
        self.assertIn("--allow acquisition_context", str(ctx.exception))

    def test_action_command_rejects_a_value(self):
        with self.assertRaises(PlanError) as ctx:
            plan_for([":RECall:FDEFault now"], allowed=("destructive",))
        self.assertIn("takes no argument", str(ctx.exception))

    def test_destructive_command_needs_its_own_permission(self):
        with self.assertRaises(PlanError) as ctx:
            plan_for([":RECall:SERase"], allowed=("file_write",))
        self.assertIn("--allow destructive", str(ctx.exception))

    def test_unlisted_command_needs_permission_and_page(self):
        with self.assertRaises(PlanError) as ctx:
            plan_for([":SYSTem:BEEPer ON"])
        self.assertIn("--allow-unlisted", str(ctx.exception))

        with self.assertRaises(PlanError) as ctx:
            plan_for([":SYSTem:BEEPer ON"], allow_unlisted=True)
        self.assertIn("--manual-page", str(ctx.exception))

        steps = plan_for([":SYSTem:BEEPer ON"], allow_unlisted=True, manual_page=411)
        self.assertFalse(steps[0].listed)
        self.assertEqual(steps[0].page, 411)
        self.assertEqual(steps[0].status, "planned")

    def test_string_argument_must_be_quoted(self):
        spec = catalog.CATALOG[":FUNCtion<x>:LABel:TEXT"]
        self.assertTrue(check_value(spec, "MATH")[0])
        self.assertEqual(check_value(spec, '"MATH"')[0], [])

    def test_compound_argument_requires_separators(self):
        spec = catalog.CATALOG[":SAVE:IMAGe"]
        self.assertTrue(check_value(spec, '"path"')[0])
        self.assertEqual(check_value(spec, '"path",PNG,OFF')[0], [])

    def test_index_placeholder_must_be_concrete(self):
        with self.assertRaises(PlanError) as ctx:
            plan_for([":DECode:BUS<n>:FORMat HEX"])
        self.assertIn("concrete index", str(ctx.exception))

    def test_channel_reference_domain(self):
        spec = catalog.CATALOG[":DECode:BUS<n>:CAN:SOURce"]
        self.assertEqual(check_value(spec, "C1")[0], [])
        self.assertEqual(check_value(spec, "D15")[0], [])
        self.assertTrue(check_value(spec, "Cx")[0])


class ReadbackComparison(unittest.TestCase):
    def test_numeric_tolerance(self):
        self.assertTrue(readback_matches("1.5e-08", "1.50E-08"))
        self.assertTrue(readback_matches("9600", "9.60E+03"))
        self.assertFalse(readback_matches("9600", "115200"))

    def test_short_keyword_forms(self):
        self.assertTrue(readback_matches("ALTernate", "ALT"))
        self.assertTrue(readback_matches("RISing", "RIS"))
        self.assertFalse(readback_matches("RISing", "FALL"))

    def test_boolean_encoding(self):
        self.assertTrue(readback_matches("ON", "1"))
        self.assertTrue(readback_matches("OFF", "0"))
        self.assertFalse(readback_matches("ON", "OFF"))

    def test_keyword_with_resolved_value(self):
        self.assertTrue(readback_matches("CUSTom,1000000", "1000000"))
        self.assertTrue(readback_matches("INTernal,2", "INT,2"))

    def test_quoted_path(self):
        self.assertTrue(readback_matches('"U-disk0/a.png"', "U-disk0/a.png"))
        self.assertFalse(readback_matches('"U-disk0/a.png"', "U-disk0/b.png"))


class ApplyEngine(unittest.TestCase):
    def _steps(self, assignments, allowed=("display",)):
        return plan_for(assignments, allowed=allowed)

    def test_verified_run_sends_one_command_at_a_time(self):
        session = FakeSession()
        steps = self._steps([":DECode ON", ":DECode:BUS1:FORMat HEX"])
        apply_steps(session, steps)

        self.assertEqual(session.writes, [":DECode ON", ":DECode:BUS1:FORMat HEX"])
        self.assertEqual([step.status for step in steps], ["verified", "verified"])
        self.assertEqual(overall_status(steps), "COMPLETE")
        self.assertEqual(exit_code(steps), 0)

    def test_queue_error_stops_the_run(self):
        session = FakeSession(fail_on={":DECode:BUS1:FORMat"})
        steps = self._steps([
            ":DECode ON",
            ":DECode:BUS1:FORMat HEX",
            ":DECode:BUS1:PROTocol UART",
        ])
        apply_steps(session, steps)

        self.assertEqual([step.status for step in steps],
                         ["verified", "rejected", "not_attempted"])
        self.assertIn("Undefined header", steps[1].detail)
        self.assertEqual(overall_status(steps), "INCOMPLETE")
        self.assertEqual(exit_code(steps), 1)

    def test_mismatch_stops_the_run(self):
        session = FakeSession(resolve=lambda command, value: "OFF")
        steps = self._steps([":DECode ON", ":DECode:BUS1:FORMat HEX"])
        apply_steps(session, steps)

        self.assertEqual([step.status for step in steps], ["mismatch", "not_attempted"])
        self.assertIn("OFF", steps[0].detail)

    def test_continue_on_mismatch_is_opt_in(self):
        session = FakeSession(
            resolve=lambda command, value: "BIN" if command.endswith("FORMat") else value
        )
        steps = self._steps([":DECode:BUS1:FORMat HEX", ":DECode OFF"])
        apply_steps(session, steps, stop_on_mismatch=False)

        self.assertEqual([step.status for step in steps], ["mismatch", "verified"])

    def test_command_without_readback_is_unverified_not_complete(self):
        session = FakeSession()
        steps = self._steps(
            [":MTESt:MASK:CREat 1,1"],
            allowed=("display", "acquisition_context", "file_write", "destructive"),
        )
        self.assertIsNone(steps[0].query)
        apply_steps(session, steps)

        self.assertEqual(steps[0].status, "unverified")
        self.assertEqual(overall_status(steps), "UNVERIFIED")
        self.assertEqual(exit_code(steps), 3)
        self.assertEqual(session.writes, [":MTESt:MASK:CREat 1,1"])

    def test_dry_run_sends_nothing(self):
        code = main(["plan", "--allow", "display", "--set", ":DECode ON"])
        self.assertEqual(code, 0)

    def test_refused_plan_never_connects(self):
        code = main(["apply", "--write", "--allow", "display", "--set", ":DECode:BUS3:FORMat HEX"])
        self.assertEqual(code, 2)

    def test_plan_file_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            path.write_text(json.dumps({
                "steps": [{"command": ":DECode", "value": "ON"}]
            }), encoding="utf-8")
            self.assertEqual(load_assignment_file(str(path)), [":DECode ON"])

    def test_plan_file_with_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            path.write_text(json.dumps({"steps": [":DECode ON"]}), encoding="utf-8")
            self.assertEqual(load_assignment_file(str(path)), [":DECode ON"])


class StatusVocabulary(unittest.TestCase):
    def test_empty_run_is_incomplete(self):
        self.assertEqual(overall_status([]), "INCOMPLETE")

    def test_mixed_status_is_incomplete(self):
        steps = [Step("a", ":A", "1", status="verified"), Step("b", ":B", "1", status="unverified")]
        self.assertEqual(overall_status(steps), "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
