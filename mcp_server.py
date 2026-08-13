#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""科技项目台账 — 只读 MCP server（供 Codex/WorkBuddy 等 AI 工具读库填表）

设计原则：AI 只能「读」，不能「写」——这里只注册查询工具，没有任何写入/修改能力。
台账的增删改只能通过浏览器界面完成，勾稽核对/节点提醒由确定性规则负责。

安装依赖：pip install mcp
启动（MCP 客户端通过 stdio 调用）：python mcp_server.py
"""

import os
import sqlite3

from mcp.server.fastmcp import FastMCP
from ledger import queries

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "project.db")

mcp = FastMCP("科技项目台账")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_list(rows):
    return [dict(r) for r in rows]


def archived_years(conn):
    """读取年度归档配置；MCP 默认不暴露已归档年度的项目业务数据。"""
    row = conn.execute("SELECT value FROM system_config WHERE key='archived_years'").fetchone()
    return {year.strip() for year in (row[0] if row else "").split(",") if year.strip()}


def is_archived_project(project, years):
    """归档按项目开始年度判断，与领域写服务的冻结规则保持一致。"""
    return bool(project and project.get("start_date") and project["start_date"][:4] in years)


def project_visibility_sql(alias, years):
    """生成项目可见性条件，所有直接 SQL 查询均复用这一软删除和归档边界。"""
    clause = f"{alias}.is_deleted=0"
    params = []
    if years:
        placeholders = ",".join("?" for _ in years)
        clause += f" AND ({alias}.start_date IS NULL OR substr({alias}.start_date,1,4) NOT IN ({placeholders}))"
        params.extend(sorted(years))
    return clause, params


# ---------------------------------------------------------------- 项目
@mcp.tool()
def list_projects(level: str = None, category: str = None, stage: str = None,
                  query: str = None) -> list:
    """查询项目列表，返回 planned_total、disbursed_total、received_total 三项统一资金口径。"""
    conn = get_db()
    try:
        years = archived_years(conn)
        result = queries.project_list(conn, {"level": level, "category": category, "stage": stage, "query": query})
        return [project for project in result if not is_archived_project(project, years)]
    finally:
        conn.close()


@mcp.tool()
def get_project(project_id: int) -> dict:
    """按 ID 查询单个项目全貌：基本信息 + 承担企业 + 资金明细(fundings) + 节点明细(nodes)。"""
    conn = get_db()
    try:
        result = queries.project_detail(conn, project_id)
        if not result or is_archived_project(result, archived_years(conn)):
            return {"error": "项目不存在或当前不可见"}
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------- 企业
@mcp.tool()
def list_enterprises(district: str = None, enterprise_type: str = None) -> list:
    """查询企业列表。可按区镇(district)、企业类型(enterprise_type)过滤。返回企业核心字段、承担项目数(project_count)、累计金额(total_amount_sum)。"""
    conn = get_db()
    try:
        years = archived_years(conn)
        project_clause, project_params = project_visibility_sql("p", years)
        sql = ("SELECT e.id, e.name, e.credit_code, e.enterprise_type, e.qualifications, "
               "e.district, e.contact_person, e.contact_phone, e.address, "
               "COUNT(p.id) AS project_count, COALESCE(SUM(p.total_amount),0) AS total_amount_sum "
               f"FROM enterprise e JOIN project p ON p.enterprise_id=e.id AND {project_clause} "
               "WHERE e.is_deleted=0")
        params = list(project_params)
        if district:
            sql += " AND e.district=?"; params.append(district)
        if enterprise_type:
            sql += " AND e.enterprise_type=?"; params.append(enterprise_type)
        sql += " GROUP BY e.id ORDER BY e.id DESC"
        return rows_to_list(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


@mcp.tool()
def get_enterprise(enterprise_id: int) -> dict:
    """按 ID 查询企业画像：基本信息 + 该企业承担的全部项目(projects)。"""
    conn = get_db()
    try:
        years = archived_years(conn)
        ent = conn.execute("SELECT * FROM enterprise WHERE id=? AND is_deleted=0", (enterprise_id,)).fetchone()
        if not ent:
            return {"error": "企业不存在"}
        project_clause, project_params = project_visibility_sql("p", years)
        projects = conn.execute(
            f"SELECT p.* FROM project p WHERE p.enterprise_id=? AND {project_clause} ORDER BY p.id DESC",
            [enterprise_id, *project_params],
        ).fetchall()
        if not projects:
            return {"error": "企业不存在或当前不可见"}
        result = dict(ent)
        result["projects"] = rows_to_list(projects)
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------- 资金 / 节点
@mcp.tool()
def list_fundings(project_id: int = None) -> list:
    """查询资金拨付明细。可按项目ID过滤；不过滤则返回全部。字段含来源(source_type: 上级拨付/本级配套/本级自付)、金额、批次、应拨/实拨时间、状态。"""
    conn = get_db()
    try:
        years = archived_years(conn)
        project_clause, project_params = project_visibility_sql("p", years)
        if project_id:
            rows = conn.execute(
                f"SELECT f.* FROM funding f JOIN project p ON p.id=f.project_id WHERE f.project_id=? AND f.is_deleted=0 AND {project_clause} ORDER BY f.id",
                [project_id, *project_params],
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT f.* FROM funding f JOIN project p ON p.id=f.project_id WHERE f.is_deleted=0 AND {project_clause} ORDER BY f.id DESC",
                project_params,
            ).fetchall()
        return rows_to_list(rows)
    finally:
        conn.close()


@mcp.tool()
def list_nodes(project_id: int = None) -> list:
    """查询项目节点（里程碑）。可按项目ID过滤。字段含节点类型、计划/实际时间、状态、是否重大事项变更。"""
    conn = get_db()
    try:
        years = archived_years(conn)
        project_clause, project_params = project_visibility_sql("p", years)
        if project_id:
            rows = conn.execute(
                f"SELECT n.* FROM node n JOIN project p ON p.id=n.project_id WHERE n.project_id=? AND n.is_deleted=0 AND {project_clause} ORDER BY n.plan_date, n.id",
                [project_id, *project_params],
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT n.* FROM node n JOIN project p ON p.id=n.project_id WHERE n.is_deleted=0 AND {project_clause} ORDER BY n.plan_date, n.id",
                project_params,
            ).fetchall()
        return rows_to_list(rows)
    finally:
        conn.close()


# ---------------------------------------------------------------- 提醒 / 统计 / 勾稽
@mcp.tool()
def get_reminders(days: int = 30) -> list:
    """查询节点到期提醒。返回 days 天内到期及已逾期的未完成节点，含项目名、节点类型、计划时间、剩余天数(days_left)、预警级别(level: overdue=已逾期/red=<=7天/yellow=<=30天)。"""
    conn = get_db()
    try:
        project_clause, project_params = project_visibility_sql("p", archived_years(conn))
        rows = conn.execute(
            "SELECT n.id, n.project_id, n.node_type, n.plan_date, n.status, "
            "p.name AS project_name, p.level AS project_level, "
            "(julianday(n.plan_date) - julianday(date('now','localtime'))) AS days_left "
            "FROM node n JOIN project p ON n.project_id = p.id "
            f"WHERE n.is_deleted=0 AND n.status != '已完成' AND n.plan_date IS NOT NULL AND {project_clause} "
            "AND (julianday(n.plan_date) - julianday(date('now','localtime'))) <= ? "
            "ORDER BY n.plan_date",
            [*project_params, days]).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            dl = d.get("days_left")
            if dl is None:
                d["level"] = "later"
            elif dl < 0:
                d["level"] = "overdue"
            elif dl <= 7:
                d["level"] = "red"
            else:
                d["level"] = "yellow"
            out.append(d)
        return out
    finally:
        conn.close()


@mcp.tool()
def get_stats(by: str = "category") -> list:
    """统计报表。by 取值：category(按类型)/level(按层级)/stage(按阶段)/year(按年度)/enterprise(按企业)/source(按资金来源)。返回 [{key, count, amount}]。"""
    conn = get_db()
    try:
        project_clause, project_params = project_visibility_sql("p", archived_years(conn))
        if by == "source":
            sql = ("SELECT f.source_type AS key, COUNT(*) AS count, COALESCE(SUM(f.amount),0) AS amount "
                   f"FROM funding f JOIN project p ON p.id=f.project_id WHERE f.is_deleted=0 AND {project_clause} GROUP BY f.source_type ORDER BY amount DESC")
        elif by == "enterprise":
            sql = ("SELECT COALESCE(e.name,'未关联') AS key, COUNT(p.id) AS count, "
                   "COALESCE(SUM(p.total_amount),0) AS amount "
                   f"FROM project p LEFT JOIN enterprise e ON p.enterprise_id=e.id AND e.is_deleted=0 WHERE {project_clause} "
                   "GROUP BY p.enterprise_id ORDER BY amount DESC")
        elif by == "year":
            sql = ("SELECT substr(p.start_date,1,4) AS key, COUNT(*) AS count, "
                   "COALESCE(SUM(p.total_amount),0) AS amount "
                   f"FROM project p WHERE {project_clause} GROUP BY substr(p.start_date,1,4) ORDER BY key")
        elif by == "stage":
            sql = ("SELECT p.stage AS key, COUNT(*) AS count, COALESCE(SUM(p.total_amount),0) AS amount "
                   f"FROM project p WHERE {project_clause} GROUP BY p.stage ORDER BY count DESC")
        else:
            col = by if by in ("level", "category") else "category"
            sql = (f"SELECT p.{col} AS key, COUNT(*) AS count, COALESCE(SUM(p.total_amount),0) AS amount "
                   f"FROM project p WHERE {project_clause} GROUP BY p.{col} ORDER BY count DESC")
        out = []
        for r in conn.execute(sql, project_params).fetchall():
            d = dict(r)
            d["key"] = d.get("key") or "未设置"
            out.append(d)
        return out
    finally:
        conn.close()


@mcp.tool()
def get_funding_check() -> list:
    """资金勾稽核对：每个项目的上级拨付/本级配套/本级自付合计与项目总金额、配套比例应配额比对。返回每项 ok 布尔与 issues 问题清单。"""
    conn = get_db()
    try:
        project_clause, project_params = project_visibility_sql("p", archived_years(conn))
        rows = conn.execute(
            "SELECT p.id, p.name, p.total_amount, p.match_ratio, "
            "COALESCE(SUM(CASE WHEN f.source_type='上级拨付' THEN f.amount ELSE 0 END),0) AS sum_up, "
            "COALESCE(SUM(CASE WHEN f.source_type='本级配套' THEN f.amount ELSE 0 END),0) AS sum_match, "
            "COALESCE(SUM(CASE WHEN f.source_type='本级自付' THEN f.amount ELSE 0 END),0) AS sum_self "
            f"FROM project p LEFT JOIN funding f ON f.project_id=p.id AND f.is_deleted=0 WHERE {project_clause} "
            "GROUP BY p.id ORDER BY p.id", project_params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["sum_all"] = d["sum_up"] + d["sum_match"] + d["sum_self"]
            issues = []
            if d["total_amount"] is not None and abs(d["sum_all"] - d["total_amount"]) > 0.005:
                issues.append("资金合计与项目总金额不一致")
            if d["match_ratio"] and d["sum_up"]:
                expected = d["sum_up"] * d["match_ratio"]
                d["match_expected"] = round(expected, 2)
                if abs(d["sum_match"] - expected) > 0.005:
                    issues.append("本级配套与应配额不一致")
            d["issues"] = issues
            d["ok"] = len(issues) == 0
            out.append(d)
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------- 搜索
@mcp.tool()
def search(keyword: str) -> dict:
    """跨企业、项目、资金、节点全局搜索。返回命中的企业、项目列表。"""
    conn = get_db()
    try:
        project_clause, project_params = project_visibility_sql("p", archived_years(conn))
        like = f"%{keyword}%"
        ents = conn.execute(
            "SELECT id, name, credit_code, district, enterprise_type FROM enterprise "
            f"WHERE is_deleted=0 AND EXISTS (SELECT 1 FROM project p WHERE p.enterprise_id=enterprise.id AND {project_clause}) "
            "AND (name LIKE ? OR credit_code LIKE ?)", [*project_params, like, like]).fetchall()
        projs = conn.execute(
            "SELECT p.id, p.name, p.project_no, p.level, p.category, p.stage, "
            "e.name AS enterprise_name FROM project p LEFT JOIN enterprise e ON p.enterprise_id=e.id "
            f"WHERE {project_clause} AND e.is_deleted=0 AND (p.name LIKE ? OR p.project_no LIKE ? OR e.name LIKE ?)",
            [*project_params, like, like, like]).fetchall()
        return {
            "enterprises": rows_to_list(ents),
            "projects": rows_to_list(projs),
        }
    finally:
        conn.close()


if __name__ == "__main__":
    # stdio 传输（默认），供 MCP 客户端启动
    mcp.run()
