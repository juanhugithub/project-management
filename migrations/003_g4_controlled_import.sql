-- G4 受控导入审计结构。由 migrations.apply 对明确传入的数据库执行。
CREATE TABLE IF NOT EXISTS import_batch (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    field_map_version TEXT NOT NULL,
    archive_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('staged','committed','failed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    committed_at TEXT
);
CREATE TABLE IF NOT EXISTS import_staging (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES import_batch(id) ON DELETE CASCADE,
    row_no INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    conclusion TEXT NOT NULL,
    error TEXT,
    UNIQUE(batch_id, row_no)
);
CREATE INDEX IF NOT EXISTS idx_import_staging_batch ON import_staging(batch_id, row_no);
