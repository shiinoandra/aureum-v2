from dataclasses import dataclass


@dataclass
class TaskProgress:
    """Mutable per-task state. Owned by TaskManager."""
    raids_completed: int = 0
    current_turn: int = 0
    current_raid_name: str = ""
    current_raid_id: str = ""
    boss_hp_at_entry: float = 0.0
    current_state: str = "idle"
    status: str = "pending"          # pending | running | completed | failed | stopped
