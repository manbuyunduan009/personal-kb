import re
from typing import Dict, List, Optional, Tuple


QUERY_EXPANSIONS = [
    (["需求", "功能", "模块", "页面"], "需求 功能 模块 页面 规则 验收"),
    (["哪个游戏", "哪个项目", "什么游戏", "所属", "属于", "项目"], "项目/部门所属 项目所属 所属项目 游戏 产品 需求基础信息 概域名"),
    (["目标用户", "用户", "谁"], "目标用户 用户人群 使用对象 角色"),
    (["解决", "问题", "痛点"], "背景 痛点 问题 目标 价值"),
    (["阶段", "计划", "排期", "时间"], "阶段 计划 排期 时间 里程碑 状态"),
    (["验收", "标准", "指标"], "验收标准 指标 通过条件 检查项"),
    (["活动", "奖励", "任务", "规则"], "活动规则 任务 奖励 参与方式"),
]


def query_variants(query: str) -> List[str]:
    """Create lightweight query transformations without calling an LLM."""
    normalized = normalize_text(query)
    variants = [query.strip()]
    if normalized and normalized != query.strip():
        variants.append(normalized)

    for keywords, expansion in QUERY_EXPANSIONS:
        if any(keyword in query for keyword in keywords):
            variants.append("%s %s" % (query.strip(), expansion))

    for part in re.split(r"[，,；;、\n]|以及|并且|和", query):
        cleaned = part.strip()
        if 4 <= len(cleaned) <= 40:
            variants.append(cleaned)

    unique = []
    for variant in variants:
        if variant and variant not in unique:
            unique.append(variant)
    return unique[:8]


def rerank_hits(
    query: str,
    hits: List[Dict[str, object]],
    limit: int,
    feedback_scores: Optional[Dict[Tuple[str, int], float]] = None,
) -> List[Dict[str, object]]:
    feedback_scores = feedback_scores or {}
    reranked = []
    for hit in hits:
        item = dict(hit)
        metadata = item.get("metadata", {})
        haystack = "\n".join(
            [
                str(metadata.get("title", "")),
                str(metadata.get("chunk_header", "")),
                format_field_facts(metadata.get("field_facts", []) or []),
                " ".join(metadata.get("generated_questions", []) or []),
                str(metadata.get("summary", "")),
                str(item.get("content", "")),
            ]
        )
        vector_score = float(item.get("vector_recall_score", item.get("score", 0.0)))
        keyword_recall_score = float(item.get("keyword_recall_score", 0.0))
        keyword_score = max(lexical_overlap_score(query, haystack), keyword_recall_score)
        header_score = lexical_overlap_score(query, str(metadata.get("chunk_header", "")))
        feedback_score = feedback_scores.get(
            (str(metadata.get("source_path", "")), int(metadata.get("chunk_index", 0))),
            0.0,
        )
        hybrid_bonus = min(keyword_recall_score * 0.06, 0.08)
        feedback_bonus = max(min(feedback_score * 0.04, 0.12), -0.12)
        final_score = (
            (vector_score * 0.56)
            + (keyword_score * 0.24)
            + (header_score * 0.08)
            + hybrid_bonus
            + feedback_bonus
        )

        item["vector_score"] = vector_score
        item["keyword_score"] = keyword_score
        item["keyword_recall_score"] = keyword_recall_score
        item["hybrid_bonus"] = hybrid_bonus
        item["feedback_score"] = feedback_score
        item["feedback_bonus"] = feedback_bonus
        item["score"] = final_score
        reranked.append(item)

    reranked.sort(key=lambda item: item["score"], reverse=True)
    return reranked[:limit]


def keyword_recall_hits(query: str, chunks: List[Dict[str, object]], limit: int = 20) -> List[Dict[str, object]]:
    hits = []
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        haystack = "\n".join(
            [
                str(metadata.get("title", "")),
                str(metadata.get("chunk_header", "")),
                format_field_facts(metadata.get("field_facts", []) or []),
                " ".join(metadata.get("generated_questions", []) or []),
                str(metadata.get("summary", "")),
                str(chunk.get("content", "")),
            ]
        )
        score = lexical_overlap_score(query, haystack)
        if score <= 0:
            continue
        hits.append(
            {
                "id": chunk.get("id", ""),
                "content": chunk.get("content", ""),
                "metadata": metadata,
                "distance": 1.0 - score,
                "score": 0.0,
                "keyword_recall_score": score,
                "retrieval_mode": "keyword",
                "matched_query": query,
            }
        )

    hits.sort(key=lambda item: item["keyword_recall_score"], reverse=True)
    return hits[:limit]


def compress_context(query: str, text: str, max_chars: int = 700) -> str:
    """Keep query-related sentences first, then cap context length."""
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact

    sentences = split_sentences(compact)
    scored = []
    for index, sentence in enumerate(sentences):
        score = lexical_overlap_score(query, sentence)
        scored.append((score, index, sentence))
    scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)

    selected = []
    total = 0
    for score, _, sentence in scored:
        if score <= 0 and selected:
            continue
        if total + len(sentence) > max_chars:
            continue
        selected.append(sentence)
        total += len(sentence)
        if total >= max_chars * 0.75:
            break

    if not selected:
        return compact[:max_chars].rstrip() + "..."

    selected.sort(key=lambda sentence: sentences.index(sentence))
    result = "".join(selected).strip()
    if len(result) > max_chars:
        result = result[:max_chars].rstrip() + "..."
    return result


def lexical_overlap_score(query: str, text: str) -> float:
    query_tokens = set(char_ngrams(query))
    if not query_tokens:
        return 0.0

    target = normalize_text(text)
    if not target:
        return 0.0

    matches = sum(1 for token in query_tokens if token in target)
    score = matches / len(query_tokens)
    normalized_query = normalize_text(query)
    if normalized_query and normalized_query in target:
        score += 0.25
    return min(score, 1.0)


def char_ngrams(text: str) -> List[str]:
    compact = normalize_text(text)
    tokens = []
    for size in (2, 3):
        if len(compact) >= size:
            tokens.extend(compact[index : index + size] for index in range(len(compact) - size + 1))
    return tokens


def normalize_text(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text.lower(), flags=re.UNICODE)


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[。！？!?；;])", text)
    return [part.strip() for part in parts if part.strip()]


def format_field_facts(field_facts: List[Dict[str, str]]) -> str:
    return " ".join(
        "%s %s" % (fact.get("label", ""), fact.get("value", ""))
        for fact in field_facts
    )
