import unittest

from correction import apply_corrections
from evaluator import evaluate_output
from schemas import EvalResult, GenerateRequest, VisualGoal


class CorrectionTests(unittest.TestCase):
    def test_bumps_fast_to_balanced(self) -> None:
        req = GenerateRequest(prompt="x", quality_tier="fast")
        goal = VisualGoal(realism="high")
        evaluation = evaluate_output(goal, req, attempt=1)
        patched = apply_corrections(req, evaluation)
        self.assertIsNotNone(patched)
        assert patched is not None
        self.assertEqual(patched.quality_tier, "balanced")

    def test_no_patch_when_passed(self) -> None:
        req = GenerateRequest(prompt="x", quality_tier="quality")
        evaluation = EvalResult(passed=True, score=1.0, issues=[], attempt=1, metrics={})
        self.assertIsNone(apply_corrections(req, evaluation))

    def test_bumps_tier_on_product_similarity_low(self) -> None:
        req = GenerateRequest(prompt="x", quality_tier="fast")
        evaluation = EvalResult(
            passed=False,
            score=0.5,
            issues=["product_similarity_low"],
            attempt=1,
            metrics={"clip_similarity": 0.5},
        )
        patched = apply_corrections(req, evaluation)
        self.assertIsNotNone(patched)
        assert patched is not None
        self.assertEqual(patched.quality_tier, "balanced")


if __name__ == "__main__":
    unittest.main()
