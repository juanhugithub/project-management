-- 科技项目全生命周期台账系统 - 数据库结构
-- SQLite 3

PRAGMA foreign_keys = ON;

-- 1. 企业表
CREATE TABLE IF NOT EXISTS enterprise (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,               -- 企业名称（必填）
    credit_code     TEXT UNIQUE,                 -- 统一社会信用代码
    enterprise_type TEXT,                        -- 企业类型（取值由 dict_item 维护）
    qualifications  TEXT,                        -- 资质
    district        TEXT,                        -- 区镇（取值由 dict_item 维护）
    contact_person  TEXT,                        -- 联系人
    contact_phone   TEXT,                        -- 联系电话
    address         TEXT,                        -- 地址
    note            TEXT,                        -- 备注
    created_at      TEXT DEFAULT (datetime('now','localtime')),
    updated_at      TEXT DEFAULT (datetime('now','localtime')),
    is_deleted      INTEGER NOT NULL DEFAULT 0,   -- G3 软删除标记：0=正常 1=已删除
    deleted_at      TEXT,                         -- G3 软删除时间（本地时间）
    is_active       INTEGER NOT NULL DEFAULT 1    -- G7 独立停用：保留历史，0 时不得新增承接项目
);

-- 2. 项目表
CREATE TABLE IF NOT EXISTS project (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,               -- 项目名称（必填）
    project_no      TEXT,                        -- 项目编号/立项文号
    identity_status TEXT NOT NULL DEFAULT '正式编号' CHECK(identity_status IN ('正式编号','人工编号待补')),
                                                    -- G7 编号身份：缺正式编号时必须显式标记为人工待补
    level           TEXT,                        -- 层级（取值由 dict_item 维护）
    category        TEXT,                        -- 项目类型（取值由 dict_item 维护）
    enterprise_id   INTEGER REFERENCES enterprise(id) ON DELETE SET NULL,
    total_amount    REAL,                        -- 项目总金额（万元）
    start_date      TEXT,                        -- 开始日期 YYYY-MM-DD
    end_date        TEXT,                        -- 结束日期 YYYY-MM-DD
    stage           TEXT,                        -- 当前阶段（状态机）
    match_ratio     REAL,                        -- 配套比例（如 1 表示 1:1）
    leader          TEXT,                        -- 项目负责人
    contact_phone   TEXT,                        -- 联系人手机号
    note            TEXT,                        -- 备注
    created_at      TEXT DEFAULT (datetime('now','localtime')),
    updated_at      TEXT DEFAULT (datetime('now','localtime')),
    is_deleted      INTEGER NOT NULL DEFAULT 0,   -- G3 软删除标记：0=正常 1=已删除
    deleted_at      TEXT                          -- G3 软删除时间（本地时间）
);

-- 3. 资金表
CREATE TABLE IF NOT EXISTS funding (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER REFERENCES project(id) ON DELETE CASCADE,
    source_type     TEXT,                        -- 资金来源（取值由 dict_item 维护）
    amount          REAL,                        -- 金额（万元）
    batch           TEXT,                        -- 批次
    plan_date       TEXT,                        -- 应拨时间
    actual_date     TEXT,                        -- 实拨时间
    status          TEXT,                        -- 未拨付/已拨付/已到账
    note            TEXT,
    created_at      TEXT DEFAULT (datetime('now','localtime')),
    is_deleted      INTEGER NOT NULL DEFAULT 0,   -- G3 软删除标记：0=正常 1=已删除
    deleted_at      TEXT                          -- G3 软删除时间（本地时间）
);

-- 4. 节点表
CREATE TABLE IF NOT EXISTS node (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id        INTEGER REFERENCES project(id) ON DELETE CASCADE,
    node_type         TEXT,                      -- 节点类型（取值由 dict_item 维护）
    plan_date         TEXT,                      -- 计划时间
    actual_date       TEXT,                      -- 实际完成时间
    status            TEXT,                      -- 待办/已完成/已逾期
    has_major_change  INTEGER DEFAULT 0,         -- 是否发生重大事项变更 0/1
    note              TEXT,
    created_at        TEXT DEFAULT (datetime('now','localtime')),
    is_deleted        INTEGER NOT NULL DEFAULT 0, -- G3 软删除标记：0=正常 1=已删除
    deleted_at        TEXT                        -- G3 软删除时间（本地时间）
);

-- 5. 配置表（可枚举取值的唯一来源）
CREATE TABLE IF NOT EXISTS dict_item (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dict_type   TEXT NOT NULL,                   -- level/category/funding_source/node_type/district/enterprise_type
    value       TEXT NOT NULL,
    sort_order  INTEGER DEFAULT 0,
    is_active   INTEGER DEFAULT 1,               -- 1=启用 0=停用
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

-- ===== 种子数据 =====

-- 层级
INSERT INTO dict_item (dict_type, value, sort_order) VALUES
    ('level', '国家级',   1),
    ('level', '省级',     2),
    ('level', '苏州市级', 3),
    ('level', '昆山本级', 4);

-- 项目类型
INSERT INTO dict_item (dict_type, value, sort_order) VALUES
    ('category', '科技成果转化', 1),
    ('category', '国际合作',     2),
    ('category', '创新联合体',   3);

-- 资金来源
INSERT INTO dict_item (dict_type, value, sort_order) VALUES
    ('funding_source', '上级拨付', 1),
    ('funding_source', '本级配套', 2),
    ('funding_source', '本级自付', 3);

-- 节点类型
INSERT INTO dict_item (dict_type, value, sort_order) VALUES
    ('node_type', '申报',     1),
    ('node_type', '立项',     2),
    ('node_type', '中期检查', 3),
    ('node_type', '验收',     4),
    ('node_type', '结题',     5),
    ('node_type', '绩效评价', 6);

-- 区镇（11 个）
INSERT INTO dict_item (dict_type, value, sort_order) VALUES
    ('district', '开发区', 1),
    ('district', '高新区', 2),
    ('district', '花桥',   3),
    ('district', '张浦',   4),
    ('district', '周市',   5),
    ('district', '陆家',   6),
    ('district', '巴城',   7),
    ('district', '千灯',   8),
    ('district', '周庄',   9),
    ('district', '淀山湖', 10),
    ('district', '锦溪',   11);

-- 企业类型
INSERT INTO dict_item (dict_type, value, sort_order) VALUES
    ('enterprise_type', '高新技术企业',     1),
    ('enterprise_type', '科技型中小企业',   2),
    ('enterprise_type', '规上工业',         3),
    ('enterprise_type', '其他',             4);

-- 6. 审计日志表（G3，设计见 docs/migrations/迁移清单.md M004）
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

-- 7. G4 受控导入：原件身份、暂存行与确认状态均留在台账内，正式业务表只在确认时写入。
CREATE TABLE IF NOT EXISTS import_batch (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name         TEXT NOT NULL,
    file_sha256       TEXT NOT NULL,
    field_map_version TEXT NOT NULL,
    archive_path      TEXT NOT NULL,
    status            TEXT NOT NULL CHECK(status IN ('staged','committed','failed')),
    created_at        TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    committed_at      TEXT
);
CREATE TABLE IF NOT EXISTS import_staging (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id    INTEGER NOT NULL REFERENCES import_batch(id) ON DELETE CASCADE,
    row_no      INTEGER NOT NULL,
    raw_json    TEXT NOT NULL,
    conclusion  TEXT NOT NULL,
    error       TEXT,
    UNIQUE(batch_id, row_no)
);
CREATE INDEX IF NOT EXISTS idx_import_staging_batch ON import_staging(batch_id, row_no);

-- 索引
CREATE INDEX IF NOT EXISTS idx_project_enterprise ON project(enterprise_id);
CREATE INDEX IF NOT EXISTS idx_funding_project    ON funding(project_id);
CREATE INDEX IF NOT EXISTS idx_node_project       ON node(project_id);
CREATE INDEX IF NOT EXISTS idx_dict_type          ON dict_item(dict_type, is_active);
CREATE UNIQUE INDEX IF NOT EXISTS ux_project_no_enterprise ON project(project_no, enterprise_id) WHERE project_no IS NOT NULL AND project_no <> '' AND enterprise_id IS NOT NULL;
CREATE TRIGGER IF NOT EXISTS trg_funding_amount_guard BEFORE INSERT ON funding WHEN NEW.amount IS NOT NULL AND (NEW.amount < 0 OR NEW.amount * 100 != CAST(NEW.amount * 100 AS INTEGER)) BEGIN SELECT RAISE(ABORT, '非法金额'); END;
CREATE TRIGGER IF NOT EXISTS trg_funding_status_guard BEFORE INSERT ON funding WHEN (NEW.status IN ('已拨付','已到账') AND (NEW.actual_date IS NULL OR NEW.actual_date='')) OR (NEW.status='未拨付' AND NEW.actual_date IS NOT NULL AND NEW.actual_date<>'') BEGIN SELECT RAISE(ABORT, '资金状态与实拨日期不一致'); END;
CREATE TRIGGER IF NOT EXISTS trg_funding_amount_update_guard BEFORE UPDATE OF amount ON funding WHEN NEW.amount IS NOT NULL AND (NEW.amount < 0 OR NEW.amount * 100 != CAST(NEW.amount * 100 AS INTEGER)) BEGIN SELECT RAISE(ABORT, '非法金额'); END;
CREATE TRIGGER IF NOT EXISTS trg_funding_status_update_guard BEFORE UPDATE OF status, actual_date ON funding WHEN (NEW.status IN ('已拨付','已到账') AND (NEW.actual_date IS NULL OR NEW.actual_date='')) OR (NEW.status='未拨付' AND NEW.actual_date IS NOT NULL AND NEW.actual_date<>'') BEGIN SELECT RAISE(ABORT, '资金状态与实拨日期不一致'); END;
CREATE TRIGGER IF NOT EXISTS trg_project_stage_update_guard BEFORE UPDATE OF stage ON project WHEN NEW.stage <> OLD.stage AND NOT ((OLD.stage='申报中' AND NEW.stage IN ('已立项','撤销')) OR (OLD.stage='已立项' AND NEW.stage IN ('实施中','中止','撤销')) OR (OLD.stage='实施中' AND NEW.stage IN ('待验收','中止','撤销')) OR (OLD.stage='待验收' AND NEW.stage IN ('已验收','中止','撤销')) OR (OLD.stage='已验收' AND NEW.stage IN ('绩效跟踪','撤销')) OR (OLD.stage='绩效跟踪' AND NEW.stage IN ('已完结','撤销'))) BEGIN SELECT RAISE(ABORT, '非法项目阶段流转'); END;

-- 6. 系统配置表（如年度归档冻结）
CREATE TABLE IF NOT EXISTS system_config (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT UNIQUE NOT NULL,
    value       TEXT
);
INSERT OR IGNORE INTO system_config (key, value) VALUES ('archived_years', '');
