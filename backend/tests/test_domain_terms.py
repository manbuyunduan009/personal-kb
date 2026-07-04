from app.domain_terms import concept_evidence_groups, expand_query_terms, mine_domain_term_candidates


def test_expand_query_terms_uses_domain_dictionary():
    expanded = expand_query_terms("游园会的载体是啥")

    assert "承载形式" in expanded
    assert "小程序" in expanded
    assert "移动端" in expanded


def test_concept_evidence_groups_are_built_from_terms():
    groups = concept_evidence_groups()

    assert any("载体" in question_markers and "小程序" in evidence_markers for question_markers, evidence_markers in groups)


def test_mine_domain_term_candidates_from_documents_and_low_score_traces():
    documents = [
        {
            "title": "游园会活动需求.docx",
            "source_path": "docs/游园会活动需求.docx",
            "content_preview": "游园会活动将在移动端小程序中承载，首页入口页需要配置资源位。",
        }
    ]
    traces = [
        {
            "question": "游园会的载体是啥",
            "self_rag_status": "insufficient_after_rescue",
            "is_refusal": True,
            "final_best_score": 0.22,
            "min_evidence_score": 0.3,
        }
    ]

    candidates = mine_domain_term_candidates(documents, traces, limit=20)

    assert any(candidate["term"] == "承载形式" and candidate["status"] == "known" for candidate in candidates)
    assert any("low_score_question" in candidate["sources"] for candidate in candidates)
    assert any(candidate["category"] in {"平台/终端", "页面/入口"} for candidate in candidates)
