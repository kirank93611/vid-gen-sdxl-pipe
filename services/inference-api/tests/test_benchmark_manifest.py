import json
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST = _REPO_ROOT / "benchmarks" / "product_similarity" / "manifest.json"


class BenchmarkManifestTests(unittest.TestCase):
    def test_manifest_loads_and_has_cases(self) -> None:
        self.assertTrue(_MANIFEST.is_file(), f"missing {_MANIFEST}")
        with _MANIFEST.open(encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("cases", data)
        self.assertGreaterEqual(len(data["cases"]), 1)
        case = data["cases"][0]
        self.assertIn("id", case)
        self.assertIn("prompt", case)
        self.assertIn("reference_path", case)


if __name__ == "__main__":
    unittest.main()
