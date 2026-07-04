import json
import re
from typing import Callable, Dict, List, Optional, Sequence

from openai import OpenAI, OpenAIError


DEFAULT_MAX_QUERIES = 5
MAX_QUERY_CHARS = 80
MAX_RAW_RESPONSE_CHARS = 3000

LLMCallable = Callable[[str], str]


def rewrite_queries(
    question: str,
    fallback_queries: Optional[Sequence[str]] = None,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    max_queries: int = DEFAULT_MAX_QUERIES,
    *,
    llm_callable: Optional[LLMCallable] = None,
    client_factory: Optional[Callable[..., object]] = None,
) -> Dict[str, object]:
    """Rewrite one user question into several retrieval-oriented queries.

    This module is intentionally standalone. It does not search documents and
    does not decide whether evidence is enough; Self-RAG can call it later when
    low-score retrieval needs a generic rescue path.
    """
    normalized_max = _normalize_max_queries(max_queries)
    fallback = _fallback_queries(question, fallback_queries, normalized_max)

    if not _clean_query(question):
        return {"queries": fallback, "used_llm": False, "error": "question is empty"}

    if not _can_call_llm(api_key, llm_callable):
        return {
            "queries": fallback,
            "used_llm": False,
            "error": "OPENAI_API_KEY is not configured; used rule fallback queries.",
        }

    prompt = _build_prompt(question, fallback, normalized_max)

    try:
        raw_response = (
            llm_callable(prompt)
            if llm_callable is not None
            else _call_openai(prompt, api_key=api_key, base_url=base_url, model=model, client_factory=client_factory)
        )
    except (OpenAIError, Exception) as exc:
        return {"queries": fallback, "used_llm": False, "error": "LLM query rewrite failed: %s" % str(exc)}

    llm_queries = _extract_queries(raw_response, max_queries=normalized_max)
    if not llm_queries:
        return {
            "queries": fallback,
            "used_llm": False,
            "error": "LLM query rewrite returned no valid queries; used rule fallback queries.",
        }

    queries = _merge_queries(llm_queries + fallback, max_queries=normalized_max)
    return {"queries": queries, "used_llm": True, "error": None}


def _normalize_max_queries(max_queries: int) -> int:
    try:
        value = int(max_queries)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_QUERIES
    return min(max(value, 1), 10)


def _can_call_llm(api_key: str, llm_callable: Optional[LLMCallable]) -> bool:
    return bool(llm_callable) or bool((api_key or "").strip())


def _fallback_queries(
    question: str,
    fallback_queries: Optional[Sequence[str]],
    max_queries: int,
) -> List[str]:
    candidates: List[str] = []
    cleaned_question = _clean_query(question)
    if cleaned_question:
        candidates.append(cleaned_question)
        simplified = _simplify_question(cleaned_question)
        if simplified != cleaned_question:
            candidates.append(simplified)

    candidates.extend(str(item) for item in (fallback_queries or []))
    return _merge_queries(candidates, max_queries=max_queries)


def _simplify_question(question: str) -> str:
    simplified = question
    filler_patterns = [
        r"^(请问|麻烦问下|帮我查一下|帮我查|我想知道|能不能告诉我)",
        r"(吗|呢|啊|呀)[?？]?$",
    ]
    for pattern in filler_patterns:
        simplified = re.sub(pattern, "", simplified, flags=re.IGNORECASE).strip()
    return _clean_query(simplified)


def _build_prompt(question: str, fallback: Sequence[str], max_queries: int) -> str:
    fallback_text = "\n".join("- %s" % query for query in fallback) or "- 无"
    return (
        "你是一个 RAG 检索问题改写器。请把用户问题改写成更适合向量检索和关键词检索的 query。\n"
        "只输出 JSON 字符串数组，不要解释，不要 Markdown，不要编号。\n"
        "规则：\n"
        "1. 保留原始意图，不要编造答案。\n"
        "2. 可以生成明确化、泛化、关键词化、子问题化的检索 query。\n"
        "3. 每条 query 不超过 %s 个字符。\n"
        "4. 最多输出 %s 条，避免重复。\n\n"
        "用户问题：%s\n\n"
        "已有 fallback query：\n%s"
        % (MAX_QUERY_CHARS, max_queries, question.strip(), fallback_text)
    )


def _call_openai(
    prompt: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
    client_factory: Optional[Callable[..., object]],
) -> str:
    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = client_factory(**client_kwargs) if client_factory else OpenAI(**client_kwargs)
    response = client.chat.completions.create(
        model=model or "gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You rewrite user questions for retrieval. Return only a JSON array of strings.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    return response.choices[0].message.content or ""


def _extract_queries(raw_response: object, max_queries: int) -> List[str]:
    if raw_response is None:
        return []

    if isinstance(raw_response, list):
        return _merge_queries([str(item) for item in raw_response], max_queries=max_queries)

    raw_text = str(raw_response)[:MAX_RAW_RESPONSE_CHARS]
    json_items = _queries_from_json(raw_text)
    if json_items:
        return _merge_queries(json_items, max_queries=max_queries)

    line_items = _queries_from_lines(raw_text)
    return _merge_queries(line_items, max_queries=max_queries)


def _queries_from_json(raw_text: str) -> List[str]:
    text = _strip_code_fence(raw_text)
    candidates = [text]

    bracket_match = re.search(r"\[[\s\S]*\]", text)
    if bracket_match:
        candidates.insert(0, bracket_match.group(0))

    object_match = re.search(r"\{[\s\S]*\}", text)
    if object_match:
        candidates.append(object_match.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return [str(item) for item in parsed if isinstance(item, (str, int, float))]
        if isinstance(parsed, dict):
            for key in ("queries", "query_variants", "rewrites", "items"):
                value = parsed.get(key)
                if isinstance(value, list):
                    return [str(item) for item in value if isinstance(item, (str, int, float))]
    return []


def _queries_from_lines(raw_text: str) -> List[str]:
    text = _strip_code_fence(raw_text)
    items: List[str] = []
    for line in re.split(r"[\r\n]+", text):
        cleaned = _clean_query(line)
        if not cleaned or _looks_like_explanation(cleaned):
            continue
        items.append(cleaned)
    return items


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
    stripped = re.sub(r"```$", "", stripped).strip()
    return stripped


def _clean_query(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip("`\"'“”‘’[]()（）")
    text = re.sub(r"^\s*(?:[-*•]|[0-9]+[.)、]|[一二三四五六七八九十]+[、.])\s*", "", text)
    text = re.sub(r"^(?:query|查询|检索词|问题|改写)\s*[0-9一二三四五六七八九十]*\s*[:：]\s*", "", text, flags=re.IGNORECASE)
    text = text.strip("`\"'“”‘’[]()（）")
    if len(text) > MAX_QUERY_CHARS:
        text = text[:MAX_QUERY_CHARS].rstrip("，,。.!！？?；;、 ")
    return text


def _looks_like_explanation(text: str) -> bool:
    lowered = text.lower()
    prefixes = (
        "以下是",
        "这里是",
        "说明",
        "解释",
        "注意",
        "好的",
        "可以",
        "json",
        "```",
        "the rewritten",
        "here are",
    )
    if lowered.startswith(prefixes):
        return True
    return len(text) > 0 and not re.search(r"[\w\u4e00-\u9fff]", text)


def _merge_queries(candidates: Sequence[str], max_queries: int) -> List[str]:
    queries: List[str] = []
    seen = set()
    for candidate in candidates:
        cleaned = _clean_query(candidate)
        if not cleaned or _looks_like_explanation(cleaned):
            continue
        key = _dedupe_key(cleaned)
        if not key or key in seen:
            continue
        queries.append(cleaned)
        seen.add(key)
        if len(queries) >= max_queries:
            break
    return queries


def _dedupe_key(query: str) -> str:
    return re.sub(r"[\W_]+", "", query.lower(), flags=re.UNICODE)
