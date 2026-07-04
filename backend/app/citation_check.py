import re
from typing import Dict, Iterable, List, Sequence, Set


SUPPORTED = "supported"
WARNING = "warning"
UNSUPPORTED = "unsupported"

STRONG_SUPPORT_THRESHOLD = 0.55
WEAK_SUPPORT_THRESHOLD = 0.25
UNSUPPORTED_AVERAGE_THRESHOLD = 0.2

EVIDENCE_TEXT_KEYS = {
    "title",
    "source_path",
    "file_type",
    "chunk_header",
    "summary",
    "context",
    "content",
    "text",
    "excerpt",
    "snippet",
    "page_content",
    "previous_context",
    "next_context",
}

SKIP_VALUE_KEYS = {
    "id",
    "score",
    "feedback_score",
    "distance",
    "chunk_index",
    "vector_score",
    "keyword_score",
    "keyword_recall_score",
}


def check_citation_support(answer: str, citations: List[Dict[str, object]]) -> Dict[str, object]:
    """Check whether answer claims are lexically supported by citation evidence.

    v0 intentionally avoids online services and LLM calls. It is a conservative
    signal for observability, not a final factuality judge.
    """
    cleaned_answer = (answer or "").strip()
    if not cleaned_answer:
        return _result(
            UNSUPPORTED,
            0.0,
            ["answer is empty, so citation support cannot be checked"],
            checked_claim_count=0,
        )

    claims = _extract_claims(cleaned_answer)
    if not claims:
        return _result(
            WARNING,
            0.0,
            ["answer did not contain a long enough checkable claim"],
            checked_claim_count=0,
        )

    if not citations:
        return _result(
            WARNING,
            0.0,
            ["no citations were provided for %s checkable claim(s)" % len(claims)],
            checked_claim_count=len(claims),
        )

    evidence_text = _evidence_text(citations)
    if not evidence_text.strip():
        return _result(
            WARNING,
            0.0,
            ["citations did not include usable title, summary, context, or content text"],
            checked_claim_count=len(claims),
        )

    claim_scores = [_support_score(claim, evidence_text) for claim in claims]
    support_score = round(sum(claim_scores) / len(claim_scores), 4)
    strong_count = sum(1 for score in claim_scores if score >= STRONG_SUPPORT_THRESHOLD)
    weak_count = sum(1 for score in claim_scores if WEAK_SUPPORT_THRESHOLD <= score < STRONG_SUPPORT_THRESHOLD)
    low_count = len(claim_scores) - strong_count - weak_count

    reasons = [
        "checked %s claim(s) against %s citation(s)" % (len(claims), len(citations)),
        "%s claim(s) had strong lexical support" % strong_count,
    ]
    if weak_count:
        reasons.append("%s claim(s) had partial lexical support" % weak_count)
    if low_count:
        reasons.append("%s claim(s) had little lexical support" % low_count)

    if strong_count == len(claim_scores):
        status = SUPPORTED
    elif low_count == len(claim_scores) and support_score < UNSUPPORTED_AVERAGE_THRESHOLD:
        status = UNSUPPORTED
    else:
        status = WARNING

    return _result(
        status,
        support_score,
        reasons,
        checked_claim_count=len(claims),
    )


def _result(status: str, support_score: float, reasons: List[str], checked_claim_count: int) -> Dict[str, object]:
    return {
        "status": status,
        "support_score": max(0.0, min(float(support_score), 1.0)),
        "reasons": reasons,
        "checked_claim_count": checked_claim_count,
    }


def _extract_claims(answer: str) -> List[str]:
    claims = []
    for sentence in _split_sentences(answer):
        cleaned = _strip_citation_markers(sentence)
        if not _is_checkable_claim(cleaned):
            continue
        claims.append(cleaned)
    return claims[:12]


def _split_sentences(text: str) -> List[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[。！？!?；;.\n])\s*", normalized)
    return [part.strip() for part in parts if part.strip()]


def _strip_citation_markers(text: str) -> str:
    text = re.sub(r"\[(?:source\s*)?\d+\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[（(](?:来源|source)\s*\d+[）)]", "", text, flags=re.IGNORECASE)
    return text.strip()


def _is_checkable_claim(text: str) -> bool:
    compact = _normalize_text(text)
    if len(compact) >= 8:
        return True
    return len(_word_tokens(text)) >= 3 or bool(_numbers(text))


def _evidence_text(citations: Sequence[Dict[str, object]]) -> str:
    parts = []
    for citation in citations:
        parts.extend(_collect_evidence_values(citation))
    return "\n".join(part for part in parts if part)


def _collect_evidence_values(value: object, key: str = "") -> List[str]:
    if value is None:
        return []

    if isinstance(value, str):
        if key and key not in EVIDENCE_TEXT_KEYS and key not in {"label", "value", "metadata"}:
            return []
        return [value]

    if isinstance(value, (int, float, bool)):
        if key in SKIP_VALUE_KEYS:
            return []
        return [str(value)]

    if isinstance(value, dict):
        parts = []
        for child_key, child_value in value.items():
            child_key_text = str(child_key)
            if child_key_text in SKIP_VALUE_KEYS:
                continue
            if not key and child_key_text not in EVIDENCE_TEXT_KEYS and child_key_text not in {"metadata", "field_facts"}:
                continue
            parts.extend(_collect_evidence_values(child_value, child_key_text))
        return parts

    if isinstance(value, list):
        parts = []
        for item in value:
            parts.extend(_collect_evidence_values(item, key))
        return parts

    return []


def _support_score(claim: str, evidence: str) -> float:
    claim_numbers = _numbers(claim)
    evidence_numbers = _numbers(evidence)
    missing_numbers = [number for number in claim_numbers if number not in evidence_numbers]

    score = max(
        _token_overlap_score(claim, evidence, cjk_ngram_sizes=(2,)),
        _token_overlap_score(claim, evidence, cjk_ngram_sizes=(2, 3)),
    )
    if score <= 0:
        return 0.0

    normalized_claim = _normalize_text(claim)
    normalized_evidence = _normalize_text(evidence)
    if normalized_claim and normalized_claim in normalized_evidence:
        score = max(score, 0.95)

    if missing_numbers:
        score = min(score, 0.45)

    return max(0.0, min(score, 1.0))


def _token_overlap_score(claim: str, evidence: str, cjk_ngram_sizes: Iterable[int]) -> float:
    claim_tokens = _claim_tokens(claim, cjk_ngram_sizes)
    if not claim_tokens:
        return 0.0

    evidence_tokens = _evidence_tokens(evidence, cjk_ngram_sizes)
    matched = sum(1 for token in claim_tokens if token in evidence_tokens)
    return matched / len(claim_tokens)


def _claim_tokens(text: str, cjk_ngram_sizes: Iterable[int] = (2, 3)) -> Set[str]:
    return set(_word_tokens(text) + _cjk_ngrams(text, cjk_ngram_sizes))


def _evidence_tokens(text: str, cjk_ngram_sizes: Iterable[int] = (2, 3)) -> Set[str]:
    tokens: Set[str] = set()
    for token in _word_tokens(text):
        tokens.add(token)
    for token in _cjk_ngrams(text, cjk_ngram_sizes):
        tokens.add(token)
    return tokens


def _word_tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9][a-z0-9_+\-.%]{1,}", text.lower(), flags=re.IGNORECASE)


def _cjk_ngrams(text: str, sizes: Iterable[int]) -> List[str]:
    tokens = []
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        for size in sizes:
            if len(run) < size:
                continue
            tokens.extend(run[index : index + size] for index in range(len(run) - size + 1))
    return tokens


def _numbers(text: str) -> List[str]:
    return re.findall(r"\d+(?:\.\d+)?%?", text)


def _normalize_text(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text.lower(), flags=re.UNICODE)
