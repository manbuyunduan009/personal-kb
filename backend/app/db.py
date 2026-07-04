import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional


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
