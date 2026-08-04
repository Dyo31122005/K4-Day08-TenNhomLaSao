# RAG Evaluation Results

## Framework sử dụng

**RAGAS**

## Overall Scores

| Metric | config_a_top5 | config_b_top3 |
|---|---:|---:|
| Faithfulness | 0.799 | 0.913 |
| Answer Relevance | 0.360 | 0.413 |
| Context Recall | 0.986 | 0.942 |
| Context Precision | 1.000 | 1.000 | 
| **Average** | 0.786 | 0.817 |

## A/B Comparison Analysis

- **config_a**: Hybrid retrieval (no rerank) — `retrieve(..., use_reranking=False)`
- **config_b**: Dense-only semantic search (no rerank)

| Metric | Config A | Config B | Δ (A - B) |
|---|---:|---:|---:|
| Hit@5 mean | 1.000 | 0.000 | +1.000 |
| MRR | 1.000 | 0.000 | +1.000 |
| Latency mean (s) | 0.7547 | 0.1532 | +0.6015 |
| Fallback rate | 0.000 | 0.000 | 0.000 |

**Phân tích:**
- Trên 5 test case được chọn, cấu hình hybrid (không rerank) đạt `Hit@5 = 1` và `MRR = 1.0`, trong khi dense-only không tìm được kết quả phù hợp ở top 5.
- `Config B` có latency thấp hơn đáng kể, nhưng hiệu quả relevance thực tế vẫn kém hơn so với hybrid trên tập test này.
- Cả hai cấu hình đều không cần fallback PageIndex trong 5 case này.

**Kết luận:** Với đánh giá 5 case hiện tại, hybrid retrieval không rerank có ưu thế rõ ràng về độ chính xác truy vấn, còn dense-only chỉ có ưu thế về tốc độ. Để đánh giá đầy đủ hơn, nên mở rộng số lượng trường hợp và tiếp tục kiểm tra tính hợp lệ của metric relevance.

## Worst Performers (Bottom 3)

| # | Config | Question | Faithfulness | Relevance | Recall | Precision |
|---:|---|---|---:|---:|---:|---:|
| 1 | config_b_top3 | Shopee sử dụng dữ liệu cá nhân của người dùng cho những mục đích chính nào? | 1.000 | 0.000 | 0.000 | 1.000 |
| 2 | config_a_top5 | Người bán không được đăng bán những sản phẩm nào? | 0.000 | 0.000 | 1.000 | 1.000 |
| 3 | config_a_top5 | Shopee có thể chia sẻ dữ liệu cá nhân với những bên nào? | 0.000 | 0.000 | 1.000 | 1.000 |

## Recommendations

1. Kiểm tra chunks của ba câu có điểm thấp nhất và điều chỉnh chunking/metadata filter.
2. Chọn `top_k` dựa trên cả context recall và context precision để tránh context thừa.
3. Siết prompt sinh câu trả lời nếu faithfulness hoặc answer relevance là điểm yếu chính.
