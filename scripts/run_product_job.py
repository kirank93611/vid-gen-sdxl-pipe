#!/usr/bin/env python3
"""
Run one product-composite correction job (reference + goal + prompt).

Usage on Spheron (API on localhost):
  python scripts/run_product_job.py --case ring_velvet_studio
  python scripts/run_product_job.py --case watch_hero --quality-tier balanced

Custom:
  python scripts/run_product_job.py \\
    --reference benchmarks/product_similarity/fixtures/ring_reference.jpg \\
    --prompt "gold engagement ring on black velvet, softbox, catalog photo" \\
    --out generated/my_ring.jpg
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

import httpx

_REPO = Path(__file__).resolve().parents[1]
_MANIFEST = _REPO / "benchmarks" / "product_similarity" / "manifest.json"


def _load_case(case_id: str) -> tuple[dict, dict, Path]:
    data = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    defaults = data.get("defaults", {})
    for case in data.get("cases", []):
        if case["id"] == case_id:
            ref = _MANIFEST.parent / case["reference_path"]
            return case, defaults, ref
    raise SystemExit(f"Unknown case {case_id!r} in manifest")


def _poll(client: httpx.Client, job_id: str, headers: dict, timeout_s: float) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = client.get(f"/jobs/{job_id}", headers=headers)
        r.raise_for_status()
        body = r.json()
        status = body["status"]
        print(f"  job {job_id[:8]}… status={status} iterations={len(body.get('iterations', []))}")
        if status in ("converged", "failed", "error"):
            return body
        time.sleep(1.0)
    raise TimeoutError(f"job {job_id} did not finish in {timeout_s}s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Product composite job via /jobs")
    parser.add_argument("--api-url", default="http://127.0.0.1:8001")
    parser.add_argument("--api-key", default="dev-local-key")
    parser.add_argument("--case", help="manifest case id (ring_velvet_studio, watch_hero)")
    parser.add_argument("--reference", type=Path, help="reference JPEG (overrides --case)")
    parser.add_argument("--prompt", help="scene prompt (placement/lighting, not SKU clone)")
    parser.add_argument("--quality-tier", choices=["fast", "balanced", "quality"])
    parser.add_argument("--max-iterations", type=int)
    parser.add_argument("--poll-timeout", type=float, default=600.0)
    parser.add_argument("--out", type=Path, default=_REPO / "generated" / "product_job.jpg")
    args = parser.parse_args()

    if args.case:
        case, defaults, ref_path = _load_case(args.case)
        prompt = args.prompt or case["prompt"]
        quality_tier = args.quality_tier or case.get("quality_tier", defaults.get("quality_tier", "fast"))
        max_iter = args.max_iterations or case.get("max_iterations", defaults.get("max_iterations", 3))
        goal = {**defaults.get("goal", {}), **case.get("goal", {})}
        reference_path = ref_path
    else:
        if not args.reference or not args.prompt:
            parser.error("Without --case, provide --reference and --prompt")
        reference_path = args.reference
        prompt = args.prompt
        quality_tier = args.quality_tier or "fast"
        max_iter = args.max_iterations or 3
        goal = {
            "task": "product_composite",
            "preserve_product": True,
            "product_similarity_min": 0.85,
            "realism": "high",
        }

    if not reference_path.is_file():
        print(f"Missing reference: {reference_path}", file=sys.stderr)
        return 2

    ref_b64 = base64.b64encode(reference_path.read_bytes()).decode("utf-8")
    headers = {"X-API-Key": args.api_key}

    print(f"Reference: {reference_path}")
    print(f"Prompt: {prompt}")
    print(f"Tier: {quality_tier}  max_iterations: {max_iter}")

    with httpx.Client(base_url=args.api_url, timeout=600.0) as client:
        r = client.post(
            "/jobs",
            headers=headers,
            json={
                "goal": goal,
                "prompt": prompt,
                "quality_tier": quality_tier,
                "max_iterations": max_iter,
                "reference_image_base64": ref_b64,
                "negative_prompt": (
                    "blurry, low quality, deformed, wrong product, duplicate product, "
                    "cartoon, illustration, text, watermark, glitter, gold dust, "
                    "empty room, backdrop stand, photography equipment"
                ),
            },
        )
        r.raise_for_status()
        job_id = r.json()["job_id"]
        print(f"Started job {job_id}")

        body = _poll(client, job_id, headers, args.poll_timeout)

    for it in body.get("iterations", []):
        clip = it.get("clip_similarity")
        clip_s = f" clip={clip:.3f}" if clip is not None else ""
        print(
            f"  attempt {it['attempt']}: passed={it['passed']} tier={it.get('quality_tier')} "
            f"issues={it.get('issues')}{clip_s}"
        )

    print(f"Final status: {body['status']}  error_code={body.get('error_code')}")

    if body.get("image_base64"):
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(base64.b64decode(body["image_base64"]))
        print(f"Wrote {args.out.resolve()}")
        return 0 if body["status"] == "converged" else 1

    print("No image in response.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
