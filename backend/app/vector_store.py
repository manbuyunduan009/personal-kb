import json
import math
import re
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

CREATE TABLE IF NOT EXISTS document_chunks_keyword (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    search_text TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_keyword_document_id
ON document_chunks_keyword(document_id);
"""


FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    search_text
);
"""

KEYWORD_METADATA_KEYS = (
    "title",
    "source_path",
    "file_type",
    "chunk_header",
    "document_facts",
    "chunk_facts",
    "field_facts",
    "generated_questions",
    "context_summary",
)


class VectorStore:
    """Small local vector store for teaching and personal docs.

    It stores embeddings in SQLite and performs cosine similarity in Python.
    This is not meant for huge corpora, but it avoids native SQLite extension
    issues and keeps the first RAG version easy to inspect.
    """

    def __init__(self, sqlite_path: Path):
        self.sqlite_path = sqlite_path
        self.fts_enabled = False
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
            self.fts_enabled = self._init_fts_schema(connection)

    def _init_fts_schema(self, connection: sqlite3.Connection) -> bool:
        try:
            connection.executescript(FTS_SCHEMA)
            return True
        except sqlite3.OperationalError:
            return False

    def replace_document_chunks(
        self,
        document_id: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadata: Dict[str, object],
        chunk_metadatas: Optional[List[Dict[str, object]]] = None,
    ) -> None:
        with self.connect() as connection:
            self._delete_document_chunks(connection, document_id)
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                item = dict(metadata)
                if chunk_metadatas and index < len(chunk_metadatas):
                    item.update(chunk_metadatas[index])
                item["document_id"] = document_id
                item["chunk_index"] = index
                item["summary"] = item.get("context_summary", chunk[:180])
                chunk_id = "%s:%s" % (document_id, index)
                connection.execute(
                    """
                    INSERT INTO document_chunks (id, document_id, content, embedding, metadata)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        document_id,
                        chunk,
                        json.dumps(embedding),
                        json.dumps(item, ensure_ascii=False),
                    ),
                )
                search_text = build_keyword_search_text(chunk, item)
                connection.execute(
                    """
                    INSERT INTO document_chunks_keyword (chunk_id, document_id, search_text)
                    VALUES (?, ?, ?)
                    """,
                    (chunk_id, document_id, search_text),
                )
                if self.fts_enabled:
                    self._insert_fts_row(connection, chunk_id, document_id, search_text)

    def delete_document_chunks(self, document_id: str) -> None:
        with self.connect() as connection:
            self._delete_document_chunks(connection, document_id)

    def _delete_document_chunks(self, connection: sqlite3.Connection, document_id: str) -> None:
        connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
        connection.execute(
            "DELETE FROM document_chunks_keyword WHERE document_id = ?", (document_id,)
        )
        if self.fts_enabled:
            try:
                connection.execute("DELETE FROM document_chunks_fts WHERE document_id = ?", (document_id,))
            except sqlite3.OperationalError:
                self.fts_enabled = False

    def _insert_fts_row(
        self,
        connection: sqlite3.Connection,
        chunk_id: str,
        document_id: str,
        search_text: str,
    ) -> None:
        try:
            connection.execute(
                """
                INSERT INTO document_chunks_fts (chunk_id, document_id, search_text)
                VALUES (?, ?, ?)
                """,
                (chunk_id, document_id, search_text),
            )
        except sqlite3.OperationalError:
            self.fts_enabled = False

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

    def keyword_search(self, query: str, limit: int = 5) -> List[Dict[str, object]]:
        terms = build_keyword_terms(query)
        if not terms or limit <= 0:
            return []

        with self.connect() as connection:
            if self.fts_enabled:
                try:
                    return self._fts_keyword_search(connection, terms, limit)
                except sqlite3.OperationalError:
                    self.fts_enabled = False
            return self._fallback_keyword_search(connection, terms, limit)

    def _fts_keyword_search(
        self,
        connection: sqlite3.Connection,
        terms: List[str],
        limit: int,
    ) -> List[Dict[str, object]]:
        match_query = " OR ".join(quote_fts_term(term) for term in terms[:32])
        rows = connection.execute(
            """
            SELECT
                document_chunks.id,
                document_chunks.content,
                document_chunks.metadata,
                document_chunks_keyword.search_text,
                bm25(document_chunks_fts) AS bm25_score
            FROM document_chunks_fts
            JOIN document_chunks ON document_chunks.id = document_chunks_fts.chunk_id
            JOIN document_chunks_keyword ON document_chunks_keyword.chunk_id = document_chunks.id
            WHERE document_chunks_fts MATCH ?
            ORDER BY bm25_score ASC
            LIMIT ?
            """,
            (match_query, limit),
        ).fetchall()
        return [keyword_hit_from_row(row, terms, "fts5") for row in rows]

    def _fallback_keyword_search(
        self,
        connection: sqlite3.Connection,
        terms: List[str],
        limit: int,
    ) -> List[Dict[str, object]]:
        rows = connection.execute(
            """
            SELECT
                document_chunks.id,
                document_chunks.content,
                document_chunks.metadata,
                document_chunks_keyword.search_text
            FROM document_chunks_keyword
            JOIN document_chunks ON document_chunks.id = document_chunks_keyword.chunk_id
            """
        ).fetchall()
        hits = [keyword_hit_from_row(row, terms, "fallback") for row in rows]
        hits = [hit for hit in hits if hit["keyword_recall_score"] > 0]
        hits.sort(key=lambda item: item["keyword_recall_score"], reverse=True)
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


def build_keyword_search_text(content: str, metadata: Dict[str, object]) -> str:
    parts = [content]
    for key in KEYWORD_METADATA_KEYS:
        value = metadata.get(key)
        if value is not None:
            parts.extend(flatten_keyword_value(value))
    raw_text = " ".join(part for part in parts if part)
    terms = build_keyword_terms(raw_text)
    return "%s %s" % (raw_text, " ".join(terms))


def flatten_keyword_value(value: object) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        items = []
        for key, item in value.items():
            items.append(str(key))
            items.extend(flatten_keyword_value(item))
        return items
    if isinstance(value, list):
        items = []
        for item in value:
            items.extend(flatten_keyword_value(item))
        return items
    return [str(value)]


def build_keyword_terms(text: str) -> List[str]:
    normalized = text.lower()
    raw_tokens = re.findall(r"[\w\u4e00-\u9fff#.-]+", normalized, flags=re.UNICODE)
    terms = []
    seen = set()
    for token in raw_tokens:
        for term in expand_keyword_token(token):
            if term and term not in seen:
                terms.append(term)
                seen.add(term)
    return terms


def expand_keyword_token(token: str) -> List[str]:
    if len(token) <= 1:
        return []
    terms = []
    if len(token) <= 32:
        terms.append(token)
    if contains_cjk(token):
        for size in (2, 3):
            if len(token) >= size:
                terms.extend(token[index : index + size] for index in range(len(token) - size + 1))
    return terms


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def quote_fts_term(term: str) -> str:
    return '"%s"' % term.replace('"', '""')


def keyword_hit_from_row(
    row: sqlite3.Row,
    terms: List[str],
    backend: str,
) -> Dict[str, object]:
    search_text = row["search_text"].lower()
    matched_terms = [term for term in terms if term in search_text]
    recall_score = len(matched_terms) / len(terms) if terms else 0.0
    hit = {
        "id": row["id"],
        "content": row["content"],
        "metadata": json.loads(row["metadata"]),
        "keyword_recall_score": recall_score,
        "keyword_backend": backend,
        "matched_keywords": matched_terms[:12],
    }
    if "bm25_score" in row.keys():
        hit["bm25_score"] = float(row["bm25_score"])
    return hit
