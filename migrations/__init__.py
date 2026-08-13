"""版本化 SQLite 迁移入口；调用方必须显式传入目标数据库。"""
from pathlib import Path

def apply(conn, directory=None):
    directory = Path(directory or Path(__file__).parent)
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migration (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    done = {row[0] for row in conn.execute("SELECT version FROM schema_migration")}
    for path in sorted(directory.glob("[0-9][0-9][0-9]_*.sql")):
        if path.name in done: continue
        with conn:
            conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migration(version) VALUES (?)", (path.name,))
