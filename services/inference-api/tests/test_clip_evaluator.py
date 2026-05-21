import unittest
from unittest import mock

from evaluator import evaluate_output
from schemas import GenerateRequest, VisualGoal


class ClipEvaluatorIntegrationTests(unittest.TestCase):
    def test_low_similarity_fails_when_reference_set(self) -> None:
        goal = VisualGoal(preserve_product=True, product_similarity_min=0.85)
        req = GenerateRequest(prompt="x", quality_tier="quality")
        with mock.patch(
            "evaluator.clip_similarity",
            return_value=0.5,
        ):
            result = evaluate_output(
                goal,
                req,
                attempt=1,
                output_image=b"fake-out",
                reference_image=b"fake-ref",
            )
        self.assertFalse(result.passed)
        self.assertIn("product_similarity_low", result.issues)
        self.assertAlmostEqual(result.metrics["clip_similarity"], 0.5)

    def test_high_similarity_passes_with_reference(self) -> None:
        goal = VisualGoal(preserve_product=True)
        req = GenerateRequest(prompt="x", quality_tier="quality")
        with mock.patch(
            "evaluator.clip_similarity",
            return_value=0.92,
        ):
            result = evaluate_output(
                goal,
                req,
                attempt=1,
                output_image=b"fake-out",
                reference_image=b"fake-ref",
            )
        self.assertTrue(result.passed)
        self.assertNotIn("product_similarity_low", result.issues)


if __name__ == "__main__":
    unittest.main()
