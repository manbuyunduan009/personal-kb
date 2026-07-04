from app.retrieval import query_variants, rerank_hits


def test_query_variants_expand_requirement_question():
    variants = query_variants("十七周年庆小程序有哪些需求？")

    assert any("功能" in variant for variant in variants)
    assert any("模块" in variant for variant in variants)


def test_rerank_uses_keyword_overlap():
    hits = [
        {
            "content": "部署说明和环境变量",
            "metadata": {"title": "部署.md", "chunk_header": "部署"},
            "score": 0.5,
        },
        {
            "content": "十七周年庆小程序需求包含任务奖励和活动规则",
            "metadata": {"title": "需求.docx", "chunk_header": "周年庆需求"},
            "score": 0.45,
        },
    ]

    results = rerank_hits("十七周年庆小程序有哪些需求？", hits, limit=2)

    assert results[0]["metadata"]["title"] == "需求.docx"
    assert results[0]["keyword_score"] > results[1]["keyword_score"]


def test_rerank_uses_feedback_score_as_small_bonus():
    hits = [
        {
            "content": "十七周年庆小程序需求",
            "metadata": {"title": "a.docx", "source_path": "a.docx", "chunk_index": 0},
            "score": 0.4,
        },
        {
            "content": "十七周年庆小程序需求",
            "metadata": {"title": "b.docx", "source_path": "b.docx", "chunk_index": 1},
            "score": 0.4,
        },
    ]

    results = rerank_hits(
        "十七周年庆小程序有哪些需求？",
        hits,
        limit=2,
        feedback_scores={("b.docx", 1): 2.0},
    )

    assert results[0]["metadata"]["title"] == "b.docx"
    assert results[0]["feedback_bonus"] > 0
