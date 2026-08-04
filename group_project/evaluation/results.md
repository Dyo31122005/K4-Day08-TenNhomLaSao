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

- **config_a_top5**: `{"top_k": 5}` — average **0.786**
- **config_b_top3**: `{"top_k": 3}` — average **0.817**

**Kết luận:** `config_b_top3` có điểm trung bình cao nhất.

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
