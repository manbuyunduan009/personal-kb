import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from eval_retrieval import CASES as SEARCH_CASES
    from eval_retrieval import CHAT_CASES
except ImportError:  # pragma: no cover - used when imported as scripts.eval_report
    from .eval_retrieval import CASES as SEARCH_CASES
    from .eval_retrieval import CHAT_CASES


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
COMPARISON_METRICS = (
    ("search_pass_rate", "rate"),
    ("chat_pass_rate", "rate"),
    ("refusal_rate", "rate"),
    ("rescue_rate", "rate"),
    ("recent_trace_citation_check_risk_rate", "rate"),
    ("recent_trace_avg_citation_support_score", "score"),
    ("avg_latency_ms", "ms"),
    ("api_failure_count", "count"),
)
REFUSAL_MARKERS = (
    "文档中没有找到依据",
    "没有找到依据",
    "insufficient evidence",
    "insufficient",
)


def rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def average_ms(values: Iterable[Any]) -> int:
    numbers = [int(value) for value in values if value is not None]
    if not numbers:
        return 0
    return int(round(sum(numbers) / len(numbers)))


def average_float(values: Iterable[Any]) -> float:
    numbers = []
    for value in values:
        if value is None:
            continue
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            continue
    if not numbers:
        return 0.0
    return round(sum(numbers) / len(numbers), 4)


def request_json(
    base_url: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 60,
    query: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], int, str]:
    url = base_url.rstrip("/") + path
    if query:
        url = "%s?%s" % (url, urllib.parse.urlencode(query))

    data = None
    method = "GET"
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        method = "POST"
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            latency_ms = int((time.perf_counter() - started) * 1000)
            body = response.read().decode("utf-8")
            return json.loads(body), latency_ms, ""
    except urllib.error.HTTPError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        detail = exc.read().decode("utf-8", errors="replace")
        return None, latency_ms, "HTTP %s %s: %s" % (exc.code, exc.reason, detail[:300])
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return None, latency_ms, str(exc)


def metadata_titles(items: Iterable[Dict[str, Any]]) -> List[str]:
    titles = []
    for item in items:
        metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
        title = str(metadata.get("title", ""))
        if title:
            titles.append(title)
    return titles


def citation_titles(citations: Iterable[Dict[str, Any]]) -> List[str]:
    titles = []
    for citation in citations:
        if isinstance(citation, dict):
            title = str(citation.get("title", ""))
            if title:
                titles.append(title)
    return titles


def is_refusal_response(response: Dict[str, Any]) -> bool:
    citations = response.get("citations", [])
    self_rag = response.get("self_rag", {})
    status = ""
    if isinstance(self_rag, dict):
        status = str(self_rag.get("status", ""))
    answer = str(response.get("answer", "")).lower()
    has_refusal_text = any(marker.lower() in answer for marker in REFUSAL_MARKERS)
    return status.startswith("insufficient") or (not citations and has_refusal_text)


def evaluate_search_case(case: Dict[str, Any], response: Optional[Dict[str, Any]], latency_ms: int, error: str = ""):
    results = response.get("results", []) if isinstance(response, dict) else []
    titles = metadata_titles(results)
    expected_title = str(case.get("expected_title", ""))
    ok = not error
    passed = ok and expected_title in titles
    return {
        "kind": "search",
        "question": case.get("question", ""),
        "expected_title": expected_title,
        "ok": ok,
        "passed": passed,
        "latency_ms": latency_ms,
        "error": error,
        "result_count": len(results),
        "top_titles": titles[:5],
    }


def evaluate_chat_case(case: Dict[str, Any], response: Optional[Dict[str, Any]], latency_ms: int, error: str = ""):
    response = response if isinstance(response, dict) else {}
    citations = response.get("citations", []) if isinstance(response.get("citations", []), list) else []
    citation_check = response.get("citation_check", {})
    citation_check = citation_check if isinstance(citation_check, dict) else {}
    titles = citation_titles(citations)
    self_rag = response.get("self_rag", {}) if isinstance(response.get("self_rag", {}), dict) else {}
    is_refusal = is_refusal_response(response)
    rescue_attempted = bool(self_rag.get("rescue_attempted", False))
    rescued = bool(self_rag.get("rescued", False))
    expected_title = str(case.get("expected_title", ""))

    ok = not error
    if case.get("expect_no_evidence"):
        passed = ok and is_refusal and not citations
    else:
        passed = ok and expected_title in titles
    if case.get("expect_rescue_attempted") and not rescue_attempted:
        passed = False

    return {
        "kind": "chat",
        "question": case.get("question", ""),
        "expected_title": expected_title,
        "expect_no_evidence": bool(case.get("expect_no_evidence", False)),
        "ok": ok,
        "passed": passed,
        "latency_ms": latency_ms,
        "error": error,
        "answer_preview": str(response.get("answer", "")).replace("\n", " ")[:180],
        "citation_count": len(citations),
        "citation_titles": titles[:5],
        "citation_check_status": str(citation_check.get("status", "")),
        "citation_support_score": citation_check.get("support_score", 0.0),
        "citation_checked_claim_count": citation_check.get("checked_claim_count", 0),
        "self_rag_status": str(self_rag.get("status", "")),
        "is_refusal": is_refusal,
        "rescue_attempted": rescue_attempted,
        "rescued": rescued,
        "initial_best_score": self_rag.get("initial_best_score", 0.0),
        "final_best_score": self_rag.get("final_best_score", 0.0),
    }


def summarize_traces(traces: List[Dict[str, Any]]) -> Dict[str, Any]:
    status_counts = Counter(str(trace.get("self_rag_status", "unknown") or "unknown") for trace in traces)
    citation_status_counts = Counter(str(trace.get("citation_check_status", "unknown") or "unknown") for trace in traces)
    refusal_count = sum(1 for trace in traces if bool(trace.get("is_refusal", False)))
    rescue_attempted_count = sum(1 for trace in traces if bool(trace.get("rescue_attempted", False)))
    rescued_count = sum(1 for trace in traces if bool(trace.get("rescued", False)))
    llm_rewrite_count = sum(1 for trace in traces if bool(trace.get("query_rewrite_used_llm", False)))
    citation_applicable = [
        trace
        for trace in traces
        if str(trace.get("citation_check_status", "") or "") in {"supported", "warning", "unsupported"}
    ]
    citation_risk_count = sum(
        1
        for trace in citation_applicable
        if str(trace.get("citation_check_status", "") or "") in {"warning", "unsupported"}
    )
    retrieval_mode_counts: Counter = Counter()
    for trace in traces:
        modes = trace.get("retrieval_modes", [])
        if isinstance(modes, list):
            retrieval_mode_counts.update(str(mode) for mode in modes if mode)
    return {
        "recent_trace_total": len(traces),
        "recent_trace_status_distribution": dict(status_counts),
        "recent_trace_refusal_rate": rate(refusal_count, len(traces)),
        "recent_trace_rescue_rate": rate(rescued_count, rescue_attempted_count),
        "recent_trace_llm_rewrite_rate": rate(llm_rewrite_count, len(traces)),
        "recent_trace_retrieval_mode_distribution": dict(retrieval_mode_counts),
        "recent_trace_citation_check_distribution": dict(citation_status_counts),
        "recent_trace_citation_check_applicable_count": len(citation_applicable),
        "recent_trace_citation_check_risk_count": citation_risk_count,
        "recent_trace_citation_check_risk_rate": rate(citation_risk_count, len(citation_applicable)),
        "recent_trace_avg_citation_support_score": average_float(
            trace.get("citation_support_score") for trace in citation_applicable
        ),
        "recent_trace_avg_latency_ms": average_ms(trace.get("latency_ms") for trace in traces),
    }


def summarize_results(
    search_records: List[Dict[str, Any]],
    chat_records: List[Dict[str, Any]],
    traces: Optional[List[Dict[str, Any]]] = None,
    trace_error: str = "",
) -> Dict[str, Any]:
    traces = traces or []
    search_passed = sum(1 for record in search_records if record.get("passed"))
    chat_passed = sum(1 for record in chat_records if record.get("passed"))
    search_failures = sum(1 for record in search_records if not record.get("ok"))
    chat_failures = sum(1 for record in chat_records if not record.get("ok"))
    api_failure_count = search_failures + chat_failures + (1 if trace_error else 0)

    successful_chat_records = [record for record in chat_records if record.get("ok")]
    refusal_count = sum(1 for record in successful_chat_records if record.get("is_refusal"))
    rescue_attempted_count = sum(1 for record in successful_chat_records if record.get("rescue_attempted"))
    rescued_count = sum(1 for record in successful_chat_records if record.get("rescued"))
    successful_latencies = [
        record.get("latency_ms")
        for record in search_records + chat_records
        if record.get("ok")
    ]

    summary = {
        "search_total": len(search_records),
        "search_passed": search_passed,
        "search_pass_rate": rate(search_passed, len(search_records)),
        "chat_total": len(chat_records),
        "chat_passed": chat_passed,
        "chat_pass_rate": rate(chat_passed, len(chat_records)),
        "refusal_count": refusal_count,
        "refusal_rate": rate(refusal_count, len(successful_chat_records)),
        "rescue_attempted_count": rescue_attempted_count,
        "rescued_count": rescued_count,
        "rescue_rate": rate(rescued_count, rescue_attempted_count),
        "avg_latency_ms": average_ms(successful_latencies),
        "api_failure_count": api_failure_count,
        "trace_error": trace_error,
    }
    summary.update(summarize_traces(traces))
    return summary


def run_search_cases(base_url: str, search_limit: int) -> List[Dict[str, Any]]:
    records = []
    for case in SEARCH_CASES:
        response, latency_ms, error = request_json(
            base_url,
            "/api/search",
            payload={"query": case["question"], "limit": search_limit},
            timeout=60,
        )
        records.append(evaluate_search_case(case, response, latency_ms, error))
    return records


def run_chat_cases(base_url: str) -> List[Dict[str, Any]]:
    records = []
    for case in CHAT_CASES:
        response, latency_ms, error = request_json(
            base_url,
            "/api/chat",
            payload={"question": case["question"]},
            timeout=180,
        )
        records.append(evaluate_chat_case(case, response, latency_ms, error))
    return records


def fetch_traces(base_url: str, limit: int) -> Tuple[List[Dict[str, Any]], str]:
    response, _, error = request_json(base_url, "/api/traces", timeout=30, query={"limit": limit})
    if error:
        return [], error
    traces = response.get("traces", []) if isinstance(response, dict) else []
    return traces if isinstance(traces, list) else [], ""


def format_percent(value: float) -> str:
    return "%.1f%%" % (value * 100)


def metric_number(summary: Dict[str, Any], metric: str) -> Optional[float]:
    value = summary.get(metric)
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_comparison(
    current_report: Dict[str, Any],
    baseline_report: Dict[str, Any],
    baseline_path: str = "",
) -> Dict[str, Any]:
    current_summary = current_report.get("summary", {})
    baseline_summary = baseline_report.get("summary", {})
    current_summary = current_summary if isinstance(current_summary, dict) else {}
    baseline_summary = baseline_summary if isinstance(baseline_summary, dict) else {}

    metrics = {}
    for metric, unit in COMPARISON_METRICS:
        current_value = metric_number(current_summary, metric)
        baseline_value = metric_number(baseline_summary, metric)
        delta = None
        if current_value is not None and baseline_value is not None:
            delta = round(current_value - baseline_value, 4)
        metrics[metric] = {
            "unit": unit,
            "baseline": baseline_value,
            "current": current_value,
            "delta": delta,
        }

    return {
        "baseline_path": baseline_path,
        "baseline_generated_at": baseline_report.get("generated_at", ""),
        "current_generated_at": current_report.get("generated_at", ""),
        "metrics": metrics,
    }


def load_report(path: str) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        report = json.load(file)
    if not isinstance(report, dict):
        raise ValueError("Report JSON must be an object.")
    return report


def save_report(report: Dict[str, Any], path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")


def format_metric_value(value: Optional[float], unit: str) -> str:
    if value is None:
        return "n/a"
    if unit == "rate":
        return format_percent(value)
    if unit == "ms":
        return "%sms" % int(round(value))
    if unit == "count":
        return str(int(round(value)))
    if unit == "score":
        return "%.2f" % value
    return str(value)


def format_metric_delta(value: Optional[float], unit: str) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value > 0 else ""
    if unit == "rate":
        return "%s%.1fpp" % (sign, value * 100)
    if unit == "ms":
        return "%s%sms" % (sign, int(round(value)))
    if unit == "count":
        return "%s%s" % (sign, int(round(value)))
    if unit == "score":
        return "%s%.2f" % (sign, value)
    return "%s%s" % (sign, value)


def format_comparison(comparison: Dict[str, Any]) -> List[str]:
    lines = [
        "",
        "Comparison:",
        "baseline_path: %s" % (comparison.get("baseline_path") or "unknown"),
        "baseline_generated_at: %s" % (comparison.get("baseline_generated_at") or "unknown"),
    ]
    metrics = comparison.get("metrics", {})
    metrics = metrics if isinstance(metrics, dict) else {}
    for metric, unit in COMPARISON_METRICS:
        item = metrics.get(metric, {})
        item = item if isinstance(item, dict) else {}
        lines.append(
            "%s: %s -> %s (%s)"
            % (
                metric,
                format_metric_value(item.get("baseline"), unit),
                format_metric_value(item.get("current"), unit),
                format_metric_delta(item.get("delta"), unit),
            )
        )
    return lines


def format_status_counts(counts: Dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join("%s=%s" % (key, counts[key]) for key in sorted(counts))


def format_case(record: Dict[str, Any]) -> List[str]:
    if record.get("error"):
        status = "API_ERROR"
    else:
        status = "PASS" if record.get("passed") else "FAIL"
    lines = ["[%s][%s] %s" % (status, str(record.get("kind", "")).upper(), record.get("question", ""))]
    if record.get("error"):
        lines.append("  error: %s" % record["error"])
    if record.get("kind") == "search":
        lines.append("  expected_title: %s" % record.get("expected_title", ""))
        lines.append("  top_titles: %s" % (", ".join(record.get("top_titles", [])) or "none"))
    else:
        if record.get("expect_no_evidence"):
            lines.append("  expected: no evidence refusal")
        else:
            lines.append("  expected_title: %s" % record.get("expected_title", ""))
        lines.append(
            "  chat: status=%s refusal=%s rescue_attempted=%s rescued=%s citations=%s"
            % (
                record.get("self_rag_status", ""),
                record.get("is_refusal", False),
                record.get("rescue_attempted", False),
                record.get("rescued", False),
                record.get("citation_count", 0),
            )
        )
        if record.get("answer_preview"):
            lines.append("  answer_preview: %s" % record["answer_preview"])
        lines.append("  citation_titles: %s" % (", ".join(record.get("citation_titles", [])) or "none"))
        if record.get("citation_check_status"):
            lines.append(
                "  citation_check: status=%s support=%.2f claims=%s"
                % (
                    record.get("citation_check_status", ""),
                    float(record.get("citation_support_score", 0.0) or 0.0),
                    record.get("citation_checked_claim_count", 0),
                )
            )
    lines.append("  latency_ms: %s" % record.get("latency_ms", 0))
    return lines


def format_text_report(report: Dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "Eval Report",
        "base_url: %s" % report["base_url"],
        "generated_at: %s" % report["generated_at"],
        "",
        "Core metrics:",
        "search_pass_rate: %s (%s/%s)"
        % (format_percent(summary["search_pass_rate"]), summary["search_passed"], summary["search_total"]),
        "chat_pass_rate: %s (%s/%s)"
        % (format_percent(summary["chat_pass_rate"]), summary["chat_passed"], summary["chat_total"]),
        "refusal_rate: %s (%s/%s successful chat responses)"
        % (
            format_percent(summary["refusal_rate"]),
            summary["refusal_count"],
            summary["chat_total"] - sum(1 for record in report["chat_cases"] if not record.get("ok")),
        ),
        "rescue_rate: %s (%s/%s rescue attempts)"
        % (
            format_percent(summary["rescue_rate"]),
            summary["rescued_count"],
            summary["rescue_attempted_count"],
        ),
        "avg_latency_ms: %s" % summary["avg_latency_ms"],
        "api_failure_count: %s" % summary["api_failure_count"],
        "",
        "Recent traces:",
        "recent_trace_total: %s" % summary["recent_trace_total"],
        "recent_trace_status_distribution: %s"
        % format_status_counts(summary["recent_trace_status_distribution"]),
        "recent_trace_refusal_rate: %s" % format_percent(summary["recent_trace_refusal_rate"]),
        "recent_trace_rescue_rate: %s" % format_percent(summary["recent_trace_rescue_rate"]),
        "recent_trace_llm_rewrite_rate: %s" % format_percent(summary["recent_trace_llm_rewrite_rate"]),
        "recent_trace_retrieval_mode_distribution: %s"
        % format_status_counts(summary["recent_trace_retrieval_mode_distribution"]),
        "recent_trace_citation_check_distribution: %s"
        % format_status_counts(summary["recent_trace_citation_check_distribution"]),
        "recent_trace_citation_check_risk_rate: %s (%s/%s applicable traces)"
        % (
            format_percent(summary["recent_trace_citation_check_risk_rate"]),
            summary["recent_trace_citation_check_risk_count"],
            summary["recent_trace_citation_check_applicable_count"],
        ),
        "recent_trace_avg_citation_support_score: %.2f" % summary["recent_trace_avg_citation_support_score"],
        "recent_trace_avg_latency_ms: %s" % summary["recent_trace_avg_latency_ms"],
    ]
    if summary.get("trace_error"):
        lines.append("trace_error: %s" % summary["trace_error"])

    if isinstance(report.get("comparison"), dict):
        lines.extend(format_comparison(report["comparison"]))

    lines.extend(["", "Search cases:"])
    for record in report["search_cases"]:
        lines.extend(format_case(record))
    lines.extend(["", "Chat cases:"])
    for record in report["chat_cases"]:
        lines.extend(format_case(record))
    return "\n".join(lines)


def build_report(base_url: str, search_limit: int, trace_limit: int) -> Dict[str, Any]:
    search_records = run_search_cases(base_url, search_limit)
    chat_records = run_chat_cases(base_url)
    traces, trace_error = fetch_traces(base_url, trace_limit)
    summary = summarize_results(search_records, chat_records, traces, trace_error)
    return {
        "base_url": base_url,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary,
        "search_cases": search_records,
        "chat_cases": chat_records,
        "recent_traces": traces,
    }


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a RAG eval report against a running backend API.")
    parser.add_argument("--base-url", default=os.environ.get("EVAL_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--search-limit", type=int, default=3)
    parser.add_argument("--trace-limit", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON.")
    parser.add_argument("--save", help="Save the current report JSON to this path.")
    parser.add_argument("--compare", help="Compare the current report with a saved baseline JSON.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    report = build_report(args.base_url, args.search_limit, args.trace_limit)
    if args.compare:
        baseline = load_report(args.compare)
        report["comparison"] = build_comparison(report, baseline, args.compare)
    if args.save:
        save_report(report, args.save)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(report))

    summary = report["summary"]
    if summary["api_failure_count"]:
        return 2
    if summary["search_passed"] < summary["search_total"] or summary["chat_passed"] < summary["chat_total"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
