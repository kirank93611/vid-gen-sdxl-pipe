import unittest

from lora_utils import (
    infer_lora_backend,
    image_model_lora_backend,
    lora_backend_mismatch_message,
)


class LoraUtilsTests(unittest.TestCase):
    def test_infer_ltx_lora(self) -> None:
        self.assertEqual(infer_lora_backend("DR34ML4Y_LTXXX_V2"), "ltx")

    def test_infer_wan_lora(self) -> None:
        self.assertEqual(infer_lora_backend("DR34ML4Y_WAN_I2V_14B"), "wan")

    def test_infer_sdxl_lora(self) -> None:
        self.assertEqual(infer_lora_backend("nyaliaXL_il_loha_V8340"), "sdxl")
        self.assertEqual(infer_lora_backend("sdxl_lightning_4step_lora"), "sdxl")

    def test_image_model_backends(self) -> None:
        self.assertEqual(image_model_lora_backend("sdxl_base"), "sdxl")
        self.assertEqual(image_model_lora_backend("wan2.1_t2v_1.3b"), "wan")
        self.assertEqual(image_model_lora_backend("ltx_video"), "ltx")
        self.assertIsNone(image_model_lora_backend("ckpt_test"))

    def test_lora_backend_mismatch_message(self) -> None:
        msg = lora_backend_mismatch_message("DR34ML4Y_LTXXX_V2", "sdxl_base")
        self.assertIsNotNone(msg)
        assert msg is not None
        self.assertIn("LTX", msg)
        self.assertIsNone(
            lora_backend_mismatch_message("nyaliaXL_il_loha_V8340", "sdxl_base")
        )


if __name__ == "__main__":
    unittest.main()
