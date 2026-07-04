import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


DEFAULT_TERMS_PATH = Path(__file__).resolve().parents[1] / "config" / "domain_terms.json"
STOP_TERMS = {
    "这个",
    "那个",
    "哪些",
    "什么",
    "怎么",
    "是否",
    "有没有",
    "为什么",
    "需要",
    "可以",
    "进行",
    "文档",
    "需求",
    "项目",
}
VALUABLE_MARKERS = [
    "页",
    "端",
    "入口",
    "专题",
    "小程序",
    "平台",
    "接口",
    "权限",
    "登录",
    "验收",
    "排期",
    "灰度",
    "兜底",
    "资源位",
    "埋点",
    "统计",
    "配置",
]


@lru_cache(maxsize=1)
def load_domain_terms() -> List[Dict[str, object]]:
    if not DEFAULT_TERMS_PATH.exists():
        return []
    with DEFAULT_TERMS_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        return []
    return [normalize_term(item) for item in data if isinstance(item, dict)]


def normalize_term(item: Dict[str, object]) -> Dict[str, object]:
    return {
        "id": str(item.get("id", "")).strip(),
        "label": str(item.get("label", "")).strip(),
        "category": str(item.get("category", "")).strip(),
        "aliases": unique_strings(item.get("aliases", [])),
        "search_terms": unique_strings(item.get("search_terms", [])),
        "evidence_terms": unique_strings(item.get("evidence_terms", [])),
    }


def expand_query_terms(query: str, terms: Sequence[Dict[str, object]] = ()) -> List[str]:
    loaded_terms = list(terms) if terms else load_domain_terms()
    normalized_query = normalize_text(query)
    expanded: List[str] = []
    for term in loaded_terms:
        markers = term_markers(term)
        if not markers:
            continue
        if any(normalize_text(marker) in normalized_query for marker in markers if normalize_text(marker)):
            expanded.extend([str(term.get("label", ""))])
            expanded.extend(str(item) for item in term.get("aliases", []))
            expanded.extend(str(item) for item in term.get("search_terms", []))
    return unique_strings(expanded)


def concept_evidence_groups() -> List[tuple]:
    groups = []
    for term in load_domain_terms():
        question_markers = unique_strings([str(term.get("label", ""))] + list(term.get("aliases", [])))
        evidence_markers = unique_strings(list(term.get("evidence_terms", [])) + list(term.get("search_terms", [])))
        if question_markers and evidence_markers:
            groups.append((question_markers, evidence_markers))
    return groups


def mine_domain_term_candidates(
    documents: Sequence[Dict[str, object]],
    traces: Sequence[Dict[str, object]] = (),
    limit: int = 40,
) -> List[Dict[str, object]]:
    candidates: Dict[str, Dict[str, object]] = {}
    terms = load_domain_terms()

    for document in documents:
        text = document_text(document)
        source = str(document.get("title", "") or document.get("source_path", ""))
        for term in terms:
            matched = [marker for marker in term_markers(term) if marker and marker in text]
            if matched:
                add_candidate(
                    candidates,
                    key=str(term.get("id", "")) or str(term.get("label", "")),
                    term=str(term.get("label", "")),
                    normalized=str(term.get("label", "")),
                    category=str(term.get("category", "")),
                    status="known",
                    source_type="document",
                    matched_terms=matched,
                    example=source,
                    reason="文档命中通用术语表，可直接参与 query 扩展。",
                    suggested_aliases=term.get("aliases", []),
                    suggested_search_terms=term.get("search_terms", []),
                    priority=2,
                )

        for phrase in extract_document_phrases(text):
            add_candidate(
                candidates,
                key="candidate:%s" % phrase,
                term=phrase,
                normalized=suggest_normalized_label(phrase, terms),
                category=suggest_category(phrase, terms),
                status="candidate",
                source_type="document",
                matched_terms=[phrase],
                example=source,
                reason="文档中反复出现的产品/技术表达，建议人工确认是否进入术语表。",
                priority=1,
            )

    for trace in traces:
        if not is_low_quality_trace(trace):
            continue
        question = str(trace.get("question", ""))
        for phrase in extract_question_phrases(question):
            add_candidate(
                candidates,
                key="question:%s" % phrase,
                term=phrase,
                normalized=suggest_normalized_label(phrase, terms),
                category=suggest_category(phrase, terms),
                status="candidate",
                source_type="low_score_question",
                matched_terms=[phrase],
                example=question,
                reason="来自低分、拒答或补救失败问题，优先级高，适合人工纠正。",
                priority=4,
            )

    scored = []
    for candidate in candidates.values():
        source_count = len(candidate["sources"])
        priority = int(candidate.pop("_priority", 0))
        confidence = min(0.35 + source_count * 0.08 + priority * 0.08, 0.95)
        candidate["confidence"] = round(confidence, 2)
        candidate["source_count"] = source_count
        candidate["sources"] = sorted(candidate["sources"])
        candidate["matched_terms"] = unique_strings(candidate["matched_terms"])[:12]
        candidate["suggested_aliases"] = unique_strings(candidate["suggested_aliases"])[:12]
        candidate["suggested_search_terms"] = unique_strings(candidate["suggested_search_terms"])[:12]
        candidate["examples"] = unique_strings(candidate["examples"])[:3]
        scored.append(candidate)

    scored.sort(
        key=lambda item: (
            item.get("status") != "candidate",
            -float(item.get("confidence", 0.0)),
            -int(item.get("source_count", 0)),
            str(item.get("term", "")),
        )
    )
    return scored[: max(1, min(int(limit or 40), 100))]


def add_candidate(
    candidates: Dict[str, Dict[str, object]],
    *,
    key: str,
    term: str,
    normalized: str,
    category: str,
    status: str,
    source_type: str,
    matched_terms: Iterable[str],
    example: str,
    reason: str,
    suggested_aliases: Iterable[str] = (),
    suggested_search_terms: Iterable[str] = (),
    priority: int = 1,
) -> None:
    if not term or normalize_text(term) in STOP_TERMS:
        return
    candidate = candidates.setdefault(
        key,
        {
            "term": term,
            "normalized": normalized or term,
            "category": category or "待分类",
            "status": status,
            "sources": set(),
            "matched_terms": [],
            "suggested_aliases": [],
            "suggested_search_terms": [],
            "examples": [],
            "reason": reason,
            "_priority": 0,
        },
    )
    candidate["sources"].add(source_type)
    candidate["matched_terms"].extend(str(item) for item in matched_terms if item)
    candidate["suggested_aliases"].extend(str(item) for item in suggested_aliases if item)
    candidate["suggested_search_terms"].extend(str(item) for item in suggested_search_terms if item)
    if example:
        candidate["examples"].append(example)
    candidate["_priority"] = max(int(candidate["_priority"]), priority)


def extract_document_phrases(text: str) -> List[str]:
    phrases = []
    for token in re.findall(r"[A-Za-z0-9#._+-]{2,20}|[\u4e00-\u9fffA-Za-z0-9#._+-]{2,16}", text):
        cleaned = clean_phrase(token)
        if not cleaned or cleaned in STOP_TERMS:
            continue
        if is_valuable_phrase(cleaned):
            phrases.append(cleaned)
    return unique_strings(phrases)


def extract_question_phrases(question: str) -> List[str]:
    cleaned_question = question
    for stop in STOP_TERMS | {"是啥", "是什么", "有哪些", "多少", "谁", "吗", "呢", "的"}:
        cleaned_question = cleaned_question.replace(stop, " ")
    phrases = []
    for token in re.findall(r"[A-Za-z0-9#._+-]{2,20}|[\u4e00-\u9fffA-Za-z0-9#._+-]{2,10}", cleaned_question):
        cleaned = clean_phrase(token)
        if cleaned and cleaned not in STOP_TERMS:
            phrases.append(cleaned)
    return unique_strings(phrases)


def is_low_quality_trace(trace: Dict[str, object]) -> bool:
    status = str(trace.get("self_rag_status", ""))
    is_refusal = bool(trace.get("is_refusal", False))
    final_best_score = float(trace.get("final_best_score", 0.0) or 0.0)
    min_evidence_score = float(trace.get("min_evidence_score", 0.3) or 0.3)
    return is_refusal or status in {"insufficient", "insufficient_after_rescue"} or final_best_score < min_evidence_score


def suggest_normalized_label(phrase: str, terms: Sequence[Dict[str, object]]) -> str:
    normalized_phrase = normalize_text(phrase)
    for term in terms:
        if any(normalize_text(marker) in normalized_phrase for marker in term_markers(term) if normalize_text(marker)):
            return str(term.get("label", "")) or phrase
    return phrase


def suggest_category(phrase: str, terms: Sequence[Dict[str, object]]) -> str:
    normalized_phrase = normalize_text(phrase)
    for term in terms:
        if any(normalize_text(marker) in normalized_phrase for marker in term_markers(term) if normalize_text(marker)):
            return str(term.get("category", "")) or "待分类"
    if any(marker in phrase for marker in ["小程序", "移动端", "H5", "PC", "App", "端"]):
        return "平台/终端"
    if any(marker in phrase for marker in ["入口", "页", "专题", "资源位"]):
        return "页面/入口"
    if any(marker in phrase for marker in ["接口", "配置", "后台"]):
        return "接口/后端"
    return "待分类"


def is_valuable_phrase(phrase: str) -> bool:
    if len(phrase) < 2 or len(phrase) > 16:
        return False
    if phrase.lower() in STOP_TERMS:
        return False
    return any(marker.lower() in phrase.lower() for marker in VALUABLE_MARKERS)


def clean_phrase(value: str) -> str:
    cleaned = re.sub(r"^[^\w\u4e00-\u9fff]+|[^\w\u4e00-\u9fff]+$", "", value.strip(), flags=re.UNICODE)
    return cleaned.strip()


def document_text(document: Dict[str, object]) -> str:
    return "\n".join(
        [
            str(document.get("title", "")),
            str(document.get("source_path", "")),
            str(document.get("content_preview", "")),
        ]
    )


def term_markers(term: Dict[str, object]) -> List[str]:
    return unique_strings(
        [str(term.get("label", ""))]
        + list(term.get("aliases", []))
        + list(term.get("search_terms", []))
        + list(term.get("evidence_terms", []))
    )


def normalize_text(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or "").lower(), flags=re.UNICODE)


def unique_strings(values: object) -> List[str]:
    unique: List[str] = []
    seen = set()
    if not isinstance(values, (list, tuple, set)):
        values = [values]
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        unique.append(cleaned)
    return unique
