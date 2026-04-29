# Aureum v2

Browser automation for Granblue Fantasy, built with Python, Selenium, and Flask.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# (Linux/Wayland only) Set up XAuthority for PyAutoGUI
python setup_xwayland.py

# Run the Flask UI (main entry point)
python ui/app.py
```

Then open `http://127.0.0.1:5000` in your browser.

## What It Does

Aureum automates repetitive gameplay loops in Granblue Fantasy:
- **Raid farming**: Join public raids, execute a set number of turns, then hop to the next one
- **Quest battles**: Start your own quests and run them to completion
- **Event battles**: Scan event pages, generate task JSONs, and farm event quests
- **Human-like interaction**: Bezier-curve mouse movement, randomized delays, scroll adjustments

## Architecture

- **Flask** serves the control panel and exposes a REST API + SSE stream
- **RuntimeManager** owns the task queue, global config, and automation lifecycle
- **TaskManager** owns per-task progress, exit conditions, and drop logging
- **TaskExecutor** drives an FSM-based action pipeline defined in JSON task files
- **Task Creator** (UI tab) allows editing battle parameters and generating event task JSONs
- **Navigator** handles Selenium + PyAutoGUI browser interaction
- **SQLite** stores task history and drop logs

Each task JSON is **self-contained** and embeds its own `task_config` (turn, refresh, summon priority, etc.).
There is no global `config/default.json` — task files in `tasks/` are the single source of truth.

See `AGENTS.md` for full architecture documentation.

## UI

The control panel uses **HTMX + Jinja2 + Tailwind CSS** with **Server-Sent Events** for live updates.

### Tabs
- **Main** — Queue management, task selector, content picker (raid/event/quest), live raid card
- **Task Creator** — Edit battle parameters, scan events, generate task JSONs
- **History** — View past task runs with completion counts, durations, and drop logs

## Key Features

| Feature | Status |
|---------|--------|
| Queue-based task execution | ✅ |
| Queue persistence (`data/queue.json`) | ✅ |
| Pause / Resume | ✅ |
| Task history logging (SQLite) | ✅ |
| Drop logging (SQLite) | ✅ |
| HTMX server-rendered UI | ✅ |
| Real-time SSE progress updates | ✅ |
| Event discovery / task generation | ✅ |
| Local Font Awesome (no CDN dependency) | ✅ |

## Legacy Entry Point

`src/main.py` still works as a standalone CLI entry point, but it is no longer the primary path.

## Tech Stack

- Python 3
- Flask (web UI)
- Selenium + undetected-chromedriver (browser automation)
- PyAutoGUI + pure-Python bezier (human-like mouse movement)
- SQLite (task history, drop logs, knowledge base)
