import json
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

CREATE TABLE IF NOT EXISTS rag_traces (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    answer_preview TEXT NOT NULL,
    is_refusal INTEGER NOT NULL,
    citation_count INTEGER NOT NULL,
    citation_check_status TEXT NOT NULL DEFAULT '',
    citation_support_score REAL NOT NULL DEFAULT 0,
    citation_checked_claim_count INTEGER NOT NULL DEFAULT 0,
    citation_check_reasons TEXT NOT NULL DEFAULT '[]',
    cited_titles TEXT NOT NULL,
    self_rag_status TEXT NOT NULL,
    rescue_attempted INTEGER NOT NULL,
    rescued INTEGER NOT NULL,
    initial_best_score REAL NOT NULL,
    final_best_score REAL NOT NULL,
    min_evidence_score REAL NOT NULL,
    evidence_count INTEGER NOT NULL,
    rescue_queries TEXT NOT NULL,
    rescue_query_source TEXT NOT NULL DEFAULT '',
    query_rewrite_used_llm INTEGER NOT NULL DEFAULT 0,
    query_rewrite_error TEXT NOT NULL DEFAULT '',
    retrieval_modes TEXT NOT NULL DEFAULT '[]',
    latency_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rag_traces_created_at
ON rag_traces(created_at DESC);
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
            self._ensure_rag_trace_columns(connection)

    def _ensure_rag_trace_columns(self, connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(rag_traces)").fetchall()
        }
        migrations = {
            "rescue_query_source": "ALTER TABLE rag_traces ADD COLUMN rescue_query_source TEXT NOT NULL DEFAULT ''",
            "query_rewrite_used_llm": "ALTER TABLE rag_traces ADD COLUMN query_rewrite_used_llm INTEGER NOT NULL DEFAULT 0",
            "query_rewrite_error": "ALTER TABLE rag_traces ADD COLUMN query_rewrite_error TEXT NOT NULL DEFAULT ''",
            "retrieval_modes": "ALTER TABLE rag_traces ADD COLUMN retrieval_modes TEXT NOT NULL DEFAULT '[]'",
            "citation_check_status": "ALTER TABLE rag_traces ADD COLUMN citation_check_status TEXT NOT NULL DEFAULT ''",
            "citation_support_score": "ALTER TABLE rag_traces ADD COLUMN citation_support_score REAL NOT NULL DEFAULT 0",
            "citation_checked_claim_count": "ALTER TABLE rag_traces ADD COLUMN citation_checked_claim_count INTEGER NOT NULL DEFAULT 0",
            "citation_check_reasons": "ALTER TABLE rag_traces ADD COLUMN citation_check_reasons TEXT NOT NULL DEFAULT '[]'",
        }
        for column, statement in migrations.items():
            if column not in columns:
                connection.execute(statement)

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

    def add_rag_trace(self, question: str, result: Dict[str, object], latency_ms: int) -> Dict[str, object]:
        self_rag = result.get("self_rag", {}) if isinstance(result.get("self_rag", {}), dict) else {}
        citations = result.get("citations", []) if isinstance(result.get("citations", []), list) else []
        citation_check = result.get("citation_check", {})
        citation_check = citation_check if isinstance(citation_check, dict) else {}
        citation_check_reasons = citation_check.get("reasons", [])
        if not isinstance(citation_check_reasons, list):
            citation_check_reasons = [str(citation_check_reasons)]
        answer = str(result.get("answer", ""))
        cited_titles = []
        for citation in citations:
            if isinstance(citation, dict):
                title = str(citation.get("title", ""))
                if title and title not in cited_titles:
                    cited_titles.append(title)

        status = str(self_rag.get("status", "unknown"))
        trace = {
            "id": str(uuid.uuid4()),
            "question": question.strip(),
            "answer_preview": answer[:240],
            "is_refusal": int(status.startswith("insufficient") or ("文档中没有找到依据" in answer and not citations)),
            "citation_count": len(citations),
            "citation_check_status": str(citation_check.get("status", "")),
            "citation_support_score": float(citation_check.get("support_score", 0.0) or 0.0),
            "citation_checked_claim_count": int(citation_check.get("checked_claim_count", 0) or 0),
            "citation_check_reasons": json.dumps(citation_check_reasons, ensure_ascii=False),
            "cited_titles": json.dumps(cited_titles, ensure_ascii=False),
            "self_rag_status": status,
            "rescue_attempted": int(bool(self_rag.get("rescue_attempted", False))),
            "rescued": int(bool(self_rag.get("rescued", False))),
            "initial_best_score": float(self_rag.get("initial_best_score", 0.0)),
            "final_best_score": float(self_rag.get("final_best_score", 0.0)),
            "min_evidence_score": float(self_rag.get("min_evidence_score", 0.0)),
            "evidence_count": int(self_rag.get("evidence_count", 0)),
            "rescue_queries": json.dumps(self_rag.get("rescue_queries", []), ensure_ascii=False),
            "rescue_query_source": str(self_rag.get("rescue_query_source", "")),
            "query_rewrite_used_llm": int(bool(self_rag.get("query_rewrite_used_llm", False))),
            "query_rewrite_error": str(self_rag.get("query_rewrite_error", "")),
            "retrieval_modes": json.dumps(self_rag.get("retrieval_modes", []), ensure_ascii=False),
            "latency_ms": latency_ms,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO rag_traces (
                    id, question, answer_preview, is_refusal, citation_count,
                    citation_check_status, citation_support_score,
                    citation_checked_claim_count, citation_check_reasons,
                    cited_titles, self_rag_status, rescue_attempted, rescued,
                    initial_best_score, final_best_score, min_evidence_score,
                    evidence_count, rescue_queries, rescue_query_source,
                    query_rewrite_used_llm, query_rewrite_error, retrieval_modes,
                    latency_ms, created_at
                )
                VALUES (
                    :id, :question, :answer_preview, :is_refusal, :citation_count,
                    :citation_check_status, :citation_support_score,
                    :citation_checked_claim_count, :citation_check_reasons,
                    :cited_titles, :self_rag_status, :rescue_attempted, :rescued,
                    :initial_best_score, :final_best_score, :min_evidence_score,
                    :evidence_count, :rescue_queries, :rescue_query_source,
                    :query_rewrite_used_llm, :query_rewrite_error, :retrieval_modes,
                    :latency_ms, :created_at
                )
                """,
                trace,
            )
        return self._decode_trace(trace)

    def list_rag_traces(self, limit: int = 20) -> List[Dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id, question, answer_preview, is_refusal, citation_count,
                    citation_check_status, citation_support_score,
                    citation_checked_claim_count, citation_check_reasons,
                    cited_titles, self_rag_status, rescue_attempted, rescued,
                    initial_best_score, final_best_score, min_evidence_score,
                    evidence_count, rescue_queries, rescue_query_source,
                    query_rewrite_used_llm, query_rewrite_error, retrieval_modes,
                    latency_ms, created_at
                FROM rag_traces
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._decode_trace(dict(row)) for row in rows]

    @staticmethod
    def _decode_trace(trace: Dict[str, object]) -> Dict[str, object]:
        decoded = dict(trace)
        decoded["is_refusal"] = bool(decoded.get("is_refusal"))
        decoded["rescue_attempted"] = bool(decoded.get("rescue_attempted"))
        decoded["rescued"] = bool(decoded.get("rescued"))
        decoded["query_rewrite_used_llm"] = bool(decoded.get("query_rewrite_used_llm"))
        decoded["cited_titles"] = json.loads(str(decoded.get("cited_titles") or "[]"))
        decoded["rescue_queries"] = json.loads(str(decoded.get("rescue_queries") or "[]"))
        decoded["retrieval_modes"] = json.loads(str(decoded.get("retrieval_modes") or "[]"))
        decoded["citation_check_reasons"] = json.loads(str(decoded.get("citation_check_reasons") or "[]"))
        return decoded
