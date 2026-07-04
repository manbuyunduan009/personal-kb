import re
from typing import Dict, List


def split_text(text: str, chunk_size: int = 800, overlap: int = 120) -> List[str]:
    """Split text into overlapping chunks for retrieval."""
    cleaned = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not cleaned:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")

    chunks = []
    start = 0
    text_len = len(cleaned)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == text_len:
            break
        start = end - overlap

    return chunks


def build_chunk_records(
    document_title: str,
    text: str,
    chunk_size: int = 800,
    overlap: int = 120,
) -> List[Dict[str, object]]:
    """Build enriched chunk records for indexing and answer context."""
    chunks = split_text(text, chunk_size=chunk_size, overlap=overlap)
    records = []
    for index, chunk in enumerate(chunks):
        header = infer_chunk_header(document_title, chunk)
        generated_questions = generate_potential_questions(document_title, header, chunk)
        previous_context = chunks[index - 1][-260:] if index > 0 else ""
        next_context = chunks[index + 1][:260] if index + 1 < len(chunks) else ""
        embedding_text = "\n".join(
            part
            for part in [
                "文档：%s" % document_title,
                "章节：%s" % header,
                "可能问题：%s" % "；".join(generated_questions),
                "正文：%s" % chunk,
            ]
            if part.strip()
        )
        records.append(
            {
                "content": chunk,
                "chunk_header": header,
                "generated_questions": generated_questions,
                "previous_context": previous_context,
                "next_context": next_context,
                "embedding_text": embedding_text,
                "context_summary": summarize_text(chunk),
            }
        )
    return records


def infer_chunk_header(document_title: str, chunk: str) -> str:
    """Infer a lightweight chunk header from headings or section-like lines."""
    for line in chunk.splitlines():
        cleaned = line.strip().strip("|").strip()
        if not cleaned:
            continue

        markdown_heading = re.match(r"^#{1,6}\s+(.{2,80})$", cleaned)
        if markdown_heading:
            return markdown_heading.group(1).strip()

        section_heading = re.match(
            r"^((第[一二三四五六七八九十\d]+[章节部分篇])|([一二三四五六七八九十\d]+[、.．]))\s*(.{2,80})$",
            cleaned,
        )
        if section_heading:
            return cleaned[:80]

        if len(cleaned) <= 36 and any(marker in cleaned for marker in ["需求", "目标", "背景", "计划", "规则", "验收"]):
            return cleaned

    return document_title.rsplit(".", 1)[0]


def generate_potential_questions(document_title: str, header: str, chunk: str) -> List[str]:
    """Rule-based document augmentation for the first teaching version."""
    haystack = "%s %s %s" % (document_title, header, chunk[:500])
    questions = []

    def add(question: str) -> None:
        if question not in questions:
            questions.append(question)

    topic = header or document_title
    add("%s讲了什么？" % topic)

    if any(word in haystack for word in ["需求", "功能", "模块", "页面"]):
        add("%s有哪些需求？" % topic)
        add("%s包含哪些功能模块？" % topic)
    if any(word in haystack for word in ["目标", "目的", "价值"]):
        add("%s的目标是什么？" % topic)
    if any(word in haystack for word in ["用户", "人群", "角色", "对象"]):
        add("%s的目标用户是谁？" % topic)
    if any(word in haystack for word in ["问题", "痛点", "背景"]):
        add("%s要解决什么问题？" % topic)
    if any(word in haystack for word in ["阶段", "计划", "排期", "时间", "里程碑"]):
        add("%s有哪些阶段和计划？" % topic)
    if any(word in haystack for word in ["验收", "标准", "指标"]):
        add("%s的验收标准是什么？" % topic)
    if any(word in haystack for word in ["规则", "奖励", "任务", "活动"]):
        add("%s有哪些活动规则和任务？" % topic)

    return questions[:6]


def summarize_text(text: str, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."
