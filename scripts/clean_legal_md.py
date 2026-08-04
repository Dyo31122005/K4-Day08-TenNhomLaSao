"""
Script làm sạch dữ liệu Markdown được chuyển đổi từ PDF (legal docs).
- Xóa các ký tự ngắt trang \x0c
- Xóa Header/Footer lặp lại của từng trang PDF
- Chuẩn hóa khoảng trắng thừa trong dòng
- Nối các dòng câu bị ngắt vô lý ở giữa câu
"""

import sys
import re
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

LEGAL_DIR = Path(__file__).parent.parent / "data" / "standardized" / "legal"

def clean_markdown_text(text: str) -> str:
    # 1. Remove form feed character \x0c
    text = text.replace("\x0c", "")

    # 2. Remove repeating header/footer lines
    header_pattern = r"(?i)SHOPEE VIETNAM - TRUNG TAM TRO GIUP KHACH HANG\s+help\.shopee\.vn"
    footer_pattern = r"(?i)Trang \d+ \| Nguon: help\.shopee\.vn.*"
    
    text = re.sub(header_pattern, "", text)
    text = re.sub(footer_pattern, "", text)

    # 3. Split into lines and strip trailing spaces
    lines = [line.strip() for line in text.splitlines()]
    
    # Filter out empty consecutive lines
    cleaned_lines = []
    for line in lines:
        if line:
            # Reformat multiple internal spaces (e.g. "Bạn  có  thể" -> "Bạn có thể")
            line = re.sub(r" {2,}", " ", line)
            cleaned_lines.append(line)

    # 4. Smart join lines that were artificially broken by PDF page layout
    # Paragraph blocks should only split on headings, bullet points, numbered items, or end of sentence.
    blocks = []
    current_block = []

    for line in cleaned_lines:
        is_heading_or_list = (
            line.startswith("#")
            or line.startswith("- ")
            or line.startswith("* ")
            or re.match(r"^\d+(\.\d+)*\.", line)
            or line.startswith("Nguồn:")
            or line.startswith("Source:")
            or line.startswith("Lưu ý:")
            or line.startswith("CHÍNH SÁCH")
        )

        if is_heading_or_list:
            if current_block:
                blocks.append(" ".join(current_block))
                current_block = []
            blocks.append(line)
        else:
            if not current_block:
                current_block.append(line)
            else:
                last_line = current_block[-1]
                # If last line ends with sentence punctuation, start new block
                if last_line.endswith((".", ":", "?", "!", '")', '”')):
                    blocks.append(" ".join(current_block))
                    current_block = [line]
                else:
                    current_block.append(line)

    if current_block:
        blocks.append(" ".join(current_block))

    return "\n\n".join(blocks)


def clean_all_legal_files():
    print("=" * 50)
    print("Làm sạch các file Legal Markdown từ PDF...")
    print("=" * 50)

    for md_file in LEGAL_DIR.glob("*.md"):
        original_text = md_file.read_text(encoding="utf-8")
        cleaned_text = clean_markdown_text(original_text)
        md_file.write_text(cleaned_text, encoding="utf-8")
        print(f"[OK] Cleaned {md_file.name}: {len(original_text)} -> {len(cleaned_text)} chars")

if __name__ == "__main__":
    clean_all_legal_files()
