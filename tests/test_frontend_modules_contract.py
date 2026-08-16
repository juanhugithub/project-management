# -*- coding: utf-8 -*-
"""原生前端模块化改造的静态契约。

这些测试只关心改造后的公开边界：入口是否使用 ES Module、目录是否形成
清晰的 core/pages/components 分层，以及浏览器脚本能否被 Node 解析。测试
不会检查函数内部的 DOM 细节，避免把实现选择错误地固化成测试约束。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def read(path: Path) -> str:
    """统一按 UTF-8 读取源码，契约测试不依赖运行中的后端服务。"""
    return path.read_text(encoding="utf-8")


def exported_names(source: str) -> set[str]:
    """提取常见 ES Module 导出形式，不绑定导出声明的排版方式。"""
    names = set(re.findall(r"\bexport\s+(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)", source))
    for group in re.findall(r"\bexport\s*\{([^}]*)\}", source, flags=re.S):
        for item in group.split(","):
            name = item.strip().split(" as ")[-1].strip()
            if re.match(r"^[A-Za-z_$][\w$]*$", name):
                names.add(name)
    return names


def test_index_uses_module_entry_without_legacy_stylesheet_reference():
    """入口必须加载模块化启动器，样式由分层 CSS 入口接管。"""
    html = read(STATIC / "index.html")
    assert re.search(r'<script\b[^>]*type=["\']module["\'][^>]*src=', html), (
        "index.html 必须通过 type=module 加载新的前端入口"
    )
    assert not re.search(r'<link\b[^>]*href=["\'][^"\']*style\.css(?:\?|["\'])', html), (
        "index.html 不应继续直接引用合并前的旧 style.css"
    )


def test_core_modules_exist_and_export_public_interfaces():
    """core 层必须提供请求、状态、路由和反馈四类基础能力。"""
    # 工厂式接口和直接函数接口都能满足边界；这里约束“至少一个公开能力”，
    # 允许实现继续使用 createApiClient/createHashRouter 等清晰的命名。
    expected = {
        "core/api.js": ("api", "createApiClient"),
        "core/store.js": ("createStore",),
        "core/router.js": ("navigate", "createHashRouter"),
        "core/toast.js": ("toast", "createToast"),
    }
    missing = []
    for relative, interfaces in expected.items():
        path = STATIC / relative
        if not path.is_file():
            missing.append(f"{relative}（文件不存在）")
            continue
        exports = exported_names(read(path))
        if not any(interface in exports for interface in interfaces):
            missing.append(f"{relative}::{'/'.join(interfaces)}")
    assert not missing, f"core 模块缺少公开接口: {missing}"


def test_pages_and_components_have_expected_boundaries():
    """页面和通用组件目录完整，后续业务代码可按边界独立演进。"""
    pages = ("dashboard", "projects", "enterprises", "reminders", "statistics", "settings")
    components = ("table", "pagination", "modal", "filters")
    missing = [f"pages/{name}.js" for name in pages if not (STATIC / "pages" / f"{name}.js").is_file()]
    missing += [f"components/{name}.js" for name in components if not (STATIC / "components" / f"{name}.js").is_file()]
    assert not missing, f"模块化目录缺少文件: {missing}"


def test_every_primary_navigation_route_has_a_page_loader():
    """主导航必须同时激活页面并触发加载，避免只改变 hash 而页面不切换。"""
    source = read(STATIC / "app.js")
    routes = ("dashboard", "projects", "reminders", "enterprises", "stats")
    missing = [route for route in routes if not re.search(rf"\b{route}\s*:\s*\(\)\s*=>", source)]
    assert not missing, f"主导航缺少页面加载器: {missing}"


def test_page_state_defines_full_lifecycle_semantics():
    """集中式状态至少表达空闲、加载、成功和失败四种生命周期。"""
    sources = [read(path) for path in (STATIC / "core").rglob("*.js")]
    sources += [read(path) for path in (STATIC / "pages").rglob("*.js")]
    source = "\n".join(sources)
    missing = [status for status in ("idle", "loading", "ready", "error") if not re.search(rf"['\"]{status}['\"]", source)]
    assert not missing, f"页面状态缺少生命周期语义: {missing}"


def test_project_and_enterprise_queries_support_cancellation():
    """大列表连续查询必须具备取消信号或请求协调器，避免旧响应覆盖新筛选。"""
    missing = []
    for page in ("projects", "enterprises"):
        path = STATIC / "pages" / f"{page}.js"
        source = read(path) if path.is_file() else ""
        if not re.search(r"AbortController|\bsignal\b|requestCoordinator|请求协调", source):
            missing.append(f"pages/{page}.js")
    assert not missing, f"列表查询缺少 AbortController/Signal 或请求协调能力: {missing}"


def test_project_excel_import_uses_preview_and_explicit_confirmation():
    """项目 Excel 上传只能先预览，用户确认后才刷新列表并报告成功。"""
    source = read(STATIC / "components" / "importer.js")
    assert "renderProjectPreview" in source
    assert re.search(r"/import/\$\{result\.id\}/confirm", source)
    assert "全部导入成功" not in source, "不得再用旧版 0/0 统计误报导入成功"
    assert "summary.blocking" in source


def test_excel_drop_zone_has_layered_component_styles_without_emoji_dependency():
    """模块化样式必须包含完整拖拽区规则，上传图标不依赖单位电脑的 Emoji 字体。"""
    html = read(STATIC / "index.html")
    css = read(STATIC / "style" / "components.css")
    assert all(selector in css for selector in (".drop-zone", ".dz-icon", ".drag-overlay", ".excel-tools"))
    assert "📥" not in html and "📄" not in html
    assert 'role="button"' in html and 'tabindex="0"' in html


def test_layered_css_files_exist_and_every_javascript_passes_node_check():
    """CSS 分层和逐文件语法检查共同保证拆分后仍可被浏览器加载。"""
    layers = ("tokens.css", "base.css", "layout.css", "components.css", "pages.css")
    missing = [f"style/{name}" for name in layers if not (STATIC / "style" / name).is_file()]
    assert not missing, f"CSS 分层文件缺失: {missing}"

    node = shutil.which("node")
    assert node, "前端模块契约需要 Node.js 执行逐文件 --check"
    failures = []
    for path in sorted(STATIC.rglob("*.js")):
        result = subprocess.run(
            [node, "--check", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode:
            failures.append(f"{path.relative_to(ROOT)}: {result.stderr.strip()}")
    assert not failures, "以下 JavaScript 文件未通过 Node 语法检查:\n" + "\n".join(failures)
