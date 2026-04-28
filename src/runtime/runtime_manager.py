import threading
import time
from collections import deque
from typing import Optional

from infra.navigator import Navigator
from runtime.global_config import GlobalConfig
from task.task import Task
from task.task_manager import TaskManager


class RuntimeManager:
    """Top-level scheduler. Owns the queue, global config, and navigator.

    Responsibilities:
    - Maintain task_queue
    - Spawn automation daemon thread
    - Dequeue tasks and create TaskManagers
    - Handle failure policy (captcha halt, network halt, failed skip)
    - Provide progress snapshots for Flask UI
    """

    def __init__(self, navigator: Navigator):
        self.navigator = navigator
        self.global_config = GlobalConfig()
        self.task_queue: deque[Task] = deque()
        self.current_task_manager: Optional[TaskManager] = None
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_requested = False

    def enqueue_task(self, task: Task):
        """Add a task to the queue."""
        self.task_queue.append(task)
        print(f"[*] Enqueued task {task.task_id} ({task.task_type})")

    def start(self):
        """Start the automation daemon thread if not already running."""
        if self.is_running:
            print("[!] Runtime is already running")
            return
        if self._thread and self._thread.is_alive():
            print("[!] Previous thread still alive")
            return

        self.is_running = True
        self._stop_requested = False
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[*] RuntimeManager started")

    def _run_loop(self):
        """Main loop: dequeue tasks and run them until queue empty or stopped."""
        while self.is_running and not self._stop_requested:
            if not self.task_queue:
                time.sleep(0.5)
                continue

            task = self.task_queue.popleft()
            self.current_task_manager = TaskManager(
                task, self.navigator, self.global_config
            )

            print(f"[*] Starting task {task.task_id} ({task.task_type})")
            result = self.current_task_manager.run()
            print(f"[*] Task {task.task_id} finished: {result}")

            # Failure policy
            if result == "captcha":
                print("[!!!] CAPTCHA detected. Halting runtime and clearing queue.")
                self._stop_requested = True
                self.task_queue.clear()
                break
            elif result == "network_failed":
                print("[!!!] Network failure. Halting runtime.")
                self._stop_requested = True
                break
            # "failed" or "stopped" → just continue to next task naturally

        self.is_running = False
        self.current_task_manager = None
        print("[*] RuntimeManager loop ended")

    def stop(self):
        """Stop automation cooperatively. Current task stops at next boundary."""
        print("[*] Stop requested")
        self._stop_requested = True
        if self.current_task_manager:
            self.current_task_manager.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self.is_running = False

    def get_current_progress_snapshot(self) -> dict:
        """Return snapshot for Flask UI. If no task running, return idle state."""
        if self.current_task_manager:
            snapshot = self.current_task_manager.get_progress_snapshot()
            snapshot["is_running"] = self.is_running
            return snapshot
        return {
            "is_running": False,
            "current_state": "idle",
            "raids_completed": 0,
            "raids_target": 0,
            "current_turn": 0,
            "turn_target": 0,
            "current_raid_name": "",
            "current_raid_id": "",
            "boss_hp_at_entry": 0.0,
        }

    def load_default_config(self, config_path):
        """Load global defaults from JSON file."""
        import json
        from pathlib import Path
        path = Path(config_path)
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            # GlobalConfig only takes truly global fields
            self.global_config.think_time_min = data.get("think_time_min", 0.2)
            self.global_config.think_time_max = data.get("think_time_max", 0.5)
            print(f"[*] Loaded global config from {path}")

    def save_default_config(self, config_path, task_config_dict: dict):
        """Save merged config back to JSON."""
        import json
        from pathlib import Path
        path = Path(config_path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(task_config_dict, f, indent=2)
