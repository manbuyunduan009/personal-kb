from scripts.eval_product_expert import evaluate_card, evaluate_requirements, format_text_report, summarize


def test_evaluate_requirements_counts_versions():
    response = {
        "requirements": [
            {"requirement_key": "a", "document_count": 1},
            {"requirement_key": "b", "document_count": 3},
        ]
    }

    record = evaluate_requirements(response, latency_ms=20)

    assert record["ok"] is True
    assert record["requirement_total"] == 2
    assert record["version_total"] == 4
    assert record["single_version_count"] == 1
    assert record["multi_version_count"] == 1


def test_evaluate_card_extracts_quality_fields():
    requirement = {"requirement_key": "a", "requirement_title": "需求A", "project_name": "项目A"}
    response = {
        "quality": {
            "status": "fair",
            "completeness_score": 0.64,
            "missing_sections": ["验收点"],
            "weak_sections": ["风险点"],
        },
        "open_questions": ["补验收"],
        "next_actions": ["核对原文"],
    }

    record = evaluate_card(requirement, response, latency_ms=15)

    assert record["ok"] is True
    assert record["quality_status"] == "fair"
    assert record["completeness_score"] == 0.64
    assert record["missing_sections"] == ["验收点"]
    assert record["open_question_count"] == 1


def test_summarize_and_format_text_report():
    requirement_record = {
        "ok": True,
        "requirement_total": 2,
        "version_total": 3,
        "single_version_count": 1,
        "multi_version_count": 1,
    }
    card_records = [
        {
            "ok": True,
            "quality_status": "good",
            "completeness_score": 0.8,
            "missing_sections": [],
            "weak_sections": ["风险点"],
            "open_question_count": 2,
            "next_action_count": 3,
            "requirement_title": "需求A",
        },
        {
            "ok": True,
            "quality_status": "needs_review",
            "completeness_score": 0.2,
            "missing_sections": ["目标"],
            "weak_sections": [],
            "open_question_count": 4,
            "next_action_count": 2,
            "requirement_title": "需求B",
        },
    ]

    summary = summarize(requirement_record, card_records)

    assert summary["avg_card_completeness_score"] == 0.5
    assert summary["quality_status_distribution"] == {"good": 1, "needs_review": 1}
    assert summary["missing_section_distribution"] == {"目标": 1}

    text = format_text_report(
        {
            "base_url": "http://127.0.0.1:8000",
            "generated_at": "2026-07-04T00:00:00+00:00",
            "summary": summary,
            "cards": card_records,
        }
    )

    assert "Product Expert Eval" in text
    assert "avg_card_completeness_score: 0.50" in text
