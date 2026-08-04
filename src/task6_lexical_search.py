"""
Task 6 — Lexical Search Module (BM25).

Mặc định sử dụng BM25. Nếu dùng phương pháp khác (TF-IDF, Elasticsearch,
Weaviate BM25 built-in), hãy giải thích cơ chế trong buổi demo → +5 bonus.

Cài đặt:
    pip install rank-bm25

BM25 hoạt động thế nào:
    - Term Frequency (TF): từ xuất hiện nhiều trong document → điểm cao
    - Inverse Document Frequency (IDF): từ hiếm → quan trọng hơn
    - Document length normalization: document dài không bị ưu tiên quá mức
    - Formula: score(q,d) = Σ IDF(qi) * (tf(qi,d) * (k1+1)) / (tf(qi,d) + k1*(1-b+b*|d|/avgdl))
    - k1=1.5 (term saturation), b=0.75 (length normalization)
"""

import math
import re
from collections import Counter

# TODO: Load corpus từ data/standardized/ hoặc từ vector store
CORPUS: list[dict] = []  # List of {'content': str, 'metadata': dict}
_BM25_INDEX = None
_INDEXED_CORPUS_ID = None


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\w]+", text.casefold(), flags=re.UNICODE)


class _BM25:
    """Fallback BM25 để module vẫn chạy khi rank-bm25 chưa được cài."""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.corpus = corpus
        self.k1, self.b = k1, b
        self.avgdl = sum(map(len, corpus)) / len(corpus) if corpus else 0
        self.df = Counter(token for doc in corpus for token in set(doc))

    def get_scores(self, query: list[str]) -> list[float]:
        if not self.corpus or not query or not self.avgdl:
            return [0.0] * len(self.corpus)
        n_docs = len(self.corpus)
        scores = []
        for doc in self.corpus:
            counts = Counter(doc)
            score = 0.0
            for token in set(query):
                tf = counts.get(token, 0)
                if not tf:
                    continue
                idf = math.log(1 + (n_docs - self.df[token] + 0.5) / (self.df[token] + 0.5))
                denominator = tf + self.k1 * (1 - self.b + self.b * len(doc) / self.avgdl)
                score += idf * tf * (self.k1 + 1) / denominator
            scores.append(score)
        return scores


def build_bm25_index(corpus: list[dict]):
    """
    Xây dựng BM25 index từ corpus.

    Args:
        corpus: List of {'content': str, 'metadata': dict}
    """
    # TODO: Implement BM25 index
    #
    # from rank_bm25 import BM25Okapi
    #
    # # Tokenize - có thể đơn giản split(), hoặc dùng underthesea cho tiếng Việt
    # tokenized_corpus = [doc["content"].lower().split() for doc in corpus]
    # bm25 = BM25Okapi(tokenized_corpus)
    # return bm25
    if not isinstance(corpus, list):
        raise TypeError("corpus phải là list")
    tokenized = [_tokenize(doc.get("content", "")) for doc in corpus]
    try:
        from rank_bm25 import BM25Okapi
        return BM25Okapi(tokenized)
    except ImportError:
        return _BM25(tokenized)


def _matches_filter(metadata: dict, filter_metadata: dict) -> bool:
    return all(metadata.get(key) == value for key, value in filter_metadata.items())


def lexical_search(query: str, top_k: int = 10, filter_metadata: dict = None) -> list[dict]:
    """
    Tìm kiếm từ khóa sử dụng BM25.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa
        filter_metadata: Dict điều kiện lọc metadata exact-match (VD:
            {'customer_role': 'seller'}), cùng interface với semantic_search
            — bắt buộc phải giữ đồng bộ với nhánh dense, nếu không nhánh BM25
            sẽ làm rò rỉ kết quả bị lọc ra ở nhánh kia khi merge bằng RRF.

    Returns:
        List of {
            'content': str,
            'score': float,      # BM25 score
            'metadata': dict
        }
        Sorted by score descending.
    """
    # TODO: Implement lexical search
    #
    # tokenized_query = query.lower().split()
    # scores = bm25.get_scores(tokenized_query)
    #
    # # Get top_k indices
    # import numpy as np
    # top_indices = np.argsort(scores)[::-1][:top_k]
    #
    # results = []
    # for idx in top_indices:
    #     if scores[idx] > 0:
    #         results.append({
    #             "content": CORPUS[idx]["content"],
    #             "score": float(scores[idx]),
    #             "metadata": CORPUS[idx]["metadata"]
    #         })
    # return results
    global CORPUS, _BM25_INDEX, _INDEXED_CORPUS_ID
    if not isinstance(query, str) or not query.strip() or top_k <= 0:
        return []

    if not CORPUS:
        from .task4_chunking_indexing import chunk_documents, load_documents
        CORPUS = chunk_documents(load_documents())
        print(f"  [Lexical Search] Da nap corpus: {len(CORPUS)} chunk")

    corpus_id = id(CORPUS)
    if _BM25_INDEX is None or _INDEXED_CORPUS_ID != corpus_id:
        _BM25_INDEX = build_bm25_index(CORPUS)
        _INDEXED_CORPUS_ID = corpus_id
        print(f"  [Lexical Search] Da xay BM25 index tren {len(CORPUS)} chunk")

    scores = _BM25_INDEX.get_scores(_tokenize(query))
    ranked = sorted(enumerate(scores), key=lambda item: (-float(item[1]), item[0]))

    results = []
    for index, score in ranked:
        if score <= 0:
            continue
        metadata = CORPUS[index].get("metadata", {})
        if filter_metadata and not _matches_filter(metadata, filter_metadata):
            continue
        results.append({
            "content": CORPUS[index]["content"],
            "score": float(score),
            "metadata": metadata,
        })
        if len(results) >= top_k:
            break
    print(f"  [Lexical Search] Ket qua: {len(results)} chunk (BM25 > 0)")
    return results


if __name__ == "__main__":
    # Test
    results = lexical_search("phương thức thanh toán shopee", top_k=5)
    for r in results:
        print(f"[{r['score']:.3f}] {r['content'][:100]}...")