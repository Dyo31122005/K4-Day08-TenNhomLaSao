"""
Shopee AI — Trợ lý chính sách Shopee Web Application (Flask UI từ Day 07)
Kết nối với Day 08 RAG Pipeline (Task 9 Hybrid Retrieval + Task 10 Generation có Citation).

Chạy server:
    python server.py
    (Truy cập tại http://localhost:5000 hoặc http://localhost:5000/chat)
"""

import json
import sys
import time
from pathlib import Path
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from src.task4_chunking_indexing import classify_customer_role
from src.task9_retrieval_pipeline import retrieve
from src.task10_generation import generate_with_citation, generate_with_citation_stream

app = Flask(__name__, template_folder="templates", static_folder="static")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat")
def chat():
    return render_template("chat.html")


@app.route("/presentation")
def presentation():
    return render_template("presentation.html")


def log_retrieval_to_console(question: str, retrieved_sources: list[dict]):
    print("\n" + "=" * 70, flush=True)
    print(f"📩 [USER QUERY]: {question}", flush=True)
    print("-" * 70, flush=True)
    print(f"🔍 [RETRIEVAL LOG]: Top {len(retrieved_sources)} Chunks (Hybrid RRF Fusion):", flush=True)
    for i, s in enumerate(retrieved_sources, 1):
        meta = s.get("metadata", {})
        src_name = meta.get("source", file_name(meta.get("path", "")))
        score = round(s.get("score", 0), 4)
        chunk_idx = meta.get("chunk_index", 0)
        role = meta.get("customer_role", "both")
        print(f"  {i}. [Score: {score:.4f}] {src_name} (Chunk #{chunk_idx} | Role: {role})", flush=True)
    print("=" * 70 + "\n", flush=True)


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json() or {}
    question = data.get("question") or data.get("query", "")
    top_k = data.get("top_k", 5)

    if not question:
        return jsonify({"error": "Missing question"}), 400

    sources = retrieve(question, top_k=top_k)
    log_retrieval_to_console(question, sources)

    res = generate_with_citation(question, top_k=top_k)
    return jsonify(res)


@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    data = request.get_json() or {}
    question = data.get("question") or data.get("query", "")
    top_k = data.get("top_k", 5)

    if not question:
        return jsonify({"error": "Missing question"}), 400

    def generate():
        # Step 1: Hybrid Retrieval (Task 9) — Siêu tốc nhờ Pre-warming RAM
        retrieved_sources = retrieve(question, top_k=top_k)
        log_retrieval_to_console(question, retrieved_sources)

        sources_meta = []
        for i, s in enumerate(retrieved_sources, 1):
            meta = s.get("metadata", {})
            src_name = meta.get("source", file_name(meta.get("path", "")))
            score = round(s.get("score", 0), 4)
            sources_meta.append({
                "id": i,
                "title": src_name,
                "score": score,
                "content": s.get("content", ""),
                "type": meta.get("type", "policy"),
                "url": meta.get("url", "https://help.shopee.vn")
            })

        # Gửi sự kiện sources về client
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources_meta})}\n\n"

        # Step 2: Real-time LLM Token Streaming
        for token in generate_with_citation_stream(question, top_k=top_k):
            time.sleep(0.015)
            yield f"data: {json.dumps({'type': 'content', 'delta': token})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


def file_name(path: str) -> str:
    if not path:
        return "Shopee Policy"
    return Path(path).stem.replace("-", " ").title()


@app.route("/api/documents", methods=["GET"])
def api_documents():
    std_dir = PROJECT_ROOT / "data" / "standardized"
    docs = []
    if std_dir.exists():
        for file in sorted(std_dir.rglob("*.md")):
            try:
                content_text = file.read_text(encoding="utf-8")
            except Exception:
                content_text = ""

            role = classify_customer_role(file.name, content_text)

            docs.append({
                "id": file.stem,
                "title": file.stem.replace("-", " ").title(),
                "category": file.parent.name,
                "customer_role": role,
                "path": str(file.relative_to(PROJECT_ROOT)),
                "content": content_text
            })
    return jsonify(docs)



@app.route('/source.mp4')
def serve_video():
    from flask import send_from_directory
    return send_from_directory(PROJECT_ROOT, 'source.mp4')



# Pre-warm Embedding Model & BM25 Index vào RAM khi khởi động server
try:
    print("[PRE-WARM] Khởi tạo sẵn Embedding Model và BM25 Index vào RAM...")
    retrieve("warmup query", top_k=1)
    print("[PRE-WARM] Đã nạp thành công! Tìm kiếm Retrieval hiện tại mất < 0.05 giây.")
except Exception as _err:
    print(f"[PRE-WARM WARNING] {_err}")


if __name__ == "__main__":
    print("=" * 60)
    print("[SERVER] Shopee AI Chatbot Web Application (Day 07 UI + Day 08 RAG Pipeline)")
    print("Server dang chay tai: http://localhost:5000")
    print("Trang Chat Workspace: http://localhost:5000/chat")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)

