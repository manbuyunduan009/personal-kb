from pathlib import Path

from app.db import DocumentRepository
from app.indexer import Indexer


class FakeEmbeddings:
    def embed(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]


class FakeVectorStore:
    def __init__(self):
        self.replacements = []

    def replace_document_chunks(self, document_id, chunks, embeddings, metadata):
        self.replacements.append(
            {
                "document_id": document_id,
                "chunks": chunks,
                "embeddings": embeddings,
                "metadata": metadata,
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
