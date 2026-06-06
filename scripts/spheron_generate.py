#!/usr/bin/env python3
"""Smoke test: POST /generate and save JPEG (local or Spheron via --api-url)."""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:8001")
    parser.add_argument("--api-key", default="dev-local-key")
    parser.add_argument("--prompt", default="luxury gold ring on black velvet, studio lighting")
    parser.add_argument("--quality-tier", default="fast")
    parser.add_argument("--out", type=Path, default=Path("generated/spheron_smoke.jpg"))
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    headers = {"X-API-Key": args.api_key}
    with httpx.Client(base_url=args.api_url, timeout=args.timeout) as client:
        health = client.get("/health", headers=headers)
        health.raise_for_status()
        print("health:", health.json())

        resp = client.post(
            "/generate",
            headers=headers,
            json={"prompt": args.prompt, "quality_tier": args.quality_tier},
        )
        if resp.status_code != 200:
            print(resp.status_code, resp.text, file=sys.stderr)
            return 1
        body = resp.json()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(base64.b64decode(body["image_base64"]))
    print(f"Wrote {args.out.resolve()} ({args.out.stat().st_size} bytes)")
    print("metadata:", body.get("metadata"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
