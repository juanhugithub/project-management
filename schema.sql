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
    updated_at      TEXT DEFAULT (datetime('now','localtime'))
);

-- 2. 项目表
CREATE TABLE IF NOT EXISTS project (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,               -- 项目名称（必填）
    project_no      TEXT,                        -- 项目编号/立项文号
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
    updated_at      TEXT DEFAULT (datetime('now','localtime'))
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
    created_at      TEXT DEFAULT (datetime('now','localtime'))
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
    created_at        TEXT DEFAULT (datetime('now','localtime'))
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

-- 索引
CREATE INDEX IF NOT EXISTS idx_project_enterprise ON project(enterprise_id);
CREATE INDEX IF NOT EXISTS idx_funding_project    ON funding(project_id);
CREATE INDEX IF NOT EXISTS idx_node_project       ON node(project_id);
CREATE INDEX IF NOT EXISTS idx_dict_type          ON dict_item(dict_type, is_active);

-- 6. 系统配置表（如年度归档冻结）
CREATE TABLE IF NOT EXISTS system_config (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT UNIQUE NOT NULL,
    value       TEXT
);
INSERT OR IGNORE INTO system_config (key, value) VALUES ('archived_years', '');
