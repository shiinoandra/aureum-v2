from typing import Dict, Callable, Any, Optional
import json
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import time
import random

from action.action_context import ActionContext
from action.action_registry import ActionRegistry
from action.actions import _check_and_handle_popup


class CaptchaDetectedException(Exception):
    """Raised when a CAPTCHA popup is detected. Halts all automation."""
    pass


class StopRequestedException(Exception):
    """Raised when the user requests a stop."""
    pass


class TaskExecutor:
    """Pure FSM runner. Executes one action cycle via transitions.

    Does NOT check task-level exit conditions.
    Does NOT track progress counters.
    Raises CaptchaDetectedException on captcha popup.
    """

    def __init__(self, navigator, global_config, task_config, task_progress, raid_id=None):
        self.navigator = navigator
        self.global_config = global_config
        self.task_config = task_config
        self.task_progress = task_progress
        self.context = ActionContext(navigator, global_config, task_config, task_progress, raid_id=raid_id)
        self._stop_requested = False

    def execute_task_cycle(self, actions: list) -> str:
        """
        Execute ONE task cycle through the action FSM.

        Args:
            actions: List of action definitions from task JSON.

        Returns:
            ActionContext.RESULT_SUCCESS or ActionContext.RESULT_FAILED

        Raises:
            CaptchaDetectedException: if captcha popup encountered.
            StopRequestedException: if stop requested mid-cycle.
        """
        action_map = {a["name"]: a for a in actions}
        current_name = actions[0]["name"]

        while current_name:
            if self._stop_requested:
                raise StopRequestedException()

            # Check popup before action
            popup_type = _check_and_handle_popup(self.navigator)
            if popup_type:
                can_continue, redirect = self._handle_popup_recovery(popup_type)
                if not can_continue:
                    return ActionContext.RESULT_FAILED
                if redirect:
                    current_name = redirect
                    continue

            action_def = action_map.get(current_name)
            if not action_def:
                print(f"[!] Action '{current_name}' not found")
                return ActionContext.RESULT_FAILED

            name = action_def["name"]
            params = action_def.get("params", {})
            transitions = action_def.get("transitions", {})

            # Wait if previous action failed
            if self.context.last_result == ActionContext.RESULT_FAILED:
                time.sleep(random.uniform(3, 5))

            # Execute action
            action_func = ActionRegistry.get(name)
            if action_func:
                result = (
                    action_func(params, self.context) or ActionContext.RESULT_SUCCESS
                )
                time.sleep(random.uniform(0.2, 0.5))
            else:
                print(f"[!] Action '{name}' not found")
                return ActionContext.RESULT_FAILED

            self.context.last_result = result

            # If last action succeeded, cycle complete
            if action_def == actions[-1] and result == ActionContext.RESULT_SUCCESS:
                self.context.last_result = None
                return ActionContext.RESULT_SUCCESS

            # Transition
            if result in transitions:
                current_name = transitions[result]
            elif ActionContext.RESULT_SUCCESS in transitions:
                current_name = transitions[ActionContext.RESULT_SUCCESS]
            elif not transitions:
                # Fallback: if no transitions defined, move to next action in list
                try:
                    current_idx = actions.index(action_def)
                    if current_idx + 1 < len(actions):
                        current_name = actions[current_idx + 1]["name"]
                    else:
                        # Last action with no transitions - cycle complete
                        return ActionContext.RESULT_SUCCESS
                except ValueError:
                    print(f"[!] Could not find action '{current_name}' in list")
                    return ActionContext.RESULT_FAILED
            else:
                print(
                    f"[!] No transition for result '{result}' in '{current_name}'"
                )
                return ActionContext.RESULT_FAILED

        self.context.last_result = None
        return ActionContext.RESULT_SUCCESS

    def _handle_popup_recovery(self, popup_type: str):
        """
        Handle popup based on type.
        Returns (can_continue: bool, redirect: str|None).
        Raises CaptchaDetectedException for captcha.
        """
        if popup_type == "captcha":
            print("[!!!] CAPTCHA detected - stopping automation")
            raise CaptchaDetectedException()
        elif popup_type == "raid_full":
            print("[i] Raid full - will refresh and retry")
            return True, "refresh_raid_list"
        elif popup_type == "not_enough_ap":
            print("[i] Not enough AP - waiting to retry")
            time.sleep(random.uniform(10, 20))
            return True, "refresh_raid_list"
        elif popup_type == "three_raid":
            print("[i] Three raids limit - waiting before refreshing")
            time.sleep(random.uniform(5, 10))
            return True, "refresh_raid_list"
        elif popup_type == "toomuch_pending":
            print("[i] Too many pending - cleaning queue")
            clean_action = ActionRegistry.get("clean_raid_queue")
            if clean_action:
                clean_action({}, self.context)
            return True, "refresh_raid_list"
        elif popup_type == "ended":
            print("[i] Raid already ended - skipping")
            return True, "refresh_raid_list"
        else:
            print(f"[i] Unknown popup: {popup_type}")
            return True, None

    def stop(self):
        self._stop_requested = True
