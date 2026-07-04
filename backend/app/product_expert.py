import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from .chunking import extract_field_facts
from .parsers import parse_document


IMPACT_RULES = [
    ("页面/入口", ["页面", "入口", "弹窗", "专题", "H5", "小程序", "导航"]),
    ("接口/后端", ["接口", "后端", "API", "返回", "配置", "服务端"]),
    ("权限/登录", ["权限", "授权", "登录", "微信", "免登", "openid"]),
    ("业务规则", ["预约", "票务", "活动", "规则", "资格", "奖励", "任务"]),
    ("排期", ["时间", "日期", "排期", "阶段", "完成", "上线"]),
    ("数据统计", ["数据", "统计", "埋点", "日志", "报表"]),
    ("验收测试", ["验收", "测试", "校验", "异常", "兼容"]),
]
CARD_SECTIONS = [
    ("background", "需求背景", ["背景", "痛点", "问题", "目的", "价值", "为什么"]),
    ("goals", "目标", ["目标", "目的", "期望", "成功", "指标", "收益"]),
    ("users", "用户/角色", ["用户", "角色", "对象", "玩家", "人群", "产品经理", "运营", "测试"]),
    ("scope", "范围/功能", ["需求", "功能", "模块", "页面", "入口", "小程序", "预约", "票务", "导航", "配置"]),
    ("rules", "关键规则", ["规则", "流程", "逻辑", "条件", "限制", "状态", "授权", "登录", "免登"]),
    ("risks", "风险点", ["风险", "注意", "异常", "兼容", "依赖", "问题", "不支持", "限制"]),
    ("acceptance", "验收点", ["验收", "测试", "标准", "校验", "完成", "检查", "用例"]),
]


def group_documents_by_requirement(documents: List[Dict[str, object]]) -> List[Dict[str, object]]:
    groups: Dict[str, Dict[str, object]] = {}
    for document in documents:
        identity = infer_requirement_identity(document)
        key = str(identity["requirement_key"])
        group = groups.setdefault(
            key,
            {
                "requirement_key": key,
                "requirement_title": identity["requirement_title"],
                "project_name": identity["project_name"],
                "document_count": 0,
                "latest_document": None,
                "versions": [],
                "confidence": identity["confidence"],
                "signals": [],
            },
        )
        version = {
            "document_id": document.get("id", ""),
            "title": document.get("title", ""),
            "source_path": document.get("source_path", ""),
            "file_type": document.get("file_type", ""),
            "last_modified": document.get("last_modified", 0),
            "indexed_at": document.get("indexed_at", ""),
            "version_label": identity["version_label"],
            "is_latest": False,
        }
        group["versions"].append(version)
        group["signals"] = _unique_strings(list(group["signals"]) + list(identity["signals"]))

    for group in groups.values():
        versions = sorted(
            group["versions"],
            key=lambda item: (float(item.get("last_modified") or 0), str(item.get("indexed_at") or "")),
            reverse=True,
        )
        if versions:
            versions[0]["is_latest"] = True
            group["latest_document"] = versions[0]
        group["versions"] = versions
        group["document_count"] = len(versions)

    return sorted(
        groups.values(),
        key=lambda item: (
            -int(item.get("document_count", 0)),
            str(item.get("project_name", "")),
            str(item.get("requirement_title", "")),
        ),
    )


def infer_requirement_identity(document: Dict[str, object]) -> Dict[str, object]:
    title = str(document.get("title", ""))
    preview = str(document.get("content_preview", ""))
    source_path = str(document.get("source_path", ""))
    haystack = "\n".join([title, preview, source_path])
    project_name = infer_project_name(haystack)
    requirement_title = infer_requirement_title(title, project_name)
    key = slugify("%s-%s" % (project_name, requirement_title))
    signals = []
    confidence = 0.45

    if project_name:
        signals.append("从标题或字段中识别项目：%s" % project_name)
        confidence += 0.2
    if requirement_title and requirement_title != title:
        signals.append("从文件名中清洗需求名：%s" % requirement_title)
        confidence += 0.15
    if preview:
        signals.append("已使用内容预览辅助判断")
        confidence += 0.1

    return {
        "project_name": project_name or "未识别项目",
        "requirement_title": requirement_title or title,
        "requirement_key": key or slugify(title),
        "version_label": infer_version_label(title, float(document.get("last_modified") or 0)),
        "confidence": round(min(confidence, 0.95), 2),
        "signals": signals or ["仅根据文件名推断"],
    }


def infer_project_name(text: str) -> str:
    quoted = re.search(r"《([^》]{2,40})》", text)
    if quoted:
        return normalize_project_name(quoted.group(1))

    facts = extract_field_facts(text, scope="document")
    for fact in facts:
        label = fact.get("label", "")
        value = fact.get("value", "")
        if any(marker in label for marker in ["项目", "所属", "游戏", "产品"]):
            return normalize_project_name(value)

    compact = text.replace(" ", "")
    if "剑网3" in compact or "剑网三" in compact:
        return "剑网3"
    return ""


def normalize_project_name(value: str) -> str:
    cleaned = re.sub(r"\s+", "", value or "")
    cleaned = re.sub(r"^K\d+[-_－—]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("剑网三", "剑网3")
    return cleaned[:40]


def infer_requirement_title(title: str, project_name: str = "") -> str:
    cleaned = re.sub(r"\.[^.]+$", "", title)
    cleaned = re.sub(r"【[^】]{1,30}】", "", cleaned)
    cleaned = re.sub(r"\[[^\]]{1,30}\]", "", cleaned)
    cleaned = re.sub(r"《[^》]{1,40}》", "", cleaned)
    cleaned = re.sub(r"@\d{4,10}$", "", cleaned)
    cleaned = re.sub(r"^\d{4}年[-_－—]?", "", cleaned)
    if project_name and project_name != "未识别项目":
        cleaned = cleaned.replace(project_name, "")
    cleaned = cleaned.replace("PRD", "").replace("prd", "")
    cleaned = cleaned.strip(" -_－—")
    return cleaned or re.sub(r"\.[^.]+$", "", title)


def infer_version_label(title: str, last_modified: float) -> str:
    for pattern in [r"@(\d{4,10})", r"(\d{4}[-_/年]\d{1,2}[-_/月]\d{1,2})"]:
        match = re.search(pattern, title)
        if match:
            return match.group(1)
    if last_modified:
        return datetime.fromtimestamp(last_modified).strftime("%Y-%m-%d")
    return "未识别版本"


def analyze_requirement_change(
    old_document: Dict[str, object],
    new_document: Dict[str, object],
) -> Dict[str, object]:
    old_text = load_document_text(old_document)
    new_text = load_document_text(new_document)
    old_lines = normalize_lines(old_text)
    new_lines = normalize_lines(new_text)
    added_lines, removed_lines = line_set_diff(old_lines, new_lines)
    field_changes = compare_field_facts(old_text, new_text)
    impact_modules = infer_impact_modules(added_lines + removed_lines + field_change_texts(field_changes))
    open_questions = build_open_questions(field_changes, impact_modules, added_lines, removed_lines)

    return {
        "old_document": document_ref(old_document),
        "new_document": document_ref(new_document),
        "summary": build_change_summary(added_lines, removed_lines, field_changes, impact_modules),
        "added": added_lines[:20],
        "removed": removed_lines[:20],
        "field_changes": field_changes[:20],
        "impact_modules": impact_modules,
        "open_questions": open_questions[:10],
        "limitations": [
            "v0.1 使用规则 diff，不调用 AI。",
            "Word/Excel 结构会先转成纯文本，复杂表格差异可能需要后续增强。",
            "正式效果需要办公电脑上的真实历史版本资料来验证。",
        ],
    }


def build_requirement_card(requirement_key: str, documents: List[Dict[str, object]]) -> Dict[str, object]:
    groups = group_documents_by_requirement(documents)
    group = next((item for item in groups if item["requirement_key"] == requirement_key), None)
    if group is None:
        raise KeyError(requirement_key)

    latest = group.get("latest_document") or {}
    latest_document_id = str(latest.get("document_id", ""))
    latest_document = next(
        (document for document in documents if str(document.get("id", "")) == latest_document_id),
        documents[0] if documents else {},
    )
    text = load_document_text(latest_document)
    lines = normalize_lines(text)
    field_facts = extract_field_facts(text, scope="document")
    impact_modules = infer_impact_modules(lines)
    sections = {
        key: extract_section_lines(lines, keywords, fallback=(key == "scope"))
        for key, _, keywords in CARD_SECTIONS
    }
    open_questions = build_card_open_questions(sections, field_facts, impact_modules, group)
    quality = score_requirement_card(sections, field_facts, impact_modules, group)

    return {
        "requirement_key": group["requirement_key"],
        "requirement_title": group["requirement_title"],
        "project_name": group["project_name"],
        "source_document": document_ref(latest_document),
        "version_label": latest.get("version_label", ""),
        "document_count": group["document_count"],
        "summary": build_card_summary(group, sections, field_facts, impact_modules),
        "sections": sections,
        "field_facts": field_facts[:12],
        "impact_modules": impact_modules,
        "quality": quality,
        "open_questions": open_questions,
        "next_actions": build_next_actions(sections, impact_modules, group),
        "signals": group.get("signals", []),
        "limitations": [
            "v0.1 使用规则抽取，不调用 AI。",
            "正式效果需要办公电脑上的完整历史资料和真实问题集验证。",
            "卡片是产品分析入口，不替代原始需求文档和人工确认。",
        ],
    }


def find_similar_requirements(
    requirement_key: str,
    documents: List[Dict[str, object]],
    limit: int = 3,
) -> Dict[str, object]:
    target_card = build_requirement_card(requirement_key, documents)
    groups = group_documents_by_requirement(documents)
    candidates = []
    for group in groups:
        candidate_key = str(group.get("requirement_key", ""))
        if candidate_key == requirement_key:
            continue
        candidate_card = build_requirement_card(candidate_key, documents)
        score, reasons, shared_terms, shared_modules = score_card_similarity(target_card, candidate_card)
        candidates.append(
            {
                "requirement_key": candidate_card["requirement_key"],
                "requirement_title": candidate_card["requirement_title"],
                "project_name": candidate_card["project_name"],
                "score": score,
                "reasons": reasons,
                "shared_terms": shared_terms[:12],
                "shared_modules": shared_modules,
                "summary": candidate_card["summary"],
                "document_count": candidate_card["document_count"],
                "version_label": candidate_card["version_label"],
            }
        )

    candidates = sorted(candidates, key=lambda item: float(item["score"]), reverse=True)
    return {
        "target": {
            "requirement_key": target_card["requirement_key"],
            "requirement_title": target_card["requirement_title"],
            "project_name": target_card["project_name"],
            "summary": target_card["summary"],
        },
        "similar": candidates[: max(0, limit)],
        "strategy": "规则版相似度：需求卡片关键词 + 影响模块 + 项目名加权；不调用 AI，不依赖真实 embedding。",
        "limitations": [
            "v0 使用词面相似度，不能理解深层业务语义。",
            "同项目、同模块会更容易相似，但仍需要人工复核。",
            "切到真实 embedding 后，可以把卡片相似度升级为语义相似度。",
        ],
    }


def score_card_similarity(
    target_card: Dict[str, object],
    candidate_card: Dict[str, object],
) -> Tuple[float, List[str], List[str], List[str]]:
    target_tokens = card_tokens(target_card)
    candidate_tokens = card_tokens(candidate_card)
    shared_terms = sorted(target_tokens & candidate_tokens)
    union_size = len(target_tokens | candidate_tokens)
    token_score = len(shared_terms) / union_size if union_size else 0.0

    target_modules = module_labels(target_card)
    candidate_modules = module_labels(candidate_card)
    shared_modules = sorted(target_modules & candidate_modules)
    module_union_size = len(target_modules | candidate_modules)
    module_score = len(shared_modules) / module_union_size if module_union_size else 0.0

    same_project = target_card.get("project_name") == candidate_card.get("project_name")
    project_score = 1.0 if same_project and target_card.get("project_name") not in {"", "未识别项目"} else 0.0

    score = round(min((token_score * 0.58) + (module_score * 0.27) + (project_score * 0.15), 1.0), 4)
    reasons = []
    if same_project:
        reasons.append("同项目：%s" % target_card.get("project_name", ""))
    if shared_modules:
        reasons.append("共同影响模块：%s" % "、".join(shared_modules[:4]))
    if shared_terms:
        reasons.append("共同关键词：%s" % "、".join(shared_terms[:8]))
    if not reasons:
        reasons.append("未找到明显共同特征，仅作为低相似候选。")
    return score, reasons, shared_terms, shared_modules


def card_tokens(card: Dict[str, object]) -> set:
    text_parts = [
        str(card.get("requirement_title", "")),
        str(card.get("project_name", "")),
        str(card.get("summary", "")),
    ]
    sections = card.get("sections", {})
    if isinstance(sections, dict):
        for items in sections.values():
            if isinstance(items, list):
                text_parts.extend(str(item) for item in items)
    field_facts = card.get("field_facts", [])
    if isinstance(field_facts, list):
        for fact in field_facts:
            if isinstance(fact, dict):
                text_parts.append("%s %s" % (fact.get("label", ""), fact.get("value", "")))
    return tokenize_similarity_text("\n".join(text_parts))


def module_labels(card: Dict[str, object]) -> set:
    modules = card.get("impact_modules", [])
    labels = set()
    if isinstance(modules, list):
        for module in modules:
            if isinstance(module, dict) and module.get("label"):
                labels.add(str(module["label"]))
    return labels


def tokenize_similarity_text(text: str) -> set:
    normalized = text.lower()
    tokens = set(re.findall(r"[a-z0-9][a-z0-9_+\-.%]{1,}", normalized, flags=re.IGNORECASE))
    cjk_runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
    for run in cjk_runs:
        if len(run) <= 2:
            tokens.add(run)
            continue
        for size in (2, 3):
            if len(run) < size:
                continue
            for index in range(len(run) - size + 1):
                token = run[index : index + size]
                if not is_weak_similarity_token(token):
                    tokens.add(token)
    return tokens


def is_weak_similarity_token(token: str) -> bool:
    weak_tokens = {
        "需求",
        "文档",
        "功能",
        "项目",
        "页面",
        "用户",
        "规则",
        "支持",
        "进行",
        "需要",
        "可以",
        "实现",
    }
    return token in weak_tokens


def load_document_text(document: Dict[str, object]) -> str:
    path = Path(str(document.get("source_path", "")))
    if path.exists():
        try:
            return parse_document(path)
        except Exception:
            pass
    return str(document.get("content_preview", ""))


def normalize_lines(text: str) -> List[str]:
    lines = []
    seen = set()
    for line in text.splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if len(cleaned) < 2:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        lines.append(cleaned)
    return lines


def line_set_diff(old_lines: List[str], new_lines: List[str]) -> Tuple[List[str], List[str]]:
    old_set = set(old_lines)
    new_set = set(new_lines)
    added = [line for line in new_lines if line not in old_set]
    removed = [line for line in old_lines if line not in new_set]
    return added, removed


def compare_field_facts(old_text: str, new_text: str) -> List[Dict[str, str]]:
    old_facts = fact_map(extract_field_facts(old_text, scope="document"))
    new_facts = fact_map(extract_field_facts(new_text, scope="document"))
    changes = []
    for label in sorted(set(old_facts) | set(new_facts)):
        old_value = old_facts.get(label, "")
        new_value = new_facts.get(label, "")
        if old_value == new_value:
            continue
        change_type = "modified"
        if not old_value:
            change_type = "added"
        elif not new_value:
            change_type = "removed"
        changes.append(
            {
                "label": label,
                "old_value": old_value,
                "new_value": new_value,
                "change_type": change_type,
            }
        )
    return changes


def fact_map(facts: List[Dict[str, str]]) -> Dict[str, str]:
    mapped: Dict[str, List[str]] = {}
    for fact in facts:
        label = str(fact.get("label", "")).strip()
        value = str(fact.get("value", "")).strip()
        if not label or not value:
            continue
        mapped.setdefault(label, [])
        if value not in mapped[label]:
            mapped[label].append(value)
    return {label: "；".join(values) for label, values in mapped.items()}


def field_change_texts(field_changes: List[Dict[str, str]]) -> List[str]:
    return [
        "%s %s %s" % (change.get("label", ""), change.get("old_value", ""), change.get("new_value", ""))
        for change in field_changes
    ]


def infer_impact_modules(changed_lines: List[str]) -> List[Dict[str, object]]:
    text = "\n".join(changed_lines)
    modules = []
    for label, keywords in IMPACT_RULES:
        matched = [keyword for keyword in keywords if keyword.lower() in text.lower()]
        if matched:
            modules.append({"label": label, "matched_keywords": matched[:8]})
    if not modules and changed_lines:
        modules.append({"label": "内容变更", "matched_keywords": []})
    return modules


def build_open_questions(
    field_changes: List[Dict[str, str]],
    impact_modules: List[Dict[str, object]],
    added_lines: List[str],
    removed_lines: List[str],
) -> List[str]:
    questions = []
    for change in field_changes[:5]:
        questions.append(
            "确认字段【%s】从“%s”调整为“%s”是否已同步给相关同学。"
            % (change.get("label", ""), change.get("old_value", "空"), change.get("new_value", "空"))
        )
    labels = {str(module.get("label", "")) for module in impact_modules}
    if "接口/后端" in labels:
        questions.append("确认接口、后端配置和前端展示是否同步调整。")
    if "权限/登录" in labels:
        questions.append("确认授权、登录和异常态是否补充验收用例。")
    if "排期" in labels:
        questions.append("确认排期变化是否影响研发、测试和上线节奏。")
    if added_lines and not questions:
        questions.append("确认新增内容是否需要补充验收标准和测试用例。")
    if removed_lines:
        questions.append("确认删除内容是否会影响历史入口、用户路径或运营配置。")
    return _unique_strings(questions)


def build_change_summary(
    added_lines: List[str],
    removed_lines: List[str],
    field_changes: List[Dict[str, str]],
    impact_modules: List[Dict[str, object]],
) -> str:
    if not added_lines and not removed_lines and not field_changes:
        return "未发现明显文本或字段差异。"
    modules = "、".join(str(module.get("label", "")) for module in impact_modules) or "未识别"
    return "发现新增 %s 条、删除 %s 条、字段变化 %s 个；可能影响：%s。" % (
        len(added_lines),
        len(removed_lines),
        len(field_changes),
        modules,
    )


def extract_section_lines(lines: List[str], keywords: List[str], fallback: bool = False) -> List[str]:
    matched = []
    for line in lines:
        if any(keyword.lower() in line.lower() for keyword in keywords):
            matched.append(line)
    if not matched and fallback:
        matched = lines[:6]
    return trim_lines(matched, limit=8, max_chars=180)


def trim_lines(lines: List[str], limit: int, max_chars: int) -> List[str]:
    trimmed = []
    for line in lines:
        cleaned = line.strip()
        if len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars].rstrip() + "..."
        if cleaned and cleaned not in trimmed:
            trimmed.append(cleaned)
        if len(trimmed) >= limit:
            break
    return trimmed


def build_card_summary(
    group: Dict[str, object],
    sections: Dict[str, List[str]],
    field_facts: List[Dict[str, str]],
    impact_modules: List[Dict[str, object]],
) -> str:
    facts = fact_map(field_facts)
    target = ""
    if sections.get("goals"):
        target = sections["goals"][0]
    elif sections.get("background"):
        target = sections["background"][0]
    modules = "、".join(str(module.get("label", "")) for module in impact_modules[:4]) or "未识别"
    owner = facts.get("项目/部门所属") or facts.get("项目") or str(group.get("project_name", ""))
    return "%s / %s：%s可能涉及 %s。" % (
        owner or "未识别项目",
        group.get("requirement_title", ""),
        (target + "；") if target else "",
        modules,
    )


def score_requirement_card(
    sections: Dict[str, List[str]],
    field_facts: List[Dict[str, str]],
    impact_modules: List[Dict[str, object]],
    group: Dict[str, object],
) -> Dict[str, object]:
    section_labels = {key: label for key, label, _ in CARD_SECTIONS}
    required_sections = ["background", "goals", "scope", "rules", "acceptance"]
    optional_sections = ["users", "risks"]
    missing_sections = [
        section_labels[key]
        for key in required_sections
        if not sections.get(key)
    ]
    weak_sections = [
        section_labels[key]
        for key in optional_sections
        if not sections.get(key)
    ]

    score = 0.0
    for key in required_sections:
        if sections.get(key):
            score += 0.14
    for key in optional_sections:
        if sections.get(key):
            score += 0.07
    if field_facts:
        score += 0.08
    if impact_modules:
        score += 0.08
    if int(group.get("document_count", 0)) >= 2:
        score += 0.02

    score = round(min(score, 1.0), 2)
    if score >= 0.72 and not missing_sections:
        status = "good"
    elif score >= 0.42:
        status = "fair"
    else:
        status = "needs_review"

    return {
        "status": status,
        "completeness_score": score,
        "missing_sections": missing_sections,
        "weak_sections": weak_sections,
        "review_notes": build_card_review_notes(missing_sections, weak_sections, field_facts, group),
    }


def build_card_review_notes(
    missing_sections: List[str],
    weak_sections: List[str],
    field_facts: List[Dict[str, str]],
    group: Dict[str, object],
) -> List[str]:
    notes = []
    if missing_sections:
        notes.append("优先补齐：%s。" % "、".join(missing_sections))
    if weak_sections:
        notes.append("可继续增强：%s。" % "、".join(weak_sections))
    if not field_facts:
        notes.append("建议在文档中补充结构化字段，便于后续版本对比和影响分析。")
    if int(group.get("document_count", 0)) < 2:
        notes.append("当前缺少历史版本，暂时只能做单版本摘要，不能做趋势判断。")
    return notes


def build_card_open_questions(
    sections: Dict[str, List[str]],
    field_facts: List[Dict[str, str]],
    impact_modules: List[Dict[str, object]],
    group: Dict[str, object],
) -> List[str]:
    questions = []
    facts = fact_map(field_facts)
    if not sections.get("goals"):
        questions.append("需求目标没有被清晰抽取，建议补充可验收的目标或成功指标。")
    if not sections.get("acceptance"):
        questions.append("验收标准没有被清晰抽取，建议补充测试口径和通过条件。")
    if not facts:
        questions.append("文档级字段较少，建议补充项目、负责人、排期、对接人等基础信息。")
    if int(group.get("document_count", 0)) < 2:
        questions.append("当前只识别到 1 个版本，后续需要更多历史版本才能分析变化趋势。")

    labels = {str(module.get("label", "")) for module in impact_modules}
    if "权限/登录" in labels:
        questions.append("涉及登录或授权，建议确认未登录、授权失败、切环境等异常态。")
    if "接口/后端" in labels:
        questions.append("涉及接口或配置，建议确认返回字段、默认值和前后端兜底逻辑。")
    if "业务规则" in labels:
        questions.append("涉及业务规则，建议确认边界条件、重复操作和运营配置口径。")
    return _unique_strings(questions)[:10]


def build_next_actions(
    sections: Dict[str, List[str]],
    impact_modules: List[Dict[str, object]],
    group: Dict[str, object],
) -> List[str]:
    actions = [
        "用原始文档核对需求卡片是否准确。",
        "把不准确的抽取结果记录成后续规则优化样例。",
    ]
    if int(group.get("document_count", 0)) >= 2:
        actions.append("对最新两个版本执行变更分析，确认新增、删除和字段变化。")
    else:
        actions.append("补充同一需求的历史版本后，再做变更趋势分析。")
    if sections.get("risks"):
        actions.append("把风险点转成测试关注点和验收清单。")
    if impact_modules:
        actions.append("按影响模块同步产品、研发、测试和运营。")
    return _unique_strings(actions)


def document_ref(document: Dict[str, object]) -> Dict[str, object]:
    return {
        "id": document.get("id", ""),
        "title": document.get("title", ""),
        "source_path": document.get("source_path", ""),
        "file_type": document.get("file_type", ""),
    }


def slugify(value: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", (value or "").lower(), flags=re.UNICODE)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:120]


def _unique_strings(values: List[str]) -> List[str]:
    unique = []
    seen = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique
