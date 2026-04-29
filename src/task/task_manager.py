import time
from typing import Optional

from domain.state_machine import detect_state, State
from domain.drop_logger import DropLogger
from task.task import Task
from task.task_progress import TaskProgress
from task.task_executor import TaskExecutor, CaptchaDetectedException, StopRequestedException
from runtime.global_config import GlobalConfig
from action.action_context import ActionContext
import infra.database as db


class TaskManager:
    """Owns the lifecycle of a single Task.

    Responsibilities:
    - Track TaskProgress (raids_completed, current_turn, etc.)
    - Run TaskExecutor cycles until exit condition met
    - Detect state between cycles
    - Call DropLogger on result screens
    - Handle retry/backoff for transient failures
    - Write task execution history to SQLite
    """

    def __init__(self, task: Task, navigator, global_config: GlobalConfig):
        self.task = task
        self.navigator = navigator
        self.global_config = global_config
        self.progress = TaskProgress()
        # Resume from previously saved progress if this task was stopped mid-run
        self.progress.raids_completed = task.completed
        self.executor = TaskExecutor(
            navigator, global_config, task.task_config, self.progress
        )
        self.logger = DropLogger()
        self._stop_requested = False
        self._network_retries = 0
        self._max_retries = 3
        self.history_id: Optional[int] = None

    def run(self) -> str:
        """
        Run task until exit condition met or failure.

        Returns:
            "completed" - exit condition reached
            "stopped" - user requested stop
            "failed" - action execution failed (RuntimeManager will skip to next task)
            "captcha" - captcha detected (RuntimeManager will halt queue)
            "network_failed" - network error exhausted retries (RuntimeManager will halt)
        """
        self.progress.status = "running"
        print(f"[*] TaskManager started for {self.task.task_type} ({self.task.task_id})")

        target = (
            self.task.exit_condition.get("value")
            if self.task.exit_condition
            else None
        )
        try:
            self.history_id = db.insert_task_history(
                task_name=self.task.source_file or self.task.task_id,
                task_type=self.task.task_type,
                target_count=target,
            )
        except Exception as e:
            print(f"[!] Failed to insert task history: {e}")
            self.history_id = None

        try:
            while not self._stop_requested:
                try:
                    # State detection between raids (non-blocking, just for UI/tracking)
                    url = self.navigator.get_current_url()
                    current_state = detect_state(url)
                    self.progress.current_state = current_state.value

                    # Reset transient per-raid state
                    self.executor.context.reset_per_raid()
                    self.progress.current_turn = 0

                    # Execute ONE raid/quest cycle
                    result = self.executor.execute_task_cycle(self.task.actions)

                    # Post-cycle hook: if success and on result screen, log drops
                    if result == ActionContext.RESULT_SUCCESS:
                        self._handle_post_cycle()
                        if self.history_id:
                            try:
                                db.update_task_history(
                                    self.history_id,
                                    completed_count=self.progress.raids_completed,
                                )
                            except Exception as e:
                                print(f"[!] Failed to update task history: {e}")

                    # Check exit condition
                    if self._check_exit_condition():
                        self.progress.status = "completed"
                        print(f"[*] Task {self.task.task_id} completed")
                        return "completed"

                except CaptchaDetectedException:
                    self.progress.status = "failed"
                    print(f"[!!!] Task {self.task.task_id} hit captcha")
                    return "captcha"
                except StopRequestedException:
                    self.progress.status = "stopped"
                    print(f"[*] Task {self.task.task_id} stopped by user")
                    return "stopped"
                except Exception as e:
                    print(f"[!] Exception in task {self.task.task_id}: {e}")
                    import traceback

                    traceback.print_exc()
                    self.progress.status = "failed"
                    return "failed"

            self.progress.status = "stopped"
            return "stopped"
        finally:
            # Persist completed count back to the Task so queue persistence
            # can resume from the correct progress on next start.
            self.task.completed = self.progress.raids_completed
            if self.history_id:
                try:
                    db.update_task_history(
                        self.history_id,
                        completed_count=self.progress.raids_completed,
                        status=self.progress.status,
                    )
                except Exception as e:
                    print(f"[!] Failed to finalize task history: {e}")

    def _handle_post_cycle(self):
        """Called after every successful cycle. Safe to inspect DOM."""
        url = self.navigator.get_current_url()
        state = detect_state(url)
        if state in (State.RAID_RESULT, State.QUEST_RESULT):
            items_json = self.logger.capture(
                driver=self.navigator.driver,
                raid_id=self.progress.current_raid_id,
                raid_name=self.progress.current_raid_name,
            )
            if self.history_id and items_json and items_json != "[]":
                try:
                    db.insert_drop_log(
                        task_history_id=self.history_id,
                        items_json=items_json,
                        raid_id=self.progress.current_raid_id or None,
                    )
                except Exception as e:
                    print(f"[!] Failed to insert drop log: {e}")
        # Increment raids_completed after the cycle
        self.progress.raids_completed += 1

    def _check_exit_condition(self) -> bool:
        """Check if task exit condition is met."""
        exit_cond = self.task.exit_condition
        if not exit_cond:
            return False
        cond_type = exit_cond.get("type")
        cond_value = exit_cond.get("value")
        if cond_type == "raid_count":
            return self.progress.raids_completed >= cond_value
        elif cond_type == "until_finish":
            return self.executor.context.battle_finished
        return False

    def stop(self):
        """Request cooperative stop."""
        self._stop_requested = True
        self.executor.stop()

    def get_progress_snapshot(self) -> dict:
        """Return a snapshot for Flask UI."""
        return {
            "is_running": self.progress.status == "running",
            "current_state": self.progress.current_state,
            "raids_completed": self.progress.raids_completed,
            "raids_target": (
                self.task.exit_condition.get("value", 0)
                if self.task.exit_condition
                else 0
            ),
            "current_turn": self.progress.current_turn,
            "turn_target": self.task.task_config.turn,
            "current_raid_name": self.progress.current_raid_name,
            "current_raid_id": self.progress.current_raid_id,
            "boss_hp_at_entry": self.progress.boss_hp_at_entry,
        }
