import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_path TEXT NOT NULL UNIQUE,
    file_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    last_modified REAL NOT NULL,
    chunk_count INTEGER NOT NULL,
    indexed_at TEXT NOT NULL,
    content_preview TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    source_path TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_header TEXT NOT NULL DEFAULT '',
    rating INTEGER NOT NULL CHECK (rating IN (-1, 1)),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_feedback_chunk
ON feedback(source_path, chunk_index);

CREATE INDEX IF NOT EXISTS idx_feedback_question
ON feedback(question);
"""


class DocumentRepository:
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

    def upsert_document(self, document: Dict[str, object]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    id, title, source_path, file_type, content_hash,
                    last_modified, chunk_count, indexed_at, content_preview
                )
                VALUES (
                    :id, :title, :source_path, :file_type, :content_hash,
                    :last_modified, :chunk_count, :indexed_at, :content_preview
                )
                ON CONFLICT(source_path) DO UPDATE SET
                    id = excluded.id,
                    title = excluded.title,
                    file_type = excluded.file_type,
                    content_hash = excluded.content_hash,
                    last_modified = excluded.last_modified,
                    chunk_count = excluded.chunk_count,
                    indexed_at = excluded.indexed_at,
                    content_preview = excluded.content_preview
                """,
                document,
            )

    def list_documents(self) -> List[Dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, source_path, file_type, content_hash,
                       last_modified, chunk_count, indexed_at, content_preview
                FROM documents
                ORDER BY indexed_at DESC, title ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_document(self, document_id: str) -> Optional[Dict[str, object]]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, title, source_path, file_type, content_hash,
                       last_modified, chunk_count, indexed_at, content_preview
                FROM documents
                WHERE id = ?
                """,
                (document_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_by_source_path(self, source_path: str) -> Optional[Dict[str, object]]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, title, source_path, file_type, content_hash,
                       last_modified, chunk_count, indexed_at, content_preview
                FROM documents
                WHERE source_path = ?
                """,
                (source_path,),
            ).fetchone()
        return dict(row) if row else None

    def add_feedback(
        self,
        question: str,
        source_path: str,
        chunk_index: int,
        chunk_header: str,
        rating: int,
        note: str = "",
    ) -> Dict[str, object]:
        feedback = {
            "id": str(uuid.uuid4()),
            "question": question.strip(),
            "source_path": source_path,
            "chunk_index": chunk_index,
            "chunk_header": chunk_header or "",
            "rating": rating,
            "note": note.strip(),
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO feedback (
                    id, question, source_path, chunk_index,
                    chunk_header, rating, note, created_at
                )
                VALUES (
                    :id, :question, :source_path, :chunk_index,
                    :chunk_header, :rating, :note, :created_at
                )
                """,
                feedback,
            )
        return feedback

    def feedback_summary(self) -> List[Dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    source_path,
                    chunk_index,
                    MAX(chunk_header) AS chunk_header,
                    SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) AS helpful_count,
                    SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END) AS unhelpful_count,
                    SUM(rating) AS feedback_score,
                    COUNT(*) AS total_count
                FROM feedback
                GROUP BY source_path, chunk_index
                ORDER BY feedback_score DESC, total_count DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def feedback_scores(self) -> Dict[Tuple[str, int], float]:
        scores = {}
        for row in self.feedback_summary():
            scores[(str(row["source_path"]), int(row["chunk_index"]))] = float(row["feedback_score"])
        return scores
