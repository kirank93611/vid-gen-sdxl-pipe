#!/usr/bin/env python3
"""
Run product-similarity benchmark: baseline /generate vs correction /jobs.

Requires inference API running (make run). See benchmarks/product_similarity/README.md.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BENCHMARK_DIR = _REPO_ROOT / "benchmarks" / "product_similarity"
_INFERENCE_ROOT = _REPO_ROOT / "services" / "inference-api"


def _load_clip_similarity(reference_jpeg: bytes, output_jpeg: bytes) -> float:
    if str(_INFERENCE_ROOT) not in sys.path:
        sys.path.insert(0, str(_INFERENCE_ROOT))
    from clip_evaluator import clip_similarity

    return clip_similarity(reference_jpeg, output_jpeg)


def _read_manifest(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _poll_job(
    client: httpx.Client,
    job_id: str,
    headers: dict,
    timeout_s: float,
    poll_read_timeout: httpx.Timeout,
) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/jobs/{job_id}", headers=headers, timeout=poll_read_timeout)
        resp.raise_for_status()
        body = resp.json()
        if body["status"] in ("converged", "failed", "error"):
            return body
        time.sleep(0.5)
    raise TimeoutError(f"job {job_id} did not finish within {timeout_s}s")


def _run_case(
    client: httpx.Client,
    headers: dict,
    case: dict,
    defaults: dict,
    reference_bytes: bytes,
    job_poll_timeout_s: float,
    generate_timeout: httpx.Timeout,
    poll_read_timeout: httpx.Timeout,
    create_timeout: httpx.Timeout,
) -> dict:
    case_id = case["id"]
    prompt = case["prompt"]
    quality_tier = case.get("quality_tier", defaults.get("quality_tier", "fast"))
    max_iterations = case.get("max_iterations", defaults.get("max_iterations", 3))
    goal = {**defaults.get("goal", {}), **case.get("goal", {})}
    ref_b64 = base64.b64encode(reference_bytes).decode("utf-8")

    baseline_resp = client.post(
        "/generate",
        headers=headers,
        json={"prompt": prompt, "quality_tier": quality_tier},
        timeout=generate_timeout,
    )
    if baseline_resp.status_code == 504:
        print(
            "API returned 504 on POST /generate. The server stopped the run "
            "(GENERATION_TIMEOUT_SECONDS). On M3 Pro, export a higher value before "
            "`make run`, e.g. export GENERATION_TIMEOUT_SECONDS=600, and ensure "
            "BENCHMARK_GENERATE_TIMEOUT_S is >= that + margin.",
            file=sys.stderr,
        )
    baseline_resp.raise_for_status()
    baseline_body = baseline_resp.json()
    baseline_image = base64.b64decode(baseline_body["image_base64"])
    baseline_clip = _load_clip_similarity(reference_bytes, baseline_image)

    job_resp = client.post(
        "/jobs",
        headers=headers,
        json={
            "goal": goal,
            "prompt": prompt,
            "quality_tier": quality_tier,
            "max_iterations": max_iterations,
            "reference_image_base64": ref_b64,
        },
        timeout=create_timeout,
    )
    job_resp.raise_for_status()
    job_id = job_resp.json()["job_id"]
    job_body = _poll_job(
        client, job_id, headers, job_poll_timeout_s, poll_read_timeout
    )

    final_clip = None
    if job_body.get("image_base64"):
        out_bytes = base64.b64decode(job_body["image_base64"])
        final_clip = _load_clip_similarity(reference_bytes, out_bytes)

    return {
        "id": case_id,
        "prompt": prompt,
        "quality_tier": quality_tier,
        "baseline": {
            "clip_similarity": baseline_clip,
            "metadata": baseline_body.get("metadata"),
        },
        "job": {
            "job_id": job_id,
            "status": job_body["status"],
            "converged": job_body["status"] == "converged",
            "iterations": job_body.get("iterations", []),
            "final_clip_similarity": final_clip,
            "error_code": job_body.get("error_code"),
        },
        "delta_clip": (final_clip - baseline_clip) if final_clip is not None else None,
    }


def _write_report(report: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "latest.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    lines = [
        "# Product similarity benchmark",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "| case | baseline CLIP | job final CLIP | delta | converged | iters |",
        "|------|---------------|----------------|-------|-----------|-------|",
    ]
    for row in report.get("results", []):
        job = row["job"]
        iters = len(job.get("iterations", []))
        lines.append(
            f"| {row['id']} | {row['baseline']['clip_similarity']:.3f} "
            f"| {(row['job']['final_clip_similarity'] or 0):.3f} "
            f"| {(row['delta_clip'] if row['delta_clip'] is not None else 0):+.3f} "
            f"| {job['converged']} | {iters} |"
        )
    if report.get("skipped"):
        lines.extend(["", "Skipped (missing fixture):", ""])
        for s in report["skipped"]:
            lines.append(f"- {s}")
    md_path = out_dir / "latest.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Product CLIP benchmark")
    parser.add_argument("--api-url", default="http://127.0.0.1:8001")
    parser.add_argument("--api-key", default="dev-local-key")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=_BENCHMARK_DIR / "manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_BENCHMARK_DIR / "results",
    )
    parser.add_argument(
        "--generate-timeout",
        type=float,
        default=float(os.getenv("BENCHMARK_GENERATE_TIMEOUT_S", "420")),
        help="HTTP read timeout for POST /generate (seconds). "
        "Use >= GENERATION_TIMEOUT_SECONDS on the API plus margin.",
    )
    parser.add_argument(
        "--job-poll-timeout",
        type=float,
        default=float(os.getenv("BENCHMARK_JOB_POLL_TIMEOUT_S", "600")),
        help="Max wall time to poll GET /jobs until terminal status.",
    )
    args = parser.parse_args()

    generate_timeout = httpx.Timeout(args.generate_timeout)
    poll_read_timeout = httpx.Timeout(30.0)
    create_timeout = httpx.Timeout(30.0)
    health_timeout = httpx.Timeout(30.0)

    manifest = _read_manifest(args.manifest)
    defaults = manifest.get("defaults", {})
    benchmark_root = args.manifest.parent

    headers = {"X-API-Key": args.api_key}
    results: list[dict] = []
    skipped: list[str] = []

    with httpx.Client(base_url=args.api_url) as client:
        health = client.get("/health", timeout=health_timeout)
        if health.status_code != 200:
            print(f"API not healthy at {args.api_url}", file=sys.stderr)
            return 1

        for case in manifest.get("cases", []):
            ref_path = benchmark_root / case["reference_path"]
            if not ref_path.is_file():
                skipped.append(f"{case['id']}: missing {ref_path}")
                continue
            reference_bytes = ref_path.read_bytes()
            print(f"Running case {case['id']}...")
            results.append(
                _run_case(
                    client,
                    headers,
                    case,
                    defaults,
                    reference_bytes,
                    args.job_poll_timeout,
                    generate_timeout,
                    poll_read_timeout,
                    create_timeout,
                )
            )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_url": args.api_url,
        "manifest": str(args.manifest),
        "hypothesis": (
            "Job loop (evaluate + tier correction) improves CLIP vs reference "
            "compared to single-shot /generate."
        ),
        "results": results,
        "skipped": skipped,
    }
    _write_report(report, args.output_dir)
    if not results and skipped:
        print("No cases ran. Add JPEGs under benchmarks/product_similarity/fixtures/.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
