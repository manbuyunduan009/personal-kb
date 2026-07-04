from typing import Dict, List

from openai import OpenAI, OpenAIError

from .embeddings import EmbeddingProvider
from .vector_store import VectorStore


class RagService:
    def __init__(
        self,
        embeddings: EmbeddingProvider,
        vector_store: VectorStore,
        openai_api_key: str,
        openai_base_url: str,
        openai_model: str,
    ):
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.openai_api_key = openai_api_key
        self.openai_base_url = openai_base_url
        self.openai_model = openai_model

    def search(self, query: str, limit: int = 5) -> List[Dict[str, object]]:
        query = query.strip()
        if not query:
            return []
        query_vector = self.embeddings.embed([query])[0]
        return self.vector_store.search(query_vector, limit=limit)

    def answer(self, question: str) -> Dict[str, object]:
        hits = self.search(question, limit=5)
        citations = [self._citation_from_hit(hit) for hit in hits]

        if not self.openai_api_key:
            return {
                "answer": "OPENAI_API_KEY is not configured. Semantic search is available, but AI answers need an OpenAI-compatible API key.",
                "citations": citations,
            }

        context = "\n\n".join(
            "[Source %s]\nFile: %s\nChunk: %s\n%s"
            % (
                index + 1,
                citation["source_path"],
                citation["chunk_index"],
                hit["content"],
            )
            for index, (hit, citation) in enumerate(zip(hits, citations))
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

    @staticmethod
    def _citation_from_hit(hit: Dict[str, object]) -> Dict[str, object]:
        metadata = hit["metadata"]
        return {
            "title": metadata.get("title", ""),
            "source_path": metadata.get("source_path", ""),
            "file_type": metadata.get("file_type", ""),
            "chunk_index": metadata.get("chunk_index", 0),
            "summary": metadata.get("summary", ""),
            "score": hit.get("score", 0.0),
        }
