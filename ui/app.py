from flask import Flask, render_template, request, jsonify, Response
import sys
import os
import json
import queue
import threading
import time

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, 'src')

from src.config_manager import ConfigManager
from src.navigator import Navigator
from src.core_engine import CoreEngine
from src.state_machine import detect_state
import undetected_chromedriver as uc

app = Flask(__name__)
config = ConfigManager()
# --- Globals ---
engine = None
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
    os.makedirs(user_data_dir, exist_ok=True)
    driver = uc.Chrome(
        options=chrome_options, user_data_dir=user_data_dir, version_main=146
    )
    return driver


def init_engine():
    global engine, engine_ready, engine_error
    try:
        driver = create_browser()
        driver.get("https://game.granbluefantasy.jp/")
        navigator = Navigator(driver)
        engine = CoreEngine(navigator)
        project_root = __import__("pathlib").Path(__file__).parent.parent
        config_path = project_root / "config" / "default.json"
        if config_path.exists():
            config.load_default_config(config_path)
        # Start background progress pusher
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
        if engine:
            ctx = engine.task_executor.context
            url = getattr(config, "last_known_url", "")
            state = detect_state(url).value if url else config.current_state.value
            payload = {
                "is_running": getattr(config, "is_running", False),
                "current_state": state,
                "raids_completed": ctx.raids_completed,
                "raids_target": getattr(config, "raids_target", 0),
                "current_turn": ctx.current_turn,
                "turn_target": getattr(config, "turn_target", 0),
            }
            announcer.announce(json.dumps(payload))
        time.sleep(0.5)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify({"ready": engine_ready, "error": engine_error})


@app.route("/api/config", methods=["GET"])
def get_config():
    battle_config = config.get_battle_config()
    return jsonify(
        {
            "turn": battle_config.turn,
            "refresh": battle_config.refresh,
            "until_finish": battle_config.until_finish,
            "trigger_skip": battle_config.trigger_skip,
            "think_time_min": battle_config.think_time_min,
            "think_time_max": battle_config.think_time_max,
            "summon_priority": battle_config.summon_priority,
            "current_state": config.current_state.value,
            "is_running": getattr(config, "is_running", False),
            "raids_completed": getattr(config, "raids_completed", 0),
            "raids_target": getattr(config, "raids_target", 0),
        }
    )


@app.route("/api/config", methods=["POST"])
def update_config():
    data = request.json
    config.update_battle_config(**data)
    return jsonify({"status": "ok", "updated": data})


@app.route("/api/start", methods=["POST"])
def start_task():
    global engine_ready
    if not engine_ready:
        return jsonify({"status": "error", "message": "Engine not ready yet"}), 503
    if engine._running:
        return jsonify({"status": "error", "message": "Already running"}), 409
    task_type = request.json.get("task_type", "raid")
    project_root = __import__("pathlib").Path(__file__).parent.parent
    task_path = project_root / "tasks" / f"{task_type}.json"
    if not task_path.exists():
        return jsonify(
            {"status": "error", "message": f"Task {task_type} not found"}
        ), 404
    engine.start_task(task_path)
    return jsonify({"status": "started", "task_type": task_type})


@app.route("/api/stop", methods=["POST"])
def stop_task():
    if engine:
        engine.stop()
    return jsonify({"status": "stopped"})


@app.route("/api/progress", methods=["GET"])
def get_progress():
    url = getattr(config, "last_known_url", "")
    state = detect_state(url).value if url else config.current_state.value
    ctx = engine.task_executor.context if engine else None
    return jsonify(
        {
            "is_running": getattr(config, "is_running", False),
            "current_state": state,
            "raids_completed": ctx.raids_completed if ctx else 0,
            "raids_target": getattr(config, "raids_target", 0),
            "current_turn": ctx.current_turn if ctx else 0,
            "turn_target": getattr(config, "turn_target", 0),
        }
    )


@app.route("/api/events")
def sse():
    def stream():
        for msg in announcer.listen():
            yield f"data: {msg}\n\n"

    return Response(stream(), mimetype="text/event-stream")


if __name__ == "__main__":
    # Initialize browser in background so Flask can start serving immediately
    threading.Thread(target=init_engine, daemon=True).start()
    app.run(debug=True, host="127.0.0.1", port=5000, threaded=True, use_reloader=False)
