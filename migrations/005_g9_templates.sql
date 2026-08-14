-- G9：模板定义与衍生稿溯源。模板文件是版本化公共契约，登记表保存每次实际使用的事实快照。
CREATE TABLE IF NOT EXISTS reporting_template (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id TEXT NOT NULL,
    version TEXT NOT NULL,
    name TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(template_id, version)
);

CREATE TABLE IF NOT EXISTS derivative_draft (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id TEXT NOT NULL,
    template_version TEXT NOT NULL,
    mcp_parameters_json TEXT NOT NULL,
    dataset_snapshot_hash TEXT NOT NULL,
    source_project_ids_json TEXT NOT NULL,
    agent_model TEXT NOT NULL,
    human_status TEXT NOT NULL CHECK(human_status IN ('待确认','已确认','已驳回')),
    export_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    confirmed_at TEXT,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_derivative_draft_template ON derivative_draft(template_id, template_version);
CREATE INDEX IF NOT EXISTS idx_derivative_draft_snapshot ON derivative_draft(dataset_snapshot_hash);
