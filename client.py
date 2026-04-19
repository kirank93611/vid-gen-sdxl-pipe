import base64
import os
from pathlib import Path

import requests


API_URL = os.getenv("SDXL_API_URL", "http://127.0.0.1:8001/generate")
OUTPUT_PATH = Path(os.getenv("SDXL_OUTPUT_PATH", "test_output.jpg"))


def main() -> None:
    payload = {
        "prompt": "cinematic portrait of a tiger in rain",
    }

    response = requests.post(API_URL, json=payload, timeout=120)
    response.raise_for_status()

    data = response.json()
    image_data = base64.b64decode(data["image_base64"])
    OUTPUT_PATH.write_bytes(image_data)
    print(f"Saved {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
