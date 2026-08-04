import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_ST_MODEL_CACHE = {}

def _get_st_model(model_name: str):
    if model_name not in _ST_MODEL_CACHE:
        from sentence_transformers import SentenceTransformer
        _ST_MODEL_CACHE[model_name] = SentenceTransformer(model_name)
    return _ST_MODEL_CACHE[model_name]


def generate_hypothetical_doc(query: str) -> str:
    """
    Tạo ra tài liệu giả định (HyDE) sử dụng mô hình LLM để tối ưu hóa tìm kiếm.
    Cài đặt fallback chain nhiều tầng để tránh gián đoạn khi 1 API key hết quota.
    """
    # OpenAI đặt đầu tiên (phản hồi ổn định/nhanh hơn DeepSeek trong thực tế đo được).
    chain = [
        ("OpenAI", "gpt-4o-mini", None, "OPENAI_API_KEY"),
        ("OpenRouter", "google/gemini-2.5-flash", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
        ("Gemini", "gemini-1.5-flash", "https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"),
        ("DeepSeek", "deepseek-chat", "https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    ]
    # Timeout cứng: 1 provider bị treo mạng sẽ raise thay vì làm cả request
    # (và cả server) đứng im vô thời hạn, chặn luôn fallback sang provider kế.
    LLM_REQUEST_TIMEOUT = 20.0

    prompt = (
        "Hãy viết một câu trả lời giả định hoặc tài liệu hướng dẫn ngắn (khoảng 100-200 từ) bằng tiếng Việt "
        "về chủ đề sau đây cho Trung tâm Hỗ trợ của sàn Thương mại điện tử (Shopee Việt Nam). "
        "Tập trung cung cấp thông tin thực tế, chi tiết và có cấu trúc rõ ràng.\n\n"
        f"Chủ đề: {query}"
    )

    from openai import OpenAI
    for provider_name, model, base_url, key_env in chain:
        api_key = os.getenv(key_env)
        if not api_key:
            print(f"  [HyDE] {provider_name} ({model}): bo qua, thieu {key_env}")
            continue
        try:
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=LLM_REQUEST_TIMEOUT)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Trợ lý hỗ trợ khách hàng TMĐT chuyên nghiệp."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=300
            )
            print(f"  [HyDE] {provider_name} ({model}): OK")
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"  [HyDE] {provider_name} ({model}): loi - {e}")
            continue

    print("  [HyDE] Tat ca provider deu loi/thieu key -> dung nguyen query goc")
    return query


def semantic_search(query: str, top_k: int = 10, filter_metadata: dict = None) -> list[dict]:
    """
    Tìm kiếm ngữ nghĩa sử dụng vector similarity kết hợp HyDE.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa
        filter_metadata: Dict chứa điều kiện lọc metadata (VD: {'customer_role': 'seller'} hoặc {'type': 'legal'})

    Returns:
        List of {
            'content': str,      # Nội dung chunk
            'score': float,      # Cosine similarity score
            'metadata': dict     # source, doc_type, chunk_index
        }
        Sorted by score descending.
    """
    print(f"[Semantic Search] Query: '{query}' (top_k={top_k}, filter={filter_metadata})")

    # 1. Sử dụng HyDE để sinh tài liệu giả định
    hyde_query = generate_hypothetical_doc(query)

    # 2. Sinh embedding cho tài liệu giả định theo Embedding Provider
    provider = os.getenv("EMBEDDING_PROVIDER", "sentence_transformers").lower()
    print(f"  [Semantic Search] Embedding provider: {provider}")

    try:
        if provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            model_name = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
            res = client.embeddings.create(input=[hyde_query], model=model_name)
            query_vector = res.data[0].embedding
        elif provider == "google":
            import google.generativeai as genai
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model_name = os.getenv("GEMINI_EMBEDDING_MODEL", "models/text-embedding-004")
            res = genai.embed_content(model=model_name, contents=hyde_query)
            query_vector = res['embedding']
        else:
            model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
            model = _get_st_model(model_name)
            query_vector = model.encode(hyde_query).tolist()
    except Exception as e:
        print(f"[Semantic Search] Embedding generation failed: {e}")
        return []

    # 3. Truy vấn cơ sở dữ liệu vector ChromaDB
    try:
        import chromadb
        chroma_dir = Path(__file__).parent.parent / "chroma_db"
        if not chroma_dir.exists():
            return []

        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection_name = os.getenv("COLLECTION_NAME", "ecommerce_support_docs")
        
        try:
            collection = client.get_collection(name=collection_name)
        except Exception:
            return []

        query_kwargs = {
            "query_embeddings": [query_vector],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"]
        }
        if filter_metadata:
            query_kwargs["where"] = filter_metadata

        try:
            results = collection.query(**query_kwargs)
        except Exception as e:
            if "dimension" in str(e).lower():
                print(f"[Semantic Search] Dimension mismatch ({e}). Auto re-indexing vector store...")
                from .task4_chunking_indexing import run_pipeline
                run_pipeline()
                collection = client.get_collection(name=collection_name)
                results = collection.query(**query_kwargs)
            else:
                raise e

        if not results or not results.get("documents") or len(results["documents"]) == 0:
            return []

        output = []
        for doc, meta, dist in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        ):
            score = max(0.0, 1.0 - dist)  # Cosine distance -> similarity
            output.append({
                "content": doc,
                "score": round(score, 4),
                "metadata": meta
            })

        output.sort(key=lambda x: x["score"], reverse=True)
        output = output[:top_k]
        print(f"  [Semantic Search] Ket qua: {len(output)} chunk (best score={output[0]['score']:.4f})" if output else "  [Semantic Search] Ket qua: 0 chunk")
        return output
    except Exception as e:
        print(f"[Semantic Search] Query failed: {e}")
        return []


if __name__ == "__main__":
    results = semantic_search("quy định trả hàng hoàn tiền shopee", top_k=5)
    for r in results:
        safe_text = r['content'][:100].encode('ascii', 'ignore').decode('ascii')
        print(f"[{r['score']:.3f}] {safe_text}...")
