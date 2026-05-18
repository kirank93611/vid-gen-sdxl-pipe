import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


import unittest

from schemas import GenerateRequest
from router import apply_quality_tier

class RouterTests(unittest.TestCase):
    def test_none_tier_leaves_steps(self) -> None:
        req = GenerateRequest(prompt="x", steps=4, guidance_scale=1.0)
        eff, model_id = apply_quality_tier(req)
        self.assertIs(eff, req)
        self.assertEqual(model_id, "sdxl_base")

    def test_balanced_overrides(self) -> None:
        req = GenerateRequest(prompt="x", steps=4, quality_tier="balanced")
        eff, model_id = apply_quality_tier(req)
        self.assertEqual(eff.steps, 25)
        self.assertEqual(eff.guidance_scale, 6.0)
        self.assertEqual(model_id, "sdxl_base")