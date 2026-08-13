-- G3：软删除字段 + 审计日志表（对应迁移清单 M003/M004）
-- 仅由 migrations/__init__.py 的 apply() 在明确目标库执行；绝不在模块导入时自行执行。
-- 老库（无这些列/表）增量升级；全新库由 schema.sql 全量建齐，本脚本的幂等写法对其同样安全。

-- M003：企业/项目/资金/节点 增加软删除标记与删除时间（老库升级用 ALTER ADD COLUMN）
ALTER TABLE enterprise ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE enterprise ADD COLUMN deleted_at TEXT;
ALTER TABLE project   ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE project   ADD COLUMN deleted_at TEXT;
ALTER TABLE funding   ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE funding   ADD COLUMN deleted_at TEXT;
ALTER TABLE node      ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE node      ADD COLUMN deleted_at TEXT;

-- M004：审计日志表（结构同 schema.sql 与迁移清单 M004 设计稿）
CREATE TABLE IF NOT EXISTS audit_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL,              -- 操作时间（本地时间）
    operator       TEXT NOT NULL,              -- 操作者标识（本地用户名/固定操作者）
    action         TEXT NOT NULL,              -- 操作动作（create/update/delete/archive/unarchive/restore 等）
    object_type    TEXT NOT NULL,              -- 对象类型（enterprise/project/funding/node/system）
    object_id      INTEGER,                    -- 对象 id（无主键对象可为 NULL）
    before_summary TEXT,                       -- 操作前摘要（关键字段 JSON）
    after_summary  TEXT,                       -- 操作后摘要（关键字段 JSON）
    reason         TEXT,                       -- 理由（解除归档/删除/恢复等必填项）
    source_batch   TEXT,                       -- 来源批次号（导入/迁移）
    note           TEXT                        -- 备注
);
CREATE INDEX IF NOT EXISTS idx_audit_ts     ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_audit_object ON audit_log(object_type, object_id);
