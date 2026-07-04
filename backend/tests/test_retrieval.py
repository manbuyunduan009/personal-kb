from app.retrieval import keyword_recall_hits, query_variants, rerank_hits


def test_query_variants_expand_requirement_question():
    variants = query_variants("十七周年庆小程序有哪些需求？")

    assert any("功能" in variant for variant in variants)
    assert any("模块" in variant for variant in variants)


def test_query_variants_expand_carrier_concept_question():
    variants = query_variants("游园会的载体是啥")
    combined = " ".join(variants)

    assert "小程序" in combined
    assert "移动端" in combined
    assert "承载形式" in combined


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


def test_keyword_recall_hits_can_find_exact_terms():
    chunks = [
        {
            "id": "doc-1:0",
            "content": "普通部署说明",
            "metadata": {"title": "部署.md", "chunk_index": 0},
        },
        {
            "id": "doc-2:0",
            "content": "猫眼订单绑定和接驳车预约规则",
            "metadata": {"title": "周年庆.docx", "chunk_index": 0},
        },
    ]

    hits = keyword_recall_hits("猫眼订单怎么绑定？", chunks, limit=1)

    assert hits[0]["id"] == "doc-2:0"
    assert hits[0]["retrieval_mode"] == "keyword"
    assert hits[0]["keyword_recall_score"] > 0


def test_rerank_adds_small_bm25_bonus():
    hits = [
        {
            "content": "十七周年庆小程序需求",
            "metadata": {"title": "需求.docx", "source_path": "需求.docx", "chunk_index": 0},
            "score": 0.4,
            "keyword_recall_score": 0.5,
            "bm25_score": -1.2,
        }
    ]

    results = rerank_hits("十七周年庆小程序有哪些需求？", hits, limit=1)

    assert results[0]["bm25_bonus"] == 0.04
