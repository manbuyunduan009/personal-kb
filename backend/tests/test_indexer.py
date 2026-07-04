from pathlib import Path

from app.db import DocumentRepository
from app.embeddings import HashEmbeddingProvider
from app.indexer import Indexer, is_indexable_document
from app.vector_store import VectorStore, cosine_similarity


class FakeEmbeddings:
    def embed(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]


class FakeVectorStore:
    def __init__(self):
        self.replacements = []

    def replace_document_chunks(self, document_id, chunks, embeddings, metadata, chunk_metadatas=None):
        self.replacements.append(
            {
                "document_id": document_id,
                "chunks": chunks,
                "embeddings": embeddings,
                "metadata": metadata,
                "chunk_metadatas": chunk_metadatas or [],
            }
        )


def test_indexer_skips_unchanged_files(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("专题验收助手" * 100, encoding="utf-8")

    repository = DocumentRepository(tmp_path / "kb.sqlite3")
    vector_store = FakeVectorStore()
    indexer = Indexer(docs, repository, vector_store, FakeEmbeddings())

    first = indexer.run()
    second = indexer.run()

    assert len(first["indexed"]) == 1
    assert len(second["skipped"]) == 1
    assert second["skipped"][0]["reason"] == "unchanged"


def test_indexer_writes_parent_chunk_metadata(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("A" * 1900, encoding="utf-8")

    repository = DocumentRepository(tmp_path / "kb.sqlite3")
    vector_store = FakeVectorStore()
    indexer = Indexer(docs, repository, vector_store, FakeEmbeddings())

    result = indexer.run()

    assert len(result["indexed"]) == 1
    replacement = vector_store.replacements[0]
    chunk_metadatas = replacement["chunk_metadatas"]
    assert len(chunk_metadatas) > 1
    assert chunk_metadatas[0]["parent_index"] == 0
    assert chunk_metadatas[0]["parent_context"]
    assert all("parent_context" in metadata for metadata in chunk_metadatas)


def test_indexer_ignores_office_temporary_files():
    assert not is_indexable_document(Path("~$需求文档.docx"))
    assert not is_indexable_document(Path("~$进度计划.xlsx"))
    assert is_indexable_document(Path("需求文档.docx"))


def test_vector_store_returns_most_similar_chunk(tmp_path: Path):
    store = VectorStore(tmp_path / "vectors.sqlite3")
    store.replace_document_chunks(
        document_id="doc-1",
        chunks=["目标用户是产品经理", "部署说明和环境变量"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        metadata={"title": "a.md", "source_path": "a.md", "file_type": ".md"},
    )

    hits = store.search([0.9, 0.1], limit=1)

    assert hits[0]["content"] == "目标用户是产品经理"
    assert hits[0]["metadata"]["chunk_index"] == 0


def test_vector_store_persists_parent_chunk_metadata(tmp_path: Path):
    store = VectorStore(tmp_path / "vectors.sqlite3")
    store.replace_document_chunks(
        document_id="doc-1",
        chunks=["child one", "child two"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        metadata={"title": "a.md", "source_path": "a.md", "file_type": ".md"},
        chunk_metadatas=[
            {"parent_index": 0, "parent_context": "parent child one child two"},
            {"parent_index": 0, "parent_context": "parent child one child two"},
        ],
    )

    hits = store.search([0.9, 0.1], limit=1)

    assert hits[0]["metadata"]["chunk_index"] == 0
    assert hits[0]["metadata"]["parent_index"] == 0
    assert hits[0]["metadata"]["parent_context"] == "parent child one child two"


def test_hash_embedding_scores_related_text_higher():
    embeddings = HashEmbeddingProvider()
    query, related, unrelated = embeddings.embed(
        ["目标用户是谁", "核心目标用户是产品经理", "部署说明和环境变量"]
    )

    assert cosine_similarity(query, related) > cosine_similarity(query, unrelated)
