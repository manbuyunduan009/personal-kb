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
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def request_json(
    base_url: str,
    path: str,
    timeout: int = 30,
) -> Tuple[Optional[Dict[str, Any]], int, str]:
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
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


def evaluate_requirements(response: Optional[Dict[str, Any]], latency_ms: int, error: str = "") -> Dict[str, Any]:
    requirements = response.get("requirements", []) if isinstance(response, dict) else []
    requirements = requirements if isinstance(requirements, list) else []
    version_counts = [int(item.get("document_count", 0) or 0) for item in requirements if isinstance(item, dict)]
    return {
        "ok": not error,
        "error": error,
        "latency_ms": latency_ms,
        "requirement_total": len(requirements),
        "version_total": sum(version_counts),
        "single_version_count": sum(1 for count in version_counts if count <= 1),
        "multi_version_count": sum(1 for count in version_counts if count > 1),
        "requirements": requirements,
    }


def evaluate_card(requirement: Dict[str, Any], response: Optional[Dict[str, Any]], latency_ms: int, error: str = ""):
    card = response if isinstance(response, dict) else {}
    quality = card.get("quality", {}) if isinstance(card.get("quality", {}), dict) else {}
    missing_sections = quality.get("missing_sections", [])
    missing_sections = missing_sections if isinstance(missing_sections, list) else []
    weak_sections = quality.get("weak_sections", [])
    weak_sections = weak_sections if isinstance(weak_sections, list) else []
    open_questions = card.get("open_questions", [])
    open_questions = open_questions if isinstance(open_questions, list) else []
    next_actions = card.get("next_actions", [])
    next_actions = next_actions if isinstance(next_actions, list) else []
    return {
        "ok": not error,
        "error": error,
        "latency_ms": latency_ms,
        "requirement_key": requirement.get("requirement_key", ""),
        "requirement_title": requirement.get("requirement_title", ""),
        "project_name": requirement.get("project_name", ""),
        "quality_status": str(quality.get("status", "unknown")),
        "completeness_score": float(quality.get("completeness_score", 0.0) or 0.0),
        "missing_sections": missing_sections,
        "weak_sections": weak_sections,
        "open_question_count": len(open_questions),
        "next_action_count": len(next_actions),
    }


def average(values: List[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def summarize(requirement_record: Dict[str, Any], card_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    successful_cards = [record for record in card_records if record.get("ok")]
    status_counts = Counter(str(record.get("quality_status", "unknown") or "unknown") for record in successful_cards)
    missing_counts: Counter = Counter()
    weak_counts: Counter = Counter()
    for record in successful_cards:
        missing_counts.update(str(item) for item in record.get("missing_sections", []) if item)
        weak_counts.update(str(item) for item in record.get("weak_sections", []) if item)
    return {
        "requirement_total": requirement_record["requirement_total"],
        "version_total": requirement_record["version_total"],
        "single_version_count": requirement_record["single_version_count"],
        "multi_version_count": requirement_record["multi_version_count"],
        "card_total": len(card_records),
        "card_success_count": len(successful_cards),
        "card_failure_count": len(card_records) - len(successful_cards),
        "avg_card_completeness_score": average([record["completeness_score"] for record in successful_cards]),
        "quality_status_distribution": dict(status_counts),
        "missing_section_distribution": dict(missing_counts),
        "weak_section_distribution": dict(weak_counts),
        "avg_open_questions": average([float(record["open_question_count"]) for record in successful_cards]),
        "avg_next_actions": average([float(record["next_action_count"]) for record in successful_cards]),
        "api_failure_count": (0 if requirement_record.get("ok") else 1)
        + sum(1 for record in card_records if not record.get("ok")),
    }


def build_report(base_url: str, limit: int) -> Dict[str, Any]:
    requirements_response, latency_ms, error = request_json(base_url, "/api/product/requirements")
    requirement_record = evaluate_requirements(requirements_response, latency_ms, error)
    requirements = requirement_record.get("requirements", []) if requirement_record.get("ok") else []
    requirements = requirements[:limit] if limit > 0 else requirements

    card_records = []
    for requirement in requirements:
        key = urllib.parse.quote(str(requirement.get("requirement_key", "")), safe="")
        response, card_latency_ms, card_error = request_json(
            base_url,
            "/api/product/requirements/%s/card" % key,
        )
        card_records.append(evaluate_card(requirement, response, card_latency_ms, card_error))

    return {
        "base_url": base_url,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summarize(requirement_record, card_records),
        "requirements": {
            key: value
            for key, value in requirement_record.items()
            if key != "requirements"
        },
        "cards": card_records,
    }


def save_report(report: Dict[str, Any], path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")


def format_counts(counts: Dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join("%s=%s" % (key, counts[key]) for key in sorted(counts))


def format_text_report(report: Dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "Product Expert Eval",
        "base_url: %s" % report["base_url"],
        "generated_at: %s" % report["generated_at"],
        "",
        "Core metrics:",
        "requirement_total: %s" % summary["requirement_total"],
        "version_total: %s" % summary["version_total"],
        "single_version_count: %s" % summary["single_version_count"],
        "multi_version_count: %s" % summary["multi_version_count"],
        "card_success_count: %s/%s" % (summary["card_success_count"], summary["card_total"]),
        "avg_card_completeness_score: %.2f" % summary["avg_card_completeness_score"],
        "quality_status_distribution: %s" % format_counts(summary["quality_status_distribution"]),
        "missing_section_distribution: %s" % format_counts(summary["missing_section_distribution"]),
        "weak_section_distribution: %s" % format_counts(summary["weak_section_distribution"]),
        "avg_open_questions: %.2f" % summary["avg_open_questions"],
        "avg_next_actions: %.2f" % summary["avg_next_actions"],
        "api_failure_count: %s" % summary["api_failure_count"],
        "",
        "Cards:",
    ]
    for record in report["cards"]:
        status = "PASS" if record.get("ok") else "API_ERROR"
        lines.append(
            "[%s] %s | %s | score=%.2f | missing=%s"
            % (
                status,
                record.get("requirement_title", ""),
                record.get("quality_status", ""),
                record.get("completeness_score", 0.0),
                ", ".join(record.get("missing_sections", [])) or "none",
            )
        )
        if record.get("error"):
            lines.append("  error: %s" % record["error"])
    return "\n".join(lines)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a product expert eval against a running backend API.")
    parser.add_argument("--base-url", default=os.environ.get("EVAL_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON.")
    parser.add_argument("--save", help="Save the report JSON to this path.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    report = build_report(args.base_url, args.limit)
    if args.save:
        save_report(report, args.save)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(report))

    summary = report["summary"]
    if summary["api_failure_count"]:
        return 2
    if summary["requirement_total"] == 0 or summary["card_success_count"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
