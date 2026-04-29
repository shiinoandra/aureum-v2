import json
from collections import deque
from pathlib import Path
from typing import Optional

from task.task import Task, TaskConfig

QUEUE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "queue.json"


def save_queue(task_queue: deque[Task], path: Optional[Path] = None) -> None:
    """Serialize queue to JSON file."""
    target = path or QUEUE_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    data = []
    for task in task_queue:
        data.append({
            "source_file": task.source_file,
            "amount": task.exit_condition.get("value", 1) if task.exit_condition else 1,
            "completed": task.completed,
            "not_found_count": task.not_found_count,
        })
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_queue(tasks_dir: Path, path: Optional[Path] = None) -> deque[Task]:
    """Deserialize queue from JSON file. Returns empty deque if file missing or invalid."""
    target = path or QUEUE_FILE
    result: deque[Task] = deque()
    if not target.exists():
        return result
    try:
        with open(target, "r", encoding="utf-8") as f:
            items = json.load(f)
    except (json.JSONDecodeError, OSError):
        return result

    if not isinstance(items, list):
        return result

    for item in items:
        source_file = item.get("source_file")
        if not source_file:
            continue
        task_path = tasks_dir / source_file
        if not task_path.exists():
            print(f"[!] Queue persistence: task file '{source_file}' not found, skipping")
            continue
        try:
            with open(task_path, "r", encoding="utf-8") as f:
                task_def = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        task_config = TaskConfig.from_dict(task_def.get("task_config", {}))
        exit_condition = dict(task_def.get("exit_condition", {}))
        if exit_condition.get("type") == "raid_count":
            exit_condition["value"] = item.get("amount", 1)

        import uuid
        task = Task(
            task_id=str(uuid.uuid4())[:8],
            task_type=task_def.get("task_type", "raid"),
            task_config=task_config,
            actions=task_def.get("actions", []),
            exit_condition=exit_condition,
            completed=item.get("completed", 0),
            not_found_count=item.get("not_found_count", 0),
            source_file=source_file,
        )
        result.append(task)

    return result
