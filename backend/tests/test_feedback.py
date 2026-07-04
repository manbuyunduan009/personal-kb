from pathlib import Path

from app.db import DocumentRepository


def test_feedback_summary_counts_helpful_and_unhelpful(tmp_path: Path):
    repository = DocumentRepository(tmp_path / "kb.sqlite3")

    repository.add_feedback("问题", "a.md", 0, "标题", 1)
    repository.add_feedback("问题", "a.md", 0, "标题", -1)
    repository.add_feedback("问题", "a.md", 0, "标题", 1)

    summary = repository.feedback_summary()

    assert summary[0]["source_path"] == "a.md"
    assert summary[0]["chunk_index"] == 0
    assert summary[0]["helpful_count"] == 2
    assert summary[0]["unhelpful_count"] == 1
    assert summary[0]["feedback_score"] == 1


def test_rag_trace_records_answer_diagnostics(tmp_path: Path):
    repository = DocumentRepository(tmp_path / "kb.sqlite3")

    trace = repository.add_rag_trace(
        question="火星移民方案预算是多少？",
        result={
            "answer": "文档中没有找到依据。",
            "citations": [],
            "self_rag": {
                "status": "insufficient_after_rescue",
                "rescue_attempted": True,
                "rescued": False,
                "rescue_queries": ["火星移民方案预算是多少"],
                "initial_best_score": 0.12,
                "final_best_score": 0.18,
                "min_evidence_score": 0.3,
                "evidence_count": 0,
                "rescue_query_source": "llm",
                "query_rewrite_used_llm": True,
                "query_rewrite_error": "",
                "retrieval_modes": ["hybrid+bm25"],
            },
        },
        latency_ms=1234,
    )

    traces = repository.list_rag_traces()

    assert trace["is_refusal"] is True
    assert traces[0]["question"] == "火星移民方案预算是多少？"
    assert traces[0]["rescue_attempted"] is True
    assert traces[0]["rescued"] is False
    assert traces[0]["final_best_score"] == 0.18
    assert traces[0]["rescue_queries"] == ["火星移民方案预算是多少"]
    assert traces[0]["rescue_query_source"] == "llm"
    assert traces[0]["query_rewrite_used_llm"] is True
    assert traces[0]["query_rewrite_error"] == ""
    assert traces[0]["retrieval_modes"] == ["hybrid+bm25"]
    assert traces[0]["latency_ms"] == 1234


def test_rag_trace_records_cited_titles(tmp_path: Path):
    repository = DocumentRepository(tmp_path / "kb.sqlite3")

    repository.add_rag_trace(
        question="专题验收助手的目标用户是谁？",
        result={
            "answer": "目标用户是产品经理。",
            "citations": [
                {"title": "专题验收助手PRD.md"},
                {"title": "专题验收助手PRD.md"},
                {"title": "补充说明.md"},
            ],
            "self_rag": {
                "status": "sufficient",
                "rescue_attempted": False,
                "rescued": False,
                "rescue_queries": [],
                "initial_best_score": 0.5,
                "final_best_score": 0.5,
                "min_evidence_score": 0.3,
                "evidence_count": 2,
            },
        },
        latency_ms=88,
    )

    trace = repository.list_rag_traces()[0]

    assert trace["is_refusal"] is False
    assert trace["citation_count"] == 3
    assert trace["cited_titles"] == ["专题验收助手PRD.md", "补充说明.md"]
