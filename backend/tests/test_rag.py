from app.rag import INSUFFICIENT_EVIDENCE_MESSAGE, RagService


class FakeEmbeddings:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class FakeVectorStore:
    def __init__(self, hits):
        self.hits = hits

    def search(self, query_embedding, limit=5):
        return self.hits[:limit]

    def list_chunks(self):
        return [
            {
                "id": hit["id"],
                "content": hit["content"],
                "metadata": hit["metadata"],
            }
            for hit in self.hits
        ]


def make_hit(score, content="目标用户是专题产品经理", metadata=None, hit_id="doc-1:0"):
    base_metadata = {
        "title": "专题验收助手PRD.md",
        "source_path": "专题验收助手PRD.md",
        "file_type": ".md",
        "chunk_index": 0,
        "chunk_header": "目标用户",
        "summary": "目标用户是专题产品经理",
    }
    if metadata:
        base_metadata.update(metadata)
    return {
        "id": hit_id,
        "content": content,
        "metadata": base_metadata,
        "score": score,
    }


def test_context_from_hit_prefers_parent_context_and_keeps_child_citation():
    hit = make_hit(
        0.8,
        content="target child answer",
        metadata={
            "chunk_index": 7,
            "parent_index": 2,
            "parent_context": "parent intro target sibling details",
            "previous_context": "old previous target",
            "next_context": "old next target",
        },
        hit_id="doc-1:7",
    )

    context = RagService._context_from_hit("target", hit)
    citation = RagService._citation_from_hit(hit)

    assert "parent intro target sibling details" in context
    assert "target child answer" in context
    assert "old previous target" not in context
    assert "old next target" not in context
    assert citation["chunk_index"] == 7
    assert "parent_index" not in citation
    assert hit["metadata"]["parent_context_used"] is True


def test_context_from_hit_falls_back_to_child_windows_for_old_metadata():
    hit = make_hit(
        0.8,
        content="target child answer",
        metadata={
            "previous_context": "old previous target",
            "next_context": "old next target",
        },
    )

    context = RagService._context_from_hit("target", hit)

    assert "old previous target" in context
    assert "target child answer" in context
    assert "old next target" in context
    assert hit["metadata"]["parent_context_used"] is False


def test_answer_stops_when_evidence_score_is_too_low():
    service = RagService(
        embeddings=FakeEmbeddings(),
        vector_store=FakeVectorStore([make_hit(0.1)]),
        openai_api_key="unused",
        openai_base_url="https://example.com/v1",
        openai_model="test-model",
        min_evidence_score=0.3,
    )

    result = service.answer("火星移民方案预算是多少？")

    assert INSUFFICIENT_EVIDENCE_MESSAGE in result["answer"]
    assert result["citations"] == []
    assert result["self_rag"]["rescue_attempted"] is True
    assert result["self_rag"]["rescued"] is False


def test_answer_keeps_citations_when_evidence_is_enough_without_api_key():
    service = RagService(
        embeddings=FakeEmbeddings(),
        vector_store=FakeVectorStore([make_hit(0.8)]),
        openai_api_key="",
        openai_base_url="https://example.com/v1",
        openai_model="test-model",
        min_evidence_score=0.3,
    )

    result = service.answer("专题验收助手的目标用户是谁？")

    assert "OPENAI_API_KEY" in result["answer"]
    assert len(result["citations"]) == 1
    assert result["citations"][0]["title"] == "专题验收助手PRD.md"
    assert result["self_rag"]["status"] == "sufficient"


def test_answer_uses_structured_fields_for_field_lookup_questions_without_api_key():
    hit = make_hit(
        0.24,
        content="十七周年庆线下活动小程序需求包含预约和授权能力。",
        metadata={
            "title": "线下活动需求.docx",
            "source_path": "周年庆.docx",
            "chunk_header": "需求基础信息",
            "summary": "十七周年庆线下活动小程序需求",
            "field_facts": [{"label": "项目/部门所属", "value": "K1-剑网 3", "scope": "document"}],
        },
    )
    service = RagService(
        embeddings=FakeEmbeddings(),
        vector_store=FakeVectorStore([hit]),
        openai_api_key="",
        openai_base_url="https://example.com/v1",
        openai_model="test-model",
        min_evidence_score=0.3,
    )

    result = service.answer("周年庆是哪个游戏的？")

    assert "OPENAI_API_KEY" in result["answer"]
    assert len(result["citations"]) == 1
    assert result["citations"][0]["title"] == "线下活动需求.docx"
    assert result["self_rag"]["rescue_attempted"] is False


def test_structured_fields_do_not_unlock_unrelated_low_score_questions():
    hit = make_hit(
        0.1,
        content="十七周年庆线下活动小程序需求包含预约和授权能力。",
        metadata={
            "title": "【需求管理】《剑网3》十七周年庆线下活动小程序.docx",
            "source_path": "周年庆.docx",
            "chunk_header": "需求基础信息",
            "summary": "十七周年庆线下活动小程序需求",
            "field_facts": [{"label": "项目/部门所属", "value": "K1-剑网 3", "scope": "document"}],
        },
    )
    service = RagService(
        embeddings=FakeEmbeddings(),
        vector_store=FakeVectorStore([hit]),
        openai_api_key="unused",
        openai_base_url="https://example.com/v1",
        openai_model="test-model",
        min_evidence_score=0.3,
    )

    result = service.answer("火星移民预算是多少？")

    assert INSUFFICIENT_EVIDENCE_MESSAGE in result["answer"]
    assert result["citations"] == []


def test_answer_rescues_low_initial_retrieval_by_expanding_search():
    low_hits = [
        make_hit(
            0.05,
            content="部署说明和环境变量。",
            metadata={
                "title": "部署.md",
                "source_path": "部署.md",
                "chunk_index": index,
                "chunk_header": "部署",
                "summary": "部署说明",
            },
            hit_id="deploy:%s" % index,
        )
        for index in range(25)
    ]
    rescued_hit = make_hit(
        0.82,
        content="产品经理负责验收活动专题和小程序页面。",
        metadata={
            "title": "验收助手用户.md",
            "source_path": "验收助手用户.md",
            "chunk_index": 25,
            "chunk_header": "使用对象",
            "summary": "产品经理负责验收活动专题和小程序页面。",
        },
        hit_id="user:25",
    )
    service = RagService(
        embeddings=FakeEmbeddings(),
        vector_store=FakeVectorStore(low_hits + [rescued_hit]),
        openai_api_key="",
        openai_base_url="https://example.com/v1",
        openai_model="test-model",
        min_evidence_score=0.3,
    )

    result = service.answer("这个工具主要面向哪些角色？")

    assert "OPENAI_API_KEY" in result["answer"]
    assert result["citations"][0]["title"] == "验收助手用户.md"
    assert result["self_rag"]["status"] == "rescued"
    assert result["self_rag"]["rescue_attempted"] is True
    assert result["self_rag"]["rescued"] is True
    assert result["self_rag"]["initial_best_score"] < 0.3
    assert result["self_rag"]["final_best_score"] >= 0.3
