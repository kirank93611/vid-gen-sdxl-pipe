import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from generation_profiles import apply_generation_policy
from schemas import GenerateRequest


class GenerationProfileTests(unittest.TestCase):
    def test_lightning_lora_auto_profile(self) -> None:
        req = GenerateRequest(
            prompt="test",
            lora_name="test_lightning_nomark_1024",
            quality_tier="fast",
        )
        effective, model_id = apply_generation_policy(req)
        self.assertEqual(model_id, "sdxl_base")
        self.assertEqual(effective.steps, 4)
        self.assertEqual(effective.guidance_scale, 0.0)
        self.assertEqual(effective.scheduler, "euler_trailing")
        self.assertEqual(effective.lora_weight, 1.0)

    def test_custom_profile_keeps_client_steps(self) -> None:
        req = GenerateRequest(
            prompt="test",
            generation_profile="custom",
            steps=18,
            guidance_scale=4.5,
            scheduler="euler",
        )
        effective, _ = apply_generation_policy(req)
        self.assertEqual(effective.steps, 18)
        self.assertEqual(effective.guidance_scale, 4.5)
        self.assertEqual(effective.scheduler, "euler")


if __name__ == "__main__":
    unittest.main()
