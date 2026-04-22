from config_manager import ConfigManager
from state_machine import State, detect_state
from navigator import Navigator
from task_executor import TaskExecutor
from context import ActionContext, ActionRegistry
from pathlib import Path
import threading
import time

# Import actions to trigger @ActionRegistry.register decorators
from actions import (
    action_select_raid,
    action_select_summon,
    action_join_battle,
    action_do_battle,
    action_refresh_raid_list,
    action_clean_raid_queue,
    action_go_to_raid_list,
    action_go_to_main_menu,
)


class CoreEngine:
    def __init__(self, navigator: Navigator):
        self.navigator = navigator
        self.config = ConfigManager()
        self.task_executor = TaskExecutor(navigator, self.config)
        self._running = False
        self._current_task = None
        self._task_thread = None

    def start(self):
        """Start the main automation loop (legacy; not used when Flask owns the engine)."""
        self._running = True
        while self._running:
            self._main_loop()

    def stop(self):
        """Stop the automation loop"""
        self._running = False
        self.task_executor.stop()
        if self._task_thread and self._task_thread.is_alive():
            self._task_thread.join(timeout=5)

    def start_task(self, task_path: Path):
        """Start a specific task in background thread"""

        if self._running:
            print("[!] Engine is already running")
            return
        if self._task_thread and self._task_thread.is_alive():
            print("[!] Previous task thread still alive")
            return

        self._current_task = self.task_executor.load_task(task_path)
        self._running = True
        self.task_executor._running = True
        self._task_thread = threading.Thread(target=self._run_task_loop)
        self._task_thread.daemon = True
        self._task_thread.start()

    def _run_task_loop(self):
        """
        Run task loop - executes raid cycle repeatedly until exit condition met.

        Flow:
        1. Reset context for new raid (turn, battle_finished)
        2. Execute ONE raid cycle (select_raid → select_summon → join_battle → do_battle)
        3. Check exit condition (raids_completed >= target)
        4. Repeat or exit
        """
        print("[*] Task loop started")
        self.config.is_running = True
        battle_cfg = self.config.get_battle_config()
        if battle_cfg.raid_amount > 0:
            self.config.raids_target = battle_cfg.raid_amount
        else:
            self.config.raids_target = self._current_task.get(
                "exit_condition", {}
            ).get("value", 0)

        while self._running and self._current_task:
            try:
                # State detection & runtime stats
                self.config.last_known_url = self.navigator.get_current_url()
                self.config.current_state = detect_state(self.config.last_known_url)
                self.config.turn_target = self.config.get_battle_config().turn
                self.config.raids_target = self._current_task.get(
                    "exit_condition", {}
                ).get("value", 0)
                # Reset per-raid transient state
                print(f"Raids completed: {self.config.raids_completed}")
                self.task_executor.context.reset()
                self.config.current_turn = 0
                # Execute ONE raid cycle
                result = self.task_executor.execute_task(self._current_task)
                if not result:
                    print("[!] Task stopped early")
                    break
                # Check exit condition after each raid completes
                if self.task_executor.check_exit_condition(self._current_task):
                    print(
                        f"[✓] Exit condition met. Completed {self.config.raids_completed} raids."
                    )
                    break
            except Exception as e:
                print(f"[!] Exception in task: {e}")
                import traceback
                traceback.print_exc()

        self.config.is_running = False
        self._running = False
        self.config.task_start_time = 0
        print("[*] Task loop ended")

    def _main_loop(self):
        """
        Main loop - monitors state and handles recovery.
        This runs in the main thread while task runs in background.
        """
        url = self.navigator.get_current_url()
        current_state = detect_state(url)
        self.config.current_state = current_state
        if current_state == State.IDLE:
            self.navigator.wait(1, 2)
        elif current_state == State.ERROR_RECOVERY:
            self._handle_recovery()
        else:
            self.navigator.wait(0.5, 1)

    def _handle_recovery(self):
        """Handle recovery based on current detected state."""
        print("[*] Attempting recovery...")
        url = self.navigator.get_current_url()
        actual_state = detect_state(url)
        if actual_state == State.RAID_BATTLE:
            print("[*] Detected raid battle - continuing")
            battle_action = ActionRegistry.get("do_battle")
            if battle_action:
                battle_action({}, self.task_executor.context)
        elif actual_state == State.RAID_LIST:
            print("[*] Detected raid list - checking if task should restart")
            if self.task_executor.check_exit_condition(self._current_task):
                print("[*] Task already complete")
                self._running = False
        elif actual_state == State.MAIN_MENU:
            print("[*] Back at main menu - restarting task")
            self.task_executor.execute_task(self._current_task)
        elif actual_state == State.RAID_UNCLAIMED:
            print("[*] Detected unclaimed raids - cleaning queue")
            clean_action = ActionRegistry.get("clean_raid_queue")
            if clean_action:
                clean_action({}, self.task_executor.context)
        else:
            print(f"[*] Unknown recovery state {actual_state} - waiting")
            self.navigator.wait(2, 3)
