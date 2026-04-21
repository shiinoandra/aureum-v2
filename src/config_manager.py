from enum import Enum
from dataclasses import dataclass
from threading import Lock
from typing import Any,Optional
import json
from pathlib import Path

from state_machine import State

@dataclass
class BattleConfig:
    turn: int = 1
    refresh: bool = True
    until_finish: bool = False
    trigger_skip : bool = False
    think_time_min: int = 0.2
    think_time_max: int = 0.5


class ConfigManager:
    _instance:Optional['ConfigManager'] = None
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
        self._state_lock = Lock()
        self._config_lock = Lock()
        self._current_state= State.IDLE
        self._battle_config = BattleConfig()
        self._initialized = True 

    @property
    def current_state(self) -> State:
        with self._state_lock:
            return self._current_state
    
    @current_state.setter
    def current_state(self,state:State):
        with self._state_lock:
            self._current_state=state
    
    def get_battle_config(self)->BattleConfig:
        with self._config_lock:
            return BattleConfig(
                turn=self._battle_config.turn,
                refresh=self._battle_config.refresh,
                until_finish=self._battle_config.until_finish,
                trigger_skip=self._battle_config.trigger_skip,
                think_time_min=self._battle_config.think_time_min,
                think_time_max=self._battle_config.think_time_max
            )
    def update_battle_config(self,**kwargs):
        with self._config_lock:
            for key,value in kwargs.items():
                if hasattr(self._battle_config,key):
                    setattr(self._battle_config,key,value)
    
    def load_default_config(self,config_path:Path):
        with open(config_path) as f:
            data = json.load(f)
        self.update_battle_config(**data)

