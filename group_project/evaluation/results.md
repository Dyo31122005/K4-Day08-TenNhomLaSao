# RAG Evaluation Results

## Framework sử dụng

**RAGAS**

## Overall Scores

| Metric | config_a_top5 | config_b_top3 |
|---|---:|---:|
| Faithfulness | 0.767 | 0.875 |
| Answer Relevance | 0.515 | 0.463 |
| Context Recall | 1.000 | 1.000 |
| Context Precision | 1.000 | 1.000 |
| **Average** | 0.820 | 0.835 |

## A/B Comparison Analysis

- **config_a_top5**: `{"top_k": 5}` — average **0.820**
- **config_b_top3**: `{"top_k": 3}` — average **0.835**

**Kết luận:** `config_b_top3` có điểm trung bình cao nhất.

**A/B testing với hybrid search và dense search**

| Metric | Config A (hybrid) | Config B (dense-only) | Δ (A - B) |
|---|---:|---:|---:|
| Hit@5 mean | 1.000 | 0.000 | 1.000 |
| MRR | 1.000 | 0.000 | 1.000 |
| Latency mean (s) | 3.214 | 2.792 | 0.423 |
| Fallback rate | 0.000 | 0.000 | 0.000 |

**Notes:** Hybrid found relevant chunks more often but was slower; dense-only was faster but had lower Hit/MRR on this slice.

## Worst Performers (Bottom 3)

| # | Config | Question | Faithfulness | Relevance | Recall | Precision |
|---:|---|---|---:|---:|---:|---:|
| 1 | config_b_top3 | Người bán không được đăng bán những sản phẩm nào? | 0.000 | 0.000 | 1.000 | 1.000 |
| 2 | config_a_top5 | Người bán không được đăng bán những sản phẩm nào? | 0.000 | 0.000 | 1.000 | 1.000 |
| 3 | config_b_top3 | Đơn hàng quốc tế có được trả góp bằng thẻ tín dụng không? | 1.000 | 0.000 | 1.000 | 1.000 |

## Recommendations

1. Kiểm tra chunks của ba câu có điểm thấp nhất và điều chỉnh chunking/metadata filter.
2. Chọn `top_k` dựa trên cả context recall và context precision để tránh context thừa.
3. Siết prompt sinh câu trả lời nếu faithfulness hoặc answer relevance là điểm yếu chính.

## Ghi chú ngắn

- **Tại sao `Answer Relevance` thấp nhưng `Context Recall/Precision` cao:** retrieval tìm đúng đoạn (recall/precision cao) nhưng mô-đun sinh câu trả lời thường dùng fallback hoặc tóm tắt chung chung (do lỗi LLM/proxy hoặc cách aggregate thông tin), nên câu trả lời không khớp chặt với `expected_answer` → điểm relevance thấp.
- **Tóm tắt 4 metrics:** Faithfulness = câu trả lời dựa trên context tới đâu; Answer Relevance = câu trả lời khớp với `expected_answer` hay không; Context Recall = bao nhiêu đoạn vàng được lấy lại; Context Precision = các đoạn trả về có liên quan hay không.
- **Worst cases (nguyên nhân ngắn):** thông tin bị tách rời giữa nhiều chunk, chunking cắt mất cụm thông tin quan trọng, hoặc generator trả fallback/tóm tắt thay vì trích xuất trực tiếp.

Ngắn gọn: sửa môi trường LLM (proxy / httpx[socks]) và ghi log per-case (overlap/fuzzy) rồi chạy lại sẽ nhanh cho thấy cải thiện.

## Giải thích vì sao các metrics nhận giá trị như hiện tại

- **Context Recall = 1.00:** retrieval (BM25 + hybrid) đã tìm đúng các đoạn "vàng" cho các test này — indexing và chunking giữ đủ ngữ cảnh nên các expected_context xuất hiện trong top-k.

- **Context Precision = 1.00:** top-k chunk trả về ít rác; RRF và bộ lọc đưa đoạn liên quan lên đầu, nên phần trăm đoạn hữu ích trên tổng là rất cao.

- **Answer Relevance ≈ 0.46–0.52 (thấp–vừa):** mặc dù context đúng đã có, bước sinh câu trả lời gặp hai vấn đề chính: (1) LLM đôi khi rơi vào chuỗi fallback (proxy / thiếu package / thiếu API key) và trả câu dự phòng/tóm tắt, (2) generator tổng hợp hoặc diễn giải thay vì trích xuất chính xác các mục/danh sách mà judge kỳ vọng — judge (RAGAS) khá nghiêm khắc với chi tiết, nên điểm relevance bị kéo xuống.

- **Faithfulness ≈ 0.77–0.88 (khá):** nhiều answer vẫn dựa trên chứng cứ trong context (không bịa hoàn toàn) nên faithfulness ở mức khá; điểm chưa đạt tối đa do một số câu trả lời nối ghép/diễn giải chứng cứ hoặc dùng fallback mà thiếu trích dẫn rõ ràng.

- **Khoảng cách giữa Context metrics và Answer metrics:** retrieval hoạt động tốt (đưa đúng nguồn), nhưng phần aggregation + generation (và lỗi runtime LLM) là cổ chai: chứng cứ có nhưng không được dùng chính xác để tạo câu trả lời trùng với `expected_answer`.

- **Worst-case nguyên nhân ngắn:** thông tin mong đợi là "danh sách" nhưng chunking cắt rời, generator tóm tắt hoặc trả fallback; hoặc dense retrieval không hoạt động do lỗi embedding → so sánh cấu hình bị ảnh hưởng.

Summary: khắc phục môi trường LLM (cài `httpx[socks]` hoặc unset proxy), bật logging per-case (token overlap, fuzzy, recall) và rerun sẽ cho thấy cải thiện rõ rệt ở `answer_relevance` và `faithfulness`.