"""
Task 10 — Generation Có Citation.

Cấu hình:
    - TOP_K = 5: Đủ thông tin làm minh chứng mà không gây rác context.
    - TOP_P = 0.9: Giới hạn không gian sampling token.
    - TEMPERATURE = 0.3: Thấp để câu trả lời có tính chính xác cao, ít bịa đặt (hallucination).
    - LLM_MODEL_FALLBACK_CHAIN: Gọi trực tiếp API key riêng của từng nhà cung cấp (không qua
      OpenRouter) — mỗi provider có (base_url, api_key, model) riêng, đều có endpoint tương
      thích chuẩn OpenAI chat.completions. Thử lần lượt, model sau chỉ được gọi khi model
      trước lỗi hoặc timeout (rate limit, quá tải, không khả dụng, v.v). Thứ tự:
      GPT-4o-mini -> OpenRouter Gemini -> Gemini 1.5 Flash -> DeepSeek Chat.
      LLM_REQUEST_TIMEOUT giới hạn thời gian chờ mỗi provider để tránh treo vô hạn.
"""

import os
from dotenv import load_dotenv

load_dotenv()

from .task9_retrieval_pipeline import retrieve

TOP_K = 5
TOP_P = 0.9
TEMPERATURE = 0.3

# (tên hiển thị, model id, base_url, tên biến env chứa API key)
# base_url=None nghĩa là dùng endpoint mặc định của SDK OpenAI (api.openai.com).
# GPT-4o-mini đặt đầu tiên (phản hồi ổn định/nhanh hơn DeepSeek trong thực tế đo được).
LLM_MODEL_FALLBACK_CHAIN = [
    ("GPT-4o-mini", "gpt-4o-mini", None, "OPENAI_API_KEY"),
    ("OpenRouter Gemini", "google/gemini-2.5-flash", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    ("Gemini Flash", "gemini-1.5-flash", "https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"),
    ("DeepSeek Chat", "deepseek-chat", "https://api.deepseek.com", "DEEPSEEK_API_KEY"),
]

# Timeout cứng cho mỗi lần gọi LLM API — không set thì 1 provider bị treo (mất
# mạng, quá tải) sẽ làm request đứng im vô thời hạn thay vì rớt xuống provider
# kế tiếp trong fallback chain, gây hiện tượng "không phản hồi" phía client.
LLM_REQUEST_TIMEOUT = 20.0

SYSTEM_PROMPT = """Bạn là trợ lý trả lời câu hỏi về chính sách thương mại điện tử và hỗ trợ khách hàng.

Quy tắc bắt buộc:
1. Chỉ sử dụng thông tin từ context được cung cấp — KHÔNG bịa đặt.
2. Mỗi khẳng định phải có trích dẫn ngay sau, ví dụ: [Returns Policy, 2026].
3. Nếu context không đủ thông tin -> trả lời: "Tôi không thể xác minh thông tin này từ nguồn hiện có".
4. Trả lời bằng tiếng Việt, có cấu trúc rõ ràng theo đoạn văn.
"""


def reorder_for_llm(chunks: list[dict]) -> list[dict]:
    """
    Sắp xếp chunks để tránh "lost in the middle" effect.
    Input order: [1, 2, 3, 4, 5] -> Output order: [1, 3, 5, 4, 2]
    """
    if len(chunks) <= 2:
        return chunks

    front = chunks[::2]
    back = chunks[1::2]
    return front + back[::-1]


def format_context(chunks: list[dict]) -> str:
    """
    Format chunks thành context string cho prompt kèm metadata source.
    """
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata", {})
        source = metadata.get("source", f"Source_{i}")
        doc_type = metadata.get("type", "general")
        context_parts.append(
            f"[Document {i} | Source: {source} | Type: {doc_type}]\n"
            f"{chunk['content']}\n"
        )
    return "\n---\n".join(context_parts)


def generate_with_citation(query: str, top_k: int = TOP_K) -> dict:
    """
    End-to-end RAG generation có citation.

    Returns:
        {
            'answer': str,
            'sources': list[dict],
            'retrieval_source': str
        }
    """
    print(f"[Generation] Retrieval xong: {top_k} chunk yeu cau")
    chunks = retrieve(query, top_k=top_k)
    reordered_chunks = reorder_for_llm(chunks)
    context_str = format_context(reordered_chunks)
    user_message = f"Context:\n{context_str}\n\n---\n\nQuestion: {query}"
    print(f"[Generation] Context: {len(chunks)} chunk, {len(context_str)} ky tu")

    from openai import OpenAI

    answer = None
    errors = []
    for display_name, model, base_url, key_env in LLM_MODEL_FALLBACK_CHAIN:
        api_key = os.getenv(key_env)
        if not api_key:
            print(f"  [Generation] {display_name} ({model}): bo qua, thieu {key_env}")
            errors.append(f"{display_name}: thiếu {key_env} trong .env")
            continue
        try:
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=LLM_REQUEST_TIMEOUT)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=TEMPERATURE,
                top_p=TOP_P,
            )
            answer = response.choices[0].message.content
            print(f"  [Generation] {display_name} ({model}): OK ({len(answer)} ky tu)")
            break
        except Exception as e:
            print(f"  [Generation] {display_name} ({model}): loi - {e}")
            errors.append(f"{display_name}: {e}")
            continue

    if answer is None:
        print("  [Generation] Tat ca model trong fallback chain deu loi -> dung cau tra loi du phong")
        if chunks:
            summary = "\n".join([f"- {c['content'][:150]}... [{c.get('metadata', {}).get('source', 'Shopee Policy')}]" for c in chunks[:3]])
            base_answer = f"Dựa trên tài liệu hệ thống:\n{summary}"
        else:
            base_answer = "Tôi không thể xác minh thông tin này từ nguồn hiện có."
        tried = "; ".join(errors)
        answer = f"{base_answer}\n\n(Note: tất cả model trong fallback chain đều lỗi: {tried})"

    return {
        "answer": answer,
        "sources": chunks,
        "retrieval_source": chunks[0].get("source", "hybrid") if chunks else "none"
    }


def generate_with_citation_stream(query: str, top_k: int = TOP_K):
    """Generator stream từng token từ LLM theo thời gian thực (Real-time LLM Streaming)."""
    print(f"[Generation Stream] Retrieval xong: {top_k} chunk yeu cau")
    chunks = retrieve(query, top_k=top_k)
    reordered_chunks = reorder_for_llm(chunks)
    context_str = format_context(reordered_chunks)
    user_message = f"Context:\n{context_str}\n\n---\n\nQuestion: {query}"
    print(f"[Generation Stream] Context: {len(chunks)} chunk, {len(context_str)} ky tu")

    from openai import OpenAI

    success = False
    for display_name, model, base_url, key_env in LLM_MODEL_FALLBACK_CHAIN:
        api_key = os.getenv(key_env)
        if not api_key:
            print(f"  [Generation Stream] {display_name} ({model}): bo qua, thieu {key_env}")
            continue
        try:
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=LLM_REQUEST_TIMEOUT)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=TEMPERATURE,
                top_p=TOP_P,
                stream=True
            )
            print(f"  [Generation Stream] {display_name} ({model}): dang stream...")
            token_count = 0
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    token_count += 1
                    yield chunk.choices[0].delta.content
            success = True
            print(f"  [Generation Stream] {display_name} ({model}): OK ({token_count} token)")
            break
        except Exception as e:
            print(f"  [Generation Stream] {display_name} ({model}): loi - {e}")
            continue

    if not success:
        print("  [Generation Stream] Tat ca model deu loi -> fallback sang generate_with_citation (non-stream)")
        res = generate_with_citation(query, top_k=top_k)
        yield res.get("answer", "Không tìm thấy thông tin phù hợp.")


if __name__ == "__main__":
    result = generate_with_citation("Shopee hỗ trợ những phương thức thanh toán nào?")
    print("A:", result["answer"])
