import re
from typing import Dict, List, Optional, Tuple

from openai import OpenAI, OpenAIError

from .citation_check import check_citation_support
from .domain_terms import concept_evidence_groups
from .embeddings import EmbeddingProvider
from .query_rewrite import rewrite_queries
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
    "载体",
    "承载",
    "形式",
    "平台",
    "终端",
    "端上",
]
FIELD_EVIDENCE_GROUPS = [
    (["项目", "所属", "部门", "游戏", "产品"], ["项目", "所属", "属于", "部门", "游戏", "产品", "哪个", "什么"]),
    (["对接人", "负责人", "联系人"], ["谁", "对接人", "负责人", "联系人"]),
    (["日期", "时间", "排期", "完成"], ["何时", "什么时候", "日期", "时间", "排期", "完成"]),
    (["域名", "网址", "链接"], ["域名", "网址", "链接"]),
    (["编号", "单号", "worktile"], ["编号", "单号", "worktile"]),
    (
        ["载体", "承载", "形式", "平台", "终端", "小程序", "移动端", "h5", "app", "端"],
        ["载体", "承载", "形式", "平台", "终端", "端上", "小程序", "移动端", "什么", "哪个"],
    ),
]
CHILD_CONTEXT_MAX_CHARS = 900
PARENT_CONTEXT_MAX_CHARS = 1200
CITATION_CHECK_NOT_APPLICABLE = "not_applicable"


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
            for hit in self._keyword_hits(variant, all_chunks, expanded_limit):
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
                if hit.get("bm25_score") is not None:
                    existing["bm25_score"] = hit.get("bm25_score")
                if hit.get("keyword_backend"):
                    existing["keyword_backend"] = hit.get("keyword_backend")
                if hit.get("matched_keywords"):
                    existing["matched_keywords"] = hit.get("matched_keywords")
                existing["retrieval_mode"] = "hybrid"

        return rerank_hits(original_query, list(merged.values()), limit=limit, feedback_scores=self.feedback_scores)

    def _keyword_hits(
        self,
        variant: str,
        all_chunks: List[Dict[str, object]],
        limit: int,
    ) -> List[Dict[str, object]]:
        hits: List[Dict[str, object]] = []
        if hasattr(self.vector_store, "keyword_search"):
            hits = self.vector_store.keyword_search(variant, limit=limit)
        if not hits:
            hits = keyword_recall_hits(variant, all_chunks, limit=limit)

        for hit in hits:
            hit.setdefault("score", 0.0)
            hit.setdefault("retrieval_mode", "keyword")
        return hits

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
            retrieval_modes=self._retrieval_modes(hits),
        )

        if not evidence_hits:
            rescue_plan = self._rescue_query_plan(question)
            rescue_queries = rescue_plan["queries"]
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
                    rescue_query_source=str(rescue_plan["source"]),
                    query_rewrite_used_llm=bool(rescue_plan["used_llm"]),
                    query_rewrite_error=str(rescue_plan["error"] or ""),
                    retrieval_modes=self._retrieval_modes(rescued_hits or hits),
                )
        citations = [self._citation_from_hit(hit) for hit in evidence_hits]

        if not evidence_hits:
            best_score = self_rag["final_best_score"]
            rescue_note = "已尝试二次检索补救，仍未找到足够证据。" if self_rag["rescue_attempted"] else ""
            answer = "%s %s最高相关度 %.2f，阈值 %.2f。" % (
                INSUFFICIENT_EVIDENCE_MESSAGE,
                rescue_note,
                best_score,
                self.min_evidence_score,
            )
            return {
                "answer": answer,
                "citations": [],
                "self_rag": self_rag,
                "citation_check": self._citation_check_not_applicable("answer refused because evidence was insufficient"),
            }

        if not self.openai_api_key:
            return {
                "answer": "OPENAI_API_KEY is not configured. Semantic search is available, but AI answers need an OpenAI-compatible API key.",
                "citations": citations,
                "self_rag": self_rag,
                "citation_check": self._citation_check_not_applicable("AI answer was not generated because OPENAI_API_KEY is missing"),
            }

        source_contexts = []
        citation_evidence = []
        for index, (hit, citation) in enumerate(zip(evidence_hits, citations)):
            hit_context = self._context_from_hit(question, hit)
            source_contexts.append(
                "[Source %s]\nFile: %s\nChunk: %s\nHeader: %s\n%s"
                % (
                    index + 1,
                    citation["source_path"],
                    citation["chunk_index"],
                    citation["chunk_header"],
                    hit_context,
                )
            )
            citation_evidence.append(self._citation_evidence_from_hit(citation, hit, hit_context))
        context = "\n\n".join(source_contexts)

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
                "citation_check": self._citation_check_not_applicable("AI call failed before a final answer was generated"),
            }
        answer = response.choices[0].message.content or ""
        return {
            "answer": answer,
            "citations": citations,
            "self_rag": self_rag,
            "citation_check": self._check_answer_citations(answer, citation_evidence),
        }

    def _rescue_query_plan(self, question: str) -> Dict[str, object]:
        fallback = self._rule_rescue_queries(question)
        rewrite = rewrite_queries(
            question=question,
            fallback_queries=fallback,
            api_key=self.openai_api_key,
            base_url=self.openai_base_url,
            model=self.openai_model,
            max_queries=8,
        )
        return {
            "queries": rewrite["queries"],
            "used_llm": rewrite["used_llm"],
            "error": rewrite["error"],
            "source": "llm" if rewrite["used_llm"] else "rules",
        }

    def _rule_rescue_queries(self, question: str) -> List[str]:
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

    def _rescue_queries(self, question: str, initial_hits: List[Dict[str, object]]) -> List[str]:
        return self._rule_rescue_queries(question)

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
        rescue_query_source: str = "",
        query_rewrite_used_llm: bool = False,
        query_rewrite_error: str = "",
        retrieval_modes: Optional[List[str]] = None,
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
            "rescue_query_source": rescue_query_source,
            "query_rewrite_used_llm": query_rewrite_used_llm,
            "query_rewrite_error": query_rewrite_error,
            "retrieval_modes": retrieval_modes or [],
        }

    @staticmethod
    def _retrieval_modes(hits: List[Dict[str, object]]) -> List[str]:
        modes = []
        for hit in hits:
            mode = str(hit.get("retrieval_mode", "") or "")
            backend = str(hit.get("keyword_backend", "") or "")
            if mode == "keyword" and backend == "fts5":
                mode = "bm25"
            if mode == "hybrid" and backend == "fts5":
                mode = "hybrid+bm25"
            if mode and mode not in modes:
                modes.append(mode)
        return modes

    def _evidence_hits(self, question: str, hits: List[Dict[str, object]]) -> List[Dict[str, object]]:
        return [
            hit
            for hit in hits
            if float(hit.get("score", 0.0)) >= self.min_evidence_score
            or self._has_structured_field_evidence(question, hit)
            or self._has_concept_evidence(question, hit)
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

    def _has_concept_evidence(self, question: str, hit: Dict[str, object]) -> bool:
        if float(hit.get("score", 0.0)) < self.min_evidence_score * 0.75:
            return False

        metadata = hit.get("metadata", {})
        haystack = "\n".join(
            [
                str(metadata.get("title", "")),
                str(metadata.get("chunk_header", "")),
                format_field_facts(metadata.get("field_facts", []) or []),
                " ".join(metadata.get("generated_questions", []) or []),
                str(metadata.get("summary", "")),
                str(metadata.get("parent_context", "")),
                str(hit.get("content", "")),
            ]
        )
        haystack_lower = haystack.lower()
        for question_markers, evidence_markers in concept_evidence_groups():
            if not any(marker in question for marker in question_markers):
                continue
            if not any(marker.lower() in haystack_lower for marker in evidence_markers):
                continue
            if self._has_question_anchor_overlap(question, haystack, question_markers):
                return True
        return False

    @staticmethod
    def _has_question_anchor_overlap(question: str, text: str, concept_markers: List[str]) -> bool:
        stripped = question
        for marker in concept_markers + ["什么", "哪个", "哪些", "是", "的", "啥", "吗", "呢", "这个", "那个", "请问"]:
            stripped = stripped.replace(marker, " ")
        anchors = []
        anchors.extend(token for token in re.findall(r"[\u4e00-\u9fff]{2,}", stripped) if len(token) >= 2)
        anchors.extend(token.lower() for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{1,}", stripped))
        if not anchors:
            return False
        normalized_text = re.sub(r"[\s\W_]+", "", text.lower(), flags=re.UNICODE)
        for anchor in anchors:
            normalized_anchor = re.sub(r"[\s\W_]+", "", anchor.lower(), flags=re.UNICODE)
            if normalized_anchor and normalized_anchor in normalized_text:
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
    def _citation_evidence_from_hit(
        citation: Dict[str, object],
        hit: Dict[str, object],
        context: str,
    ) -> Dict[str, object]:
        evidence = dict(citation)
        evidence["context"] = context
        evidence["content"] = hit.get("content", "")
        evidence["metadata"] = hit.get("metadata", {})
        return evidence

    @staticmethod
    def _citation_check_not_applicable(reason: str) -> Dict[str, object]:
        return {
            "status": CITATION_CHECK_NOT_APPLICABLE,
            "support_score": 0.0,
            "reasons": [reason],
            "checked_claim_count": 0,
        }

    def _check_answer_citations(
        self,
        answer: str,
        citation_evidence: List[Dict[str, object]],
    ) -> Dict[str, object]:
        if self._is_refusal_answer(answer):
            return self._citation_check_not_applicable("answer is a refusal, so citation support is not applicable")
        return check_citation_support(answer, citation_evidence)

    @staticmethod
    def _is_refusal_answer(answer: str) -> bool:
        normalized = (answer or "").strip()
        if not normalized:
            return False
        refusal_markers = [
            "文档中没有找到依据",
            "没有找到依据",
            "insufficient evidence",
            "not enough evidence",
        ]
        return any(marker.lower() in normalized.lower() for marker in refusal_markers)

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
