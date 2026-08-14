import json
from pathlib import Path

from ledger import field_mapping


def test_field_dictionary_and_alias_suggestion_are_versioned():
    dictionary = field_mapping.standard_fields()
    assert dictionary["version"] == "1.0.0"
    result = field_mapping.suggest_mapping(["文号", "承担单位", "项目总投资", "未知字段"])
    assert result["items"][0]["standard_field"] == "project.project_no"
    assert result["items"][1]["standard_field"] == "enterprise.name"
    assert result["items"][2]["standard_field"] == "project.total_amount"
    assert result["items"][3]["status"] == "manual_review"


def test_confirmed_mapping_translates_without_writing_facts():
    mapping = {"items": [
        {"external_name": "文号", "standard_field": "project.project_no"},
        {"external_name": "金额", "standard_field": "funding.amount"},
    ]}
    result = field_mapping.translate_rows([{"文号": "A-1", "金额": 12.5}], mapping)
    assert result["rows"] == [{"project.project_no": "A-1", "funding.amount": 12.5}]

