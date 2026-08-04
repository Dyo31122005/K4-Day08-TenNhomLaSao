import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def generate_hypothetical_doc(query: str) -> str:
    """
    Tạo ra tài liệu giả định (HyDE) sử dụng mô hình LLM để tối ưu hóa tìm kiếm.
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    
    if not openrouter_key and not openai_key:
        # Nếu không có API Key, trả về query nguyên bản làm fallback
        return query

    try:
        from openai import OpenAI
        if openrouter_key:
            client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")
            model = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
        else:
            client = OpenAI(api_key=openai_key)
            model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        
        prompt = (
            "Hãy viết một câu trả lời giả định hoặc tài liệu hướng dẫn ngắn (khoảng 100-200 từ) "
            "về chủ đề sau đây cho Trung tâm Hỗ trợ của sàn Thương mại điện tử (Shopee Việt Nam). "
            "Tập trung cung cấp thông tin thực tế, chi tiết và có cấu trúc rõ ràng.\n\n"
            f"Chủ đề: {query}"
        )
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Trợ lý hỗ trợ khách hàng TMĐT chuyên nghiệp."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[HyDE] Failed to generate hypothetical doc: {e}. Using original query.")
        return query


def semantic_search(query: str, top_k: int = 10) -> list[dict]:
    """
    Tìm kiếm ngữ nghĩa sử dụng vector similarity kết hợp HyDE.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa

    Returns:
        List of {
            'content': str,      # Nội dung chunk
            'score': float,      # Cosine similarity score
            'metadata': dict     # source, doc_type, chunk_index
        }
        Sorted by score descending.
    """
    # 1. Sử dụng HyDE để sinh tài liệu giả định
    hyde_query = generate_hypothetical_doc(query)

    # 2. Sinh embedding cho tài liệu giả định theo Embedding Provider
    provider = os.getenv("EMBEDDING_PROVIDER", "sentence_transformers").lower()
    
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
            from sentence_transformers import SentenceTransformer
            model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
            model = SentenceTransformer(model_name)
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

        results = collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

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
        return output[:top_k]
    except Exception as e:
        print(f"[Semantic Search] Query failed: {e}")
        return []


if __name__ == "__main__":
    results = semantic_search("quy định trả hàng hoàn tiền shopee", top_k=5)
    for r in results:
        safe_text = r['content'][:100].encode('ascii', 'ignore').decode('ascii')
        print(f"[{r['score']:.3f}] {safe_text}...")
