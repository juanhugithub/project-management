"""本机使用埋点：只记录模块和动作名称，不记录台账内容、Token 或网络地址。"""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


def _path(runtime_paths):
    return runtime_paths.logs / "usage_events.jsonl"


def record(runtime_paths, module, action="view"):
    """追加一条最小使用事件，便于后续判断功能优先级。"""
    if not module or not action:
        return
    path = _path(runtime_paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"at": datetime.now().isoformat(timespec="seconds"), "module": str(module)[:80], "action": str(action)[:80]}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def summary(runtime_paths, limit=20):
    """汇总模块访问次数和动作次数；损坏行不应出现在正常文件中，直接跳过。"""
    modules, actions = Counter(), Counter()
    path = _path(runtime_paths)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            modules[item["module"]] += 1
            actions[f"{item['module']} / {item['action']}"] += 1
    return {"modules": [{"name": k, "count": v} for k, v in modules.most_common(limit)],
            "actions": [{"name": k, "count": v} for k, v in actions.most_common(limit)], "event_file": str(path)}
