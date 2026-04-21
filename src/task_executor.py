from typing import Dict, Callable, Any, Optional
import json
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from actions import _check_and_handle_popup
from context import ActionContext,ActionRegistry
import time
import random


class ExitConditionType(Enum):
    RAID_COUNT = "raid_count"  # Number of raids to complete
    UNTIL_FINISH = "until_finish"

@dataclass
class ExitCondition:
    type: ExitConditionType
    value: Any


class TaskExecutor:
    """Executes tasks defined in JSON"""
    def __init__(self, navigator, config_manager):
        self.navigator = navigator
        self.config = config_manager
        self.context = ActionContext(navigator, config_manager)
        self._running = True
    
    def load_task(self, task_path: Path) -> dict:
        """Load task definition from JSON file"""
        with open(task_path) as f:
            return json.load(f)
    
    def execute_task(self, task: dict):
        """Execute a task - runs all actions in sequence with popup checks."""
        actions = task.get("actions", [])
        action_map = {a["name"]: a for a in actions}

        # Start from first action
        current_name = actions[0]["name"]
        max_iterations = 1000  # Prevent infinite loops
        iterations = 0

        while current_name and self._running and iterations < max_iterations:
            iterations += 1
            
            # Check popup
            popup_type = _check_and_handle_popup(self.navigator)
            if popup_type:
                if not self._handle_popup_recovery(popup_type):
                    return False
            
            # Get action and params
            action_def = action_map.get(current_name)
            if not action_def:
                print(f"[!] Action '{current_name}' not found")
                break
            
            name = action_def["name"]
            params = action_def.get("params", {})
            transitions = action_def.get("transitions", {})
            
            # Execute action
            action_func = ActionRegistry.get(name)
            if action_func:
                result = action_func(params, self.context) or ActionContext.RESULT_SUCCESS
                time.sleep(random.uniform(0.2,0.5))
            else:
                print(f"[!] Action '{name}' not found")
                break
            
            self.context.last_result = result
            
            # Determine next action from transitions
            if result in transitions:
                current_name = transitions[result]
            else:
                # No transition for result, try default
                if ActionContext.RESULT_SUCCESS in transitions:
                    current_name = transitions[ActionContext.RESULT_SUCCESS]
                else:
                    print(f"[!] No transition for result '{result}' in '{current_name}'")
                    break
        
        self.context.last_result = None
        return True
        
    def _handle_popup_recovery(self, popup_type: str) -> bool:
        """
        Handle popup based on type.
        Returns True if recovery can continue, False if should stop.
        """
        if popup_type == "captcha":
            print("[!!!] CAPTCHA detected - stopping automation")
            self._running = False
            return False
        elif popup_type == "raid_full":
            print("[i] Raid full - will refresh and retry")
            return True
        elif popup_type == "not_enough_ap":
            print("[i] Not enough AP - waiting to retry")
            time.sleep(random.uniform(10, 20))
            return True
        elif popup_type == "three_raid":
            print("[i] Three raids limit - waiting before refreshing")
            # Trigger clean_raid_queue action
            time.sleep(random.uniform(5, 10))

            return True
        elif popup_type == "toomuch_pending":
            print("[i] Too many pending - cleaning queue")
            # Trigger clean_raid_queue action
            clean_action = ActionRegistry.get("clean_raid_queue")
            if clean_action:
                clean_action({}, self.context)
            return True
        elif popup_type == "ended":
            print("[i] Raid already ended - skipping")
            return True
        else:
            print(f"[i] Unknown popup: {popup_type}")
            return True
    
    def check_exit_condition(self, task: dict) -> bool:
        exit_cond = task.get("exit_condition")
        if not exit_cond:
            return False
        
        cond_type = exit_cond.get("type")
        cond_value = exit_cond.get("value")
        
        if cond_type == ExitConditionType.RAID_COUNT.value:
            return self.context.raids_completed >= cond_value
        elif cond_type == ExitConditionType.UNTIL_FINISH.value:
            return self.context.battle_finished
        
        return False
    
    def stop(self):
        """Stop the task executor"""
        self._running = False