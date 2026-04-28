class ActionRegistry:
    """Registry for actions — allows registering actions via decorator."""
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
