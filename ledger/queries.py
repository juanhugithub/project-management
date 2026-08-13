"""共享只读查询，确保 Web 与 MCP 的资金口径没有两套 SQL。"""

TOTAL_SQL = """COALESCE(SUM(CASE WHEN f.plan_date IS NOT NULL THEN f.amount ELSE 0 END),0) AS planned_total,
COALESCE(SUM(CASE WHEN f.status IN ('已拨付','已到账') THEN f.amount ELSE 0 END),0) AS disbursed_total,
COALESCE(SUM(CASE WHEN f.status='已到账' THEN f.amount ELSE 0 END),0) AS received_total"""

def project_totals(conn, project_id=None):
    where = "WHERE f.is_deleted=0" + (" AND f.project_id=?" if project_id is not None else "")
    params = (project_id,) if project_id is not None else ()
    return dict(conn.execute(f"SELECT {TOTAL_SQL} FROM funding f {where}", params).fetchone())

def project_list(conn, filters=None):
    filters = filters or {}
    where, params = [], []
    for field in ("level", "category", "stage", "enterprise_id"):
        if filters.get(field): where.append(f"p.{field}=?"); params.append(filters[field])
    if filters.get("district"): where.append("e.district=?"); params.append(filters["district"])
    if filters.get("query"):
        like = f"%{filters['query']}%"; where.append("(p.name LIKE ? OR p.project_no LIKE ? OR e.name LIKE ?)"); params += [like, like, like]
    where.insert(0, "p.is_deleted=0")
    sql = f"""SELECT p.*, e.name AS enterprise_name, e.district AS enterprise_district, {TOTAL_SQL}
    FROM project p JOIN enterprise e ON p.enterprise_id=e.id AND e.is_deleted=0 LEFT JOIN funding f ON f.project_id=p.id AND f.is_deleted=0"""
    if where: sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY p.id ORDER BY p.id DESC"
    return [dict(row) for row in conn.execute(sql, params).fetchall()]

def project_detail(conn, project_id):
    row = conn.execute("SELECT * FROM project WHERE id=? AND is_deleted=0", (project_id,)).fetchone()
    if not row: return None
    result = dict(row)
    ent = conn.execute("SELECT * FROM enterprise WHERE id=? AND is_deleted=0", (row["enterprise_id"],)).fetchone()
    result["enterprise"] = dict(ent) if ent else None
    result["fundings"] = [dict(x) for x in conn.execute("SELECT * FROM funding WHERE project_id=? AND is_deleted=0 ORDER BY id", (project_id,))]
    result["nodes"] = [dict(x) for x in conn.execute("SELECT * FROM node WHERE project_id=? AND is_deleted=0 ORDER BY plan_date,id", (project_id,))]
    result.update(project_totals(conn, project_id))
    return result

def dashboard(conn):
    totals = project_totals(conn)
    return {**totals,
        "project_count": conn.execute("SELECT COUNT(*) FROM project WHERE is_deleted=0").fetchone()[0],
        "enterprise_count": conn.execute("SELECT COUNT(*) FROM enterprise WHERE is_deleted=0").fetchone()[0]}
