from pathlib import Path

from app.product_expert import (
    analyze_requirement_change,
    build_requirement_card,
    build_requirement_timeline,
    find_similar_requirements,
    group_documents_by_requirement,
    infer_requirement_identity,
)


def test_infer_requirement_identity_from_title_and_preview():
    identity = infer_requirement_identity(
        {
            "title": "【需求管理】《剑网3》十七周年庆线下活动小程序.docx",
            "source_path": r"D:\docs\周年庆.docx",
            "content_preview": "| 项目/部门所属 | K1-剑网 3 |",
            "last_modified": 1783000000,
        }
    )

    assert identity["project_name"] == "剑网3"
    assert "十七周年庆线下活动小程序" in identity["requirement_title"]
    assert identity["version_label"]
    assert identity["confidence"] >= 0.7


def test_group_documents_by_requirement_marks_latest_version():
    documents = [
        {
            "id": "old",
            "title": "专题验收助手PRD.md",
            "source_path": "old.md",
            "file_type": ".md",
            "content_preview": "专题验收助手目标用户",
            "last_modified": 100,
            "indexed_at": "2026-07-01T00:00:00Z",
        },
        {
            "id": "new",
            "title": "专题验收助手PRD.md",
            "source_path": "new.md",
            "file_type": ".md",
            "content_preview": "专题验收助手目标用户",
            "last_modified": 200,
            "indexed_at": "2026-07-02T00:00:00Z",
        },
    ]

    groups = group_documents_by_requirement(documents)

    assert len(groups) == 1
    assert groups[0]["document_count"] == 2
    assert groups[0]["latest_document"]["document_id"] == "new"
    assert groups[0]["versions"][0]["is_latest"] is True


def test_analyze_requirement_change_reports_added_removed_fields_and_impacts(tmp_path: Path):
    old_path = tmp_path / "old.md"
    new_path = tmp_path / "new.md"
    old_path.write_text(
        "\n".join(
            [
                "| 项目/部门所属 | K1-剑网 3 |",
                "| 期望完成日期 | 2026/07/01 |",
                "入口页展示活动地点。",
            ]
        ),
        encoding="utf-8",
    )
    new_path.write_text(
        "\n".join(
            [
                "| 项目/部门所属 | K1-剑网 3 |",
                "| 期望完成日期 | 2026/07/20 |",
                "入口页展示活动地点。",
                "新增微信授权登录流程。",
            ]
        ),
        encoding="utf-8",
    )

    result = analyze_requirement_change(
        {
            "id": "old",
            "title": "old.md",
            "source_path": str(old_path),
            "file_type": ".md",
        },
        {
            "id": "new",
            "title": "new.md",
            "source_path": str(new_path),
            "file_type": ".md",
        },
    )

    assert "新增" in result["summary"]
    assert "新增微信授权登录流程。" in result["added"]
    assert any(change["label"] == "期望完成日期" for change in result["field_changes"])
    assert any(module["label"] == "权限/登录" for module in result["impact_modules"])
    assert result["open_questions"]


def test_build_requirement_card_extracts_product_sections(tmp_path: Path):
    path = tmp_path / "prd.md"
    path.write_text(
        "\n".join(
            [
                "# 专题验收助手",
                "需求背景：产品经理验收活动页面时容易遗漏规则。",
                "目标：提升专题验收效率，降低线上问题。",
                "目标用户：网站专题产品经理、测试同学。",
                "功能范围：支持页面检查、规则校验和验收清单。",
                "关键规则：检查结果必须带引用来源。",
                "风险：不同活动页面结构差异较大。",
            ]
        ),
        encoding="utf-8",
    )
    documents = [
        {
            "id": "doc-1",
            "title": "专题验收助手PRD.md",
            "source_path": str(path),
            "file_type": ".md",
            "content_preview": path.read_text(encoding="utf-8"),
            "last_modified": 100,
            "indexed_at": "2026-07-01T00:00:00Z",
        }
    ]
    requirement_key = group_documents_by_requirement(documents)[0]["requirement_key"]

    card = build_requirement_card(requirement_key, documents)

    assert card["requirement_title"] == "专题验收助手"
    assert "提升专题验收效率" in card["sections"]["goals"][0]
    assert card["sections"]["scope"]
    assert card["sections"]["risks"]
    assert card["impact_modules"]
    assert card["quality"]["status"] in {"good", "fair"}
    assert card["quality"]["completeness_score"] >= 0.5
    assert any("历史版本" in question for question in card["open_questions"])
    assert card["next_actions"]


def test_requirement_card_quality_flags_missing_sections(tmp_path: Path):
    path = tmp_path / "thin.md"
    path.write_text("只有一句很短的需求说明。", encoding="utf-8")
    documents = [
        {
            "id": "doc-1",
            "title": "薄弱需求.md",
            "source_path": str(path),
            "file_type": ".md",
            "content_preview": "只有一句很短的需求说明。",
            "last_modified": 100,
            "indexed_at": "2026-07-01T00:00:00Z",
        }
    ]
    requirement_key = group_documents_by_requirement(documents)[0]["requirement_key"]

    card = build_requirement_card(requirement_key, documents)

    assert card["quality"]["status"] == "needs_review"
    assert "目标" in card["quality"]["missing_sections"]
    assert card["quality"]["review_notes"]


def test_find_similar_requirements_returns_ranked_candidates(tmp_path: Path):
    target = tmp_path / "target.md"
    similar = tmp_path / "similar.md"
    different = tmp_path / "different.md"
    target.write_text(
        "《剑网3》周年庆预约小程序\n目标：支持玩家预约活动。\n功能范围：预约、票务、微信授权登录。\n验收：检查预约规则。",
        encoding="utf-8",
    )
    similar.write_text(
        "《剑网3》演唱会预约活动\n目标：支持玩家预约演唱会。\n功能范围：预约、票务、微信授权。\n验收：检查预约状态。",
        encoding="utf-8",
    )
    different.write_text(
        "专题验收助手\n目标：帮助产品经理验收活动页面。\n功能范围：页面检查和规则校验。",
        encoding="utf-8",
    )
    documents = [
        {
            "id": "target",
            "title": "【需求管理】《剑网3》周年庆预约小程序.md",
            "source_path": str(target),
            "file_type": ".md",
            "content_preview": target.read_text(encoding="utf-8"),
            "last_modified": 300,
            "indexed_at": "2026-07-03T00:00:00Z",
        },
        {
            "id": "similar",
            "title": "【需求管理】《剑网3》演唱会预约活动.md",
            "source_path": str(similar),
            "file_type": ".md",
            "content_preview": similar.read_text(encoding="utf-8"),
            "last_modified": 200,
            "indexed_at": "2026-07-02T00:00:00Z",
        },
        {
            "id": "different",
            "title": "专题验收助手PRD.md",
            "source_path": str(different),
            "file_type": ".md",
            "content_preview": different.read_text(encoding="utf-8"),
            "last_modified": 100,
            "indexed_at": "2026-07-01T00:00:00Z",
        },
    ]
    target_key = next(
        group["requirement_key"]
        for group in group_documents_by_requirement(documents)
        if "周年庆预约" in group["requirement_title"]
    )

    result = find_similar_requirements(target_key, documents, limit=2)

    assert len(result["similar"]) == 2
    assert result["similar"][0]["requirement_title"] == "演唱会预约活动"
    assert result["similar"][0]["score"] > result["similar"][1]["score"]
    assert result["similar"][0]["shared_modules"]
    assert result["similar"][0]["reasons"]


def test_build_requirement_timeline_reports_version_changes(tmp_path: Path):
    old_path = tmp_path / "old.md"
    middle_path = tmp_path / "middle.md"
    new_path = tmp_path / "new.md"
    old_path.write_text(
        "\n".join(
            [
                "《剑网3》周年庆预约小程序",
                "| 项目/部门所属 | K1-剑网 3 |",
                "| 期望完成日期 | 2026/07/01 |",
                "功能范围：预约活动入口。",
                "验收：检查入口展示。",
            ]
        ),
        encoding="utf-8",
    )
    middle_path.write_text(
        "\n".join(
            [
                "《剑网3》周年庆预约小程序",
                "| 项目/部门所属 | K1-剑网 3 |",
                "| 期望完成日期 | 2026/07/10 |",
                "功能范围：预约活动入口和微信授权登录。",
                "验收：检查入口展示和授权失败。",
            ]
        ),
        encoding="utf-8",
    )
    new_path.write_text(
        "\n".join(
            [
                "《剑网3》周年庆预约小程序",
                "| 项目/部门所属 | K1-剑网 3 |",
                "| 期望完成日期 | 2026/07/20 |",
                "功能范围：预约活动入口、微信授权登录和票务资格规则。",
                "验收：检查入口展示、授权失败和重复预约。",
            ]
        ),
        encoding="utf-8",
    )
    documents = [
        {
            "id": "old",
            "title": "【需求管理】《剑网3》周年庆预约小程序@20260427.md",
            "source_path": str(old_path),
            "file_type": ".md",
            "content_preview": old_path.read_text(encoding="utf-8"),
            "last_modified": 100,
            "indexed_at": "2026-04-27T00:00:00Z",
        },
        {
            "id": "middle",
            "title": "【需求管理】《剑网3》周年庆预约小程序@20260701.md",
            "source_path": str(middle_path),
            "file_type": ".md",
            "content_preview": middle_path.read_text(encoding="utf-8"),
            "last_modified": 200,
            "indexed_at": "2026-07-01T00:00:00Z",
        },
        {
            "id": "new",
            "title": "【需求管理】《剑网3》周年庆预约小程序@20260720.md",
            "source_path": str(new_path),
            "file_type": ".md",
            "content_preview": new_path.read_text(encoding="utf-8"),
            "last_modified": 300,
            "indexed_at": "2026-07-20T00:00:00Z",
        },
    ]
    requirement_key = group_documents_by_requirement(documents)[0]["requirement_key"]

    timeline = build_requirement_timeline(requirement_key, documents)

    assert timeline["requirement"]["document_count"] == 3
    assert [event["document"]["id"] for event in timeline["versions"]] == ["old", "middle", "new"]
    assert len(timeline["change_events"]) == 2
    assert timeline["change_events"][0]["field_change_count"] >= 1
    assert timeline["change_events"][0]["risk_level"] in {"low", "medium", "high"}
    assert timeline["recurring_modules"]
    assert timeline["recommendations"]
