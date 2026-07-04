import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .chunking import build_chunk_records
from .db import DocumentRepository
from .embeddings import EmbeddingProvider
from .parsers import SUPPORTED_EXTENSIONS, parse_document
from .vector_store import VectorStore


INDEX_SCHEMA_VERSION = "bm25-query-rewrite-v1"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def document_id_for_path(path: Path) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, str(path.resolve()).lower()))


class Indexer:
    def __init__(
        self,
        docs_root: Path,
        repository: DocumentRepository,
        vector_store: VectorStore,
        embeddings: EmbeddingProvider,
    ):
        self.docs_root = docs_root
        self.repository = repository
        self.vector_store = vector_store
        self.embeddings = embeddings

    def scan_files(self) -> List[Path]:
        if not self.docs_root.exists():
            raise FileNotFoundError("DOCS_ROOT does not exist: %s" % self.docs_root)

        files = []
        for path in self.docs_root.rglob("*"):
            if path.is_file() and is_indexable_document(path):
                files.append(path)
        return sorted(files)

    def run(self) -> Dict[str, object]:
        indexed = []
        skipped = []
        failed = []

        for path in self.scan_files():
            try:
                content_hash = "%s:%s" % (file_hash(path), INDEX_SCHEMA_VERSION)
                source_path = str(path.resolve())
                existing = self.repository.get_by_source_path(source_path)
                if existing and existing["content_hash"] == content_hash:
                    skipped.append({"path": source_path, "reason": "unchanged"})
                    continue

                content = parse_document(path).strip()
                chunk_records = build_chunk_records(path.name, content)
                if not chunk_records:
                    skipped.append({"path": source_path, "reason": "empty"})
                    continue

                chunks = [str(record["content"]) for record in chunk_records]
                embedding_texts = [str(record["embedding_text"]) for record in chunk_records]
                vectors = self.embeddings.embed(embedding_texts)
                document_id = document_id_for_path(path)
                self.vector_store.replace_document_chunks(
                    document_id=document_id,
                    chunks=chunks,
                    embeddings=vectors,
                    metadata={
                        "title": path.name,
                        "source_path": source_path,
                        "file_type": path.suffix.lower(),
                        "index_version": INDEX_SCHEMA_VERSION,
                    },
                    chunk_metadatas=[
                        {
                            "chunk_header": record["chunk_header"],
                            "document_facts": record["document_facts"],
                            "chunk_facts": record["chunk_facts"],
                            "field_facts": record["field_facts"],
                            "generated_questions": record["generated_questions"],
                            "previous_context": record["previous_context"],
                            "next_context": record["next_context"],
                            "parent_index": record["parent_index"],
                            "parent_context": record["parent_context"],
                            "context_summary": record["context_summary"],
                        }
                        for record in chunk_records
                    ],
                )

                stat = path.stat()
                self.repository.upsert_document(
                    {
                        "id": document_id,
                        "title": path.name,
                        "source_path": source_path,
                        "file_type": path.suffix.lower(),
                        "content_hash": content_hash,
                        "last_modified": stat.st_mtime,
                        "chunk_count": len(chunks),
                        "indexed_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                        "content_preview": content[:1200],
                    }
                )
                indexed.append({"path": source_path, "chunks": len(chunks)})
            except Exception as exc:
                failed.append({"path": str(path), "error": str(exc)})

        return {
            "docs_root": str(self.docs_root),
            "indexed": indexed,
            "skipped": skipped,
            "failed": failed,
        }


def is_indexable_document(path: Path) -> bool:
    if path.name.startswith("~$"):
        return False
    return path.suffix.lower() in SUPPORTED_EXTENSIONS
