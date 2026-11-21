from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from read_decode_list import _evidence_fields  # noqa: E402


class EvidenceFieldTests(unittest.TestCase):
    """A decode reply must say what it proves, not just that bytes arrived."""

    def test_a_complete_framing_does_not_claim_complete_content(self):
        raw = b"HEAD\nrow1\n"
        result = _evidence_fields(raw, "HEAD\nrow1\n", "idle_timeout")
        self.assertTrue(result["framing_complete"])
        self.assertEqual(result["content_complete"], "UNKNOWN")
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["terminator"], "\n")
        self.assertEqual(result["frame_binding"], "UNVERIFIED")
        self.assertEqual(result["raw_sha256"], hashlib.sha256(raw).hexdigest())

    def test_a_header_only_reply_is_indistinguishable_from_no_events(self):
        header = _evidence_fields(b"HEAD\n", "HEAD\n", "idle_timeout")
        empty = _evidence_fields(b"", "", "first_byte_timeout")
        # The bytes differ; the honesty fields do not claim more than framing.
        self.assertTrue(header["framing_complete"])
        self.assertEqual(header["row_count"], 0)
        self.assertEqual(header["content_complete"], "UNKNOWN")
        self.assertFalse(empty["framing_complete"])
        self.assertEqual(empty["content_complete"], "UNKNOWN")
        self.assertIn("not evidence of zero events", empty["warning"])

    def test_a_missing_final_newline_is_a_truncation_risk(self):
        result = _evidence_fields(b"HEAD\nrow1", "HEAD\nrow1", "idle_timeout")
        self.assertFalse(result["framing_complete"])
        self.assertTrue(result["truncated_risk"])
        self.assertIn("may be truncated", result["warning"])

    def test_the_deprecated_alias_means_framing_only(self):
        result = _evidence_fields(b"HEAD\n", "HEAD\n", "idle_timeout")
        self.assertEqual(result["likely_complete"], result["framing_complete"])


if __name__ == "__main__":
    unittest.main()
