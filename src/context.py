from dataclasses import dataclass
class ActionContext:
    def __init__(self, navigator, config_manager):
        self.navigator = navigator
        self.config = config_manager
        self.current_turn = 0
        self.raids_completed = 0
        self.battle_finished = False
    
    def reset(self):
        self.current_turn = 0
        self.battle_finished = False
class ActionRegistry:
    """Registry for actions - allows registering actions via decorator"""
    _actions = {}
    
    @classmethod
    def register(cls, name: str):
        def decorator(func):
            cls._actions[name] = func
            return func
        return decorator
    
    @classmethod
    def get(cls, name: str):
        return cls._actions.get(name)
    
    @classmethod
    def list_actions(cls) -> list:
        return list(cls._actions.keys())