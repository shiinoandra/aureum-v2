from dataclasses import dataclass, field
from typing import List


@dataclass
class GlobalConfig:
    """Truly global settings that apply across all tasks in a session."""
    think_time_min: float = 0.2
    think_time_max: float = 0.5
