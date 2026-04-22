from enum import Enum
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Optional, List
import json
from pathlib import Path
from state_machine import State


@dataclass
class BattleConfig:
    turn: int = 1
    refresh: bool = True
    until_finish: bool = False
    trigger_skip: bool = False
    think_time_min: float = 0.2
    think_time_max: float = 0.5
    pre_fa: bool = False
    min_hp_threshold: int = 60
    max_hp_threshold: int = 100
    min_people: int = 1
    max_people: int = 30
    raid_amount: int = 10
    summon_priority: List[dict] = field(default_factory=list)


@dataclass
class RuntimeState:
    is_running: bool = False
    current_state: State = State.IDLE
    last_known_url: str = ""
    raids_completed: int = 0
    raids_target: int = 0
    current_turn: int = 0
    turn_target: int = 0
    current_raid_name: str = ""
    current_raid_thumbnail: str = ""
    current_raid_id: str = ""
    boss_hp_at_entry: float = 0.0
    task_start_time: float = 0.0


class ConfigManager:
    _instance: Optional["ConfigManager"] = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._config_lock = Lock()
        self._runtime_lock = Lock()
        self._battle_config = BattleConfig()
        self._runtime_state = RuntimeState()
        self._initialized = True

    # --- Runtime State (thread-safe, UI-visible) ---
    # --- Runtime State (thread-safe, UI-visible) ---
    @property
    def is_running(self) -> bool:
        with self._runtime_lock:
            return self._runtime_state.is_running

    @is_running.setter
    def is_running(self, value: bool):
        with self._runtime_lock:
            self._runtime_state.is_running = value

    @property
    def current_state(self) -> State:
        with self._runtime_lock:
            return self._runtime_state.current_state

    @current_state.setter
    def current_state(self, state: State):
        with self._runtime_lock:
            self._runtime_state.current_state = state

    @property
    def last_known_url(self) -> str:
        with self._runtime_lock:
            return self._runtime_state.last_known_url

    @last_known_url.setter
    def last_known_url(self, value: str):
        with self._runtime_lock:
            self._runtime_state.last_known_url = value

    @property
    def raids_completed(self) -> int:
        with self._runtime_lock:
            return self._runtime_state.raids_completed

    @raids_completed.setter
    def raids_completed(self, value: int):
        with self._runtime_lock:
            self._runtime_state.raids_completed = value

    @property
    def raids_target(self) -> int:
        with self._runtime_lock:
            return self._runtime_state.raids_target

    @raids_target.setter
    def raids_target(self, value: int):
        with self._runtime_lock:
            self._runtime_state.raids_target = value

    @property
    def current_turn(self) -> int:
        with self._runtime_lock:
            return self._runtime_state.current_turn

    @current_turn.setter
    def current_turn(self, value: int):
        with self._runtime_lock:
            self._runtime_state.current_turn = value

    @property
    def turn_target(self) -> int:
        with self._runtime_lock:
            return self._runtime_state.turn_target

    @turn_target.setter
    def turn_target(self, value: int):
        with self._runtime_lock:
            self._runtime_state.turn_target = value

    @property
    def current_raid_name(self) -> str:
        with self._runtime_lock:
            return self._runtime_state.current_raid_name

    @current_raid_name.setter
    def current_raid_name(self, value: str):
        with self._runtime_lock:
            self._runtime_state.current_raid_name = value

    @property
    def current_raid_id(self) -> str:
        with self._runtime_lock:
            return self._runtime_state.current_raid_id

    @current_raid_id.setter
    def current_raid_id(self, value: str):
        with self._runtime_lock:
            self._runtime_state.current_raid_id = value

    @property
    def boss_hp_at_entry(self) -> float:
        with self._runtime_lock:
            return self._runtime_state.boss_hp_at_entry

    @boss_hp_at_entry.setter
    def boss_hp_at_entry(self, value: float):
        with self._runtime_lock:
            self._runtime_state.boss_hp_at_entry = value

    @property
    def task_start_time(self) -> float:
        with self._runtime_lock:
            return self._runtime_state.task_start_time

    @task_start_time.setter
    def task_start_time(self, value: float):
        with self._runtime_lock:
            self._runtime_state.task_start_time = value

    def get_runtime_snapshot(self) -> dict:
        """Return a snapshot of runtime state for Flask."""
        with self._runtime_lock:
            return {
                "is_running": self._runtime_state.is_running,
                "current_state": self._runtime_state.current_state.value,
                "last_known_url": self._runtime_state.last_known_url,
                "raids_completed": self._runtime_state.raids_completed,
                "raids_target": self._runtime_state.raids_target,
                "current_turn": self._runtime_state.current_turn,
                "turn_target": self._runtime_state.turn_target,
                "current_raid_name": self._runtime_state.current_raid_name,
                "current_raid_id": self._runtime_state.current_raid_id,
                "boss_hp_at_entry": self._runtime_state.boss_hp_at_entry,
                "task_start_time": self._runtime_state.task_start_time,
            }

    # --- Battle Config (static settings) ---
    def get_battle_config(self) -> BattleConfig:
        with self._config_lock:
            return BattleConfig(
                turn=self._battle_config.turn,
                refresh=self._battle_config.refresh,
                until_finish=self._battle_config.until_finish,
                trigger_skip=self._battle_config.trigger_skip,
                think_time_min=self._battle_config.think_time_min,
                think_time_max=self._battle_config.think_time_max,
                pre_fa=self._battle_config.pre_fa,
                min_hp_threshold=self._battle_config.min_hp_threshold,
                max_hp_threshold=self._battle_config.max_hp_threshold,
                min_people=self._battle_config.min_people,
                max_people=self._battle_config.max_people,
                raid_amount=self._battle_config.raid_amount,
                summon_priority=list(self._battle_config.summon_priority),
            )

    def update_battle_config(self, **kwargs):
        with self._config_lock:
            for key, value in kwargs.items():
                if hasattr(self._battle_config, key):
                    setattr(self._battle_config, key, value)

    def load_default_config(self, config_path: Path):
        with open(config_path) as f:
            data = json.load(f)
        self.update_battle_config(**data)

    def save_default_config(self, config_path: Path):
        with self._config_lock:
            data = {
                "turn": self._battle_config.turn,
                "refresh": self._battle_config.refresh,
                "until_finish": self._battle_config.until_finish,
                "trigger_skip": self._battle_config.trigger_skip,
                "think_time_min": self._battle_config.think_time_min,
                "think_time_max": self._battle_config.think_time_max,
                "pre_fa": self._battle_config.pre_fa,
                "min_hp_threshold": self._battle_config.min_hp_threshold,
                "max_hp_threshold": self._battle_config.max_hp_threshold,
                "min_people": self._battle_config.min_people,
                "max_people": self._battle_config.max_people,
                "raid_amount": self._battle_config.raid_amount,
                "summon_priority": list(self._battle_config.summon_priority),
            }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
