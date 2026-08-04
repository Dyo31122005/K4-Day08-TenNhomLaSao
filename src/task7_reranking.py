"""
Task 7 — Reranking Module.

Chọn 1 trong các phương pháp:
    - Cross-encoder reranker: Jina Reranker v2 (multilingual) hoặc Qwen3-Reranker
    - MMR (Maximal Marginal Relevance): tự implement
    - RRF (Reciprocal Rank Fusion): tự implement — khuyến nghị vì không cần API key

Nếu dùng MMR hoặc RRF, đảm bảo hiểu và giải thích được cơ chế.

Lưu ý quan trọng về RRF (sẽ dùng lại ở Task 9): điểm RRF fused CHỈ phụ thuộc thứ hạng,
không phải độ tương đồng thật. Top-1 sau khi fuse luôn xấp xỉ 1/(k+1) ≈ 0.0164 (k=60),
bất kể nội dung đó có thật sự liên quan đến câu hỏi hay không. Đừng dùng điểm RRF để
quyết định fallback ở Task 9 — xem ghi chú ở đó.
"""

import math
import os
import re
from typing import Optional


def _safe_top_k(top_k: int) -> int:
    if top_k <= 0:
        return 0
    return int(top_k)


def _tokenize(text: str) -> list[str]:
    """Small dependency-free tokenizer used by the offline fallback."""
    return re.findall(r"[\wÀ-ỹ]+", str(text).casefold(), flags=re.UNICODE)


def _token_overlap(query: str, text: str) -> float:
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return 0.0
    document_tokens = set(_tokenize(text))
    return len(query_tokens & document_tokens) / len(query_tokens)


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = math.sqrt(sum(float(a) ** 2 for a in left))
    right_norm = math.sqrt(sum(float(b) ** 2 for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def rerank_cross_encoder(
    query: str, candidates: list[dict], top_k: int = 5
) -> list[dict]:
    """
    Rerank candidates sử dụng cross-encoder model.

    Args:
        query: Câu truy vấn
        candidates: List of {'content': str, 'score': float, 'metadata': dict}
        top_k: Số lượng kết quả sau rerank

    Returns:
        List of top_k candidates, re-scored và sorted by rerank_score descending.
    """
    limit = _safe_top_k(top_k)
    if not candidates or not limit:
        return []

    api_key = os.getenv("JINA_API_KEY", "").strip()
    if api_key:
        try:
            import requests

            response = requests.post(
                "https://api.jina.ai/v1/rerank",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": os.getenv(
                        "JINA_RERANKER_MODEL",
                        "jina-reranker-v2-base-multilingual",
                    ),
                    "query": query,
                    "documents": [str(c.get("content", "")) for c in candidates],
                    "top_n": min(limit, len(candidates)),
                    "return_documents": False,
                },
                timeout=float(os.getenv("JINA_TIMEOUT", "30")),
            )
            response.raise_for_status()
            payload = response.json()
            ranked = payload.get("results", [])
            output = []
            for item in ranked:
                index = item.get("index")
                if not isinstance(index, int) or not 0 <= index < len(candidates):
                    continue
                score = float(item.get("relevance_score", item.get("score", 0.0)))
                result = candidates[index].copy()
                result["score"] = score
                result["rerank_score"] = score
                output.append(result)
            if output:
                return output[:limit]
        except Exception as exc:
            # Retrieval must remain usable without an external reranker.
            print(f"[Cross-encoder] Jina unavailable ({exc}); using lexical fallback.")

    # Deterministic offline fallback. It is intentionally conservative: the
    # original retrieval score breaks ties, while token overlap supplies the
    # query-dependent re-ranking signal.
    scored = []
    for position, candidate in enumerate(candidates):
        overlap = _token_overlap(query, candidate.get("content", ""))
        original = float(candidate.get("score", 0.0) or 0.0)
        score = 0.8 * overlap + 0.2 * original
        result = candidate.copy()
        result["score"] = score
        result["rerank_score"] = score
        scored.append((score, -position, result))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scored[:limit]]


def rerank_mmr(
    query_embedding: list[float],
    candidates: list[dict],
    top_k: int = 5,
    lambda_param: float = 0.7,
) -> list[dict]:
    """
    Maximal Marginal Relevance — chọn candidates vừa relevant vừa diverse.

    MMR = λ * sim(query, doc) - (1-λ) * max(sim(doc, selected_docs))

    Args:
        query_embedding: Vector embedding của query
        candidates: List of {'content': str, 'score': float, 'embedding': list, 'metadata': dict}
        top_k: Số lượng kết quả
        lambda_param: Trade-off giữa relevance (1.0) và diversity (0.0)

    Returns:
        List of top_k candidates selected by MMR.
    """
    limit = _safe_top_k(top_k)
    if not 0.0 <= lambda_param <= 1.0:
        raise ValueError("lambda_param must be between 0 and 1")
    if not candidates or not limit:
        return []

    selected: list[int] = []
    selected_scores: list[float] = []
    remaining = list(range(len(candidates)))
    query_vector = list(query_embedding or [])
    for _ in range(min(limit, len(candidates))):
        best_index = remaining[0]
        best_mmr = float("-inf")
        for index in remaining:
            candidate = candidates[index]
            vector = candidate.get("embedding") or []
            if query_vector and vector:
                relevance = _cosine(query_vector, vector)
            else:
                # Useful for lexical/BM25 candidates which have no vectors.
                relevance = float(candidate.get("score", 0.0) or 0.0)
                if query_vector:
                    relevance = 0.0

            if selected and vector:
                similarities = [
                    _cosine(vector, candidates[selected_index].get("embedding") or [])
                    for selected_index in selected
                ]
                redundancy = max(similarities, default=0.0)
            else:
                redundancy = 0.0
            mmr_score = lambda_param * relevance - (1.0 - lambda_param) * redundancy
            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_index = index
        selected.append(best_index)
        selected_scores.append(best_mmr)
        remaining.remove(best_index)

    results = []
    for index, mmr_score in zip(selected, selected_scores):
        result = candidates[index].copy()
        result["score"] = mmr_score
        result["rerank_score"] = mmr_score
        results.append(result)
    return results


def rerank_rrf(
    ranked_lists: list[list[dict]], top_k: int = 5, k: int = 60
) -> list[dict]:
    """
    Reciprocal Rank Fusion — gộp kết quả từ nhiều ranker.

    RRF(d) = Σ 1 / (k + rank_r(d))

    Args:
        ranked_lists: List of ranked result lists (mỗi list từ 1 ranker)
        top_k: Số lượng kết quả cuối cùng
        k: Smoothing constant (default=60, từ paper Cormack et al. 2009)

    Returns:
        List of top_k candidates sorted by RRF score descending.
    """
    if top_k <= 0 or not ranked_lists:
        return []
    if k < 0:
        raise ValueError("k must be non-negative")

    # RRF deliberately ignores the original retrieval scores.  A document's
    # contribution is determined only by its 1-based rank in each list.
    #
    # Dedup key: prefer the stable (source, chunk_index) chunk id over the raw
    # content string. Dense results come from the persisted ChromaDB index
    # while sparse results are re-chunked live from the current markdown
    # files (task6_lexical_search) — if the corpus was edited without
    # reindexing, or even splitter output drifts by a single character, a
    # content-string key would treat the same logical chunk as two different
    # documents and silently break the fusion. Fall back to content when a
    # result has no usable metadata (e.g. ad-hoc candidates in tests).
    def dedup_key(item: dict) -> str:
        metadata = item.get("metadata") or {}
        source = metadata.get("source")
        chunk_index = metadata.get("chunk_index")
        if source is not None and chunk_index is not None:
            return f"{source}::{chunk_index}"
        return item["content"]

    rrf_scores: dict[str, float] = {}
    item_map: dict[str, dict] = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, start=1):
            key = dedup_key(item)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)
            # Keep the complete result shape (metadata, source, etc.) from the
            # most recently observed ranker, without changing the caller's item.
            item_map[key] = item

    # dict insertion order provides a deterministic tie-breaker based on the
    # first time a document appeared in the input lists.
    ranked_keys = sorted(
        rrf_scores, key=lambda key: rrf_scores[key], reverse=True
    )

    results = []
    for key in ranked_keys[:top_k]:
        item = item_map[key].copy()
        item["score"] = rrf_scores[key]
        results.append(item)
    return results


# =============================================================================
# Main rerank interface
# =============================================================================

def rerank(
    query: str,
    candidates: list[dict],
    top_k: int = 5,
    method: str = "rrf",  # "cross_encoder" | "mmr" | "rrf"
    query_embedding: Optional[list[float]] = None,
) -> list[dict]:
    """
    Unified reranking interface.

    Args:
        query: Câu truy vấn
        candidates: Danh sách candidates từ retrieval
        top_k: Số lượng kết quả sau rerank
        method: Phương pháp reranking

    Returns:
        List of top_k reranked candidates.
    """
    if method == "cross_encoder":
        return rerank_cross_encoder(query, candidates, top_k)
    elif method == "mmr":
        return rerank_mmr(query_embedding or [], candidates, top_k=top_k)
    elif method == "rrf":
        # The unified interface receives one candidate list.  Treat it as a
        # single ranked list; callers with multiple rankers should call
        # rerank_rrf([...], ...) directly.
        return rerank_rrf([candidates], top_k=top_k)
    else:
        raise ValueError(f"Unknown rerank method: {method}")


if __name__ == "__main__":
    # Test with dummy data
    dummy_candidates = [
        {"content": "Chính sách trả hàng và hoàn tiền Shopee trong 15 ngày", "score": 0.8, "metadata": {}},
        {"content": "Các phương thức thanh toán hỗ trợ trên Shopee Vietnam", "score": 0.6, "metadata": {}},
        {"content": "Quy định đăng bán sản phẩm dành cho người bán", "score": 0.5, "metadata": {}},
    ]
    results = rerank("chính sách trả hàng shopee", dummy_candidates, top_k=2)
    for r in results:
        print(f"[{r['score']:.3f}] {r['content']}")
