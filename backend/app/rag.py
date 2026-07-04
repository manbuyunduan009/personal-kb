from typing import Dict, List, Optional, Tuple

from openai import OpenAI, OpenAIError

from .embeddings import EmbeddingProvider
from .retrieval import compress_context, format_field_facts, keyword_recall_hits, query_variants, rerank_hits
from .vector_store import VectorStore


INSUFFICIENT_EVIDENCE_MESSAGE = (
    "文档中没有找到依据。当前检索结果相关度低于证据阈值，"
    "已停止调用 AI 生成回答。"
)
FIELD_LOOKUP_MARKERS = [
    "哪个",
    "哪些",
    "什么",
    "多少",
    "谁",
    "何时",
    "什么时候",
    "日期",
    "时间",
    "属于",
    "所属",
    "负责人",
    "对接人",
    "联系人",
    "项目",
    "部门",
    "游戏",
    "产品",
    "域名",
    "编号",
    "单号",
    "基础信息",
]
FIELD_EVIDENCE_GROUPS = [
    (["项目", "所属", "部门", "游戏", "产品"], ["项目", "所属", "属于", "部门", "游戏", "产品", "哪个", "什么"]),
    (["对接人", "负责人", "联系人"], ["谁", "对接人", "负责人", "联系人"]),
    (["日期", "时间", "排期", "完成"], ["何时", "什么时候", "日期", "时间", "排期", "完成"]),
    (["域名", "网址", "链接"], ["域名", "网址", "链接"]),
    (["编号", "单号", "worktile"], ["编号", "单号", "worktile"]),
]
CHILD_CONTEXT_MAX_CHARS = 900
PARENT_CONTEXT_MAX_CHARS = 1200


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
        return self._search_with_variants(
            original_query=query,
            variants=variants,
            limit=limit,
            expanded_limit=max(limit * 4, 20),
        )

    def _search_with_variants(
        self,
        original_query: str,
        variants: List[str],
        limit: int,
        expanded_limit: int,
    ) -> List[Dict[str, object]]:
        query_vectors = self.embeddings.embed(variants)
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
                    item["vector_recall_score"] = hit.get("score", 0.0)
                    item["retrieval_mode"] = "vector"
                    item["matched_query"] = variant
                    merged[key] = item
                elif existing is not None:
                    existing["vector_recall_score"] = max(
                        float(existing.get("vector_recall_score", 0.0)),
                        float(hit.get("score", 0.0)),
                    )

        all_chunks = self.vector_store.list_chunks()
        for variant in variants:
            for hit in keyword_recall_hits(variant, all_chunks, limit=expanded_limit):
                key = str(hit.get("id") or "%s:%s" % (
                    hit["metadata"].get("document_id", ""),
                    hit["metadata"].get("chunk_index", ""),
                ))
                existing = merged.get(key)
                if existing is None:
                    hit["matched_query"] = variant
                    merged[key] = hit
                    continue

                existing["keyword_recall_score"] = max(
                    float(existing.get("keyword_recall_score", 0.0)),
                    float(hit.get("keyword_recall_score", 0.0)),
                )
                existing["retrieval_mode"] = "hybrid"

        return rerank_hits(original_query, list(merged.values()), limit=limit, feedback_scores=self.feedback_scores)

    def answer(self, question: str) -> Dict[str, object]:
        hits = self.search(question, limit=5)
        initial_best_score = self._best_score(hits)
        evidence_hits = self._evidence_hits(question, hits)
        self_rag = self._self_rag_status(
            rescue_attempted=False,
            rescued=False,
            rescue_queries=[],
            initial_best_score=initial_best_score,
            final_best_score=initial_best_score,
            evidence_count=len(evidence_hits),
        )

        if not evidence_hits:
            rescue_queries = self._rescue_queries(question, hits)
            if rescue_queries:
                rescued_hits = self._search_with_variants(
                    original_query=question,
                    variants=rescue_queries,
                    limit=5,
                    expanded_limit=60,
                )
                for hit in rescued_hits:
                    hit["retrieval_stage"] = "rescue"
                rescued_evidence_hits = self._evidence_hits(question, rescued_hits)
                if rescued_evidence_hits:
                    hits = rescued_hits
                    evidence_hits = rescued_evidence_hits
                final_best_score = self._best_score(rescued_hits or hits)
                self_rag = self._self_rag_status(
                    rescue_attempted=True,
                    rescued=bool(rescued_evidence_hits),
                    rescue_queries=rescue_queries,
                    initial_best_score=initial_best_score,
                    final_best_score=final_best_score,
                    evidence_count=len(evidence_hits),
                )
        citations = [self._citation_from_hit(hit) for hit in evidence_hits]

        if not evidence_hits:
            best_score = self_rag["final_best_score"]
            rescue_note = "已尝试二次检索补救，仍未找到足够证据。" if self_rag["rescue_attempted"] else ""
            return {
                "answer": "%s %s最高相关度 %.2f，阈值 %.2f。"
                % (INSUFFICIENT_EVIDENCE_MESSAGE, rescue_note, best_score, self.min_evidence_score),
                "citations": [],
                "self_rag": self_rag,
            }

        if not self.openai_api_key:
            return {
                "answer": "OPENAI_API_KEY is not configured. Semantic search is available, but AI answers need an OpenAI-compatible API key.",
                "citations": citations,
                "self_rag": self_rag,
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
                "self_rag": self_rag,
            }
        return {
            "answer": response.choices[0].message.content or "",
            "citations": citations,
            "self_rag": self_rag,
        }

    def _rescue_queries(self, question: str, initial_hits: List[Dict[str, object]]) -> List[str]:
        candidates: List[str] = []

        def add(query: str) -> None:
            cleaned = " ".join(query.split()).strip()
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)

        for variant in query_variants(question):
            add(variant)

        simplified = (
            question.replace("请问", "")
            .replace("一下", "")
            .replace("这个", "")
            .replace("那个", "")
            .replace("吗", "")
            .replace("？", "")
            .replace("?", "")
        )
        add(simplified)
        return candidates[:8]

    @staticmethod
    def _best_score(hits: List[Dict[str, object]]) -> float:
        return max((float(hit.get("score", 0.0)) for hit in hits), default=0.0)

    def _self_rag_status(
        self,
        rescue_attempted: bool,
        rescued: bool,
        rescue_queries: List[str],
        initial_best_score: float,
        final_best_score: float,
        evidence_count: int,
    ) -> Dict[str, object]:
        if rescued:
            status = "rescued"
        elif evidence_count:
            status = "sufficient"
        elif rescue_attempted:
            status = "insufficient_after_rescue"
        else:
            status = "insufficient"
        return {
            "status": status,
            "rescue_attempted": rescue_attempted,
            "rescued": rescued,
            "rescue_queries": rescue_queries,
            "initial_best_score": round(initial_best_score, 4),
            "final_best_score": round(final_best_score, 4),
            "min_evidence_score": self.min_evidence_score,
            "evidence_count": evidence_count,
        }

    def _evidence_hits(self, question: str, hits: List[Dict[str, object]]) -> List[Dict[str, object]]:
        return [
            hit
            for hit in hits
            if float(hit.get("score", 0.0)) >= self.min_evidence_score
            or self._has_structured_field_evidence(question, hit)
        ]

    def _has_structured_field_evidence(self, question: str, hit: Dict[str, object]) -> bool:
        if not self._is_field_lookup_question(question):
            return False

        if float(hit.get("score", 0.0)) < self.min_evidence_score * 0.45:
            return False

        metadata = hit.get("metadata", {})
        field_facts = metadata.get("field_facts", []) or []
        for fact in field_facts:
            label = str(fact.get("label", ""))
            value = str(fact.get("value", "")).strip()
            if value and self._field_label_answers_question(question, label):
                return True
        return False

    @staticmethod
    def _is_field_lookup_question(question: str) -> bool:
        return any(marker in question for marker in FIELD_LOOKUP_MARKERS)

    @staticmethod
    def _field_label_answers_question(question: str, label: str) -> bool:
        question_lower = question.lower()
        label_lower = label.lower()
        for label_markers, question_markers in FIELD_EVIDENCE_GROUPS:
            if any(marker.lower() in label_lower for marker in label_markers) and any(
                marker.lower() in question_lower for marker in question_markers
            ):
                return True
        return False

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
        field_facts = metadata.get("field_facts", []) or []
        if field_facts:
            parts.append("文档属性：%s" % format_field_facts(field_facts))
        parent_context = str(metadata.get("parent_context") or "").strip()
        if parent_context:
            metadata["parent_context_used"] = True
            parts.append("父级上下文：%s" % parent_context)
            parts.append("命中子片段：%s" % hit.get("content", ""))
            return compress_context(question, "\n".join(parts), max_chars=PARENT_CONTEXT_MAX_CHARS)

        metadata["parent_context_used"] = False
        if metadata.get("previous_context"):
            parts.append("上文窗口：%s" % metadata["previous_context"])
        parts.append("命中片段：%s" % hit["content"])
        if metadata.get("next_context"):
            parts.append("下文窗口：%s" % metadata["next_context"])
        return compress_context(question, "\n".join(parts), max_chars=CHILD_CONTEXT_MAX_CHARS)
