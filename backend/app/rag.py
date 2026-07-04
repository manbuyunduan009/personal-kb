from typing import Dict, List, Optional, Tuple

from openai import OpenAI, OpenAIError

from .embeddings import EmbeddingProvider
from .retrieval import compress_context, query_variants, rerank_hits
from .vector_store import VectorStore


INSUFFICIENT_EVIDENCE_MESSAGE = (
    "文档中没有找到依据。当前检索结果相关度低于证据阈值，"
    "已停止调用 AI 生成回答。"
)


class RagService:
    def __init__(
        self,
        embeddings: EmbeddingProvider,
        vector_store: VectorStore,
        openai_api_key: str,
        openai_base_url: str,
        openai_model: str,
        feedback_scores: Optional[Dict[Tuple[str, int], float]] = None,
        min_evidence_score: float = 0.3,
    ):
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.openai_api_key = openai_api_key
        self.openai_base_url = openai_base_url
        self.openai_model = openai_model
        self.feedback_scores = feedback_scores or {}
        self.min_evidence_score = min_evidence_score

    def search(self, query: str, limit: int = 5) -> List[Dict[str, object]]:
        query = query.strip()
        if not query:
            return []

        variants = query_variants(query)
        query_vectors = self.embeddings.embed(variants)
        expanded_limit = max(limit * 4, 20)
        merged: Dict[str, Dict[str, object]] = {}

        for variant, query_vector in zip(variants, query_vectors):
            for hit in self.vector_store.search(query_vector, limit=expanded_limit):
                key = str(hit.get("id") or "%s:%s" % (
                    hit["metadata"].get("document_id", ""),
                    hit["metadata"].get("chunk_index", ""),
                ))
                existing = merged.get(key)
                if existing is None or hit.get("score", 0.0) > existing.get("score", 0.0):
                    item = dict(hit)
                    item["matched_query"] = variant
                    merged[key] = item

        return rerank_hits(query, list(merged.values()), limit=limit, feedback_scores=self.feedback_scores)

    def answer(self, question: str) -> Dict[str, object]:
        hits = self.search(question, limit=5)
        evidence_hits = self._evidence_hits(hits)
        citations = [self._citation_from_hit(hit) for hit in evidence_hits]

        if not evidence_hits:
            best_score = max((float(hit.get("score", 0.0)) for hit in hits), default=0.0)
            return {
                "answer": "%s 最高相关度 %.2f，阈值 %.2f。"
                % (INSUFFICIENT_EVIDENCE_MESSAGE, best_score, self.min_evidence_score),
                "citations": [],
            }

        if not self.openai_api_key:
            return {
                "answer": "OPENAI_API_KEY is not configured. Semantic search is available, but AI answers need an OpenAI-compatible API key.",
                "citations": citations,
            }

        context = "\n\n".join(
            "[Source %s]\nFile: %s\nChunk: %s\nHeader: %s\n%s"
            % (
                index + 1,
                citation["source_path"],
                citation["chunk_index"],
                citation["chunk_header"],
                self._context_from_hit(question, hit),
            )
            for index, (hit, citation) in enumerate(zip(evidence_hits, citations))
        )

        client = OpenAI(api_key=self.openai_api_key, base_url=self.openai_base_url)
        try:
            response = client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是个人知识库问答助手。只能根据用户提供的资料回答。"
                            "回答前先判断资料是否直接支持问题，不要因为词语相似就硬答。"
                            "如果资料中没有依据，明确回答“文档中没有找到依据”。"
                            "回答要简洁，并在关键结论后标注来源编号。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": "资料：\n%s\n\n问题：%s" % (context or "无检索结果", question),
                    },
                ],
            )
        except OpenAIError as exc:
            return {
                "answer": "AI 调用失败：%s" % str(exc),
                "citations": citations,
            }
        return {
            "answer": response.choices[0].message.content or "",
            "citations": citations,
        }

    def _evidence_hits(self, hits: List[Dict[str, object]]) -> List[Dict[str, object]]:
        return [
            hit
            for hit in hits
            if float(hit.get("score", 0.0)) >= self.min_evidence_score
        ]

    @staticmethod
    def _citation_from_hit(hit: Dict[str, object]) -> Dict[str, object]:
        metadata = hit["metadata"]
        return {
            "title": metadata.get("title", ""),
            "source_path": metadata.get("source_path", ""),
            "file_type": metadata.get("file_type", ""),
            "chunk_index": metadata.get("chunk_index", 0),
            "chunk_header": metadata.get("chunk_header", ""),
            "summary": metadata.get("summary", ""),
            "score": hit.get("score", 0.0),
            "feedback_score": hit.get("feedback_score", 0.0),
        }

    @staticmethod
    def _context_from_hit(question: str, hit: Dict[str, object]) -> str:
        metadata = hit["metadata"]
        parts = []
        if metadata.get("previous_context"):
            parts.append("上文窗口：%s" % metadata["previous_context"])
        parts.append("命中片段：%s" % hit["content"])
        if metadata.get("next_context"):
            parts.append("下文窗口：%s" % metadata["next_context"])
        return compress_context(question, "\n".join(parts), max_chars=900)
