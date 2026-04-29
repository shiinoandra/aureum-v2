import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

from infra.navigator import Navigator
from runtime.global_config import GlobalConfig
from runtime.queue_persistence import save_queue, load_queue
from task.task import Task
from task.task_manager import TaskManager


class RuntimeManager:
    """Top-level scheduler. Owns the queue, global config, and navigator.

    Responsibilities:
    - Maintain task_queue (with file persistence)
    - Spawn automation daemon thread
    - Run tasks from queue until completion or stop
    - Handle failure policy (captcha halt, network halt, failed skip)
    - Provide progress snapshots for Flask UI
    """

    def __init__(self, navigator: Navigator, tasks_dir: Optional[Path] = None):
        self.navigator = navigator
        self.global_config = GlobalConfig()
        self.tasks_dir = tasks_dir
        self.task_queue: deque[Task] = deque()
        self.current_task_manager: Optional[TaskManager] = None
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_requested = False

        # Load persisted queue on startup
        if self.tasks_dir:
            self.task_queue = load_queue(self.tasks_dir)
            if self.task_queue:
                print(f"[*] Restored {len(self.task_queue)} task(s) from queue file")

    def enqueue_task(self, task: Task):
        """Add a task to the queue and persist."""
        self.task_queue.append(task)
        self._persist_queue()
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
        """Main loop: run tasks from queue until empty or stopped.

        Uses queue[0] to peek at the current task instead of popleft().
        Only removes a task when it completes successfully or fails.
        This allows stop+start to resume the same task from its saved progress.
        """
        while self.is_running and not self._stop_requested:
            if not self.task_queue:
                time.sleep(0.5)
                continue

            # Peek at current task — don't remove until it finishes
            task = self.task_queue[0]
            self.current_task_manager = TaskManager(
                task, self.navigator, self.global_config
            )

            print(f"[*] Starting task {task.task_id} ({task.task_type})")
            result = self.current_task_manager.run()
            print(f"[*] Task {task.task_id} finished: {result}")

            # Failure policy
            if result == "completed":
                self.task_queue.popleft()
                self._persist_queue()
            elif result == "failed":
                # Skip failed task and move on
                self.task_queue.popleft()
                self._persist_queue()
            elif result == "captcha":
                print("[!!!] CAPTCHA detected. Halting runtime and clearing queue.")
                self._stop_requested = True
                self.task_queue.clear()
                self._persist_queue()
                break
            elif result == "network_failed":
                print("[!!!] Network failure. Halting runtime.")
                self._stop_requested = True
                break
            elif result == "stopped":
                # User stopped — task stays at front for resume on next start
                pass

        self.is_running = False
        self.current_task_manager = None
        # Persist queue so stopped tasks retain their updated completed counts
        self._persist_queue()
        print("[*] RuntimeManager loop ended")

    def stop(self):
        """Stop automation cooperatively. Queue is PRESERVED."""
        print("[*] Stop requested")
        self._stop_requested = True
        if self.current_task_manager:
            self.current_task_manager.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self.is_running = False

    def clear_queue(self):
        """Explicitly clear the entire queue."""
        self.task_queue.clear()
        self._persist_queue()
        print("[*] Queue cleared")

    def _persist_queue(self):
        """Save current queue state to disk."""
        if self.tasks_dir:
            save_queue(self.task_queue)

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
