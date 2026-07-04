from pathlib import Path

from app.vector_store import VectorStore, build_keyword_terms


def test_keyword_search_matches_content(tmp_path: Path):
    store = VectorStore(tmp_path / "vectors.sqlite3")
    store.replace_document_chunks(
        document_id="doc-1",
        chunks=["Alpha project has offline event requirements", "Deployment notes only"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        metadata={"title": "requirements.md", "source_path": "requirements.md", "file_type": ".md"},
    )

    hits = store.keyword_search("offline event", limit=3)

    assert hits
    assert hits[0]["id"] == "doc-1:0"
    assert hits[0]["content"] == "Alpha project has offline event requirements"
    assert hits[0]["keyword_recall_score"] > 0
    assert "keyword_backend" in hits[0]
    assert "bm25_score" in hits[0] or hits[0]["keyword_backend"] == "fallback"


def test_keyword_search_matches_metadata_title(tmp_path: Path):
    store = VectorStore(tmp_path / "vectors.sqlite3")
    store.replace_document_chunks(
        document_id="doc-1",
        chunks=["This chunk only says schedule and owner."],
        embeddings=[[1.0, 0.0]],
        metadata={
            "title": "AlphaProject launch plan.docx",
            "source_path": "docs/AlphaProject launch plan.docx",
            "file_type": ".docx",
        },
    )

    hits = store.keyword_search("AlphaProject owner", limit=1)

    assert hits[0]["id"] == "doc-1:0"
    assert "alphaproject" in hits[0]["matched_keywords"]


def test_keyword_search_supports_cjk_ngrams(tmp_path: Path):
    store = VectorStore(tmp_path / "vectors.sqlite3")
    store.replace_document_chunks(
        document_id="doc-1",
        chunks=["需求基础信息：项目部门所属 K1-剑网3"],
        embeddings=[[1.0, 0.0]],
        metadata={
            "title": "剑网3十七周年庆线下活动小程序.docx",
            "source_path": "docs/剑网3十七周年庆线下活动小程序.docx",
            "file_type": ".docx",
        },
    )

    hits = store.keyword_search("周年庆是哪个项目", limit=1)

    assert hits[0]["id"] == "doc-1:0"
    assert "周年" in hits[0]["matched_keywords"] or "年庆" in hits[0]["matched_keywords"]


def test_keyword_index_is_replaced_with_document_chunks(tmp_path: Path):
    store = VectorStore(tmp_path / "vectors.sqlite3")
    store.replace_document_chunks(
        document_id="doc-1",
        chunks=["old keyword"],
        embeddings=[[1.0, 0.0]],
        metadata={"title": "old.md", "source_path": "old.md", "file_type": ".md"},
    )
    store.replace_document_chunks(
        document_id="doc-1",
        chunks=["new keyword"],
        embeddings=[[0.0, 1.0]],
        metadata={"title": "new.md", "source_path": "new.md", "file_type": ".md"},
    )

    assert store.keyword_search("old", limit=1) == []
    hits = store.keyword_search("new keyword", limit=1)
    assert hits[0]["id"] == "doc-1:0"
    assert hits[0]["content"] == "new keyword"


def test_delete_document_chunks_clears_keyword_index(tmp_path: Path):
    store = VectorStore(tmp_path / "vectors.sqlite3")
    store.replace_document_chunks(
        document_id="doc-1",
        chunks=["temporary keyword"],
        embeddings=[[1.0, 0.0]],
        metadata={"title": "temp.md", "source_path": "temp.md", "file_type": ".md"},
    )

    store.delete_document_chunks("doc-1")

    assert store.count() == 0
    assert store.keyword_search("temporary keyword", limit=1) == []


def test_keyword_search_falls_back_without_fts(tmp_path: Path):
    store = VectorStore(tmp_path / "vectors.sqlite3")
    store.fts_enabled = False
    store.replace_document_chunks(
        document_id="doc-1",
        chunks=["fallback keyword"],
        embeddings=[[1.0, 0.0]],
        metadata={"title": "fallback.md", "source_path": "fallback.md", "file_type": ".md"},
    )

    hits = store.keyword_search("fallback keyword", limit=1)

    assert hits[0]["id"] == "doc-1:0"
    assert hits[0]["keyword_backend"] == "fallback"
    assert "bm25_score" not in hits[0]


def test_build_keyword_terms_expands_cjk_terms():
    terms = build_keyword_terms("周年庆项目")

    assert "周年" in terms
    assert "年庆" in terms
    assert "项目" in terms
