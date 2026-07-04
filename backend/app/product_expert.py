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
