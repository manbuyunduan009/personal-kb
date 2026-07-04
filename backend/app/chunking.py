import re
from typing import Dict, List, Optional


DOCUMENT_ATTRIBUTE_MARKERS = [
    "项目",
    "所属",
    "游戏",
    "产品",
    "部门",
    "域名",
    "概域名",
    "对接人",
    "负责人",
    "联系人",
    "日期",
    "时间",
    "编号",
    "单号",
    "WorkTile",
]
OWNERSHIP_ATTRIBUTE_MARKERS = ["项目", "所属", "游戏", "产品", "部门"]
PERSON_ATTRIBUTE_MARKERS = ["对接人", "负责人", "联系人"]
TIME_ATTRIBUTE_MARKERS = ["日期", "时间", "排期", "完成"]
DEFAULT_PARENT_CHILD_COUNT = 3
DEFAULT_PARENT_CONTEXT_MAX_CHARS = 2600


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
    parent_child_count: int = DEFAULT_PARENT_CHILD_COUNT,
    parent_context_max_chars: int = DEFAULT_PARENT_CONTEXT_MAX_CHARS,
) -> List[Dict[str, object]]:
    """Build enriched chunk records for indexing and answer context."""
    if parent_child_count <= 0:
        raise ValueError("parent_child_count must be greater than 0")
    if parent_context_max_chars <= 0:
        raise ValueError("parent_context_max_chars must be greater than 0")

    chunks = split_text(text, chunk_size=chunk_size, overlap=overlap)
    document_facts = extract_field_facts(text, scope="document")
    parent_contexts = build_parent_contexts(
        chunks,
        parent_child_count=parent_child_count,
        max_chars=parent_context_max_chars,
    )
    records = []
    for index, chunk in enumerate(chunks):
        parent_index = index // parent_child_count
        header = infer_chunk_header(document_title, chunk)
        chunk_facts = extract_field_facts(chunk, scope="chunk")
        field_facts = merge_field_facts(document_facts, chunk_facts)
        generated_questions = generate_potential_questions(document_title, header, chunk, field_facts)
        previous_context = chunks[index - 1][-260:] if index > 0 else ""
        next_context = chunks[index + 1][:260] if index + 1 < len(chunks) else ""
        embedding_text = "\n".join(
            part
            for part in [
                "文档：%s" % document_title,
                "章节：%s" % header,
                "文档属性：%s" % format_field_facts(document_facts),
                "局部字段：%s" % format_field_facts(chunk_facts),
                "可能问题：%s" % "；".join(generated_questions),
                "正文：%s" % chunk,
            ]
            if part.strip()
        )
        records.append(
            {
                "content": chunk,
                "chunk_header": header,
                "document_facts": document_facts,
                "chunk_facts": chunk_facts,
                "field_facts": field_facts,
                "generated_questions": generated_questions,
                "previous_context": previous_context,
                "next_context": next_context,
                "parent_index": parent_index,
                "parent_context": parent_contexts.get(parent_index, ""),
                "embedding_text": embedding_text,
                "context_summary": summarize_text(chunk),
            }
        )
    return records


def build_parent_contexts(
    chunks: List[str],
    parent_child_count: int,
    max_chars: int,
) -> Dict[int, str]:
    contexts = {}
    for parent_index, start in enumerate(range(0, len(chunks), parent_child_count)):
        end = min(start + parent_child_count, len(chunks))
        parts = [
            "子片段 %s：\n%s" % (chunk_index, chunks[chunk_index])
            for chunk_index in range(start, end)
        ]
        contexts[parent_index] = limit_text("\n\n".join(parts), max_chars)
    return contexts


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


def generate_potential_questions(
    document_title: str,
    header: str,
    chunk: str,
    field_facts: Optional[List[Dict[str, str]]] = None,
) -> List[str]:
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
    if has_document_attribute_field(field_facts or []):
        add("%s的基础信息是什么？" % topic)
    if has_field_label(field_facts or [], OWNERSHIP_ATTRIBUTE_MARKERS):
        add("%s是哪个项目的？" % topic)
        add("%s是哪个游戏的？" % topic)
        add("%s属于哪个项目或部门？" % topic)
        add("项目/部门所属是什么？")
    if has_field_label(field_facts or [], PERSON_ATTRIBUTE_MARKERS):
        add("%s的负责人或对接人是谁？" % topic)
    if has_field_label(field_facts or [], TIME_ATTRIBUTE_MARKERS):
        add("%s有哪些关键日期或时间？" % topic)

    return questions[:9]


def extract_field_facts(text: str, scope: str = "chunk") -> List[Dict[str, str]]:
    facts = []
    for line in text.splitlines():
        cells = [clean_table_cell(cell) for cell in line.split("|")]
        cells = [cell for cell in cells if cell]
        if len(cells) >= 2:
            for index in range(0, len(cells) - 1, 2):
                label = cells[index]
                value = cells[index + 1]
                if is_field_label(label) and is_field_value(value):
                    facts.append({"label": label, "value": value, "scope": scope})
            continue

        for match in re.finditer(r"([^：:\n]{2,24})[：:]\s*([^：:\n]{2,80})", line):
            label = clean_table_cell(match.group(1))
            value = clean_table_cell(match.group(2))
            if is_field_label(label) and is_field_value(value):
                facts.append({"label": label, "value": value, "scope": scope})

    deduped = []
    seen = set()
    for fact in facts:
        key = (fact["label"], fact["value"])
        if key not in seen:
            seen.add(key)
            deduped.append(fact)
    return deduped[:12]


def merge_field_facts(*fact_groups: List[Dict[str, str]]) -> List[Dict[str, str]]:
    merged = []
    seen = set()
    for facts in fact_groups:
        for fact in facts:
            key = (fact.get("label", ""), fact.get("value", ""))
            if key not in seen:
                seen.add(key)
                merged.append(fact)
    return merged[:18]


def clean_table_cell(value: str) -> str:
    return value.strip().strip("*").strip()


def is_field_label(value: str) -> bool:
    if len(value) > 24:
        return False
    if any(marker in value for marker in ["。", "，", "；", ";", "？", "?", "是否"]):
        return False
    return any(marker in value for marker in DOCUMENT_ATTRIBUTE_MARKERS)


def is_field_value(value: str) -> bool:
    if not value or value in {"/", "-", "无", "不涉及"}:
        return False
    return len(value) <= 120


def has_document_attribute_field(field_facts: List[Dict[str, str]]) -> bool:
    return has_field_label(field_facts, DOCUMENT_ATTRIBUTE_MARKERS)


def has_field_label(field_facts: List[Dict[str, str]], markers: List[str]) -> bool:
    for fact in field_facts:
        label = fact.get("label", "")
        if any(marker in label for marker in markers):
            return True
    return False


def format_field_facts(field_facts: List[Dict[str, str]]) -> str:
    return "；".join("%s: %s" % (fact["label"], fact["value"]) for fact in field_facts)


def limit_text(text: str, max_chars: int) -> str:
    compact = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(compact) <= max_chars:
        return compact
    if max_chars <= 3:
        return compact[:max_chars]
    return compact[: max_chars - 3].rstrip() + "..."


def summarize_text(text: str, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."
