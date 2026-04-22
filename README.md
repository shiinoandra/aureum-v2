# Aureum v2

Browser automation for Granblue Fantasy, built with Python, Selenium, and Flask.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the Flask UI (main entry point)
python ui/app.py
```

Then open `http://127.0.0.1:5000` in your browser.

## What It Does

Aureum automates repetitive gameplay loops in Granblue Fantasy:
- **Raid farming**: Join public raids, execute a set number of turns, then hop to the next one
- **Quest battles**: Start your own quests and run them to completion
- **Human-like interaction**: Bezier-curve mouse movement, randomized delays, scroll adjustments

## Architecture

- **Flask** serves the control panel and exposes a REST API + SSE stream
- **ConfigManager** (singleton) holds all shared state between the automation thread and the UI
- **CoreEngine** runs the task loop in a background daemon thread
- **TaskExecutor** drives an FSM-based action pipeline defined in JSON task files
- **Navigator** handles Selenium + PyAutoGUI browser interaction

See `AGENTS.md` for full architecture documentation.

## Legacy Entry Point

`src/main.py` still works as a standalone CLI entry point, but it is no longer the primary path.

## Tech Stack

- Python 3
- Flask (web UI)
- Selenium + undetected-chromedriver (browser automation)
- PyAutoGUI + bezier (human-like mouse movement)
