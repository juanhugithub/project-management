#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导入模板下载契约：安装包资源完整，模板缺失时也能在当前进程内生成。"""

import io
from pathlib import Path

from openpyxl import load_workbook

import app
from release_tools.release_manifest import application_data_sources


class TemplateResponse:
    """记录模板接口写出的状态、响应头和二进制内容。"""

    def __init__(self):
        self.status = None
        self.headers = {}
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers[name] = value

    def end_headers(self):
        pass

    def _err(self, status, message):
        self.status = status
        self.error = message


def test_release_package_contains_import_template():
    """正式安装包必须直接携带模板，避免安装后首次下载再临时生成。"""
    project_root = Path(app.BASE_DIR)
    packaged = {source.name for source, _ in application_data_sources(project_root)}
    assert "导入模板.xlsx" in packaged


def test_template_api_generates_xlsx_without_starting_another_application(tmp_path, monkeypatch):
    """模板文件缺失时直接生成 Excel，并按附件下载响应返回给浏览器。"""
    monkeypatch.setattr(app, "BASE_DIR", str(tmp_path))
    response = TemplateResponse()

    app.Handler._api_template(response, "GET", [], {})

    assert response.status == 200
    assert response.headers["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.headers["Content-Disposition"] == 'attachment; filename="import_template.xlsx"'
    assert int(response.headers["Content-Length"]) == len(response.wfile.getvalue())
    workbook = load_workbook(io.BytesIO(response.wfile.getvalue()), read_only=True)
    assert workbook.sheetnames == ["项目台账", "填写说明"]
