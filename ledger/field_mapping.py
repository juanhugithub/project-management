"""外部工作表与台账标准字段之间的确定性语义映射。

映射候选可以由 Agent 提出，但保存和执行都必须使用明确的标准字段、版本、
格式和单位规则。模块不修改数据库事实，只负责把输入行翻译成可校验的数据。
"""
import json
from pathlib import Path


class FieldMappingError(ValueError):
    """字段映射契约不完整或翻译输入不符合契约。"""


_ROOT = Path(__file__).resolve().parents[1]
_DICTIONARY = json.loads((_ROOT / "templates" / "standard-fields.v1.json").read_text(encoding="utf-8"))


def standard_fields():
    """返回标准字段字典，供 Agent 发现字段含义和允许格式。"""
    return _DICTIONARY


def _norm(value):
    return "".join(str(value or "").strip().lower().replace(" ", "").replace("_", ""))


def suggest_mapping(headers):
    """按标准字段别名生成确定性候选；无法唯一匹配的字段保持待人工确认。"""
    if not isinstance(headers, list) or any(not isinstance(item, str) for item in headers):
        raise FieldMappingError("headers 必须是字符串数组")
    suggestions = []
    for header in headers:
        key = _norm(header)
        matches = []
        for field in _DICTIONARY["fields"]:
            aliases = [_norm(field["name"]), *(_norm(a) for a in field.get("aliases", []))]
            if key in aliases:
                matches.append(field["name"])
        suggestions.append({"external_name": header, "standard_field": matches[0] if len(matches) == 1 else None,
                            "candidates": matches, "status": "matched" if len(matches) == 1 else "manual_review"})
    return {"dictionary_id": _DICTIONARY["dictionary_id"], "version": _DICTIONARY["version"], "items": suggestions}


def _field(name):
    for field in _DICTIONARY["fields"]:
        if field["name"] == name:
            return field
    raise FieldMappingError(f"不存在标准字段：{name}")


def validate_mapping(mapping):
    """校验已由人工确认的映射，不接受重复目标字段或未知字段。"""
    if not isinstance(mapping, dict) or not isinstance(mapping.get("items"), list):
        raise FieldMappingError("mapping.items 必须是数组")
    targets = []
    for item in mapping["items"]:
        if not isinstance(item, dict) or not item.get("external_name") or not item.get("standard_field"):
            raise FieldMappingError("每个映射项必须包含 external_name 和 standard_field")
        _field(item["standard_field"])
        if item["standard_field"] in targets:
            raise FieldMappingError(f"标准字段重复映射：{item['standard_field']}")
        targets.append(item["standard_field"])
    return True


def translate_rows(rows, mapping):
    """依照已确认映射翻译行；缺少的目标字段不擅自补值。"""
    validate_mapping(mapping)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise FieldMappingError("rows 必须是对象数组")
    translated = []
    for row in rows:
        output = {}
        for item in mapping["items"]:
            external = item["external_name"]
            if external in row:
                output[item["standard_field"]] = row[external]
        translated.append(output)
    return {"dictionary_id": _DICTIONARY["dictionary_id"], "version": _DICTIONARY["version"], "rows": translated}
