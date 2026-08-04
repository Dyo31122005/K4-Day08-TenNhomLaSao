"""
RAG Evaluation Pipeline.

Sử dụng DeepEval / RAGAS / TruLens để đánh giá chất lượng RAG pipeline.
Chọn 1 framework và implement đầy đủ.

Yêu cầu:
    1. Load golden_dataset.json (≥15 Q&A pairs)
    2. Chạy RAG pipeline trên từng question
    3. Evaluate với 4 metrics: faithfulness, relevance, context_recall, context_precision
    4. So sánh A/B ít nhất 2 configs
    5. Export results ra results.md

Lưu ý rate limit nếu dùng model OpenRouter ":free": RAGAS/DeepEval gọi LLM RẤT NHIỀU LẦN
(không phải 1 lần/câu hỏi mà nhiều lần/metric/câu hỏi). Model free của OpenRouter giới hạn
50 request/ngày CHO CẢ TÀI KHOẢN (không phải theo model hay theo API key — đổi model free
khác hay tạo key mới KHÔNG reset quota). Nếu chạy full 15+ câu hỏi mà bị rate limit giữa
chừng, thử giảm xuống subset 5 câu để chạy kịp trong buổi, hoặc nạp $10 credit để mở khóa
1000 request/ngày.
"""

import inspect
import json
import math
import os
from collections.abc import Mapping
from pathlib import Path
from statistics import mean
from typing import Any

from dotenv import load_dotenv

load_dotenv()

GOLDEN_DATASET_PATH = Path(__file__).parent / "golden_dataset.json"
RESULTS_PATH = Path(__file__).parent / "results.md"
METRIC_NAMES = ("faithfulness", "answer_relevance", "context_recall", "context_precision")


def load_golden_dataset() -> list[dict]:
    """Load golden dataset từ JSON file."""
    with open(GOLDEN_DATASET_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    if not isinstance(dataset, list) or len(dataset) < 15:
        raise ValueError("Golden dataset phải là JSON array có ít nhất 15 Q&A pairs")
    required = {"question", "expected_answer", "expected_context"}
    for index, item in enumerate(dataset, 1):
        if not isinstance(item, dict) or not required.issubset(item):
            missing = required - set(item if isinstance(item, dict) else {})
            raise ValueError(f"Test case #{index} không hợp lệ; thiếu: {sorted(missing)}")
    return dataset


def _pipeline_function(rag_pipeline):
    function = getattr(rag_pipeline, "generate_with_citation", rag_pipeline)
    if not callable(function):
        raise TypeError("rag_pipeline phải callable hoặc có generate_with_citation()")
    return function


def _run_pipeline(rag_pipeline, question: str, config: dict | None = None) -> dict:
    function = _pipeline_function(rag_pipeline)
    kwargs = dict(config or {})
    try:
        signature = inspect.signature(function)
        if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()):
            kwargs = {key: value for key, value in kwargs.items() if key in signature.parameters}
    except (TypeError, ValueError):
        pass
    output = function(question, **kwargs)
    if isinstance(output, str):
        output = {"answer": output, "sources": []}
    if not isinstance(output, Mapping) or "answer" not in output:
        raise ValueError("RAG pipeline phải trả về str hoặc dict có key 'answer'")
    contexts = []
    for source in output.get("sources") or output.get("contexts") or []:
        if isinstance(source, str):
            contexts.append(source)
        elif isinstance(source, Mapping):
            content = source.get("content") or source.get("text") or source.get("page_content")
            if content:
                contexts.append(str(content))
    return {"answer": str(output["answer"]), "contexts": contexts}


def _number(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _normalise_ragas_result(generated: list[dict], evaluated) -> dict:
    records = evaluated.to_pandas().to_dict(orient="records")
    details = []
    for row, record in zip(generated, records):
        scores = {
            "faithfulness": _number(record.get("faithfulness")),
            "answer_relevance": _number(record.get("answer_relevancy", record.get("answer_relevance"))),
            "context_recall": _number(record.get("context_recall")),
            "context_precision": _number(record.get("context_precision")),
        }
        valid = [value for value in scores.values() if value is not None]
        details.append({**row, **scores, "average": mean(valid) if valid else None})
    overall = {}
    for metric in METRIC_NAMES:
        values = [row[metric] for row in details if row[metric] is not None]
        overall[metric] = mean(values) if values else None
    valid = [value for value in overall.values() if value is not None]
    overall["average"] = mean(valid) if valid else None
    return {"framework": "RAGAS", "overall": overall, "details": details}


def _ragas_models():
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    api_key = os.getenv("RAGAS_API_KEY") or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Thiếu RAGAS_API_KEY, OPENROUTER_API_KEY hoặc OPENAI_API_KEY")
    base_url = os.getenv("RAGAS_BASE_URL")
    if not base_url and os.getenv("OPENROUTER_API_KEY"):
        base_url = "https://openrouter.ai/api/v1"
    common = {"api_key": api_key}
    if base_url:
        common["base_url"] = base_url
    judge_model = os.getenv("RAGAS_JUDGE_MODEL", "openai/gpt-4o-mini" if base_url else "gpt-4o-mini")
    embedding_model = os.getenv("RAGAS_EMBEDDING_MODEL", "openai/text-embedding-3-small" if base_url else "text-embedding-3-small")
    return (
        ChatOpenAI(model=judge_model, temperature=0, **common),
        OpenAIEmbeddings(model=embedding_model, **common),
    )


# =============================================================================
# Option 1: DeepEval
# =============================================================================

def evaluate_with_deepeval(rag_pipeline, golden_dataset: list[dict]) -> dict:
    """
    Evaluate RAG pipeline sử dụng DeepEval.

    pip install deepeval
    """
    # TODO: Implement
    #
    # from deepeval import evaluate
    # from deepeval.metrics import (
    #     FaithfulnessMetric,
    #     AnswerRelevancyMetric,
    #     ContextualRecallMetric,
    #     ContextualPrecisionMetric,
    # )
    # from deepeval.test_case import LLMTestCase
    #
    # test_cases = []
    # for item in golden_dataset:
    #     result = rag_pipeline.generate_with_citation(item["question"])
    #     test_case = LLMTestCase(
    #         input=item["question"],
    #         actual_output=result["answer"],
    #         expected_output=item["expected_answer"],
    #         retrieval_context=[c["content"] for c in result["sources"]],
    #     )
    #     test_cases.append(test_case)
    #
    # metrics = [
    #     FaithfulnessMetric(threshold=0.7),
    #     AnswerRelevancyMetric(threshold=0.7),
    #     ContextualRecallMetric(threshold=0.7),
    #     ContextualPrecisionMetric(threshold=0.7),
    # ]
    #
    # results = evaluate(test_cases, metrics)
    # return results
    from deepeval import evaluate
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        ContextualPrecisionMetric,
        ContextualRecallMetric,
        FaithfulnessMetric,
    )
    from deepeval.test_case import LLMTestCase

    test_cases = []
    for item in golden_dataset:
        result = rag_pipeline.generate_with_citation(item["question"])
        test_cases.append(
            LLMTestCase(
                input=item["question"],
                actual_output=result["answer"],
                expected_output=item["expected_answer"],
                retrieval_context=[source["content"] for source in result["sources"]],
            )
        )

    metrics = [
        FaithfulnessMetric(threshold=0.7),
        AnswerRelevancyMetric(threshold=0.7),
        ContextualRecallMetric(threshold=0.7),
        ContextualPrecisionMetric(threshold=0.7),
    ]
    return evaluate(test_cases, metrics)


# =============================================================================
# Option 2: RAGAS
# =============================================================================

def evaluate_with_ragas(rag_pipeline, golden_dataset: list[dict]) -> dict:
    """
    Evaluate RAG pipeline sử dụng RAGAS.

    pip install ragas
    """
    # TODO: Implement
    #
    # from ragas import evaluate
    # from ragas.metrics import (
    #     faithfulness,
    #     answer_relevancy,
    #     context_recall,
    #     context_precision,
    # )
    # from datasets import Dataset
    #
    # eval_data = {"question": [], "answer": [], "contexts": [], "ground_truth": []}
    #
    # for item in golden_dataset:
    #     result = rag_pipeline.generate_with_citation(item["question"])
    #     eval_data["question"].append(item["question"])
    #     eval_data["answer"].append(result["answer"])
    #     eval_data["contexts"].append([c["content"] for c in result["sources"]])
    #     eval_data["ground_truth"].append(item["expected_answer"])
    #
    # dataset = Dataset.from_dict(eval_data)
    # result = evaluate(
    #     dataset,
    #     metrics=[faithfulness, answer_relevancy, context_recall, context_precision],
    # )
    # return result.to_pandas()
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
    except ImportError as exc:
        raise RuntimeError("Chạy: pip install ragas datasets langchain-openai") from exc

    if not golden_dataset:
        raise ValueError("golden_dataset không được rỗng")
    generated = []
    for index, item in enumerate(golden_dataset, 1):
        output = _run_pipeline(rag_pipeline, item["question"])
        generated.append({"id": item.get("id", f"case_{index:02d}"), "question": item["question"],
                          "answer": output["answer"], "contexts": output["contexts"],
                          "ground_truth": item["expected_answer"]})
    dataset = Dataset.from_dict({key: [row[key] for row in generated]
                                 for key in ("question", "answer", "contexts", "ground_truth")})
    judge_llm, embeddings = _ragas_models()
    evaluated = evaluate(dataset,
                         metrics=[faithfulness, answer_relevancy, context_recall, context_precision],
                         llm=judge_llm, embeddings=embeddings, raise_exceptions=False)
    return _normalise_ragas_result(generated, evaluated)


# =============================================================================
# Option 3: TruLens
# =============================================================================

def evaluate_with_trulens(rag_pipeline, golden_dataset: list[dict]) -> dict:
    """
    Evaluate RAG pipeline sử dụng TruLens.

    pip install trulens
    """
    # TODO: Implement
    #
    # from trulens.apps.custom import TruCustomApp
    # from trulens.core import Feedback
    # from trulens.providers.openai import OpenAI as TruOpenAI
    #
    # provider = TruOpenAI()
    #
    # f_faithfulness = Feedback(provider.groundedness_measure_with_cot_reasons).on_output()
    # f_relevance = Feedback(provider.relevance).on_input_output()
    # f_context_relevance = Feedback(provider.context_relevance).on_input()
    #
    # tru_rag = TruCustomApp(
    #     rag_pipeline,
    #     app_name="EcommerceSupport_RAG",
    #     feedbacks=[f_faithfulness, f_relevance, f_context_relevance],
    # )
    #
    # with tru_rag as recording:
    #     for item in golden_dataset:
    #         rag_pipeline.generate_with_citation(item["question"])
    #
    # # Dashboard: from trulens.dashboard import run_dashboard; run_dashboard()
    raise RuntimeError("Project đã chọn RAGAS; hãy gọi evaluate_with_ragas()")


# =============================================================================
# A/B Comparison
# =============================================================================

def compare_configs(rag_pipeline, golden_dataset: list[dict]):
    """
    So sánh A/B giữa ít nhất 2 configs.

    Gợi ý configs để so sánh:
    - Config A: hybrid search + reranking
    - Config B: dense-only (không reranking)
    - Config C: hybrid search + PageIndex fallback
    """
    # TODO: Implement A/B comparison
    #
    # configs = {
    #     "hybrid_rerank": {"use_reranking": True, "alpha": 0.5},
    #     "dense_only": {"use_reranking": False, "alpha": 1.0},
    # }
    #
    # results = {}
    # for config_name, params in configs.items():
    #     # Run eval with this config
    #     ...
    #     results[config_name] = scores
    #
    # return results
    configs = {"config_a_top5": {"top_k": 5}, "config_b_top3": {"top_k": 3}}
    comparison = {}
    for config_name, params in configs.items():
        def configured_pipeline(question, _params=params):
            return _run_pipeline(rag_pipeline, question, _params)

        comparison[config_name] = {"config": dict(params),
                                   **evaluate_with_ragas(configured_pipeline, golden_dataset)}
    return comparison


# =============================================================================
# Export Results
# =============================================================================

def export_results(results: dict, comparison: dict):
    """Export evaluation results to results.md"""
    # TODO: Format and write results
    #
    # content = "# RAG Evaluation Results\n\n"
    # content += "## Overall Scores\n\n"
    # content += "| Metric | Score |\n|--------|-------|\n"
    # ...
    # content += "\n## A/B Comparison\n\n"
    # ...
    # content += "\n## Worst Performers\n\n"
    # ...
    # content += "\n## Recommendations\n\n"
    # ...
    #
    # RESULTS_PATH.write_text(content, encoding="utf-8")
    runs = comparison or {"default": results}
    names = list(runs)

    def fmt(value):
        value = _number(value)
        return "N/A" if value is None else f"{value:.3f}"

    def cell(value, limit=160):
        text = str(value).replace("|", "\\|").replace("\n", " ").strip()
        return text if len(text) <= limit else text[:limit - 1] + "…"

    lines = ["# RAG Evaluation Results", "", "## Framework sử dụng", "",
             f"**{results.get('framework', 'RAGAS')}**", "", "## Overall Scores", "",
             "| Metric | " + " | ".join(cell(name) for name in names) + " |",
             "|---|" + "---:|" * len(names)]
    labels = {"faithfulness": "Faithfulness", "answer_relevance": "Answer Relevance",
              "context_recall": "Context Recall", "context_precision": "Context Precision",
              "average": "**Average**"}
    for metric in (*METRIC_NAMES, "average"):
        lines.append(f"| {labels[metric]} | " + " | ".join(
            fmt(runs[name].get("overall", {}).get(metric)) for name in names) + " |")
    ranked = sorted(runs.items(), key=lambda item: _number(item[1].get("overall", {}).get("average")) or -1,
                    reverse=True)
    lines += ["", "## A/B Comparison Analysis", ""]
    for name, run in runs.items():
        params = json.dumps(run.get("config", {}), ensure_ascii=False)
        lines.append(f"- **{cell(name)}**: `{params}` — average **{fmt(run.get('overall', {}).get('average'))}**")
    if ranked:
        lines += ["", f"**Kết luận:** `{cell(ranked[0][0])}` có điểm trung bình cao nhất."]
    details = []
    for name, run in runs.items():
        details.extend({**row, "config": name} for row in run.get("details", []))
    worst = sorted(details, key=lambda row: row.get("average") if row.get("average") is not None else float("inf"))[:3]
    lines += ["", "## Worst Performers (Bottom 3)", "",
              "| # | Config | Question | Faithfulness | Relevance | Recall | Precision |",
              "|---:|---|---|---:|---:|---:|---:|"]
    for index, row in enumerate(worst, 1):
        lines.append(f"| {index} | {cell(row.get('config', ''))} | {cell(row.get('question', ''))} | "
                     f"{fmt(row.get('faithfulness'))} | {fmt(row.get('answer_relevance'))} | "
                     f"{fmt(row.get('context_recall'))} | {fmt(row.get('context_precision'))} |")
    lines += ["", "## Recommendations", "",
              "1. Kiểm tra chunks của ba câu có điểm thấp nhất và điều chỉnh chunking/metadata filter.",
              "2. Chọn `top_k` dựa trên cả context recall và context precision để tránh context thừa.",
              "3. Siết prompt sinh câu trả lời nếu faithfulness hoặc answer relevance là điểm yếu chính.", ""]
    RESULTS_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    golden_dataset = load_golden_dataset()
    print(f"Loaded {len(golden_dataset)} test cases")

    # TODO: Import your RAG pipeline
    # from src.task10_generation import generate_with_citation
    #
    # Chọn 1 framework:
    # results = evaluate_with_deepeval(pipeline, golden_dataset)
    # results = evaluate_with_ragas(pipeline, golden_dataset)
    # results = evaluate_with_trulens(pipeline, golden_dataset)
    #
    # comparison = compare_configs(pipeline, golden_dataset)
    # export_results(results, comparison)
    from src.task10_generation import generate_with_citation

    limit = int(os.getenv("RAG_EVAL_LIMIT", "0"))
    evaluation_dataset = golden_dataset[:limit] if limit > 0 else golden_dataset
    comparison = compare_configs(generate_with_citation, evaluation_dataset)
    results = comparison["config_a_top5"]
    export_results(results, comparison)
    print(f"Evaluated {len(evaluation_dataset)} test cases; exported {RESULTS_PATH}")
