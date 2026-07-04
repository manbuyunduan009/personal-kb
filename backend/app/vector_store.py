from pathlib import Path
from typing import Dict, List


class VectorStore:
    def __init__(self, chroma_path: Path):
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("chromadb is not installed. Run: pip install -r requirements.txt") from exc

        chroma_path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(chroma_path))
        self.collection = self.client.get_or_create_collection(
            name="document_chunks",
            metadata={"hnsw:space": "cosine"},
        )

    def replace_document_chunks(
        self,
        document_id: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadata: Dict[str, str],
    ) -> None:
        self.collection.delete(where={"document_id": document_id})
        if not chunks:
            return

        ids = ["%s:%s" % (document_id, index) for index in range(len(chunks))]
        metadatas = []
        for index, chunk in enumerate(chunks):
            item = dict(metadata)
            item["document_id"] = document_id
            item["chunk_index"] = index
            item["summary"] = chunk[:180]
            metadatas.append(item)

        self.collection.upsert(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def search(self, query_embedding: List[float], limit: int = 5) -> List[Dict[str, object]]:
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["documents", "metadatas", "distances"],
        )
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        hits = []
        for content, metadata, distance in zip(documents, metadatas, distances):
            hits.append(
                {
                    "content": content,
                    "metadata": metadata,
                    "distance": distance,
                    "score": max(0.0, 1.0 - float(distance)),
                }
            )
        return hits

    def count(self) -> int:
        return self.collection.count()
