# -*- coding: utf-8 -*-
"""D14 前端改造的静态契约。

这些检查只约束政务台账不能牺牲的可用性和既有接口边界，不限制具体视觉实现。
浏览器分辨率、键盘路径和真实数据状态仍由 docs/d14-visual-acceptance.md 人工验收。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def read_static(name: str) -> str:
    """以 UTF-8 读取受验收的前端源文件，避免测试依赖正式数据库。"""
    return (STATIC / name).read_text(encoding="utf-8")


def read_all_javascript() -> str:
    """模块化后按整个前端脚本树检查接口，不再假设所有逻辑位于 app.js。"""
    return "\n".join(path.read_text(encoding="utf-8") for path in STATIC.rglob("*.js"))


def test_d14_static_javascript_has_valid_syntax():
    """视觉重构不能让原生脚本在加载前就失败。"""
    node = shutil.which("node")
    assert node, "D14 前端验收需要 Node.js 执行 app.js 语法检查"
    result = subprocess.run(
        [node, "--check", str(STATIC / "app.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_d14_preserves_existing_api_paths_and_dom_anchors():
    """D14 只能换展示层，不得断开既有原生 JS、页面锚点和业务 API。"""
    html = read_static("index.html")
    js = read_all_javascript()

    required_api_paths = (
        "/dict", "/enterprises", "/projects", "/fundings", "/nodes",
        "/config", "/dashboard", "/reminders", "/funding-plan", "/stats",
    )
    missing_paths = [path for path in required_api_paths if path not in js]
    assert not missing_paths, f"D14 不得移除既有 API 调用: {missing_paths}"

    required_ids = (
        "tab-dashboard", "tab-projects", "tab-reminders", "tab-enterprises",
        "tab-stats", "tab-dict", "dash-cards", "dash-reminders", "dash-funding",
        "project-table", "project-empty", "project-detail", "flt-level", "flt-category",
        "flt-stage", "flt-district", "flt-q", "btn-search", "btn-add-project",
        "modal", "modal-form", "toast",
    )
    missing_ids = [element_id for element_id in required_ids if f'id="{element_id}"' not in html]
    assert not missing_ids, f"D14 不得移除既有 DOM 锚点: {missing_ids}"


def test_d14_project_detail_keeps_all_six_funding_facts_visible():
    """项目详情首屏必须同时给出六项资金事实，禁止回到含糊的“已到位”。"""
    detail = read_static("pages/projects.js")

    required_labels = ("项目总金额", "计划拨付", "已拨付", "已到账", "待拨", "资金勾稽")
    missing_labels = [label for label in required_labels if label not in detail]
    assert not missing_labels, f"项目详情缺少关键资金事实: {missing_labels}"
    detail_without_comments = re.sub(r"//[^\n]*|/\*.*?\*/", "", detail, flags=re.S)
    assert "已到位" not in detail_without_comments, "“已到位”口径含糊，不能出现在项目详情的资金事实区"


def test_project_table_displays_district_and_supports_all_business_field_sorting():
    """项目总览除操作列外全部支持排序，区镇直接显示承担企业对应的区镇。"""
    html = read_static("index.html")
    js = read_all_javascript()
    sortable_fields = re.findall(r'<th[^>]*data-sort="([^"]+)"', html)
    assert sortable_fields == [
        "name", "project_no", "level", "category", "enterprise_name",
        "enterprise_district", "total_amount", "disbursed_total", "stage",
    ]
    assert "<th>操作</th>" in html
    assert "SORT_FIELDS" in js and "sortedItems" in js
    assert "enterprise_district" in js, "项目行必须显示承担企业的区镇字段"
    assert "disbursed_total" in js, "已拨付列必须使用项目接口的明确资金口径"


def test_d14_critical_information_is_not_hover_only_and_keyboard_focus_is_visible():
    """状态、错误和主操作不能靠悬停才出现；键盘焦点必须看得见。"""
    css = read_static("style.css")
    html = read_static("index.html")

    # 政务台账不采用“悬停显示内容”的信息架构；辅助动效仍可改变颜色或边框。
    hover_display = re.findall(r"[^}]*:hover\s*\{[^}]*\bdisplay\s*:", css, flags=re.S)
    assert not hover_display, "不得仅在 :hover 时显示信息或操作；关键内容必须默认可见"

    focus_rules = re.findall(r":focus-visible\s*\{([^}]*)\}", css, flags=re.S)
    assert focus_rules, "必须定义 :focus-visible，保证键盘操作时焦点可见"
    assert any(re.search(r"\b(outline|box-shadow|border-color)\s*:", rule) for rule in focus_rules), (
        ":focus-visible 必须提供可辨识的焦点样式"
    )
    assert 'id="toast"' in html and "加载失败" in read_static("app.js"), (
        "保留可见的错误反馈容器与加载失败提示"
    )


def test_d14_office_viewport_has_responsive_layout_contract():
    """表格可横向查看，工作台在办公小屏可重排；不能把关键内容裁出视口。"""
    css = read_static("style.css")
    assert re.search(r"\.table-wrap\s*\{[^}]*\boverflow(?:-x)?\s*:\s*auto", css, re.S), (
        "数据表必须保留可访问的横向滚动容器，避免 1024px 办公屏裁切列"
    )
    assert re.search(r"\.dash-cols\s*\{[^}]*grid-template-columns", css, re.S), "工作台必须保持明确栅格"
    assert re.search(r"@media\s*\([^)]*max-width", css), "必须有窄屏重排规则"
    assert re.search(r"\.dash-cols\s*\{[^}]*grid-template-columns\s*:\s*1fr", css, re.S), (
        "窄屏时工作台双栏必须纵向重排"
    )
