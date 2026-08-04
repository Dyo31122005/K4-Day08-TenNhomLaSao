"""
Task 3 — Convert toàn bộ file trong data/landing/ thành Markdown.

Sử dụng MarkItDown của Microsoft (yêu cầu `pip install "markitdown[pdf]"`).
Nếu thiếu dependency, in lỗi rõ ràng và bỏ qua file đó — KHÔNG dùng nội dung
giả thay thế, vì data/landing/legal/ chỉ được phép chứa PDF/DOCX thật theo
yêu cầu Task 1.

MarkItDown's PDF backend không tái dựng đoạn văn: mỗi dòng bị word-wrap theo
lề trang PDF được trả về như một đoạn riêng (\\n\\n), làm câu bị chặt vụn dù
PDF gốc hiển thị bình thường. clean_markdown_text() (scripts/clean_legal_md.py)
được gọi ngay sau khi convert để dọn header/footer lặp và nối lại các dòng bị
ngắt giữa câu, trước khi ghi ra data/standardized/.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.clean_legal_md import clean_markdown_text

LANDING_DIR = Path(__file__).parent.parent / "data" / "landing"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "standardized"


def convert_legal_docs():
    """Convert PDF/DOCX files trong data/landing/legal/ sang markdown."""
    legal_dir = LANDING_DIR / "legal"
    output_dir = OUTPUT_DIR / "legal"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not legal_dir.exists():
        print(f"Warning: Thu muc {legal_dir} khong ton tai.")
        return

    try:
        from markitdown import MarkItDown
        md = MarkItDown()
    except Exception:
        md = None

    for filepath in legal_dir.iterdir():
        if filepath.is_file() and filepath.suffix.lower() in (".pdf", ".docx", ".doc"):
            print(f"Converting PDF/DOCX: {filepath.name}")
            content = None
            if md:
                try:
                    result = md.convert(str(filepath))
                    if result and len(result.text_content) > 100:
                        content = clean_markdown_text(result.text_content)
                except Exception as e:
                    print(f"  Warning: MarkItDown conversion: {e}")

            if not content or len(content) < 100:
                print(f"  [LOI] Khong convert duoc {filepath.name} (thieu markitdown[pdf]?). Bo qua.")
                continue

            output_path = output_dir / f"{filepath.stem}.md"
            output_path.write_text(content, encoding="utf-8")
            print(f"  [OK] Saved: {output_path} ({len(content)} chars)")


def convert_news_articles():
    """Convert JSON crawled articles trong data/landing/news/ sang markdown."""
    news_dir = LANDING_DIR / "news"
    output_dir = OUTPUT_DIR / "news"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not news_dir.exists():
        print(f"Warning: Thu muc {news_dir} khong ton tai.")
        return

    for filepath in news_dir.iterdir():
        if filepath.is_file() and filepath.suffix.lower() == ".json":
            print(f"Converting JSON: {filepath.name}")
            data = json.loads(filepath.read_text(encoding="utf-8"))
            output_path = output_dir / f"{filepath.stem}.md"

            header = f"# {data.get('title', 'Unknown')}\n\n"
            header += f"**Source:** {data.get('url', 'N/A')}\n"
            header += f"**Category:** {data.get('category', 'N/A')}\n"
            header += f"**Crawled:** {data.get('date_crawled', 'N/A')}\n\n---\n\n"

            content = header + data.get("content_markdown", "")
            output_path.write_text(content, encoding="utf-8")
            print(f"  [OK] Saved: {output_path} ({len(content)} chars)")


def convert_all():
    """Convert toàn bộ files."""
    print("=" * 50)
    print("Task 3: Convert to Markdown (MarkItDown)")
    print("=" * 50)

    print("\n--- Legal Documents ---")
    convert_legal_docs()

    print("\n--- News Articles ---")
    convert_news_articles()

    print("\n[OK] Done! Output tai:", OUTPUT_DIR)


if __name__ == "__main__":
    convert_all()
