-- G2 约束：仅由受控迁移在明确目标库执行，绝不在模块导入时自行执行。
CREATE UNIQUE INDEX IF NOT EXISTS ux_project_no_enterprise
ON project(project_no, enterprise_id)
WHERE project_no IS NOT NULL AND project_no <> '' AND enterprise_id IS NOT NULL;
CREATE TRIGGER IF NOT EXISTS trg_funding_amount_guard BEFORE INSERT ON funding
WHEN NEW.amount IS NOT NULL AND (NEW.amount < 0 OR NEW.amount * 100 != CAST(NEW.amount * 100 AS INTEGER))
BEGIN SELECT RAISE(ABORT, '非法金额'); END;
CREATE TRIGGER IF NOT EXISTS trg_funding_status_guard BEFORE INSERT ON funding
WHEN (NEW.status IN ('已拨付','已到账') AND (NEW.actual_date IS NULL OR NEW.actual_date='')) OR (NEW.status='未拨付' AND NEW.actual_date IS NOT NULL AND NEW.actual_date<>'')
BEGIN SELECT RAISE(ABORT, '资金状态与实拨日期不一致'); END;
CREATE TRIGGER IF NOT EXISTS trg_funding_amount_update_guard BEFORE UPDATE OF amount ON funding
WHEN NEW.amount IS NOT NULL AND (NEW.amount < 0 OR NEW.amount * 100 != CAST(NEW.amount * 100 AS INTEGER))
BEGIN SELECT RAISE(ABORT, '非法金额'); END;
CREATE TRIGGER IF NOT EXISTS trg_funding_status_update_guard BEFORE UPDATE OF status, actual_date ON funding
WHEN (NEW.status IN ('已拨付','已到账') AND (NEW.actual_date IS NULL OR NEW.actual_date='')) OR (NEW.status='未拨付' AND NEW.actual_date IS NOT NULL AND NEW.actual_date<>'')
BEGIN SELECT RAISE(ABORT, '资金状态与实拨日期不一致'); END;
CREATE TRIGGER IF NOT EXISTS trg_project_stage_update_guard BEFORE UPDATE OF stage ON project
WHEN NEW.stage <> OLD.stage AND NOT (
    (OLD.stage='申报中' AND NEW.stage IN ('已立项','撤销')) OR
    (OLD.stage='已立项' AND NEW.stage IN ('实施中','中止','撤销')) OR
    (OLD.stage='实施中' AND NEW.stage IN ('待验收','中止','撤销')) OR
    (OLD.stage='待验收' AND NEW.stage IN ('已验收','中止','撤销')) OR
    (OLD.stage='已验收' AND NEW.stage IN ('绩效跟踪','撤销')) OR
    (OLD.stage='绩效跟踪' AND NEW.stage IN ('已完结','撤销')))
BEGIN SELECT RAISE(ABORT, '非法项目阶段流转'); END;
