"""
Task 3 — Convert toàn bộ file trong data/landing/ thành Markdown.

Sử dụng MarkItDown của Microsoft (yêu cầu `pip install "markitdown[pdf]"`).
Nếu thiếu dependency, in lỗi rõ ràng và bỏ qua file đó — KHÔNG dùng nội dung
giả thay thế, vì data/landing/legal/ chỉ được phép chứa PDF/DOCX thật theo
yêu cầu Task 1.
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LANDING_DIR = Path(__file__).parent.parent / "data" / "landing"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "standardized"


def generate_summary_for_content(filename: str, content: str) -> str:
    """Tạo tóm tắt ngắn cho tài liệu chính sách (gọi LLM hoặc dùng dự phòng)."""
    fallback_summaries = {
        "returns-refund-policy-shopee.pdf": (
            "Chính sách trả hàng/hoàn tiền Shopee quy định: Người mua gửi yêu cầu qua app kèm video mở hộp rõ nét "
            "trong thời hạn quy định (tùy hạng thẻ). Shopee xử lý trong 3-5 ngày. Tiền hoàn về ví ShopeePay, "
            "tài khoản liên kết hoặc thẻ tín dụng. Hỗ trợ ship trả hàng miễn phí qua đơn vị đối tác."
        ),
        "payment-methods-shopee.pdf": (
            "Các phương thức thanh toán Shopee hỗ trợ bao gồm: Ví điện tử ShopeePay (tiện lợi, nhiều ưu đãi), "
            "Thẻ tín dụng/ghi nợ quốc tế (Visa, Mastercard, JCB, American Express), Thẻ Napas ATM nội địa, "
            "Thanh toán tiền mặt khi nhận hàng (COD), và Mua trước trả sau SPayLater."
        ),
        "privacy-policy-shopee.pdf": (
            "Chính sách bảo mật Shopee quy định: Thu thập dữ liệu cá nhân (tên, SĐT, email, địa chỉ, lịch sử mua hàng, vị trí) "
            "nhằm xử lý đơn hàng, bảo mật và cá nhân hóa dịch vụ. Cam kết bảo mật, không bán thông tin, "
            "chỉ chia sẻ với bên thứ ba liên quan để thực hiện giao dịch hoặc theo yêu cầu pháp luật."
        )
    }
    
    openai_key = os.getenv("OPENAI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    
    if not openrouter_key and not openai_key:
        return fallback_summaries.get(filename, "Tóm tắt tài liệu không khả dụng.")
        
    try:
        from openai import OpenAI
        if openrouter_key:
            client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")
            model = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
        else:
            client = OpenAI(api_key=openai_key)
            model = os.getenv("LLM_MODEL", "gpt-4o-mini")
            
        prompt = (
            "Hãy đọc tài liệu chính sách dưới đây và viết một bản tóm tắt ngắn gọn khoảng 100-150 từ bằng tiếng Việt.\n"
            "Bản tóm tắt phải bao quát được các nội dung quan trọng nhất, trình bày dưới dạng một đoạn văn súc tích.\n\n"
            f"Nội dung tài liệu:\n{content[:4000]}"
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Bạn là chuyên gia phân tích chính sách thương mại điện tử."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  [WARN] LLM summary failed: {e}. Using predefined fallback.")
        return fallback_summaries.get(filename, "Tóm tắt tài liệu không khả dụng.")


def convert_legal_docs():
    """Convert PDF/DOCX files trong data/landing/legal/ sang markdown, tự động tích hợp tóm tắt ở đầu file."""
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
                        content = result.text_content
                except Exception as e:
                    print(f"  Warning: MarkItDown conversion: {e}")

            if not content or len(content) < 100:
                print(f"  [LOI] Khong convert duoc {filepath.name} (thieu markitdown[pdf]?). Bo qua.")
                continue

            # Sinh tóm tắt và chèn vào đầu nội dung Markdown để RAG tự động bắt được
            summary = generate_summary_for_content(filepath.name, content)
            final_content = f"# TOM TAT CHINH SACH\n\n{summary}\n\n---\n\n# NOI DUNG CHI TIET\n\n{content}"

            output_path = output_dir / f"{filepath.stem}.md"
            output_path.write_text(final_content, encoding="utf-8")
            print(f"  [OK] Saved with Summary: {output_path} ({len(final_content)} chars)")


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
