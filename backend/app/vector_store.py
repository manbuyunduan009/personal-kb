import json
import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding TEXT NOT NULL,
    metadata TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
ON document_chunks(document_id);
"""


class VectorStore:
    """Small local vector store for teaching and personal docs.

    It stores embeddings in SQLite and performs cosine similarity in Python.
    This is not meant for huge corpora, but it avoids native SQLite extension
    issues and keeps the first RAG version easy to inspect.
    """

    def __init__(self, sqlite_path: Path):
        self.sqlite_path = sqlite_path
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.sqlite_path))
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def replace_document_chunks(
        self,
        document_id: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadata: Dict[str, object],
        chunk_metadatas: Optional[List[Dict[str, object]]] = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                item = dict(metadata)
                if chunk_metadatas and index < len(chunk_metadatas):
                    item.update(chunk_metadatas[index])
                item["document_id"] = document_id
                item["chunk_index"] = index
                item["summary"] = item.get("context_summary", chunk[:180])
                connection.execute(
                    """
                    INSERT INTO document_chunks (id, document_id, content, embedding, metadata)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        "%s:%s" % (document_id, index),
                        document_id,
                        chunk,
                        json.dumps(embedding),
                        json.dumps(item, ensure_ascii=False),
                    ),
                )

    def search(self, query_embedding: List[float], limit: int = 5) -> List[Dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, content, embedding, metadata FROM document_chunks"
            ).fetchall()

        hits = []
        for row in rows:
            embedding = json.loads(row["embedding"])
            score = cosine_similarity(query_embedding, embedding)
            hits.append(
                {
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata"]),
                    "distance": 1.0 - score,
                    "score": score,
                }
            )

        hits.sort(key=lambda item: item["score"], reverse=True)
        return hits[:limit]

    def list_chunks(self) -> List[Dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, content, metadata FROM document_chunks"
            ).fetchall()

        return [
            {
                "id": row["id"],
                "content": row["content"],
                "metadata": json.loads(row["metadata"]),
            }
            for row in rows
        ]

    def count(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM document_chunks").fetchone()
        return int(row["count"])


def cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
