from typing import Dict, Callable, Any, Optional
import json
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from actions import _check_and_handle_popup
from context import ActionContext, ActionRegistry
import time
import random
class ExitConditionType(Enum):
    RAID_COUNT = "raid_count"
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
    
    def execute_task(self, task: dict) -> bool:
        """
        Execute ONE task cycle.
        
        Returns:
            True - task cycle completed successfully
            False - stopped early (error/captcha)
        """
        actions = task.get("actions", [])
        action_map = {a["name"]: a for a in actions}
        # Start from first action
        current_name = actions[0]["name"]
        while current_name and self._running:
            # Check popup before action
            popup_type = _check_and_handle_popup(self.navigator)
            if popup_type:
                can_continue, redirect = self._handle_popup_recovery(popup_type)
                if not can_continue:
                    return False
                if redirect:
                    print(f"[i] Popup recovery: redirecting to '{redirect}'")
                    current_name = redirect
                    continue
            
            # Get action and params
            action_def = action_map.get(current_name)
            if not action_def:
                print(f"[!] Action '{current_name}' not found")
                return False
            
            name = action_def["name"]
            params = action_def.get("params", {})
            transitions = action_def.get("transitions", {})
            
            # Wait if previous action failed
            if self.context.last_result == ActionContext.RESULT_FAILED:
                time.sleep(random.uniform(3, 5))
            # Execute action
            action_func = ActionRegistry.get(name)
            if action_func:
                result = action_func(params, self.context) or ActionContext.RESULT_SUCCESS
                time.sleep(random.uniform(0.2, 0.5))
            else:
                print(f"[!] Action '{name}' not found")
                return False
            
            self.context.last_result = result
            
            # Check if this is the LAST action AND it succeeded
            # If so, task cycle is complete - exit and let caller handle next steps
            if action_def == actions[-1] and result == ActionContext.RESULT_SUCCESS:
                self.context.last_result = None
                return True
            
            # Determine next action from transitions
            if result in transitions:
                current_name = transitions[result]
            else:
                if ActionContext.RESULT_SUCCESS in transitions:
                    current_name = transitions[ActionContext.RESULT_SUCCESS]
                else:
                    print(f"[!] No transition for result '{result}' in '{current_name}'")
                    return False
        
        self.context.last_result = None
        return True
    
    def _handle_popup_recovery(self, popup_type: str) -> bool:
        """
        Handle popup based on type.
        Returns Tuple a flag and a redirection to other aciton if recovery can continue, False if should stop.
        """
        if popup_type == "captcha":
            print("[!!!] CAPTCHA detected - stopping automation")
            self._running = False
            return False,None
        elif popup_type == "raid_full":
            print("[i] Raid full - will refresh and retry")
            return True,"refresh_raid_list"
        elif popup_type == "not_enough_ap":
            print("[i] Not enough AP - waiting to retry")
            time.sleep(random.uniform(10, 20))
            return True,"refresh_raid_list"
        elif popup_type == "three_raid":
            print("[i] Three raids limit - waiting before refreshing")
            time.sleep(random.uniform(5, 10))
            return True,"refresh_raid_list"
        elif popup_type == "toomuch_pending":
            print("[i] Too many pending - cleaning queue")
            clean_action = ActionRegistry.get("clean_raid_queue")
            if clean_action:
                clean_action({}, self.context)
            return True,"refresh_raid_list"
        elif popup_type == "ended":
            print("[i] Raid already ended - skipping")
            return True,"refresh_raid_list"
        else:
            print(f"[i] Unknown popup: {popup_type}")
            return True,None
    
    def check_exit_condition(self, task: dict) -> bool:
        """Check if task exit condition is met."""
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