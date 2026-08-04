"""
Task 2 — Crawl bài viết/hướng dẫn hỗ trợ khách hàng về thương mại điện tử.

Nhiệm vụ:
    - Crawl THẬT (HTTP GET) tối thiểu 5 bài viết từ help.shopee.vn.
    - Mỗi bài lưu 1 file JSON chứa metadata (url, title, date_crawled, content_markdown).

URL trong ARTICLE_URLS được lấy từ sitemap.xml chính thức của help.shopee.vn
(https://help.shopee.vn/sitemap.xml), đã verify từng URL trả về HTTP 200 và có
nội dung thật (không phải trang rỗng / placeholder).

Cách trích xuất giống Task 1 — trang bài viết là server-rendered nên chỉ cần
`requests`, không cần crawl4ai/Playwright.
"""

import json
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.task1_collect_legal_docs import fetch_shopee_article

DATA_DIR = Path(__file__).parent.parent / "data" / "landing" / "news"

# URL thật, lấy từ https://help.shopee.vn/sitemap.xml — verify HTTP 200 (2026-08-04).
ARTICLE_URLS = [
    ("article_01.json", "https://help.shopee.vn/portal/4/article/79215", "Order Tracking"),
    ("article_02.json", "https://help.shopee.vn/portal/4/article/79196", "Payment"),
    ("article_03.json", "https://help.shopee.vn/portal/4/article/79467", "Returns & Refund"),
    ("article_04.json", "https://help.shopee.vn/portal/4/article/79556", "Cross-border"),
    ("article_05.json", "https://help.shopee.vn/portal/4/article/140097", "Seller Policy"),
]


def setup_directory():
    """Tạo thư mục data/landing/news/ nếu chưa có."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[OK] Thu muc da san sang: {DATA_DIR}")


def crawl_article(filename: str, url: str, category: str) -> bool:
    """Crawl 1 bài viết thật và lưu JSON. Trả về True nếu thành công."""
    try:
        fetched = fetch_shopee_article(url)
    except Exception as e:
        print(f"[LOI] Khong crawl duoc {url}: {e}")
        return False

    data = {
        "url": fetched["url"],
        "title": fetched["title"],
        "category": category,
        "date_crawled": datetime.now().isoformat(),
        "content_markdown": fetched["content_text"],
    }

    filepath = DATA_DIR / filename
    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Da crawl that: {filepath} ({filepath.stat().st_size} bytes) <- {url}")
    return True


def crawl_all():
    """Crawl toàn bộ bài viết trong ARTICLE_URLS."""
    setup_directory()

    ok_count = 0
    for filename, url, category in ARTICLE_URLS:
        print(f"Dang crawl: {url}")
        if crawl_article(filename, url, category):
            ok_count += 1

    print(f"\n[SUMMARY] Crawl thanh cong {ok_count}/{len(ARTICLE_URLS)} bai viet.")


if __name__ == "__main__":
    crawl_all()
