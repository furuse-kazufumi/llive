#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""IND-04 Annotation Channel ベンチ — round-trip + scale."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from llive.annotations import Annotation, AnnotationBundle, AnnotationEmitter


N = 1000


def _make_bundle(n: int) -> AnnotationBundle:
    em = AnnotationEmitter()
    for i in range(n):
        em.add(
            namespace=("cog", "vrb", "oka", "math", "creat", "core")[i % 6],
            key=f"key_{i}",
            value={"i": i, "tags": ["a", "b", i % 7], "f": i * 0.5},
            target_layer=("llove" if i % 2 == 0 else None),
        )
    return em.freeze()


def main() -> None:
    out_dir = Path("docs/benchmarks/2026-05-17-full-validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "annotations.json"

    # 1. build N annotations
    t0 = time.perf_counter()
    bundle = _make_bundle(N)
    t_build = time.perf_counter() - t0

    # 2. encode round-trip (single bundle)
    t0 = time.perf_counter()
    encoded = bundle.to_html_comments()
    t_encode = time.perf_counter() - t0
    encoded_bytes = len(encoded.encode("utf-8"))

    t0 = time.perf_counter()
    decoded = AnnotationBundle.from_html_comments(encoded)
    t_decode = time.perf_counter() - t0
    decode_ok = len(decoded) == N

    # 3. for_layer / by_namespace / get latency
    t0 = time.perf_counter()
    for _ in range(100):
        bundle.for_layer("llove")
    t_for_layer = (time.perf_counter() - t0) / 100

    t0 = time.perf_counter()
    for _ in range(100):
        bundle.by_namespace("cog")
    t_by_ns = (time.perf_counter() - t0) / 100

    t0 = time.perf_counter()
    for i in range(1000):
        bundle.get("cog", f"key_{i}")
    t_get = (time.perf_counter() - t0) / 1000

    # 4. small bundle round-trip (typical use)
    small = AnnotationBundle.of(
        Annotation(namespace="core", key="brief_completed", value=True),
        Annotation(namespace="oka", key="essence_card", value={"summary": "s"}, target_layer="llove"),
        Annotation(namespace="cog", key="consensus", value="proceed"),
    )
    small_enc = small.to_html_comments()

    report = {
        "n": N,
        "build_total_s": round(t_build, 6),
        "build_per_annotation_us": round(t_build / N * 1e6, 3),
        "encode": {
            "total_s": round(t_encode, 6),
            "per_annotation_us": round(t_encode / N * 1e6, 3),
            "output_bytes": encoded_bytes,
            "bytes_per_annotation": round(encoded_bytes / N, 1),
        },
        "decode": {
            "total_s": round(t_decode, 6),
            "per_annotation_us": round(t_decode / N * 1e6, 3),
            "round_trip_ok": decode_ok,
        },
        "filter_for_layer_ms_per_call": round(t_for_layer * 1000, 4),
        "filter_by_namespace_ms_per_call": round(t_by_ns * 1000, 4),
        "get_us_per_call": round(t_get * 1e6, 3),
        "small_bundle_3_items_bytes": len(small_enc.encode("utf-8")),
        "small_bundle_sample": small_enc,
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
