"""
Task 1 — Thu thập văn bản chính sách thương mại điện tử / hỗ trợ khách hàng.

Nhiệm vụ:
    - Tải THẬT (HTTP GET) 3 trang chính sách chính thức từ help.shopee.vn.
    - Trang bài viết của help.shopee.vn render server-side (nội dung nhúng sẵn
      trong HTML qua biến `window["FORGE_SSR_DATA_MAP"]`), nên không cần trình
      duyệt headless — chỉ cần `requests` + trích xuất JSON là lấy được nội
      dung thật (đã verify: khớp 100% với nội dung hiển thị trên trang thật).
    - Convert nội dung HTML lấy được thành text sạch, rồi render ra PDF theo
      giao diện thương hiệu Shopee (giữ đúng tinh thần "convert HTML -> PDF"
      mà bài lab cho phép khi nguồn không phải file PDF tải trực tiếp được).

Nếu mạng lỗi / trang bị chặn / cấu trúc trang thay đổi: script in cảnh báo rõ
ràng và BỎ QUA file đó (không bịa nội dung thay thế). Chạy lại script khi có
mạng ổn định, hoặc đổi sang URL khác cùng domain như LAB_GUIDE gợi ý.
"""

import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
from fpdf.enums import XPos, YPos

DATA_DIR = Path(__file__).parent.parent / "data" / "landing" / "legal"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Nguồn thật — đã verify HTTP 200 + nội dung khớp tiêu đề trang thật (2026-08-04).
LEGAL_ARTICLES = [
    {
        "filename": "returns-refund-policy-shopee.pdf",
        "url": "https://help.shopee.vn/portal/4/article/77251",
    },
    {
        "filename": "payment-methods-shopee.pdf",
        "url": "https://help.shopee.vn/portal/4/article/79198",
    },
    {
        "filename": "privacy-policy-shopee.pdf",
        "url": "https://help.shopee.vn/portal/4/article/77244",
    },
]


def setup_directory():
    """Tạo thư mục data/landing/legal/ nếu chưa có."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[OK] Thu muc da san sang: {DATA_DIR}")


def _extract_balanced_json(text: str, start: int) -> str:
    """Trích một object JSON cân bằng dấu ngoặc bắt đầu tại `start`."""
    depth = 0
    i = start
    in_str = False
    esc = False
    while i < len(text):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        i += 1
    raise ValueError("Không tìm thấy JSON object cân bằng dấu ngoặc.")


def fetch_shopee_article(url: str) -> dict:
    """
    Tải trang help.shopee.vn thật và trích nội dung bài viết từ dữ liệu SSR.

    Returns:
        {'url': str, 'title': str, 'content_text': str}

    Raises:
        ValueError nếu không tìm thấy dữ liệu SSR (trang đổi cấu trúc / bị chặn).
    """
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    html = resp.text

    marker = 'window["FORGE_SSR_DATA_MAP"] = '
    idx = html.find(marker)
    if idx == -1:
        raise ValueError("Không tìm thấy SSR data — trang có thể đã đổi cấu trúc hoặc chặn bot.")

    blob = _extract_balanced_json(html, idx + len(marker))
    data = json.loads(blob)

    article = next(
        (v for v in data.values() if isinstance(v, dict) and v.get("title") and v.get("content")),
        None,
    )
    if article is None:
        raise ValueError("Không tìm thấy nội dung bài viết trong dữ liệu SSR.")

    text = _html_to_text(article["content"])
    return {"url": url, "title": article["title"].strip(), "content_text": text}


def _html_to_text(html: str) -> str:
    """
    Convert HTML sang text, giữ đúng câu.

    Nội dung help.shopee.vn export theo kiểu Google Docs: mỗi cụm từ trong
    cùng một câu được bọc riêng trong <span>/<a> để giữ style/link. Nếu tách
    text theo TỪNG thẻ (vd. `soup.get_text("\n")`) thì một câu sẽ bị vỡ vụn
    thành nhiều dòng ở mỗi ranh giới span/link. Cách đúng là chỉ coi các thẻ
    khối (<p>, <li>) là ranh giới đoạn — bên trong một khối, nối text các
    thẻ con lại KHÔNG chèn separator (giữ nguyên khoảng trắng gốc trong HTML).
    """
    soup = BeautifulSoup(html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")

    blocks = []
    for el in soup.find_all(["p", "li"]):
        if el.find_parent(["p", "li"]):
            continue  # tránh lấy trùng phần tử lồng nhau
        block_text = el.get_text(separator="", strip=False)
        block_text = re.sub(r"[ \t]+", " ", block_text).strip()
        if not block_text:
            continue
        if el.name == "li":
            block_text = f"- {block_text}"
        blocks.append(block_text)

    return "\n\n".join(blocks)


class ShopeePDF(FPDF):
    """Lớp tạo PDF chuẩn thương hiệu Shopee (Màu cam #EE4D2D, font Arial)."""

    def header(self):
        self.set_fill_color(238, 77, 45)
        self.rect(0, 0, 210, 20, "F")

        self.set_text_color(255, 255, 255)
        if hasattr(self, "arial_loaded") and self.arial_loaded:
            self.set_font("Arial", "", 12)
        else:
            self.set_font("Helvetica", "B", 12)
        self.set_xy(10, 5)
        self.cell(0, 10, "SHOPEE VIETNAM - TRUNG TAM TRO GIUP KHACH HANG", align="L")

        self.set_font_size(9)
        self.set_xy(140, 5)
        self.cell(0, 10, "help.shopee.vn", align="R")

        self.set_y(25)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-15)
        if hasattr(self, "arial_loaded") and self.arial_loaded:
            self.set_font("Arial", "", 8)
        else:
            self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Trang {self.page_no()} | Nguon: help.shopee.vn (da crawl that)", align="C")


_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F\U00002190-\U000021FF]"
)


def _strip_unsupported_glyphs(text: str) -> str:
    """Bỏ emoji không có trong font Arial (nội dung thật của Shopee có emoji như ⚠️)."""
    return _EMOJI_RE.sub("", text)


def generate_pdf(filename: str, title: str, source_url: str, content_text: str):
    """Render nội dung THẬT đã crawl thành PDF thương hiệu Shopee."""
    content_text = _strip_unsupported_glyphs(content_text)
    pdf = ShopeePDF()
    arial_path = r"C:\Windows\Fonts\arial.ttf"

    if Path(arial_path).exists():
        pdf.add_font("Arial", "", arial_path)
        pdf.arial_loaded = True
    else:
        pdf.arial_loaded = False

    pdf.add_page()

    if pdf.arial_loaded:
        pdf.set_font("Arial", "", 14)
    else:
        pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(238, 77, 45)
    pdf.multi_cell(pdf.epw, 8, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    if pdf.arial_loaded:
        pdf.set_font("Arial", "", 8)
    else:
        pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(pdf.epw, 5, f"Nguồn: {source_url}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    pdf.set_draw_color(238, 77, 45)
    pdf.set_line_width(0.5)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    pdf.set_text_color(40, 40, 40)
    if pdf.arial_loaded:
        pdf.set_font("Arial", "", 10)
    else:
        pdf.set_font("Helvetica", "", 10)

    for line in content_text.split("\n"):
        line_str = line.strip()
        if not line_str:
            pdf.ln(3)
            continue

        # Chỉ coi là heading khi có dạng "N. " (số + dấu chấm + khoảng trắng
        # + chữ ngay sau) — tránh nhận nhầm số tiền dạng "10.000 VNĐ".
        if re.match(r"^\d{1,2}\.\s+\S", line_str) and len(line_str) < 80:
            pdf.ln(2)
            pdf.set_text_color(238, 77, 45)
            if pdf.arial_loaded:
                pdf.set_font("Arial", "", 11)
            pdf.multi_cell(pdf.epw, 7, line_str, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(40, 40, 40)
            if pdf.arial_loaded:
                pdf.set_font("Arial", "", 10)
        else:
            pdf.multi_cell(pdf.epw, 6, line_str, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    filepath = DATA_DIR / filename
    pdf.output(str(filepath))

    print(f"[OK] Da tao PDF tu noi dung crawl that: {filepath} ({filepath.stat().st_size} bytes)")


def generate_legal_docs():
    """Tải thật 3 văn bản chính sách Shopee và lưu thành PDF."""
    setup_directory()

    for article in LEGAL_ARTICLES:
        print(f"Dang tai: {article['url']}")
        try:
            fetched = fetch_shopee_article(article["url"])
            generate_pdf(article["filename"], fetched["title"], fetched["url"], fetched["content_text"])
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[LOI] Khong tai duoc {article['url']}: {e}")
            print("      -> Bo qua file nay. Kiem tra ket noi mang hoac chay lai sau.")


if __name__ == "__main__":
    generate_legal_docs()
