import unittest
from unittest import mock

from model_registry import list_all_models


class ModelRegistryTests(unittest.TestCase):
    def test_merges_checkpoints_without_duplicates(self) -> None:
        catalog = [
            {"model_id": "sdxl_base", "display_name": "SDXL", "family": "image"},
            {"model_id": "tiefighter_20b", "display_name": "Chat", "family": "chat"},
        ]
        ckpts = [
            {
                "model_id": "ckpt_test",
                "display_name": "test",
                "filename": "test.safetensors",
                "backend": "sd15",
            }
        ]
        with mock.patch("model_registry.list_models_payload", return_value=catalog):
            with mock.patch("model_registry.list_checkpoints", return_value=ckpts):
                models = list_all_models()
        ids = [m["model_id"] for m in models]
        self.assertIn("sdxl_base", ids)
        self.assertIn("ckpt_test", ids)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
