-- G7：项目编号身份与企业独立停用。历史记录保留，新增承接由服务层统一管控。
ALTER TABLE enterprise ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;
ALTER TABLE project ADD COLUMN identity_status TEXT NOT NULL DEFAULT '正式编号';

-- 既有无编号记录都是历史事实，迁移后明确纳入人工编号待补治理队列。
UPDATE project
SET identity_status = CASE
    WHEN project_no IS NULL OR project_no = '' THEN '人工编号待补'
    ELSE '正式编号'
END;
