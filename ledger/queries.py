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
    for cond in filters.get("adv_filters", []):
        columns = {"name": "p.name", "project_no": "p.project_no", "level": "p.level",
                   "category": "p.category", "stage": "p.stage", "enterprise_id": "p.enterprise_id",
                   "enterprise_name": "e.name", "district": "e.district", "total_amount": "p.total_amount",
                   "match_ratio": "p.match_ratio", "start_date": "p.start_date", "end_date": "p.end_date",
                   "leader": "p.leader", "contact_phone": "p.contact_phone"}
        col = columns.get(cond.get("field")); value = cond.get("value")
        if not col or value in (None, ""): continue
        op = cond.get("op")
        if op == "contains": where.append(f"{col} LIKE ?"); params.append(f"%{value}%")
        elif op in {"eq", "gt", "gte", "lt", "lte"}:
            operator = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
            where.append(f"{col} {operator} ?"); params.append(value)
    where.insert(0, "p.is_deleted=0")
    sql = f"""SELECT p.*, e.name AS enterprise_name, e.district AS enterprise_district, {TOTAL_SQL}
    FROM project p JOIN enterprise e ON p.enterprise_id=e.id AND e.is_deleted=0 LEFT JOIN funding f ON f.project_id=p.id AND f.is_deleted=0"""
    if where: sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY p.id"
    page = filters.get("page")
    if page is None:
        return [dict(row) for row in conn.execute(sql + " ORDER BY p.id DESC", params).fetchall()]
    page = max(1, int(page))
    page_size = min(100, max(20, int(filters.get("page_size", 50))))
    sort_map = {
        "name": "p.name", "project_no": "p.project_no", "level": "p.level",
        "category": "p.category", "enterprise_name": "enterprise_name",
        "enterprise_district": "enterprise_district", "total_amount": "p.total_amount",
        "disbursed_total": "disbursed_total", "stage": "p.stage",
    }
    sort = sort_map.get(filters.get("sort"), "p.id")
    direction = "ASC" if filters.get("direction") == "asc" else "DESC"
    total = conn.execute(f"SELECT COUNT(*) FROM ({sql}) project_rows", params).fetchone()[0]
    rows = conn.execute(sql + f" ORDER BY {sort} {direction}, p.id DESC LIMIT ? OFFSET ?",
                        params + [page_size, (page - 1) * page_size]).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page,
            "page_size": page_size, "total_pages": (total + page_size - 1) // page_size}

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
