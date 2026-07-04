from pathlib import Path

from app.product_expert import (
    analyze_requirement_change,
    build_requirement_card,
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
    assert any("历史版本" in question for question in card["open_questions"])
    assert card["next_actions"]
