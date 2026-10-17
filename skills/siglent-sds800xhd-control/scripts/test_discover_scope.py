#!/usr/bin/env python3
import json
import unittest
from unittest.mock import Mock, patch

from discover_scope import discover_ips, discover_lan, is_target_idn, main, parse_idn, probe_lan_host


class DiscoveryTests(unittest.TestCase):
    def test_parse_and_match_supported_idn(self):
        idn = parse_idn("Siglent Technologies,SDS824X HD,SD123,4.8.12\n")
        self.assertEqual(idn["model"], "SDS824X HD")
        self.assertTrue(is_target_idn(idn))
        self.assertFalse(is_target_idn(parse_idn("Other Corp,Scope,1,2")))

    @patch("discover_scope.socket.create_connection")
    def test_probe_sends_idn_and_ignores_banner(self, create_connection):
        sock = Mock()
        sock.recv.side_effect = [b"Welcome to the SCPI instrument 'Siglent SDS824X HD'\r\n>>\r\n", b"Siglent Technologies,SDS824X HD,S1,FW\r\n"]
        create_connection.return_value.__enter__.return_value = sock
        result = probe_lan_host("192.168.1.10")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["target"])
        sock.sendall.assert_called_once_with(b"*IDN?\n")

    @patch("discover_scope.socket.create_connection", side_effect=OSError("refused"))
    def test_probe_failure_is_structured(self, _create_connection):
        result = probe_lan_host("192.168.1.11")
        self.assertEqual(result["status"], "error")
        self.assertIn("refused", result["error"])

    @patch("discover_scope.probe_lan_host")
    def test_lan_scan_is_bounded_and_returns_successes(self, probe):
        probe.side_effect = lambda host, **_: {"host": host, "status": "ok", "target": True}
        report = discover_lan("192.168.1.0/30", max_hosts=2, workers=2)
        self.assertEqual(report["scanned"], 2)
        self.assertEqual(len(report["results"]), 2)
        with self.assertRaises(ValueError):
            discover_lan("192.168.1.0/24", max_hosts=2)

    @patch("discover_scope.probe_lan_host")
    def test_explicit_ip_report_keeps_errors_separate(self, probe):
        probe.side_effect = [
            {"host": "192.168.1.10", "status": "ok", "target": True},
            {"host": "192.168.1.11", "status": "error", "error": "timeout"},
        ]
        report = discover_ips(["192.168.1.10", "192.168.1.11"])
        self.assertEqual(len(report["results"]), 1)
        self.assertEqual(report["error_count"], 1)

    def test_cli_rejects_legacy_shell_port(self):
        with self.assertRaises(SystemExit):
            main(["--ip", "192.168.1.10", "--port", "5024"])

    @patch("discover_scope.discover_usb", return_value={"results": [{"target": True}]})
    def test_cli_emits_json(self, _discover_usb):
        with patch("builtins.print") as output:
            self.assertEqual(main(["--usb"]), 0)
        payload = json.loads(output.call_args.args[0])
        self.assertEqual(payload["results"], [{"target": True}])


if __name__ == "__main__":
    unittest.main()
