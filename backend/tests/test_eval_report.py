from scripts.eval_report import (
    build_comparison,
    evaluate_chat_case,
    evaluate_search_case,
    format_text_report,
    load_report,
    parse_args,
    rate,
    save_report,
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
            "citation_check_status": "supported",
            "citation_support_score": 0.8,
            "latency_ms": 100,
        },
        {
            "self_rag_status": "insufficient_after_rescue",
            "is_refusal": True,
            "rescue_attempted": True,
            "rescued": False,
            "query_rewrite_used_llm": True,
            "retrieval_modes": ["hybrid+bm25"],
            "citation_check_status": "warning",
            "citation_support_score": 0.2,
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
    assert summary["recent_trace_llm_rewrite_rate"] == 0.5
    assert summary["recent_trace_retrieval_mode_distribution"] == {"hybrid+bm25": 1}
    assert summary["recent_trace_citation_check_distribution"] == {"supported": 1, "warning": 1}
    assert summary["recent_trace_citation_check_applicable_count"] == 2
    assert summary["recent_trace_citation_check_risk_count"] == 1
    assert summary["recent_trace_citation_check_risk_rate"] == 0.5
    assert summary["recent_trace_avg_citation_support_score"] == 0.5
    assert summary["recent_trace_avg_latency_ms"] == 200


def test_build_comparison_calculates_core_metric_deltas():
    baseline = {
        "generated_at": "2026-07-04T01:00:00+00:00",
        "summary": {
            "search_pass_rate": 0.8,
            "chat_pass_rate": 0.75,
            "refusal_rate": 0.25,
            "rescue_rate": 0.5,
            "avg_latency_ms": 1200,
            "api_failure_count": 2,
        },
    }
    current = {
        "generated_at": "2026-07-04T02:00:00+00:00",
        "summary": {
            "search_pass_rate": 1.0,
            "chat_pass_rate": 0.5,
            "refusal_rate": 0.5,
            "rescue_rate": 0.25,
            "avg_latency_ms": 900,
            "api_failure_count": 0,
        },
    }

    comparison = build_comparison(current, baseline, "reports/baseline.json")

    assert comparison["baseline_path"] == "reports/baseline.json"
    assert comparison["baseline_generated_at"] == "2026-07-04T01:00:00+00:00"
    assert comparison["metrics"]["search_pass_rate"]["delta"] == 0.2
    assert comparison["metrics"]["chat_pass_rate"]["delta"] == -0.25
    assert comparison["metrics"]["refusal_rate"]["delta"] == 0.25
    assert comparison["metrics"]["rescue_rate"]["delta"] == -0.25
    assert comparison["metrics"]["avg_latency_ms"]["delta"] == -300
    assert comparison["metrics"]["api_failure_count"]["delta"] == -2


def test_save_and_load_report_round_trip(tmp_path):
    path = tmp_path / "nested" / "eval-report.json"
    report = {
        "generated_at": "2026-07-04T02:00:00+00:00",
        "summary": {"search_pass_rate": 1.0},
    }

    save_report(report, str(path))
    loaded = load_report(str(path))

    assert loaded == report


def test_parse_args_accepts_save_and_compare_paths():
    args = parse_args(
        [
            "--save",
            "backend/reports/current.json",
            "--compare",
            "backend/reports/baseline.json",
        ]
    )

    assert args.save == "backend/reports/current.json"
    assert args.compare == "backend/reports/baseline.json"


def test_format_text_report_includes_comparison_section():
    baseline = {
        "generated_at": "2026-07-04T01:00:00+00:00",
        "summary": {
            "search_pass_rate": 0.5,
            "chat_pass_rate": 0.5,
            "refusal_rate": 0.0,
            "rescue_rate": 0.0,
            "avg_latency_ms": 1000,
            "api_failure_count": 1,
        },
    }
    report = {
        "base_url": "http://127.0.0.1:8000",
        "generated_at": "2026-07-04T02:00:00+00:00",
        "summary": {
            "search_total": 1,
            "search_passed": 1,
            "search_pass_rate": 1.0,
            "chat_total": 1,
            "chat_passed": 1,
            "chat_pass_rate": 1.0,
            "refusal_count": 0,
            "refusal_rate": 0.0,
            "rescue_attempted_count": 0,
            "rescued_count": 0,
            "rescue_rate": 0.0,
            "avg_latency_ms": 800,
            "api_failure_count": 0,
            "recent_trace_total": 0,
            "recent_trace_status_distribution": {},
            "recent_trace_refusal_rate": 0.0,
            "recent_trace_rescue_rate": 0.0,
            "recent_trace_llm_rewrite_rate": 0.0,
            "recent_trace_retrieval_mode_distribution": {},
            "recent_trace_citation_check_distribution": {},
            "recent_trace_citation_check_applicable_count": 0,
            "recent_trace_citation_check_risk_count": 0,
            "recent_trace_citation_check_risk_rate": 0.0,
            "recent_trace_avg_citation_support_score": 0.0,
            "recent_trace_avg_latency_ms": 0,
            "trace_error": "",
        },
        "search_cases": [],
        "chat_cases": [],
    }
    report["comparison"] = build_comparison(report, baseline, "baseline.json")

    text = format_text_report(report)

    assert "Comparison:" in text
    assert "search_pass_rate: 50.0% -> 100.0% (+50.0pp)" in text
    assert "avg_latency_ms: 1000ms -> 800ms (-200ms)" in text
