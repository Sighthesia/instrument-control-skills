from __future__ import annotations

import hashlib
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "assets" / "fixtures"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gdm8352_protocol import (  # noqa: E402
    ALLOWED_QUERIES,
    BEEP_STATES,
    COMMAND_TERMINATOR,
    COMPLETE,
    INCOMPLETE,
    INVALID,
    KNOWN_ERROR_TEXTS,
    MEASUREMENT_FUNCTIONS,
    QUERY_SPECS,
    UNSUPPORTED,
    UNVERIFIED,
    CommandRefused,
    ProtocolError,
    artifact_decimal,
    build_query,
    extract_payload,
    parse_auto_range,
    parse_beep_state,
    parse_function_setting,
    parse_identity,
    parse_ieee4882_numeric,
    parse_metadata,
    parse_range_setting,
    parse_read,
    parse_response,
    parse_system_error,
    parse_temperature_unit,
    read_frame,
    resolve_query,
    response_failure,
)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FrameTests(unittest.TestCase):
    def test_crlf_is_the_observed_terminator(self):
        frame = read_frame(fixture("idn.txt"))
        self.assertEqual(frame.terminator, b"\r\n")
        self.assertEqual(frame.content, b"GWInstek,GDM8352,GEP848232,1.00")
        self.assertEqual(frame.trailing, b"")
        self.assertEqual(frame.raw, fixture("idn.txt"))

    def test_lf_is_accepted(self):
        self.assertEqual(read_frame(b"abc\n").terminator, b"\n")

    def test_cr_is_accepted(self):
        self.assertEqual(read_frame(b"abc\r").terminator, b"\r")

    def test_lfcr_is_accepted(self):
        self.assertEqual(read_frame(b"abc\n\r").terminator, b"\n\r")

    def test_missing_terminator_is_incomplete(self):
        with self.assertRaises(ProtocolError) as caught:
            read_frame(fixture("synthetic/numeric-missing-terminator.txt"))
        self.assertEqual(caught.exception.status, INCOMPLETE)

    def test_empty_is_incomplete(self):
        with self.assertRaises(ProtocolError) as caught:
            read_frame(b"")
        self.assertEqual(caught.exception.status, INCOMPLETE)

    def test_trailing_bytes_are_invalid(self):
        with self.assertRaises(ProtocolError) as caught:
            read_frame(fixture("synthetic/numeric-extra-line.txt"))
        self.assertEqual(caught.exception.status, INVALID)
        self.assertIn("extra bytes", str(caught.exception))

    def test_oversized_is_unsupported(self):
        with self.assertRaises(ProtocolError) as caught:
            read_frame(b"x" * 70_000 + b"\n")
        self.assertEqual(caught.exception.status, UNSUPPORTED)

    def test_non_bytes_is_invalid(self):
        with self.assertRaises(ProtocolError) as caught:
            read_frame("24.000\r\n")  # type: ignore[arg-type]
        self.assertEqual(caught.exception.status, INVALID)

    def test_metadata_preserves_bytes(self):
        frame = read_frame(fixture("meas-volt-dc.txt"))
        metadata = parse_metadata(frame, response_type="numeric")
        self.assertEqual(metadata["text"], "+0.10466E-01")
        self.assertEqual(
            metadata["raw_sha256"], hashlib.sha256(fixture("meas-volt-dc.txt")).hexdigest()
        )
        self.assertEqual(extract_payload(metadata)["fields"], ["+0.10466E-01"])

    def test_non_ascii_is_invalid(self):
        with self.assertRaises(ProtocolError) as caught:
            parse_metadata(read_frame(b"\xff\r\n"), response_type="numeric")
        self.assertEqual(caught.exception.status, INVALID)


class NumericTests(unittest.TestCase):
    def test_raw_text_and_decimal_are_both_preserved(self):
        numeric = parse_ieee4882_numeric("+0.10466E-01")
        self.assertEqual(numeric["numeric_token"], "+0.10466E-01")
        self.assertEqual(numeric["value"], Decimal("0.010466"))
        self.assertEqual(numeric["value_decimal"], "0.010466")
        self.assertEqual(numeric["fraction_digits"], 5)
        self.assertEqual(numeric["exponent"], -1)

    def test_suffix_is_reported_without_unit_guessing(self):
        numeric = parse_ieee4882_numeric("+1.00156E+03OHM")
        self.assertEqual(numeric["raw_unit_suffix"], "OHM")
        self.assertEqual(numeric["value"], Decimal("1001.56"))

    def test_non_numeric_is_invalid(self):
        for token in ("nan", "inf", "OVERLOAD", "+0.1E", "1,0", "", "+1.0 V"):
            with self.subTest(token=token):
                with self.assertRaises(ProtocolError) as caught:
                    parse_ieee4882_numeric(token)
                self.assertIn(caught.exception.status, (INCOMPLETE, INVALID))


class IdentityTests(unittest.TestCase):
    def test_verified_idn_is_complete(self):
        artifact = parse_identity(fixture("idn.txt"))
        self.assertEqual(artifact["status"], COMPLETE)
        self.assertEqual(artifact["vendor"], "GW Instek")
        self.assertEqual(artifact["model"], "GDM-8352")
        self.assertEqual(artifact["serial"], "GEP848232")
        self.assertEqual(artifact["firmware"], "1.00")
        self.assertEqual(artifact["raw_text"], "GWInstek,GDM8352,GEP848232,1.00")
        self.assertEqual(artifact["terminator"], "\r\n")
        self.assertEqual(artifact["integrity"]["raw_bytes"], 33)

    def test_dashed_model_and_spaced_vendor_are_accepted(self):
        artifact = parse_identity(b"GW INSTEK,GDM-8352,SN123,1.00\r\n")
        self.assertEqual(artifact["status"], COMPLETE)

    def test_missing_firmware_is_incomplete(self):
        artifact = parse_identity(fixture("synthetic/identity-missing-firmware.txt"))
        self.assertEqual(artifact["status"], INCOMPLETE)
        self.assertIn("firmware", " ".join(artifact["integrity"]["reasons"]))
        self.assertIsNone(artifact["serial"])

    def test_failure_artifacts_keep_stable_null_fields(self):
        artifact = parse_response(fixture("synthetic/numeric-non-numeric.txt"), "MEAS:VOLT:DC?")
        for field in ("function", "quantity", "unit", "numeric_token", "value_decimal"):
            self.assertIn(field, artifact)
        self.assertIsNone(artifact["value_decimal"])

    def test_wrong_model_is_invalid(self):
        artifact = parse_identity(fixture("synthetic/identity-wrong-model.txt"))
        self.assertEqual(artifact["status"], INVALID)

    def test_extra_field_is_invalid(self):
        artifact = parse_identity(fixture("synthetic/identity-extra-field.txt"))
        self.assertEqual(artifact["status"], INVALID)

    def test_wrong_vendor_is_invalid(self):
        artifact = parse_identity(b"Rigol,GDM8352,SN123,1.00\r\n")
        self.assertEqual(artifact["status"], INVALID)

    def test_v_prefixed_firmware_is_invalid(self):
        artifact = parse_identity(b"GWInstek,GDM8352,GEP848232,V1.00\r\n")
        self.assertEqual(artifact["status"], INVALID)

    def test_empty_response_is_incomplete(self):
        self.assertEqual(parse_identity(b"")["status"], INCOMPLETE)

    def test_empty_line_is_incomplete(self):
        self.assertEqual(parse_identity(b"\r\n")["status"], INCOMPLETE)


class MeasurementFunctionTableTests(unittest.TestCase):
    def test_all_documented_first_display_functions_are_present(self):
        self.assertEqual(
            set(MEASUREMENT_FUNCTIONS),
            {
                "dc-voltage",
                "ac-voltage",
                "dcac-voltage",
                "dc-current",
                "ac-current",
                "dcac-current",
                "resistance-2w",
                "resistance-4w",
                "frequency",
                "period",
                "continuity",
                "diode",
                "capacitance",
                "temperature",
            },
        )

    def test_units_come_from_the_manual(self):
        expected = {
            "dc-voltage": "V",
            "ac-voltage": "V",
            "dcac-voltage": "V",
            "dc-current": "A",
            "ac-current": "A",
            "dcac-current": "A",
            "resistance-2w": "Ω",
            "resistance-4w": "Ω",
            "frequency": "Hz",
            "period": "s",
            "continuity": "Ω",
            "diode": "V",
            "capacitance": "F",
            "temperature": "°C",
        }
        self.assertEqual({key: item.unit for key, item in MEASUREMENT_FUNCTIONS.items()}, expected)

    def test_every_query_is_unique_and_query_shaped(self):
        queries = [item.query for item in MEASUREMENT_FUNCTIONS.values()]
        self.assertEqual(len(queries), len(set(queries)))
        for query in queries:
            self.assertTrue(query.endswith("?"))

    def test_undocumented_response_formats_are_marked_unverified(self):
        for key in ("period", "continuity", "diode", "capacitance"):
            with self.subTest(key=key):
                self.assertEqual(MEASUREMENT_FUNCTIONS[key].format_status, UNVERIFIED)

    def test_temperature_unit_is_ambiguous_until_sens_unit_is_read(self):
        function = MEASUREMENT_FUNCTIONS["temperature"]
        self.assertEqual(function.unit_status, UNVERIFIED)
        self.assertEqual(function.unit_candidates, ("°C", "°F"))


class MeasurementParsingTests(unittest.TestCase):
    def test_verified_dc_voltage_is_complete(self):
        artifact = parse_response(fixture("meas-volt-dc.txt"), "MEAS:VOLT:DC?")
        self.assertEqual(artifact["status"], COMPLETE)
        self.assertEqual(artifact["function"], "dc-voltage")
        self.assertEqual(artifact["quantity"], "voltage")
        self.assertEqual(artifact["numeric_token"], "+0.10466E-01")
        self.assertEqual(artifact["raw_text"], "+0.10466E-01")
        self.assertEqual(artifact["value_decimal"], "0.010466")
        self.assertEqual(Decimal(artifact["value_decimal"]), Decimal("0.010466"))
        self.assertEqual(artifact["unit"], "V")
        self.assertEqual(artifact["unit_source"], "measurement-command")
        self.assertEqual(artifact["integrity"]["reasons"], [])
        self.assertEqual(artifact["manual_page"], 117)

    def test_verified_dc_current_is_complete(self):
        artifact = parse_response(fixture("meas-curr-dc.txt"), "MEAS:CURR:DC?")
        self.assertEqual(artifact["status"], COMPLETE)
        self.assertEqual(artifact["quantity"], "current")
        self.assertEqual(artifact["unit"], "A")
        self.assertEqual(artifact["value_decimal"], "0.0000026")

    def test_artifact_decimal_accessor_is_exact(self):
        artifact = parse_response(fixture("meas-volt-dc.txt"), "MEAS:VOLT:DC?")
        self.assertEqual(artifact_decimal(artifact), Decimal("0.010466"))
        self.assertIsNone(artifact_decimal(parse_identity(fixture("idn.txt"))))

    def test_fixture_json_never_contains_a_float(self):
        artifact = parse_response(fixture("meas-volt-dc.txt"), "MEAS:VOLT:DC?")
        encoded = json.dumps(artifact)
        self.assertIn('"value_decimal": "0.010466"', encoded)
        self.assertNotIn('"value":', encoded)
        self.assertIsInstance(artifact["value_decimal"], str)

    def test_matching_unit_suffix_is_accepted(self):
        artifact = parse_response(b"+1.00000E+00V\r\n", "MEAS:VOLT:DC?")
        self.assertEqual(artifact["status"], COMPLETE)
        self.assertEqual(artifact["unit_source"], "response-suffix")

    def test_wrong_unit_suffix_is_invalid(self):
        artifact = parse_response(
            fixture("synthetic/numeric-unit-mismatch.txt"), "MEAS:VOLT:DC?"
        )
        self.assertEqual(artifact["status"], INVALID)
        self.assertIn("conflicts", " ".join(artifact["integrity"]["reasons"]))

    def test_non_numeric_is_invalid(self):
        artifact = parse_response(fixture("synthetic/numeric-non-numeric.txt"), "MEAS:VOLT:DC?")
        self.assertEqual(artifact["status"], INVALID)

    def test_missing_terminator_is_incomplete(self):
        artifact = parse_response(
            fixture("synthetic/numeric-missing-terminator.txt"), "MEAS:VOLT:DC?"
        )
        self.assertEqual(artifact["status"], INCOMPLETE)

    def test_empty_response_is_incomplete(self):
        artifact = parse_response(fixture("synthetic/empty-response.txt"), "MEAS:VOLT:DC?")
        self.assertEqual(artifact["status"], INCOMPLETE)

    def test_extra_line_is_invalid(self):
        artifact = parse_response(fixture("synthetic/numeric-extra-line.txt"), "MEAS:VOLT:DC?")
        self.assertEqual(artifact["status"], INVALID)

    def test_temperature_reading_is_unverified(self):
        artifact = parse_response(b"+0.02667E+03\r\n", "MEAS:TEMP:TCO?")
        self.assertEqual(artifact["status"], UNVERIFIED)
        self.assertEqual(artifact["unit"], "°C")
        self.assertEqual(artifact["unit_candidates"], ["°C", "°F"])
        self.assertIn("temperature_unit_not_conveyed_by_response", artifact["integrity"]["reasons"])

    def test_temperature_fahrenheit_suffix_is_not_farad(self):
        artifact = parse_response(b"+0.02667E+03F\r\n", "MEAS:TEMP:TCO?")
        self.assertEqual(artifact["status"], COMPLETE)
        self.assertEqual(artifact["unit"], "°F")
        self.assertEqual(artifact["unit_source"], "response-suffix")

    def test_continuity_without_an_example_is_unverified(self):
        artifact = parse_response(b"+0.50000E+00\r\n", "MEAS:CONT?")
        self.assertEqual(artifact["status"], UNVERIFIED)
        self.assertIn("continuity_response_format_not_documented", artifact["integrity"]["reasons"])

    def test_documented_frequency_is_complete(self):
        artifact = parse_response(b"+1.00123E+03\r\n", "MEAS:FREQ?")
        self.assertEqual(artifact["status"], COMPLETE)
        self.assertEqual(artifact["unit"], "Hz")
        self.assertEqual(Decimal(artifact["value_decimal"]), Decimal("1001.23"))

    def test_temperature_parameter_is_accepted_and_not_guessed(self):
        artifact = parse_response(b"+0.02667E+03\r\n", "MEAS:TEMP:TCO? J")
        self.assertEqual(artifact["status"], UNVERIFIED)
        self.assertEqual(artifact["function"], "temperature")

    def test_long_form_command_parses_the_same_bytes(self):
        artifact = parse_response(fixture("meas-curr-dc.txt"), "MEASure:CURRent:DC?")
        self.assertEqual(artifact["function"], "dc-current")


class ReadParsingTests(unittest.TestCase):
    def test_verified_read_separates_both_displays(self):
        artifact = parse_read(fixture("read-two-display.txt"))
        self.assertEqual(artifact["status"], UNVERIFIED)
        self.assertEqual(artifact["sample_count"], 1)
        self.assertEqual(artifact["first_display"]["raw_text"], "+0.00023E-02")
        self.assertEqual(artifact["first_display"]["value_decimal"], "0.0000023")
        self.assertEqual(artifact["second_display"]["raw_text"], "+0.00000E+00")
        self.assertEqual(artifact["second_display"]["value_decimal"], "0.00000")
        self.assertEqual(artifact["second_display"]["role_status"], COMPLETE)
        self.assertEqual(artifact["second_display"]["semantics_status"], UNVERIFIED)
        self.assertEqual(artifact["first_display"]["semantics_status"], UNVERIFIED)
        self.assertEqual(artifact["second_display"]["unit"], None)
        self.assertEqual(artifact["second_display"]["unit_status"], UNVERIFIED)
        self.assertEqual(artifact["second_display"]["function"], None)
        self.assertIn("second_display_unit_not_conveyed", artifact["integrity"]["reasons"])

    def test_missing_second_field_is_incomplete(self):
        artifact = parse_read(fixture("synthetic/read-missing-second-field.txt"))
        self.assertEqual(artifact["status"], INCOMPLETE)
        self.assertIn("two-display", " ".join(artifact["integrity"]["reasons"]))

    def test_odd_field_count_is_incomplete(self):
        artifact = parse_read(fixture("synthetic/read-extra-fields.txt"))
        self.assertEqual(artifact["status"], INCOMPLETE)
        self.assertIn("odd field count", " ".join(artifact["integrity"]["reasons"]))

    def test_three_samples_are_grouped_pairwise(self):
        raw = b"+1.0E+00,+2.0E+00,+3.0E+00,+4.0E+00,+5.0E+00,+6.0E+00\r\n"
        artifact = parse_read(raw)
        self.assertEqual(artifact["status"], UNVERIFIED)
        self.assertEqual(artifact["sample_count"], 3)
        self.assertEqual(artifact["samples"][2]["first"]["value_decimal"], "5.0")
        self.assertEqual(artifact["samples"][2]["second"]["value_decimal"], "6.0")
        self.assertIsNone(artifact["first_display"])
        self.assertIn("sample_count_not_queried", artifact["integrity"]["reasons"])

    def test_non_numeric_display_is_invalid(self):
        artifact = parse_read(b"+1.0E+00,OVERLOAD\r\n")
        self.assertEqual(artifact["status"], INVALID)

    def test_empty_field_is_incomplete(self):
        artifact = parse_read(b"+1.0E+00,\r\n")
        self.assertEqual(artifact["status"], INCOMPLETE)

    def test_empty_response_is_incomplete(self):
        self.assertEqual(parse_read(b"")["status"], INCOMPLETE)


class BeepTests(unittest.TestCase):
    def test_verified_no_beep(self):
        artifact = parse_beep_state(fixture("syst-beep-stat-no-beep.txt"))
        self.assertEqual(artifact["status"], COMPLETE)
        self.assertEqual(artifact["mode"], "no-beep")
        self.assertEqual(artifact["numeric_code"], 0)
        self.assertEqual(artifact["raw_text"], "No Beep")

    def test_all_three_documented_states(self):
        for text, mode, code in (
            (b"No Beep\r\n", "no-beep", 0),
            (b"Beep on Pass\r\n", "beep-on-pass", 1),
            (b"Beep on Fail\r\n", "beep-on-fail", 2),
        ):
            with self.subTest(text=text):
                artifact = parse_beep_state(text)
                self.assertEqual(artifact["status"], COMPLETE)
                self.assertEqual(artifact["mode"], mode)
                self.assertEqual(artifact["numeric_code"], code)

    def test_case_and_padding_are_normalised(self):
        artifact = parse_beep_state(b"  beep   on   pass \r\n")
        self.assertEqual(artifact["mode"], "beep-on-pass")

    def test_lf_only_terminator_is_accepted(self):
        self.assertEqual(parse_beep_state(fixture("synthetic/beep-lf-only.txt"))["status"], COMPLETE)

    def test_unknown_state_is_unsupported(self):
        artifact = parse_beep_state(fixture("synthetic/beep-unknown-state.txt"))
        self.assertEqual(artifact["status"], UNSUPPORTED)

    def test_extra_token_is_unsupported(self):
        artifact = parse_beep_state(fixture("synthetic/beep-extra-token.txt"))
        self.assertEqual(artifact["status"], UNSUPPORTED)

    def test_table_matches_the_manual_codes(self):
        self.assertEqual(
            {state["numeric_code"] for state in BEEP_STATES.values()}, {0, 1, 2}
        )


class SystemErrorTests(unittest.TestCase):
    def test_verified_command_error_is_recognised(self):
        artifact = parse_system_error(fixture("syst-err-command-error.txt"))
        self.assertEqual(artifact["status"], COMPLETE)
        self.assertEqual(artifact["message"], "Command error")
        self.assertEqual(artifact["category"], "command")
        self.assertEqual(artifact["source"], "observed")
        self.assertTrue(artifact["error_present"])
        self.assertFalse(artifact["manual_enumeration"])

    def test_ieee4882_texts_are_labelled_by_source(self):
        artifact = parse_system_error(b"Execution error\r\n")
        self.assertEqual(artifact["source"], "ieee-488.2")
        self.assertEqual(artifact["category"], "execution")

    def test_unknown_free_text_is_unsupported(self):
        artifact = parse_system_error(fixture("synthetic/error-unknown-text.txt"))
        self.assertEqual(artifact["status"], UNSUPPORTED)

    def test_zero_is_unverified_not_a_cleared_queue(self):
        artifact = parse_system_error(b"0\r\n")
        self.assertEqual(artifact["status"], UNVERIFIED)
        self.assertIsNone(artifact["error_present"])
        self.assertIn("no_error_encoding", " ".join(artifact["integrity"]["reasons"]))

    def test_empty_response_is_incomplete(self):
        self.assertEqual(parse_system_error(b"")["status"], INCOMPLETE)

    def test_known_text_table_is_explicit_about_sources(self):
        self.assertEqual(KNOWN_ERROR_TEXTS["command error"]["source"], "observed")
        self.assertEqual(KNOWN_ERROR_TEXTS["query error"]["source"], "ieee-488.2")


class SettingsParsingTests(unittest.TestCase):
    def test_function_setting(self):
        artifact = parse_function_setting(b"VOLT:AC\r\n")
        self.assertEqual(artifact["status"], COMPLETE)
        self.assertEqual(artifact["function_token"], "VOLT:AC")
        self.assertEqual(artifact["function"], "ac-voltage")

    def test_unknown_function_setting_is_unsupported(self):
        artifact = parse_function_setting(b"VOLT:DC\r\n")
        self.assertEqual(artifact["status"], UNSUPPORTED)

    def test_auto_range_on_and_off(self):
        self.assertTrue(parse_auto_range(b"1\r\n")["auto_range"])
        self.assertTrue(parse_auto_range(b"0\r\n")["manual_range"])

    def test_auto_range_other_value_is_invalid(self):
        self.assertEqual(parse_auto_range(b"2\r\n")["status"], INVALID)

    def test_range_number_has_no_attributable_unit(self):
        artifact = parse_range_setting(b"0.2\r\n")
        self.assertEqual(artifact["status"], UNVERIFIED)
        self.assertEqual(artifact["value_decimal"], "0.2")
        self.assertIsNone(artifact["unit"])
        self.assertIn("range_unit_depends_on_current_function", artifact["integrity"]["reasons"])

    def test_range_with_unit_suffix_is_invalid(self):
        self.assertEqual(parse_range_setting(b"0.2V\r\n")["status"], INVALID)

    def test_temperature_unit(self):
        artifact = parse_temperature_unit(b"C\r\n")
        self.assertEqual(artifact["status"], UNVERIFIED)
        self.assertEqual(artifact["unit"], "°C")
        self.assertEqual(parse_temperature_unit(b"F\r\n")["unit"], "°F")

    def test_unknown_temperature_unit_is_unsupported(self):
        self.assertEqual(parse_temperature_unit(b"K\r\n")["status"], UNSUPPORTED)


class CommandSafetyTests(unittest.TestCase):
    def test_allowed_queries_are_all_queries(self):
        self.assertTrue(all(query.endswith("?") for query in ALLOWED_QUERIES))
        self.assertEqual(len(ALLOWED_QUERIES), 8 + len(MEASUREMENT_FUNCTIONS))

    def test_idn_bytes(self):
        self.assertEqual(build_query("*IDN?"), b"*IDN?\r\n")
        self.assertEqual(COMMAND_TERMINATOR, b"\r\n")

    def test_measure_bytes(self):
        self.assertEqual(build_query("MEAS:VOLT:DC?"), b"MEAS:VOLT:DC?\r\n")
        self.assertEqual(build_query("meas:curr:dc?"), b"MEAS:CURR:DC?\r\n")

    def test_long_form_is_canonicalised(self):
        self.assertEqual(build_query("MEASure:VOLTage:DC?"), b"MEAS:VOLT:DC?\r\n")
        self.assertEqual(build_query("SYSTem:BEEPer:STATe?"), b"SYST:BEEP:STAT?\r\n")
        self.assertEqual(build_query("UNIT?"), b"SENS:UNIT?\r\n")

    def test_temperature_parameter_bytes(self):
        self.assertEqual(build_query("MEAS:TEMP:TCO? k"), b"MEAS:TEMP:TCO? K\r\n")

    def test_state_changing_and_unknown_commands_are_refused(self):
        refused = [
            "*RST",
            "*CLS",
            "*IDN",
            "CONF:VOLT:DC 1",
            "CONF?",
            "SYST:BEEP:STAT 0",
            "SYST:BEEP:STAT",
            "SYST:BEEP",
            "OUT1",
            "CAL:VOLT",
            "DISP ON",
            "SYST:LOC",
        ]
        for command in refused:
            with self.subTest(command=command):
                with self.assertRaises(CommandRefused):
                    build_query(command)

    def test_injection_and_separators_are_refused(self):
        for command in (
            "MEAS:VOLT:DC?;*RST",
            "*IDN?\r\n*RST",
            "*IDN?\n",
            "*IDN?\x00",
            "*IDN? | *RST",
        ):
            with self.subTest(command=command):
                with self.assertRaises(CommandRefused):
                    build_query(command)

    def test_two_parameters_are_refused(self):
        with self.assertRaises(CommandRefused):
            build_query("MEAS:TEMP:TCO? J K")
        with self.assertRaises(CommandRefused):
            build_query("MEAS:VOLT:DC? 2")

    def test_invalid_temperature_type_is_refused(self):
        with self.assertRaises(CommandRefused):
            build_query("MEAS:TEMP:TCO? X")

    def test_empty_and_oversized_commands_are_refused(self):
        with self.assertRaises(CommandRefused):
            build_query("   ")
        with self.assertRaises(CommandRefused):
            build_query("*IDN?" + "X" * 64)

    def test_resolve_query_returns_spec(self):
        spec, parameter = resolve_query("SYST:ERR?")
        self.assertEqual(spec.canonical, "SYST:ERR?")
        self.assertEqual(spec.kind, "system-error")
        self.assertIsNone(parameter)

    def test_query_table_kinds(self):
        self.assertEqual(QUERY_SPECS["CONF:FUNC?"].kind, "function-setting")
        self.assertEqual(QUERY_SPECS["CONF:RANG?"].kind, "range-setting")
        self.assertEqual(QUERY_SPECS["CONF:AUTO?"].kind, "auto-range")
        self.assertEqual(QUERY_SPECS["SENS:UNIT?"].kind, "temperature-unit")


class DispatchAndEvidenceTests(unittest.TestCase):
    def test_unknown_command_for_saved_response_is_unsupported(self):
        artifact = parse_response(fixture("conf-query-timeout.empty"), "CONF?")
        self.assertEqual(artifact["status"], UNSUPPORTED)

    def test_non_bytes_response_is_invalid(self):
        artifact = parse_response("+1.0E+00\r\n", "*IDN?")  # type: ignore[arg-type]
        self.assertEqual(artifact["status"], INVALID)

    def test_timeout_failure_artifact(self):
        artifact = response_failure("MEAS:VOLT:DC?", INCOMPLETE, "no response within 2s")
        self.assertEqual(artifact["kind"], "scalar-value")
        self.assertEqual(artifact["status"], INCOMPLETE)
        self.assertEqual(artifact["integrity"]["raw_bytes"], 0)
        self.assertEqual(
            artifact["integrity"]["raw_sha256"],
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    def test_capture_index_matches_every_fixture_byte(self):
        entries = [
            json.loads(line)
            for line in (FIXTURES / "captures.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(entries), 7)
        for entry in entries:
            with self.subTest(command=entry["command"]):
                data = (FIXTURES / entry["fixture"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["response_sha256"])
                self.assertEqual(len(data), entry["response_bytes"])
                self.assertEqual(entry["captured_on"], "2026-11-19")
                self.assertEqual(entry["firmware"], "1.00")
                self.assertEqual(entry["serial"], "GEP848232")

    def test_capture_index_marks_the_conf_timeout_as_zero_bytes(self):
        entries = [
            json.loads(line)
            for line in (FIXTURES / "captures.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        conf = next(entry for entry in entries if entry["command"] == "CONF?")
        self.assertEqual(conf["response_state"], "timeout-no-bytes")
        self.assertEqual(conf["response_bytes"], 0)
        self.assertIn("未复测", conf["note"])

    def test_fixture_hashes_are_locked(self):
        expected = {
            "idn.txt": "7101090c136112d7c9398e643cc5d3632bae81eab0595b15220bb71e47026671",
            "meas-volt-dc.txt": "6380eed705e5ce2f965d4af8cb94e60f15b3b5a3519607d6ade1cbbe843fbf34",
            "meas-curr-dc.txt": "7ab2c3a3df87ee8480385c406f78e9516cfd0286ce8682b5eb7dcad08892161b",
            "read-two-display.txt": "d4aebf352351c0c55f5c162fbb6aa5fefab68949f9c1519857adf0dbba73e869",
            "syst-beep-stat-no-beep.txt": "a77e2d0f1f3c6212032ba0b1d7bbe2c1e4d45be3380c6ea713d32b037a64f852",
            "syst-err-command-error.txt": "524d46fcaf39f33d691eeb890ee6eb9f93c08635304baf54f196f9bee326f74a",
        }
        for name, digest in expected.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256(fixture(name)).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()