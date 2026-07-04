from scripts.eval_report import (
    evaluate_chat_case,
    evaluate_search_case,
    rate,
    summarize_results,
)


def test_rate_handles_zero_denominator():
    assert rate(1, 0) == 0.0
    assert rate(1, 4) == 0.25


def test_evaluate_search_case_passes_when_expected_title_is_returned():
    case = {"question": "Who is the user?", "expected_title": "prd.md"}
    response = {
        "results": [
            {"metadata": {"title": "notes.md"}},
            {"metadata": {"title": "prd.md"}},
        ]
    }

    record = evaluate_search_case(case, response, latency_ms=12)

    assert record["ok"] is True
    assert record["passed"] is True
    assert record["top_titles"] == ["notes.md", "prd.md"]


def test_evaluate_chat_case_passes_no_evidence_refusal_with_rescue_attempt():
    case = {
        "question": "What is the Mars budget?",
        "expect_no_evidence": True,
        "expect_rescue_attempted": True,
    }
    response = {
        "answer": "No enough evidence.",
        "citations": [],
        "self_rag": {
            "status": "insufficient_after_rescue",
            "rescue_attempted": True,
            "rescued": False,
        },
    }

    record = evaluate_chat_case(case, response, latency_ms=30)

    assert record["passed"] is True
    assert record["is_refusal"] is True
    assert record["rescue_attempted"] is True
    assert record["rescued"] is False


def test_summarize_results_counts_pass_rates_failures_and_traces():
    search_records = [
        {"kind": "search", "ok": True, "passed": True, "latency_ms": 10},
        {"kind": "search", "ok": False, "passed": False, "latency_ms": 5, "error": "down"},
    ]
    chat_records = [
        {
            "kind": "chat",
            "ok": True,
            "passed": True,
            "is_refusal": False,
            "rescue_attempted": False,
            "rescued": False,
            "latency_ms": 50,
        },
        {
            "kind": "chat",
            "ok": True,
            "passed": True,
            "is_refusal": True,
            "rescue_attempted": True,
            "rescued": False,
            "latency_ms": 70,
        },
    ]
    traces = [
        {
            "self_rag_status": "sufficient",
            "is_refusal": False,
            "rescue_attempted": False,
            "rescued": False,
            "latency_ms": 100,
        },
        {
            "self_rag_status": "insufficient_after_rescue",
            "is_refusal": True,
            "rescue_attempted": True,
            "rescued": False,
            "latency_ms": 300,
        },
    ]

    summary = summarize_results(search_records, chat_records, traces)

    assert summary["search_pass_rate"] == 0.5
    assert summary["chat_pass_rate"] == 1.0
    assert summary["refusal_rate"] == 0.5
    assert summary["rescue_rate"] == 0.0
    assert summary["avg_latency_ms"] == 43
    assert summary["api_failure_count"] == 1
    assert summary["recent_trace_status_distribution"] == {
        "insufficient_after_rescue": 1,
        "sufficient": 1,
    }
    assert summary["recent_trace_avg_latency_ms"] == 200
