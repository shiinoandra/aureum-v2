from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TaskConfig:
    """Per-task battle settings. Each Task carries its own config."""
    turn: int = 1
    refresh: bool = True
    until_finish: bool = False
    trigger_skip: bool = False
    pre_fa: bool = False
    min_hp_threshold: int = 60
    max_hp_threshold: int = 100
    min_people: int = 1
    max_people: int = 30
    summon_priority: List[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "TaskConfig":
        """Create TaskConfig from a dict (e.g. loaded from default.json)."""
        return cls(
            turn=data.get("turn", 1),
            refresh=data.get("refresh", True),
            until_finish=data.get("until_finish", False),
            trigger_skip=data.get("trigger_skip", False),
            pre_fa=data.get("pre_fa", False),
            min_hp_threshold=data.get("min_hp_threshold", 60),
            max_hp_threshold=data.get("max_hp_threshold", 100),
            min_people=data.get("min_people", 1),
            max_people=data.get("max_people", 30),
            summon_priority=list(data.get("summon_priority", [])),
        )

    def to_dict(self) -> dict:
        """Serialize back to dict for persistence."""
        return {
            "turn": self.turn,
            "refresh": self.refresh,
            "until_finish": self.until_finish,
            "trigger_skip": self.trigger_skip,
            "pre_fa": self.pre_fa,
            "min_hp_threshold": self.min_hp_threshold,
            "max_hp_threshold": self.max_hp_threshold,
            "min_people": self.min_people,
            "max_people": self.max_people,
            "summon_priority": list(self.summon_priority),
        }


@dataclass
class Task:
    """Self-contained task unit that goes into the RuntimeManager queue."""
    task_id: str
    task_type: str          # "raid", "quest", etc.
    task_config: TaskConfig
    actions: List[dict]     # Loaded from tasks/{task_type}.json
    exit_condition: dict
