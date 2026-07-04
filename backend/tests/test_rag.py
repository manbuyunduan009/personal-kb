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


def make_hit(score, content="目标用户是专题产品经理", metadata=None):
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
        "id": "doc-1:0",
        "content": content,
        "metadata": base_metadata,
        "score": score,
    }


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
