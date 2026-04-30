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


## need checking
the done in json is not updated realtime
reproduce case
add 10 x event -> do for 3 times ->stop -->refresh browse->correct
from refresh browser (now status is done:3 )->resume for 3 more steps (should be 6/10 now) ->stop--> change target from 10 to 12-->r resume it will start again from 3 like it read from the json

task should have unique identifier -> in history tab a same task that is stopped and resumed is treated as differetn task
reproduce example : add 10x event battle to queue -> do it for 3 times ->stop ->check history tab
there will be entry with status stopped with target 10 and completed 3
now start again the same task do it for 3 more times (now should be 6/10)->stop it-> check histroy tabn now it will add another entry that says 6 completed 10 target. it should update the first entry as it referes to same ttaask not add another entry
other than that seems fine for now
