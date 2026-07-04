from app.citation_check import check_citation_support


def test_empty_answer_is_unsupported():
    result = check_citation_support("", [{"summary": "目标用户是专题产品经理"}])

    assert result["status"] == "unsupported"
    assert result["support_score"] == 0.0
    assert result["checked_claim_count"] == 0


def test_answer_without_citations_is_warning():
    result = check_citation_support("目标用户是专题产品经理。", [])

    assert result["status"] == "warning"
    assert result["checked_claim_count"] == 1
    assert "no citations" in result["reasons"][0]


def test_chinese_answer_supported_by_summary_and_context():
    result = check_citation_support(
        "目标用户主要是专题产品经理，负责验收活动页面。",
        [
            {
                "title": "专题验收助手PRD.md",
                "summary": "专题验收助手面向专题产品经理。",
                "context": "产品经理负责验收活动专题和小程序页面。",
            }
        ],
    )

    assert result["status"] == "supported"
    assert result["support_score"] >= 0.55
    assert result["checked_claim_count"] == 1


def test_english_and_number_claim_supported():
    result = check_citation_support(
        "The release KPI is 95% pass rate.",
        [
            {
                "title": "release-plan.md",
                "summary": "Release KPI: 95% pass rate for the acceptance checklist.",
            }
        ],
    )

    assert result["status"] == "supported"
    assert result["support_score"] >= 0.55


def test_unrelated_answer_is_unsupported():
    result = check_citation_support(
        "火星移民预算是100万元。",
        [
            {
                "title": "专题验收助手PRD.md",
                "summary": "目标用户是专题产品经理，负责活动页面验收。",
            }
        ],
    )

    assert result["status"] == "unsupported"
    assert result["support_score"] < 0.2


def test_partial_support_stays_warning():
    result = check_citation_support(
        "目标用户是专题产品经理。预算是100万元。",
        [
            {
                "title": "专题验收助手PRD.md",
                "summary": "目标用户是专题产品经理。",
            }
        ],
    )

    assert result["status"] == "warning"
    assert result["checked_claim_count"] == 2
    assert any("little lexical support" in reason for reason in result["reasons"])


def test_number_mismatch_does_not_count_as_supported():
    result = check_citation_support(
        "预算是100万元。",
        [{"summary": "预算是30万元，主要用于线下物料。"}],
    )

    assert result["status"] == "warning"
    assert result["support_score"] <= 0.45


def test_nested_metadata_and_field_facts_are_usable_evidence():
    result = check_citation_support(
        "项目所属是K1剑网3。",
        [
            {
                "metadata": {
                    "title": "需求.docx",
                    "field_facts": [{"label": "项目/部门所属", "value": "K1剑网3"}],
                }
            }
        ],
    )

    assert result["status"] == "supported"
    assert result["support_score"] >= 0.55
