"""Task 8 - PageIndex vectorless retrieval.

The rest of the project works with Markdown files, while the PageIndex cloud
SDK's document endpoint accepts PDFs.  This module keeps that boundary in one
place: Markdown is rendered to a temporary PDF, uploaded once, and the
returned document ids are cached locally.  Retrieval uses PageIndex's legacy
retrieval API because it returns the structured passages required by the
Task 8/9 contract.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

PAGEINDEX_API_KEY = os.getenv("PAGEINDEX_API_KEY", "").strip()
STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"
_CACHE_FILE = STANDARDIZED_DIR / ".pageindex_documents.json"
_POLL_INTERVAL = float(os.getenv("PAGEINDEX_POLL_INTERVAL", "2"))
_POLL_TIMEOUT = float(os.getenv("PAGEINDEX_POLL_TIMEOUT", "180"))


def _client():
    """Create the official client lazily (so importing the pipeline is offline-safe)."""
    if not PAGEINDEX_API_KEY:
        raise RuntimeError("PAGEINDEX_API_KEY chưa được cấu hình")
    try:
        from pageindex import PageIndexClient
    except ImportError:  # compatibility with older package layouts
        from pageindex.client import PageIndexClient
    return PageIndexClient(api_key=PAGEINDEX_API_KEY)


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _load_cache() -> dict[str, str]:
    if not _CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_cache(cache: dict[str, str]) -> None:
    STANDARDIZED_DIR.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _markdown_to_pdf(md_file: Path, output_dir: Path) -> Path:
    """Render Markdown as a simple, Unicode-capable PDF for PageIndex upload."""
    from fpdf import FPDF

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / f"{md_file.stem}.pdf"
    font_candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    font = next((p for p in font_candidates if p.exists()), None)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    if font:
        pdf.add_font("DocumentFont", fname=str(font))
        pdf.set_font("DocumentFont", size=10)
    else:
        pdf.set_font("Helvetica", size=10)

    for line in md_file.read_text(encoding="utf-8").splitlines():
        # Keep headings visible to PageIndex's structure parser.
        text = re.sub(r"^#{1,6}\s*", "", line).strip()
        if not text:
            pdf.ln(4)
            continue
        if not font:
            text = text.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(0, 5, text)
    pdf.output(str(pdf_path))
    return pdf_path


def upload_documents() -> dict[str, str]:
    """Upload standardized Markdown documents and return ``{filename: doc_id}``.

    Existing uploads are reused from ``.pageindex_documents.json``.  This makes
    running the command repeatedly idempotent and avoids paying for duplicate
    PageIndex indexing jobs.
    """
    client = _client()
    cache = _load_cache()
    pdf_dir = STANDARDIZED_DIR / ".pageindex_pdf"

    for md_file in sorted(STANDARDIZED_DIR.rglob("*.md")):
        if md_file.name.startswith(".") or not md_file.read_text(encoding="utf-8").strip():
            continue
        key = str(md_file.relative_to(STANDARDIZED_DIR)).replace("\\", "/")
        if cache.get(key):
            continue
        pdf_path = _markdown_to_pdf(md_file, pdf_dir)
        response = _as_dict(client.submit_document(str(pdf_path)))
        doc_id = response.get("doc_id") or response.get("id")
        if not doc_id:
            raise RuntimeError(f"PageIndex không trả về doc_id cho {md_file.name}: {response}")
        cache[key] = str(doc_id)
        print(f"  Uploaded: {md_file.name} -> {doc_id}")

    _write_cache(cache)
    return cache


def _wait_for_retrieval(client: Any, retrieval_id: str) -> dict:
    deadline = time.monotonic() + _POLL_TIMEOUT
    while True:
        result = _as_dict(client.get_retrieval(retrieval_id))
        status = str(result.get("status", "")).lower()
        if status in {"completed", "complete", "success", "failed", "error"}:
            if status in {"failed", "error"}:
                return {}
            return result
        if time.monotonic() >= deadline:
            raise TimeoutError(f"PageIndex retrieval timeout: {retrieval_id}")
        time.sleep(_POLL_INTERVAL)


def _iter_relevant_contents(node: dict):
    contents = node.get("relevant_contents", [])
    # Older examples showed list[list[dict]], current API returns list[dict].
    if isinstance(contents, dict):
        contents = [contents]
    for item in contents:
        if isinstance(item, list):
            yield from (entry for entry in item if isinstance(entry, dict))
        elif isinstance(item, dict):
            yield item


def pageindex_search(query: str, top_k: int = 5) -> list[dict]:
    """Query PageIndex and normalize structured passages to the project contract."""
    if not query or top_k <= 0 or not PAGEINDEX_API_KEY:
        return []

    cache = _load_cache()
    if not cache:
        cache = upload_documents()
    if not cache:
        return []

    client = _client()
    results: list[dict] = []
    rank = 0
    for filename, doc_id in cache.items():
        try:
            if hasattr(client, "is_retrieval_ready") and not client.is_retrieval_ready(doc_id):
                continue
            submitted = _as_dict(client.submit_query(doc_id=doc_id, query=query))
            retrieval_id = submitted.get("retrieval_id") or submitted.get("id")
            if not retrieval_id:
                continue
            retrieval = _wait_for_retrieval(client, str(retrieval_id))
        except Exception as exc:
            print(f"  PageIndex query skipped for {filename}: {exc}")
            continue

        for node in retrieval.get("retrieved_nodes", []):
            if not isinstance(node, dict):
                continue
            for item in _iter_relevant_contents(node):
                content = str(item.get("relevant_content", item.get("content", ""))).strip()
                if not content:
                    continue
                rank += 1
                results.append({
                    "content": content,
                    "score": 1.0 / rank,
                    "metadata": {
                        "source": filename,
                        "section": item.get("section_title") or node.get("title"),
                        "page_index": item.get("page_index"),
                        "node_id": node.get("node_id"),
                    },
                    "source": "pageindex",
                })
                if len(results) >= top_k:
                    return results
    return results


if __name__ == "__main__":
    if not PAGEINDEX_API_KEY:
        print("Hãy set PAGEINDEX_API_KEY trong file .env")
    else:
        print("Uploaded documents:", upload_documents())
        for result in pageindex_search("danh sách sản phẩm cấm đăng bán", top_k=3):
            print(f"[{result['score']:.3f}] {result['content'][:100]}...")
