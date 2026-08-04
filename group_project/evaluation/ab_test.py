"""
A/B testing helpers for retrieval configurations.

Provides a small framework to run within-subject A/B comparisons (run both
configurations on the same queries) and compute Hit@K and MRR against the
`golden_dataset.json` in this folder.

Usage (from repo root):
    python -m group_project.evaluation.ab_test

Design choices:
- Default is within-subject: run both variants on every query so we can compute
  paired deltas.
- Relevance check: match `expected_context` substring against retrieved
  `content` fields. This is a pragmatic heuristic for the provided dataset.
- Results are saved to `ab_test_results.json` in the same folder.
"""

from __future__ import annotations

import json
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Try to import the retrieval function from the project's src. If imports fail
# when running as a module, add repo root to sys.path.
try:
    from src.task9_retrieval_pipeline import retrieve
except Exception:
    repo_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo_root))
    from src.task9_retrieval_pipeline import retrieve


GOLDEN_PATH = Path(__file__).parent / "golden_dataset.json"
RESULTS_PATH = Path(__file__).parent / "ab_test_results.json"


def load_golden(path: Path = GOLDEN_PATH) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def is_relevant(result_content: str, golden_item: Dict[str, Any]) -> bool:
    """Heuristic relevance check: expected_context substring in retrieved content."""
    expected_ctx = golden_item.get("expected_context") or golden_item.get("expected_answer")
    if not expected_ctx:
        return False
    return expected_ctx.lower() in result_content.lower()


def score_results(results: List[Dict[str, Any]], golden_item: Dict[str, Any], top_k: int = 5) -> Tuple[int, float]:
    """Compute Hit@K (0/1) and reciprocal rank for a single query.

    Returns:
        (hit_at_k, reciprocal_rank)
    """
    for idx, r in enumerate(results[:top_k], start=1):
        if is_relevant(r.get("content", ""), golden_item):
            return 1, 1.0 / idx
    return 0, 0.0


def run_within_subject(
    golden: List[Dict[str, Any]],
    config_a: Dict[str, Any],
    config_b: Dict[str, Any],
    top_k: int = 5,
    shuffle: bool = True,
    seed: int | None = 42,
) -> Dict[str, Any]:
    """Run both configs on every query and aggregate Hit@K and MRR.

    config_* are kwargs forwarded to `retrieve(query, **config)`.
    """
    if seed is not None:
        random.seed(seed)

    items = list(golden)
    if shuffle:
        random.shuffle(items)

    records: List[Dict[str, Any]] = []

    for item in items:
        q = item["question"]

        # Run A with timing
        t0 = time.perf_counter()
        res_a = retrieve(q, top_k=top_k, **config_a)
        t1 = time.perf_counter()
        latency_a = t1 - t0
        hit_a, rr_a = score_results(res_a, item, top_k=top_k)
        fallback_a = any(r.get("source") == "pageindex" for r in res_a)

        # Run B with timing
        t0 = time.perf_counter()
        res_b = retrieve(q, top_k=top_k, **config_b)
        t1 = time.perf_counter()
        latency_b = t1 - t0
        hit_b, rr_b = score_results(res_b, item, top_k=top_k)
        fallback_b = any(r.get("source") == "pageindex" for r in res_b)

        records.append(
            {
                "id": item.get("id"),
                "question": q,
                "is_in_domain": item.get("is_in_domain", True),
                "A": {
                    "hit": hit_a,
                    "rr": rr_a,
                    "results": res_a[:top_k],
                    "latency": latency_a,
                    "fallback": bool(fallback_a),
                },
                "B": {
                    "hit": hit_b,
                    "rr": rr_b,
                    "results": res_b[:top_k],
                    "latency": latency_b,
                    "fallback": bool(fallback_b),
                },
            }
        )

    # Aggregate metrics
    def agg(key: str):
        return [r[key] for r in (rec["A"] for rec in records)]

    hits_a = [r["A"]["hit"] for r in records]
    hits_b = [r["B"]["hit"] for r in records]
    rrs_a = [r["A"]["rr"] for r in records]
    rrs_b = [r["B"]["rr"] for r in records]
    lat_a = [r["A"]["latency"] for r in records]
    lat_b = [r["B"]["latency"] for r in records]
    fb_a = [1 if r["A"]["fallback"] else 0 for r in records]
    fb_b = [1 if r["B"]["fallback"] else 0 for r in records]

    summary = {
        "n_queries": len(records),
        "A": {
            "hit_at_k_mean": statistics.mean(hits_a) if hits_a else 0.0,
            "mrr": statistics.mean(rrs_a) if rrs_a else 0.0,
            "latency_mean_s": statistics.mean(lat_a) if lat_a else 0.0,
            "fallback_rate": statistics.mean(fb_a) if fb_a else 0.0,
        },
        "B": {
            "hit_at_k_mean": statistics.mean(hits_b) if hits_b else 0.0,
            "mrr": statistics.mean(rrs_b) if rrs_b else 0.0,
            "latency_mean_s": statistics.mean(lat_b) if lat_b else 0.0,
            "fallback_rate": statistics.mean(fb_b) if fb_b else 0.0,
        },
        "delta": {
            "hit_at_k_mean": (statistics.mean(hits_a) - statistics.mean(hits_b)) if hits_a and hits_b else 0.0,
            "mrr": (statistics.mean(rrs_a) - statistics.mean(rrs_b)) if rrs_a and rrs_b else 0.0,
            "latency_mean_s": (statistics.mean(lat_a) - statistics.mean(lat_b)) if lat_a and lat_b else 0.0,
            "fallback_rate": (statistics.mean(fb_a) - statistics.mean(fb_b)) if fb_a and fb_b else 0.0,
        },
    }

    out = {"summary": summary, "records": records}

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    return out


def example_experiments():
    golden = load_golden()

    # Experiment 1: hybrid (default pipeline) + rerank vs dense-only (semantic only, no rerank)
    config_hybrid_rerank = {"use_reranking": True, "score_threshold": 0.0}
    config_dense_only = {"use_reranking": False, "score_threshold": 0.0}

    print("Running A: hybrid+rerank  vs  B: dense-only")
    res1 = run_within_subject(golden, config_hybrid_rerank, config_dense_only, top_k=5)
    print(json.dumps(res1["summary"], ensure_ascii=False, indent=2))

    # Experiment 2: hybrid vs dense-only (both without rerank)
    config_hybrid = {"use_reranking": False, "score_threshold": 0.0}
    config_dense = {"use_reranking": False, "score_threshold": 0.0}

    # For hybrid vs dense-only you'd need a way to tell retrieve to use only dense
    # or hybrid. The current `retrieve` signature doesn't expose that flag; if you
    # want to compare hybrid vs dense-only, consider adding a small wrapper that
    # calls `semantic_search` directly for the dense-only arm and `retrieve` for
    # the hybrid arm. This example focuses on rerank vs no-rerank which is
    # supported by `retrieve`.


if __name__ == "__main__":
    print("A/B test runner — within-subject experiments")
    print("Results will be saved to:", RESULTS_PATH)
    example_experiments()
