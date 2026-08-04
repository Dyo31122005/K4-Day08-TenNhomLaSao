# RAG Evaluation Results

## Framework sử dụng

**RAGAS**

## Overall Scores

| Metric | config_a_top5 | config_b_top3 |
|---|---:|---:|
| Faithfulness | 0.726 | 0.804 |
| Answer Relevance | 0.288 | 0.334 |
| Context Recall | 0.889 | 0.863 |
| Context Precision | 0.852 | 0.852 |
| **Average** | 0.689 | 0.713 |

## A/B Comparison Analysis

- **config_a_top5**: `{"top_k": 5}` — average **0.689**
- **config_b_top3**: `{"top_k": 3}` — average **0.713**

**Kết luận:** `config_b_top3` có điểm trung bình cao nhất.

## Worst Performers (Bottom 3)

| # | Config | Question | Faithfulness | Relevance | Recall | Precision |
|---:|---|---|---:|---:|---:|---:|
| 1 | config_a_top5 | Ngày mai thời tiết ở Hà Nội có mưa không? | 0.000 | 0.000 | 0.000 | 0.000 |
| 2 | config_a_top5 | Trong Python, sự khác nhau giữa list và tuple là gì? | 0.000 | 0.000 | 0.000 | 0.000 |
| 3 | config_a_top5 | So sánh camera của iPhone và Samsung giúp tôi. | 0.000 | 0.000 | 0.000 | 0.000 |

## Recommendations

1. Kiểm tra chunks của ba câu có điểm thấp nhất và điều chỉnh chunking/metadata filter.
2. Chọn `top_k` dựa trên cả context recall và context precision để tránh context thừa.
3. Siết prompt sinh câu trả lời nếu faithfulness hoặc answer relevance là điểm yếu chính.
