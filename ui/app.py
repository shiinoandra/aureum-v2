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


@app.template_filter("duration")
def _duration_filter(start, end):
    """Calculate human-readable duration between two ISO timestamps."""
    if not start or not end:
        return "-"
    try:
        fmt = "%Y-%m-%d %H:%M:%S"
        # Strip fractional seconds if present
        s_str = str(start).split(".")[0]
        e_str = str(end).split(".")[0]
        s = datetime.strptime(s_str, fmt)
        e = datetime.strptime(e_str, fmt)
        total_seconds = int((e - s).total_seconds())
        if total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            return f"{total_seconds // 60}m {total_seconds % 60}s"
        else:
            return f"{total_seconds // 3600}h {(total_seconds % 3600) // 60}m"
    except Exception:
        return "-"


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
        tasks_dir = _get_tasks_dir()
        runtime = RuntimeManager(navigator, tasks_dir=tasks_dir)
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
            "source_file": task.source_file,
            "amount": exit_val,
            "completed": task.completed,
            "not_found_count": task.not_found_count,
            "history_id": task.history_id,
        })
    return result


def _get_tasks_dir():
    return Path(__file__).parent.parent / "tasks"


# =============================================================================
# Page Routes
# =============================================================================

def _get_task_files():
    """Get sorted list of task JSON files."""
    tasks_dir = _get_tasks_dir()
    if not tasks_dir.exists():
        return []
    return sorted([f.name for f in tasks_dir.glob("*.json")])


# =============================================================================
# Page Routes (HTMX)
# =============================================================================

@app.route("/")
def index():
    return render_template("pages/dashboard.html", task_files=_get_task_files())


@app.route("/creator")
def creator_page():
    return render_template("pages/task_creator.html", task_files=_get_task_files())


@app.route("/history")
def history_page():
    return render_template("pages/history.html")


# =============================================================================
# HTMX Partials
# =============================================================================

@app.route("/htmx/status")
def htmx_status():
    """Return status header partial."""
    if not runtime:
        return render_template("partials/status_header.html", runtime=False)
    snapshot = runtime.get_current_progress_snapshot()
    queue_items = _get_queue_snapshot()
    raids_target = snapshot.get("raids_target", 0)
    raids_completed = snapshot.get("raids_completed", 0)
    progress_pct = round((raids_completed / raids_target) * 100) if raids_target > 0 else 0
    return render_template(
        "partials/status_header.html",
        runtime=True,
        is_running=snapshot.get("is_running", False),
        current_state=snapshot.get("current_state", "idle"),
        raids_completed=raids_completed,
        raids_target=raids_target,
        progress_pct=progress_pct,
        queue_length=len(queue_items),
    )


@app.route("/htmx/queue")
def htmx_queue():
    """Return queue partial."""
    if not runtime:
        return render_template("partials/queue.html", queue_items=[], is_running=False)
    queue_items = _get_queue_snapshot()
    snapshot = runtime.get_current_progress_snapshot()
    return render_template(
        "partials/queue.html",
        queue_items=queue_items,
        is_running=snapshot.get("is_running", False),
    )


@app.route("/htmx/task-preview")
def htmx_task_preview():
    """Return task preview partial."""
    task_name = request.args.get("task_name", "")
    if not task_name:
        return render_template("partials/task_preview.html")
    tasks_dir = _get_tasks_dir()
    task_path = tasks_dir / task_name
    if not task_path.exists():
        return render_template("partials/task_preview.html")
    with open(task_path) as f:
        data = json.load(f)
    cfg = data.get("task_config", {})
    summons = cfg.get("summon_priority", [])
    summons_text = ", ".join([s.get("name", "") + (" " + s.get("level", "") if s.get("level") else "") for s in summons]) if summons else "None"
    return render_template(
        "partials/task_preview.html",
        task_type=data.get("task_type", "raid"),
        task_config=cfg,
        summons_text=summons_text,
    )


@app.route("/htmx/raid-card")
def htmx_raid_card():
    """Return raid card partial."""
    if not runtime:
        return render_template(
            "partials/raid_card.html",
            is_running=False,
            current_raid_name="",
            boss_hp=0,
            turn_pct=0,
            current_turn=0,
            turn_target=0,
        )
    snapshot = runtime.get_current_progress_snapshot()
    current_turn = snapshot.get("current_turn", 0)
    turn_target = snapshot.get("turn_target", 0)
    turn_pct = round((current_turn / turn_target) * 100) if turn_target > 0 else 0
    return render_template(
        "partials/raid_card.html",
        is_running=snapshot.get("is_running", False),
        current_raid_name=snapshot.get("current_raid_name", ""),
        boss_hp=snapshot.get("boss_hp_at_entry", 0),
        turn_pct=turn_pct,
        current_turn=current_turn,
        turn_target=turn_target,
    )


@app.route("/htmx/creator-load")
def htmx_creator_load():
    """Load task config into creator form."""
    from infra.database import get_all_summons, get_raid_by_id
    task_name = request.args.get("task_name", "")
    if not task_name:
        return "<p class='text-sm text-slate-400'>Select a task to load</p>"
    tasks_dir = _get_tasks_dir()
    task_path = tasks_dir / task_name
    if not task_path.exists():
        return "<p class='text-sm text-red-400'>Task not found</p>"
    with open(task_path) as f:
        data = json.load(f)
    cfg = data.get("task_config", {})
    all_summons = get_all_summons()

    # Look up raid info if raid_id is present
    raid_id = data.get("raid_id")
    raid_name = None
    raid_level = None
    raid_difficulty = None
    if raid_id:
        raid = get_raid_by_id(raid_id)
        if raid:
            raid_name = raid.get("name")
            raid_level = raid.get("level")
            raid_difficulty = raid.get("difficulty")

    exit_cond = data.get("exit_condition", {})
    amount = exit_cond.get("value", 10) if exit_cond.get("type") == "raid_count" else 10

    return render_template(
        "partials/creator_form.html",
        task_name=task_name,
        cfg=cfg,
        task_type=data.get("task_type", "raid"),
        actions=data.get("actions", []),
        raid_id=raid_id,
        raid_name=raid_name,
        raid_level=raid_level,
        raid_difficulty=raid_difficulty,
        amount=amount,
        all_summons=all_summons,
        selected_summons=list(cfg.get("summon_priority", [])),
    )


@app.route("/htmx/raid-grid/<category>")
def htmx_raid_grid(category):
    """Return raid grid for a category from the database."""
    from infra.database import get_all_raids
    try:
        all_raids = get_all_raids()
        if category == "all":
            raids = all_raids
        elif category == "v2":
            raids = [r for r in all_raids if r.get("v2")]
        elif category == "standard":
            raids = [r for r in all_raids if r.get("difficulty") in ("Normal", "Hard", "Very Hard", "Extreme")]
        elif category == "impossible":
            raids = [r for r in all_raids if r.get("difficulty") == "Impossible" and not r.get("v2")]
        elif category == "unlimited":
            raids = [r for r in all_raids if r.get("difficulty") in ("Impossible+", "Nightmare")]
        else:
            raids = all_raids
        return render_template("partials/raid_grid.html", raids=raids, category=category)
    except Exception as e:
        return f"<p class='text-sm text-red-500'>Error loading raids: {e}</p>"


@app.route("/htmx/content-list/<content_type>")
def htmx_content_list(content_type):
    """Return paginated list for events or quests."""
    page = request.args.get("page", 1, type=int)
    per_page = 6

    # Placeholder data until database is populated
    placeholder_items = {
        "event": [
            {"id": "evt001", "name": "Unite and Fight", "ap_cost": 30, "ap_current": 1, "ap_max": 2, "cleared": True},
            {"id": "evt002", "name": "Rise of the Beasts", "ap_cost": 20, "ap_current": 1, "ap_max": 2, "cleared": False},
            {"id": "evt003", "name": "Xeno Clash", "ap_cost": 30, "ap_current": 2, "ap_max": 2, "cleared": True},
            {"id": "evt004", "name": "Guild Wars", "ap_cost": 0, "ap_current": 1, "ap_max": 3, "cleared": False},
            {"id": "evt005", "name": "Treasure Raid", "ap_cost": 30, "ap_current": 1, "ap_max": 2, "cleared": False},
            {"id": "evt006", "name": "Story Event", "ap_cost": 15, "ap_current": 1, "ap_max": 2, "cleared": True},
            {"id": "evt007", "name": "Dread Barrage", "ap_cost": 30, "ap_current": 1, "ap_max": 2, "cleared": False},
            {"id": "evt008", "name": "A Tale of Intersecting Fates", "ap_cost": 20, "ap_current": 1, "ap_max": 2, "cleared": False},
        ],
        "quest": [
            {"id": "qst001", "name": "Next Up: A Mechanical Beast?!", "ap_cost": 11, "ap_current": 1, "ap_max": 2, "cleared": True},
            {"id": "qst002", "name": "Strength and Chivalry", "ap_cost": 25, "ap_current": 1, "ap_max": 2, "cleared": True},
            {"id": "qst003", "name": "Baker and the Merrymaker", "ap_cost": 15, "ap_current": 1, "ap_max": 2, "cleared": True},
            {"id": "qst004", "name": "Trust-Busting Dustup", "ap_cost": 11, "ap_current": 1, "ap_max": 2, "cleared": False},
            {"id": "qst005", "name": "The Mysterious Room", "ap_cost": 25, "ap_current": 1, "ap_max": 2, "cleared": False},
            {"id": "qst006", "name": "The Right of Might", "ap_cost": 25, "ap_current": 1, "ap_max": 2, "cleared": False},
            {"id": "qst007", "name": "A Tale of Sky and Darkness", "ap_cost": 20, "ap_current": 1, "ap_max": 2, "cleared": True},
            {"id": "qst008", "name": "Footprints on Sacred Ground", "ap_cost": 30, "ap_current": 1, "ap_max": 2, "cleared": False},
        ],
    }

    all_items = placeholder_items.get(content_type, [])
    total = len(all_items)
    total_pages = (total + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    items = all_items[start:end]

    return render_template(
        "partials/content_list.html",
        items=items,
        content_type=content_type,
        current_page=page,
        total_pages=total_pages,
    )


@app.route("/htmx/history-table")
def htmx_history_table():
    """Return history table partial."""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    from infra.database import get_task_history
    items = get_task_history(limit=per_page, offset=(page - 1) * per_page)
    return render_template(
        "partials/history_table.html",
        items=items,
        page=page,
        per_page=per_page,
    )


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


@app.route("/api/summons", methods=["GET"])
def get_summons():
    """Return all summons from the database."""
    from infra.database import get_all_summons
    try:
        summons = get_all_summons()
        return jsonify({"status": "ok", "summons": summons})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/raids", methods=["GET"])
def get_raids():
    """Return raids from the database, optionally filtered by category."""
    from infra.database import get_all_raids
    category = request.args.get("category", "all")
    try:
        all_raids = get_all_raids()
        if category == "all":
            raids = all_raids
        elif category == "v2":
            raids = [r for r in all_raids if r.get("v2")]
        elif category == "standard":
            raids = [r for r in all_raids if r.get("difficulty") in ("Normal", "Hard", "Very Hard", "Extreme")]
        elif category == "impossible":
            raids = [r for r in all_raids if r.get("difficulty") == "Impossible" and not r.get("v2")]
        elif category == "unlimited":
            raids = [r for r in all_raids if r.get("difficulty") in ("Impossible+", "Nightmare")]
        else:
            raids = all_raids
        return jsonify({"status": "ok", "raids": raids})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


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
# Task History
# =============================================================================

@app.route("/api/history", methods=["GET"])
def get_history():
    """Return paginated task history."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    from infra.database import get_task_history
    items = get_task_history(limit=per_page, offset=(page - 1) * per_page)
    return jsonify({"status": "ok", "items": items, "page": page, "per_page": per_page})


@app.route("/api/history/<int:history_id>/drops", methods=["GET"])
def get_history_drops(history_id):
    """Return drop logs for a task history entry."""
    from infra.database import get_drops_by_task_history
    drops = get_drops_by_task_history(history_id)
    return jsonify({"status": "ok", "drops": drops})


# =============================================================================
# Queue Management
# =============================================================================

def _get_request_data():
    """Safely extract request data regardless of Content-Type."""
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form or {}


@app.route("/api/enqueue", methods=["POST"])
def enqueue():
    """Add a task to the runtime queue."""
    global engine_ready
    if not engine_ready:
        return jsonify({"status": "error", "message": "Engine not ready"}), 503

    data = _get_request_data()
    task_name = data.get("task_name")
    amount = int(data.get("amount", 1) or 1)

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
        source_file=task_name,
    )

    runtime.enqueue_task(task)

    # If HTMX request, return success message + trigger queue refresh via header
    if request.headers.get("HX-Request"):
        from flask import Response
        return Response(
            f'<span class="text-green-600 font-medium"><i class="fa-solid fa-check mr-1"></i>Added {task_name} x{amount}</span>',
            headers={"HX-Trigger": "queueUpdated"}
        )

    return jsonify({"status": "ok", "task_name": task_name, "amount": amount})


@app.route("/api/queue", methods=["GET"])
def get_queue():
    """Return current queue state."""
    return jsonify(_get_queue_snapshot())


def _queue_mutable():
    """Check if queue can be mutated. Returns (ok, error_message)."""
    if not runtime:
        return False, "Runtime not initialized"
    if runtime.is_running:
        return False, "Cannot modify queue while running. Stop first."
    return True, None


@app.route("/api/sync_queue", methods=["POST"])
def sync_queue():
    """Replace entire queue with client-provided state."""
    ok, err = _queue_mutable()
    if not ok:
        return jsonify({"status": "error", "message": err}), 409

    data = _get_request_data()
    items = data.get("items", [])
    tasks_dir = _get_tasks_dir()

    # Build lookup of existing tasks to preserve backend-only fields
    old_tasks = {t.task_id: t for t in runtime.task_queue}

    new_queue = []
    for item in items:
        source_file = item.get("source_file")
        if not source_file:
            continue
        task_path = tasks_dir / source_file
        if not task_path.exists():
            continue
        try:
            with open(task_path) as f:
                task_def = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        task_config = TaskConfig.from_dict(task_def.get("task_config", {}))
        exit_condition = dict(task_def.get("exit_condition", {}))
        if exit_condition.get("type") == "raid_count":
            exit_condition["value"] = item.get("amount", 1)

        task_id = item.get("task_id", str(uuid.uuid4())[:8])
        old_task = old_tasks.get(task_id)

        # Preserve backend-only fields from existing task if present
        completed = old_task.completed if old_task else 0
        not_found_count = old_task.not_found_count if old_task else 0
        history_id = old_task.history_id if old_task else None

        task = Task(
            task_id=task_id,
            task_type=task_def.get("task_type", "raid"),
            task_config=task_config,
            actions=task_def.get("actions", []),
            exit_condition=exit_condition,
            completed=completed,
            not_found_count=not_found_count,
            source_file=source_file,
            history_id=history_id,
        )
        new_queue.append(task)

    runtime.task_queue.clear()
    runtime.task_queue.extend(new_queue)
    runtime._persist_queue()

    if request.headers.get("HX-Request"):
        queue_items = _get_queue_snapshot()
        snapshot = runtime.get_current_progress_snapshot()
        return render_template("partials/queue.html", queue_items=queue_items, is_running=snapshot.get("is_running", False))
    return jsonify({"status": "ok", "count": len(new_queue)})


@app.route("/api/remove_from_queue", methods=["POST"])
def remove_from_queue():
    """Remove a task from queue by index."""
    ok, err = _queue_mutable()
    if not ok:
        return jsonify({"status": "error", "message": err}), 409

    data = _get_request_data()
    index = data.get("index")
    if index is None:
        return jsonify({"status": "error"}), 400
    try:
        index = int(index)
        queue_list = list(runtime.task_queue)
        if 0 <= index < len(queue_list):
            del queue_list[index]
            runtime.task_queue.clear()
            runtime.task_queue.extend(queue_list)
            runtime._persist_queue()
            if request.headers.get("HX-Request"):
                queue_items = _get_queue_snapshot()
                snapshot = runtime.get_current_progress_snapshot()
                return render_template("partials/queue.html", queue_items=queue_items, is_running=snapshot.get("is_running", False))
            return jsonify({"status": "ok"})
        return jsonify({"status": "error", "message": "Invalid index"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/reorder_queue", methods=["POST"])
def reorder_queue():
    """Reorder queue items."""
    ok, err = _queue_mutable()
    if not ok:
        return jsonify({"status": "error", "message": err}), 409

    data = _get_request_data()
    old_index = data.get("old_index")
    new_index = data.get("new_index")
    if old_index is None or new_index is None:
        return jsonify({"status": "error"}), 400
    try:
        old_index = int(old_index)
        new_index = int(new_index)
        queue_list = list(runtime.task_queue)
        if 0 <= old_index < len(queue_list) and 0 <= new_index <= len(queue_list):
            item = queue_list.pop(old_index)
            queue_list.insert(new_index, item)
            runtime.task_queue.clear()
            runtime.task_queue.extend(queue_list)
            runtime._persist_queue()
            if request.headers.get("HX-Request"):
                queue_items = _get_queue_snapshot()
                snapshot = runtime.get_current_progress_snapshot()
                return render_template("partials/queue.html", queue_items=queue_items, is_running=snapshot.get("is_running", False))
            return jsonify({"status": "ok"})
        return jsonify({"status": "error", "message": "Invalid index"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/clear_queue", methods=["POST"])
def clear_queue():
    """Clear the entire queue."""
    ok, err = _queue_mutable()
    if not ok:
        return jsonify({"status": "error", "message": err}), 409

    if runtime:
        runtime.clear_queue()
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
    """Stop runtime. Queue is PRESERVED."""
    if runtime:
        runtime.stop()
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


def _parse_bool_value(value):
    """Parse a boolean value from various input sources (checkbox, JSON, form)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "on", "yes")
    return bool(value)


@app.route("/api/save_task", methods=["POST"])
def save_task():
    """Save a task definition to tasks/ directory.

    Accepts both JSON (Content-Type: application/json) and form-encoded data.
    """
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form or {}

    filename = data.get("filename")
    if not filename:
        return jsonify({"status": "error", "message": "filename required"}), 400

    if not filename.endswith(".json"):
        filename += ".json"

    tasks_dir = _get_tasks_dir()
    tasks_dir.mkdir(exist_ok=True)
    task_path = tasks_dir / filename

    # Handle summon priority from JSON string (HTMX form) or direct list (JSON API)
    summon_priority = data.get("summon_priority", [])
    if not summon_priority and data.get("summon_priority_json"):
        try:
            summon_priority = json.loads(data.get("summon_priority_json"))
        except (json.JSONDecodeError, TypeError):
            summon_priority = []

    task_config = {
        "turn": int(data.get("turn", 1) or 1),
        "refresh": _parse_bool_value(data.get("refresh", False)),
        "until_finish": _parse_bool_value(data.get("until_finish", False)),
        "trigger_skip": _parse_bool_value(data.get("trigger_skip", False)),
        "pre_fa": _parse_bool_value(data.get("pre_fa", False)),
        "min_hp_threshold": int(data.get("min_hp_threshold", 60) or 60),
        "max_hp_threshold": int(data.get("max_hp_threshold", 100) or 100),
        "min_people": int(data.get("min_people", 1) or 1),
        "max_people": int(data.get("max_people", 30) or 30),
        "summon_priority": summon_priority,
    }

    # Preserve existing actions if file already exists
    existing_actions = None
    if task_path.exists():
        try:
            with open(task_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing_actions = existing.get("actions")
        except Exception:
            pass

    task_def = {
        "task_type": data.get("task_type", "raid"),
        "raid_id": data.get("raid_id") or None,
        "task_config": task_config,
        "actions": existing_actions or [
            {"name": "refresh_raid_list", "params": {}, "transitions": {"success": "select_raid", "failed": "refresh_raid_list"}},
            {"name": "select_raid", "params": {"filter": "prefer_Lv100"}, "transitions": {"success": "select_summon", "failed": "refresh_raid_list"}},
            {"name": "select_summon", "params": {}, "transitions": {"success": "join_battle", "failed": "select_raid"}},
            {"name": "join_battle", "params": {}, "transitions": {"success": "do_battle", "failed": "select_raid"}},
            {"name": "do_battle", "params": {"mode": "full_auto"}, "transitions": {"success": "select_raid", "failed": "select_raid"}},
        ],
        "exit_condition": {"type": "raid_count", "value": int(data.get("amount", 10) or 10)},
    }

    try:
        with open(task_path, "w", encoding="utf-8") as f:
            json.dump(task_def, f, indent=2, ensure_ascii=False)
        return jsonify({"status": "ok", "filename": filename})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    threading.Thread(target=init_engine, daemon=True).start()
    app.run(debug=True, host="127.0.0.1", port=5000, threaded=True, use_reloader=False)
