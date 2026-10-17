import json
import re
import unittest
from pathlib import Path


EXAMPLES = Path(__file__).parent
FORBIDDEN_IMPORTS = re.compile(r"\b(?:socket|serial|pyvisa|visa|requests|urllib)\b")
FORBIDDEN_CALLS = re.compile(r"(?:create_connection|socket\.|ResourceManager\s*\(|open_resource\s*\()")


class ExampleSafetyTests(unittest.TestCase):
    def test_example_metadata_is_json_and_hardware_free(self):
        example_dirs = [path for path in EXAMPLES.iterdir() if path.is_dir() and not path.name.startswith("_")]
        self.assertEqual(len(example_dirs), 5)
        for example in example_dirs:
            metadata = json.loads((example / "example.json").read_text(encoding="utf-8"))
            self.assertTrue(metadata["synthetic"], example)
            self.assertFalse(metadata["hardware_io"], example)
            self.assertIn(metadata["support_level"], {"documented"})

    def test_example_sources_have_no_hardware_transport(self):
        for path in EXAMPLES.rglob("*.py"):
            if path.name == "test_example_safety.py":
                continue
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(FORBIDDEN_IMPORTS.search(text), path)
            self.assertIsNone(FORBIDDEN_CALLS.search(text), path)


if __name__ == "__main__":
    unittest.main()
