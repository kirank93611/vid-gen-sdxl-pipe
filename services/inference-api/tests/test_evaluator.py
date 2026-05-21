import unittest

from evaluator import evaluate_output
from schemas import GenerateRequest, VisualGoal


class EvaluatorTests(unittest.TestCase):
    def test_high_realism_fails_fast_tier(self) -> None:
        goal = VisualGoal(realism="high")
        req = GenerateRequest(prompt="x", quality_tier="fast")
        result = evaluate_output(goal, req, attempt=1)
        self.assertFalse(result.passed)
        self.assertIn("tier_too_low", result.issues)

    def test_high_realism_passes_balanced(self) -> None:
        goal = VisualGoal(realism="high")
        req = GenerateRequest(prompt="x", quality_tier="balanced")
        result = evaluate_output(goal, req, attempt=1)
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
