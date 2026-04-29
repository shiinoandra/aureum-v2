from flask import Flask, render_template, request, jsonify, Response
import sys
import os
import json
import queue
import threading
import time
import uuid
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup


_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, 'src'))

import undetected_chromedriver as uc  # Alternative to regular Chrome driver


from infra.navigator import Navigator
from runtime.runtime_manager import RuntimeManager
from task.task import Task, TaskConfig

app = Flask(__name__)
runtime = None
engine_ready = False
engine_error = None
announcer = None


class MessageAnnouncer:
    def __init__(self):
        self.listeners = []

    def listen(self):
        q = queue.Queue(maxsize=10)
        self.listeners.append(q)
        try:
            while True:
                msg = q.get()
                yield msg
        finally:
            self.listeners.remove(q)

    def announce(self, msg):
        for i in reversed(range(len(self.listeners))):
            try:
                self.listeners[i].put_nowait(msg)
            except queue.Full:
                del self.listeners[i]


announcer = MessageAnnouncer()


def create_browser():
    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    if sys.platform == "win32":
        user_data_dir = r"C:\Selenium\ChromeProfile"
    else:
        user_data_dir = os.path.expanduser("~/.config/google-chrome/selenium_profile")
        if sys.platform == "linux":
            chrome_options.add_argument("--ozone-platform=x11")
    os.makedirs(user_data_dir, exist_ok=True)
    driver = uc.Chrome(
        options=chrome_options, user_data_dir=user_data_dir, version_main=145
    )
    return driver

    


def init_engine():
    global runtime, engine_ready, engine_error
    try:
        driver = create_browser()
        driver.get("https://game.granbluefantasy.jp/")
        navigator = Navigator(driver)
        runtime = RuntimeManager(navigator)
        threading.Thread(target=_progress_monitor, daemon=True).start()
        engine_ready = True
        print("[*] Engine initialized and ready")
    except Exception as e:
        engine_error = str(e)
        print(f"[!] Engine init failed: {e}")
        import traceback
        traceback.print_exc()


def _progress_monitor():
    """Push progress updates via SSE every 500ms."""
    while True:
        if runtime:
            snapshot = runtime.get_current_progress_snapshot()
            queue_snapshot = _get_queue_snapshot()
            payload = {
                "is_running": snapshot["is_running"],
                "current_state": snapshot["current_state"],
                "raids_completed": snapshot["raids_completed"],
                "raids_target": snapshot["raids_target"],
                "current_turn": snapshot["current_turn"],
                "turn_target": snapshot["turn_target"],
                "current_raid_name": snapshot["current_raid_name"],
                "boss_hp_at_entry": snapshot["boss_hp_at_entry"],
                "queue": queue_snapshot,
            }
            announcer.announce(json.dumps(payload))
        time.sleep(0.5)


def _get_queue_snapshot():
    """Serialize runtime queue for UI."""
    if not runtime:
        return []
    result = []
    for idx, task in enumerate(runtime.task_queue):
        exit_val = task.exit_condition.get("value", 0) if task.exit_condition else 0
        result.append({
            "index": idx,
            "task_type": task.task_type,
            "task_id": task.task_id,
            "amount": exit_val,
        })
    return result


def _get_tasks_dir():
    return Path(__file__).parent.parent / "tasks"


# =============================================================================
# Page Routes
# =============================================================================

@app.route("/")
def index():
    return render_template("index.html")


# =============================================================================
# Status
# =============================================================================

@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify({"ready": engine_ready, "error": engine_error})


# =============================================================================
# Task List / Details
# =============================================================================

@app.route("/api/list_tasks", methods=["GET"])
def list_tasks():
    """Return all .json filenames in tasks/ directory."""
    tasks_dir = _get_tasks_dir()
    if not tasks_dir.exists():
        return jsonify([])
    files = sorted([f.name for f in tasks_dir.glob("*.json")])
    return jsonify(files)


@app.route("/api/task/<name>", methods=["GET"])
def get_task(name):
    """Load a task JSON file by name."""
    tasks_dir = _get_tasks_dir()
    task_path = tasks_dir / name
    if not task_path.exists():
        return jsonify({"status": "error", "message": "Task not found"}), 404
    with open(task_path) as f:
        data = json.load(f)
    return jsonify(data)


# =============================================================================
# Queue Management
# =============================================================================

@app.route("/api/enqueue", methods=["POST"])
def enqueue():
    """Add a task to the runtime queue."""
    global engine_ready
    if not engine_ready:
        return jsonify({"status": "error", "message": "Engine not ready"}), 503

    data = request.json or {}
    task_name = data.get("task_name")
    amount = data.get("amount", 1)

    if not task_name:
        return jsonify({"status": "error", "message": "task_name required"}), 400

    tasks_dir = _get_tasks_dir()
    task_path = tasks_dir / task_name
    if not task_path.exists():
        return jsonify({"status": "error", "message": f"Task {task_name} not found"}), 404

    with open(task_path) as f:
        task_def = json.load(f)

    task_config = TaskConfig.from_dict(task_def.get("task_config", {}))
    exit_condition = dict(task_def.get("exit_condition", {}))
    if exit_condition.get("type") == "raid_count":
        exit_condition["value"] = amount

    task = Task(
        task_id=str(uuid.uuid4())[:8],
        task_type=task_def.get("task_type", "raid"),
        task_config=task_config,
        actions=task_def.get("actions", []),
        exit_condition=exit_condition,
    )

    runtime.enqueue_task(task)
    return jsonify({"status": "ok", "task_name": task_name, "amount": amount})


@app.route("/api/queue", methods=["GET"])
def get_queue():
    """Return current queue state."""
    return jsonify(_get_queue_snapshot())


@app.route("/api/remove_from_queue", methods=["POST"])
def remove_from_queue():
    """Remove a task from queue by index."""
    data = request.json or {}
    index = data.get("index")
    if index is None or not runtime:
        return jsonify({"status": "error"}), 400
    try:
        # deque doesn't support del by index directly
        queue_list = list(runtime.task_queue)
        if 0 <= index < len(queue_list):
            del queue_list[index]
            runtime.task_queue.clear()
            runtime.task_queue.extend(queue_list)
            return jsonify({"status": "ok"})
        return jsonify({"status": "error", "message": "Invalid index"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/reorder_queue", methods=["POST"])
def reorder_queue():
    """Reorder queue items."""
    data = request.json or {}
    old_index = data.get("old_index")
    new_index = data.get("new_index")
    if old_index is None or new_index is None or not runtime:
        return jsonify({"status": "error"}), 400
    try:
        queue_list = list(runtime.task_queue)
        if 0 <= old_index < len(queue_list) and 0 <= new_index <= len(queue_list):
            item = queue_list.pop(old_index)
            queue_list.insert(new_index, item)
            runtime.task_queue.clear()
            runtime.task_queue.extend(queue_list)
            return jsonify({"status": "ok"})
        return jsonify({"status": "error", "message": "Invalid index"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/clear_queue", methods=["POST"])
def clear_queue():
    """Clear the entire queue."""
    if runtime:
        runtime.task_queue.clear()
    return jsonify({"status": "ok"})


# =============================================================================
# Start / Stop
# =============================================================================

@app.route("/api/start", methods=["POST"])
def start_runtime():
    """Start the runtime if queue is non-empty."""
    global engine_ready
    if not engine_ready:
        return jsonify({"status": "error", "message": "Engine not ready yet"}), 503
    if runtime.is_running:
        return jsonify({"status": "error", "message": "Already running"}), 409
    if not runtime.task_queue:
        return jsonify({"status": "error", "message": "Queue is empty"}), 400

    runtime.start()
    return jsonify({"status": "started"})


@app.route("/api/stop", methods=["POST"])
def stop_runtime():
    """Stop runtime and clear queue."""
    if runtime:
        runtime.stop()
        runtime.task_queue.clear()
    return jsonify({"status": "stopped"})


# =============================================================================
# Progress / SSE
# =============================================================================

@app.route("/api/progress", methods=["GET"])
def get_progress():
    if runtime:
        snapshot = runtime.get_current_progress_snapshot()
        snapshot["queue"] = _get_queue_snapshot()
        return jsonify(snapshot)
    return jsonify({
        "is_running": False,
        "current_state": "idle",
        "raids_completed": 0,
        "raids_target": 0,
        "current_turn": 0,
        "turn_target": 0,
        "current_raid_name": "",
        "current_raid_id": "",
        "boss_hp_at_entry": 0.0,
        "queue": [],
    })


@app.route("/api/events")
def sse():
    def stream():
        for msg in announcer.listen():
            yield f"data: {msg}\n\n"
    return Response(stream(), mimetype="text/event-stream")


# =============================================================================
# Task Creator / Event Discovery
# =============================================================================

@app.route("/api/discover_event", methods=["POST"])
def discover_event():
    """
    Visit an event URL and scan for battle buttons.
    Returns a flat list of discovered buttons with placeholder types.
    """
    global engine_ready
    if not engine_ready:
        return jsonify({"status": "error", "message": "Engine not ready"}), 503

    data = request.json or {}
    event_url = data.get("event_url")
    if not event_url:
        return jsonify({"status": "error", "message": "event_url required"}), 400

    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException

        driver = runtime.navigator.driver
        driver.get(event_url)

        # Wait for page to load
        time.sleep(2)

        battles = []
        event_type=""

        if "treasureraid" in event_url:
            event_type="box_event"
            scripts = driver.find_elements(By.CSS_SELECTOR, "script[id^='tpl-button-battle']")

            for script in scripts:
                html = script.get_attribute("innerHTML")
                soup = BeautifulSoup(html, "html.parser")
                div = soup.find("div", class_="btn-offer")
                
                ap_value = div.get("data-ap")
                quest_id = div.get("data-quest-id")
                treasure_id = div.get("data-treasure-id")
                if div and ap_value and ap_value.isdigit():
                    ap = int(ap_value)

                    difficulty_map = {
                        20: "Very Hard",
                        30: "Extreme",
                        40: "Impossible",
                    }

                    battle_url_map = {
                        20:f"https://game.granbluefantasy.jp/#quest/supporter/{quest_id}/1",
                        30:f"https://game.granbluefantasy.jp/#quest/supporter/{quest_id}/1/0/{treasure_id}",
                        40:f"https://game.granbluefantasy.jp/#quest/supporter/{quest_id}/1/0/{treasure_id}",

                    }

                    battles.append({
                        "ap": ap,
                        "quest_id": quest_id,
                        "chapter_id": div.get("data-chapter-id"),
                        "chapter_name": div.get("data-chapter-name"),
                        "treasure_id": treasure_id,
                        "difficulty": difficulty_map.get(ap, "Unknown"),
                        "battle_url" : battle_url_map.get(ap,"")
                    })
        
        print(battles)

        return jsonify({"status": "ok", "event_url": event_url, "event_type" :event_type, "battles": battles})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/save_task", methods=["POST"])
def save_task():
    """Save a task definition to tasks/ directory."""
    data = request.json or {}
    filename = data.get("filename")
    if not filename:
        return jsonify({"status": "error", "message": "filename required"}), 400

    if not filename.endswith(".json"):
        filename += ".json"

    tasks_dir = _get_tasks_dir()
    tasks_dir.mkdir(exist_ok=True)
    task_path = tasks_dir / filename

    task_def = {
        "task_type": data.get("task_type", "quest"),
        "task_config": data.get("task_config", {}),
        "actions": data.get("actions", []),
        "exit_condition": data.get("exit_condition", {"type": "raid_count", "value": 10}),
    }

    try:
        with open(task_path, "w", encoding="utf-8") as f:
            json.dump(task_def, f, indent=2)
        return jsonify({"status": "ok", "filename": filename})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    threading.Thread(target=init_engine, daemon=True).start()
    app.run(debug=True, host="127.0.0.1", port=5000, threaded=True, use_reloader=False)
