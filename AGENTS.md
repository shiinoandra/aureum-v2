# AGENTS.md

## General Workflow and Guideline
1. Analyze project, read docs, understand tech stacks and requirements
2. Guide, assist, give feedback on code and implementation
3. Build-mode agents may edit code directly when explicitly authorized
4. After user implements, review and evaluate for correctness
5. Update AGENTS.md to document progress and design decisions
6. Suggest better approaches if needed
7. Thanks for the collaboration

## Project Overview

Browser automation project for automating Granblue Fantasy. Transformed from a single script (`hihihori3.py`) into a modular application with a Flask-based control UI.

## Technology Stack

- **Core**: Python (background automation)
- **UI**: Flask (minimalist web interface, local only)
- **Browser**: Selenium with undetected-chromedriver
- **Automation**: PyAutoGUI for human-like mouse movement
- **Real-time Updates**: Server-Sent Events (SSE)

## Architecture

```
RuntimeManager              ← 1 per app lifecycle. Owns queue, global config, navigator.
│                             Decides: start/stop scheduling, failure policy, captcha halt.
├── GlobalConfig            ← Truly global settings (think_time, etc.)
├── Navigator               ← Shared Selenium driver (NOT thread-safe, single thread only)
└── task_queue: deque[Task]
    │
    └── [dequeue] ──► TaskManager     ← 1 per running task. Owns task lifecycle.
            │                         Decides: when this task ends, retry logic,
            │                         post-raid logging, progress tracking.
            ├── Task                 ← Immutable definition: type, config, actions, exit_condition
            ├── TaskProgress         ← Mutable state: raids_completed, current_turn, status
            ├── TaskExecutor         ← Pure FSM runner. Decides: action transitions.
            │   └── ActionContext    ← Transient envelope per task. Holds refs only.
            └── DropLogger           ← Post-raid DOM parsing + SQLite drop_log writes
```

## Entry Point

**Flask is the main entry point.** Run:
```bash
python ui/app.py
```

This starts Flask on `http://127.0.0.1:5000` and launches the browser in a background thread. `src/main.py` remains as a legacy standalone entry point but is not the primary path.

## Data Flow & State Ownership

### Ownership Rules

| Layer | Owns | Does NOT Own |
|-------|------|--------------|
| **RuntimeManager** | Queue order, GlobalConfig, Navigator, start/stop of automation as a whole | Task-level progress, action transitions, exit conditions |
| **TaskManager** | Task lifecycle, TaskProgress, retry/backoff, drop logging hook, exit condition check | Queue order, other tasks' progress |
| **TaskExecutor** | FSM graph traversal, action-to-action transitions, popup detection between actions | Exit condition, progress counting, queue scheduling |
| **Actions** | DOM interaction, clicks, battle loop logic | Any state beyond `task_progress` writes |
| **ActionContext** | References to navigator + configs + progress | No logic, no lifecycle decisions |

### Who Writes What

| Field | Writer | Reader |
|-------|--------|--------|
| `GlobalConfig.think_time_*` | Flask `POST /api/save_task` (indirect) | Actions via `context.global_config` |
| `TaskConfig.*` | Task Creator → saved into task JSON | Actions via `context.task_config` |
| `TaskProgress.is_running` | `RuntimeManager._run_loop` | Flask SSE / API |
| `TaskProgress.current_state` | `TaskManager.run()` (URL detection) | Flask SSE / API |
| `TaskProgress.raids_completed` | `TaskManager._handle_post_cycle()` | Flask SSE / API |
| `TaskProgress.current_turn` | `action_do_battle` via `context.task_progress` | Flask SSE / API |
| `TaskProgress.raids_target` | `TaskManager` (from task JSON exit_condition) | Flask SSE / API |
| `TaskProgress.turn_target` | `TaskManager` (from `TaskConfig.turn`) | Flask SSE / API |

### Why This Design

- **Unidirectional data flow**: Actions write to TaskProgress → Flask reads from TaskManager snapshot
- **No singletons**: Everything is explicitly passed via constructor
- **Thread-safe**: `Navigator` is used by one thread only; `TaskProgress` is mutated only by `TaskManager`
- **Flask isolation**: Flask never touches `engine._running` or `ctx` directly

## Battle Flow (Raid)

```
1. refresh_raid_list → Refresh raid list to get latest raids
2. select_raid       → Browse list, filter by HP%, select raid
3. select_summon     → On summon screen, click OK (auto-preset)
4. join_battle       → Click start button to enter battle
5. do_battle         → Loop until conditions met:
   - task_config.turn turns reached, OR
   - task_config.until_finish=true loops until boss dies, OR
   - Boss dies early (battle ends automatically)
   - Writes current_turn and battle_finished to ActionContext / TaskProgress
6. Result screen     → Browser auto-shows when battle ends
7. Back to step 1   → Repeat for next raid (via TaskManager loop)
```

### do_battle Flow Detail

Each turn in battle:
1. Write `context.task_progress.current_turn = current_turn`
2. Click full auto button
3. Wait for attack button to appear (display-on)
4. Check if attack button is `display-off` (turn processing)
5. If `display-off`: turn completed
   - If `refresh=true`: refresh browser immediately, fullauto_clicked=0, next turn
   - If `refresh=false`: wait for attack button to reappear, fullauto_clicked=1, next turn
6. Click attack button (triggers full auto action sequence)
7. On battle end: `context.battle_finished = True`
8. `TaskManager._handle_post_cycle()` increments `task_progress.raids_completed` once
9. Loop until turn limit or boss dies

## Two-Layer System

### Task Layer (FSM-based)
Defines "what to do" using finite state machine with transitions.
- Actions have `transitions` dict mapping result → next action
- Example: `{"success": "select_summon", "failed": "refresh_raid_list"}`
- Actions return `RESULT_SUCCESS` or `RESULT_FAILED`
- `exit_condition` is task-level (how many raids to complete)
- **execute_task_cycle runs ONE raid cycle, then returns**
- If no `transitions` dict is defined, fallback to next action in list (linear workflow)

### State Machine Layer
Defines "where am I" - used for recovery when errors occur.
- Detects current state from URL
- Recovery: if error, detect current URL → decide next action
- **Actively updated during `TaskManager.run()`** via `detect_state(url)` each raid cycle

## State Design

States correspond to URL paths:

| State | URL Pattern | Description |
|-------|-------------|-------------|
| `IDLE` | - | No specific state |
| `MAIN_MENU` | `#mypage/*` | Home / mypage |
| `RAID_LIST` | `#quest/assist/*` | List of raids to join |
| `RAID_SUMMON_SELECT` | `#quest/supporter_raid/*` | Summon selection |
| `RAID_BATTLE` | `#raid_multi/*` | Inside raid battle |
| `RAID_RESULT` | `#result_multi/*` | Raid finished |
| `RAID_UNCLAIMED` | `#quest/assist/unclaimed/*` | Unclaimed results |
| `QUEST_SUMMON_SELECT` | `#quest/supporter/*` | Quest summon selection |
| `QUEST_BATTLE` | `#raid/*` | Inside quest battle |
| `QUEST_RESULT` | `#result/*` | Quest finished |
| `ERROR_RECOVERY` | - | Recovery mode |

## Task Definition

Tasks are defined in JSON files with FSM-based transitions.

### raid.json Example
```json
{
  "task_type": "raid",
  "task_config": {
    "turn": 1,
    "refresh": false,
    "until_finish": false,
    "trigger_skip": true,
    "pre_fa": false,
    "min_hp_threshold": 60,
    "max_hp_threshold": 100,
    "min_people": 1,
    "max_people": 30,
    "summon_priority": [
      {"name": "Titan", "level": "Lvl 250"},
      {"name": "Huanglong", "level": "Lvl 100"}
    ]
  },
  "actions": [
    {
      "name": "refresh_raid_list",
      "params": {},
      "transitions": {
        "success": "select_raid",
        "failed": "refresh_raid_list"
      }
    },
    {
      "name": "select_raid",
      "params": {"filter": "prefer_Lv100"},
      "transitions": {
        "success": "select_summon",
        "failed": "refresh_raid_list"
      }
    },
    {
      "name": "select_summon",
      "params": {},
      "transitions": {
        "success": "join_battle",
        "failed": "select_raid"
      }
    },
    {
      "name": "join_battle",
      "params": {},
      "transitions": {
        "success": "do_battle",
        "failed": "select_raid"
      }
    },
    {
      "name": "do_battle",
      "params": {"mode": "full_auto"},
      "transitions": {
        "success": "select_raid",
        "failed": "select_raid"
      }
    }
  ],
  "exit_condition": {"type": "raid_count", "value": 1000}
}
```

### Event Task Example (generated by Task Creator)
```json
{
  "task_type": "event",
  "task_config": {
    "turn": 1,
    "refresh": false,
    "until_finish": true,
    "summon_priority": []
  },
  "actions": [
    {"name": "go_to_url", "params": {"url": "https://game.granbluefantasy.jp/#quest/supporter/..."}},
    {"name": "select_summon", "params": {}},
    {"name": "join_battle", "params": {}},
    {"name": "do_battle", "params": {"mode": "full_auto"}}
  ],
  "exit_condition": {"type": "raid_count", "value": 10}
}
```

## Exit Conditions (Task-Level)

| Type | Value | Meaning |
|------|-------|---------|
| `raid_count` | Integer (e.g., 10) | Number of raids / battles to complete |
| `until_finish` | boolean | Stay until battle completes (for quests) |

**Note**: `turns` is NOT a task-level exit condition. Turns are:
- A **battle parameter** (`task_config.turn`) - controls per-battle turn limit
- Tracked in **`TaskProgress.current_turn`** during the battle loop

## Battle Parameters (Config-Level)

Battle parameters are **embedded in each task JSON** under `task_config`. Each task carries its own settings:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `turn` | int | 1 | Max turns per single battle |
| `refresh` | bool | true | Refresh browser after each turn |
| `until_finish` | bool | false | Loop until boss dies (ignore turn limit) |
| `trigger_skip` | bool | false | Skip boss entrance animation |
| `pre_fa` | bool | false | Click on-the-spot before battle starts |
| `min_hp_threshold` | int | 60 | Minimum HP % for raid selection |
| `max_hp_threshold` | int | 100 | Maximum HP % for raid selection |
| `min_people` | int | 1 | Minimum player count for raid selection |
| `max_people` | int | 30 | Maximum player count for raid selection |
| `summon_priority` | List[dict] | [] | Preferred support summons (name + optional level) |

### Persistence
`config/default.json` has been **eliminated**. Task JSONs in `tasks/` are the single source of truth. The Task Creator tab in the UI allows editing parameters and saving back to task JSONs.

## ActionContext

Passed to all actions. Contains:
- `navigator`: Navigator instance for browser interaction
- `global_config`: GlobalConfig (read-only, session-wide settings)
- `task_config`: TaskConfig (read-only, per-task battle settings)
- `task_progress`: TaskProgress (actions write progress here)
- `battle_finished`: Flag set when battle ends (transient, per-raid)
- `last_result`: Last action result for FSM transitions

### Result Constants
```python
class ActionContext:
    RESULT_SUCCESS = "success"
    RESULT_FAILED = "failed"
    RESULT_SKIP = "skip"
```

## Action Registry

Actions registered via decorator and return results:

```python
@ActionRegistry.register("action_name")
def action_function(params, context: ActionContext):
    # Do work...
    # Write progress: context.task_progress.raids_completed += 1
    return ActionContext.RESULT_SUCCESS
```

### Available Actions

| Action | Description | Transitions |
|--------|-------------|-------------|
| `select_raid` | Browse raid list, filter by HP%, select raid | success→select_summon, failed→refresh_raid_list |
| `select_summon` | Auto-detect preset summon | success→join_battle, failed→select_raid |
| `join_battle` | Click quest start button | success→do_battle, failed→select_raid |
| `do_battle` | Full auto loop | success/failed (follows transitions) |
| `refresh_raid_list` | Click refresh button | success→select_raid, failed→refresh_raid_list |
| `clean_raid_queue` | Process pending unclaimed raids | success/failed |
| `go_to_raid_list` | Navigate to `#quest/assist` | success |
| `go_to_main_menu` | Navigate to `#mypage/` | success |
| `go_to_url` | Navigate to arbitrary URL (quest/event) | success |

## Task Executor (FSM-based)

Task executor reads task JSON and executes actions based on transitions:

1. Start from first action in list
2. Execute action, get result
3. Look up transition for that result
4. Jump to next action (can loop back)
5. **When last action in list returns RESULT_SUCCESS, exit and return True**
6. If no transitions defined, fallback to next action in list (linear workflow)
7. Caller (TaskManager) checks exit condition

```python
def execute_task_cycle(self, actions: list) -> str:
    """
    Execute ONE task cycle through the action FSM.
    Returns: RESULT_SUCCESS or RESULT_FAILED
    """
    action_map = {a["name"]: a for a in actions}
    current_name = actions[0]["name"]

    while current_name:
        # Check popup, execute action, get result...
        
        # If last action AND result is SUCCESS, exit loop
        if action_def == actions[-1] and result == ActionContext.RESULT_SUCCESS:
            return ActionContext.RESULT_SUCCESS
        
        # Transition: explicit dict -> fallback next action
        if result in transitions:
            current_name = transitions[result]
        elif not transitions:
            # Linear workflow: move to next action
            current_idx = actions.index(action_def)
            if current_idx + 1 < len(actions):
                current_name = actions[current_idx + 1]["name"]
            else:
                return ActionContext.RESULT_SUCCESS
        ...
```

## Task Manager

Owns the lifecycle of a single Task:
- Tracks `TaskProgress` (raids_completed, current_turn, etc.)
- Runs `TaskExecutor` cycles until exit condition met
- Detects state between cycles
- Calls `DropLogger` on result screens
- Handles retry/backoff for transient failures

### Task Loop Flow
```
while not stopped:
    detect_state(url) -> task_progress.current_state
    reset_per_raid()
    task_progress.current_turn = 0
    
    # Execute ONE cycle
    result = task_executor.execute_task_cycle(actions)
    
    # Post-cycle hook
    if result == SUCCESS:
        if on result screen: drop_logger.capture()
        task_progress.raids_completed += 1
    
    # Check exit condition
    if task_progress.raids_completed >= target:
        return "completed"
```

## Popup Handling

Popups are handled centrally by `TaskExecutor.execute_task_cycle()` between actions.

### Internal Helper
`_check_and_handle_popup(nav)` - checks for popup, handles if present, returns popup type or None

### Popup Types
| Popup Text | Recovery Action |
|------------|----------------|
| "captcha" | Stop automation |
| "raid_full" | Refresh raid list |
| "not_enough_ap" | Wait and retry |
| "three_raid" | Wait before refreshing |
| "toomuch_pending" | Clean raid queue |
| "ended" | Skip to next raid |

### Stale Element Defense
`StaleElementReferenceException` is caught in `select_summon`, `join_battle`, `_check_and_handle_popup`, and `_check_and_handle_popup` to handle GBF's SPA transitions where elements go stale mid-poll. A 1.5s stabilization wait after `go_to_url` reduces race conditions.

## Navigator

Browser automation module handling Selenium + PyAutoGUI.

### Key Methods
- `get_current_url()`: Returns current browser URL
- `click_element(element, fast=False)`: Human-like click using bezier curves with scrollIntoView
- `_human_move(end_pos)`: Bezier curve mouse movement
- `_fast_move(end_pos)`: Linear mouse movement with overshoot
- `_move_away(element)`: Move mouse away from element center (radius-based randomness)
- `_move_away_from_point(center_x, center_y)`: Move mouse away from arbitrary coordinates (used by `click_onthespot`)
- `get_element_rect(element)`: Get element position/size
- `refresh()`: Browser refresh
- `wait(min_time, max_time)`: Random human-like delays
- `wait_for_element(by, selector, timeout)`: Wait for element
- `wait_for_clickable(by, selector, timeout)`: Wait for clickable element
- `click_onthespot()`: Click at current mouse position after a short delay, then 50% chance to `_move_away_from_point`

### Click Element Behavior
1. `scrollIntoView({block: 'center', inline: 'nearest'})` - bring element into view
2. Random scroll offset `(-20 to +20)` - humans rarely stop perfectly aligned
3. Small pause as if to locate element
4. Calculate element center with sigma-based offset (10% of element size)
5. Move mouse using bezier curve (or fast linear for `fast=True`)
6. 1-2 tiny correction movements
7. Variable hold click (0.03-0.08s)
8. 50% chance to move away from element after click

## Flask UI

HTTP endpoints for UI↔core communication:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main control panel (HTMX dashboard) |
| `/creator` | GET | Task creator page |
| `/history` | GET | Task history page |
| `/api/status` | GET | Engine ready state + any init error |
| `/api/list_tasks` | GET | Return all `.json` filenames in `tasks/` |
| `/api/task/<name>` | GET | Load a specific task JSON by name |
| `/api/enqueue` | POST | Add `{task_name, amount}` to runtime queue |
| `/api/queue` | GET | Return current queue state |
| `/api/sync_queue` | POST | Replace entire queue with client state |
| `/api/remove_from_queue` | POST | Remove task at index from queue |
| `/api/reorder_queue` | POST | Reorder queue items (up/down arrows) |
| `/api/clear_queue` | POST | Clear entire queue |
| `/api/start` | POST | Start runtime if queue non-empty |
| `/api/stop` | POST | Stop runtime (queue preserved) |
| `/api/pause` | POST | Pause runtime at next boundary |
| `/api/resume` | POST | Resume from paused state |
| `/api/progress` | GET | Running status + progress + queue |
| `/api/events` | GET | **SSE stream** for live progress updates |
| `/api/history` | GET | Paginated task history JSON |
| `/api/history/<id>/drops` | GET | Drop logs for a task history entry |
| `/api/discover_event` | POST | Scan event URL, return discovered battles |
| `/api/save_task` | POST | Write task JSON to `tasks/` directory |
| `/htmx/status` | GET | Status header partial |
| `/htmx/queue` | GET | Queue panel partial |
| `/htmx/task-preview` | GET | Task preview partial |
| `/htmx/raid-card` | GET | Current raid card partial |
| `/htmx/creator-load` | GET | Creator form partial |
| `/htmx/raid-grid/<category>` | GET | Raid grid partial |
| `/htmx/content-list/<type>` | GET | Paginated event/quest list partial |
| `/htmx/history-table` | GET | History table partial |

### Real-Time Updates (SSE)
A background thread (`_progress_monitor`) pushes `TaskProgress` snapshots + queue state to all connected SSE clients every 500ms. The frontend auto-reconnects on disconnect.

### Start/Stop Control Flow
1. User adds tasks to queue via **Main** tab → `POST /api/enqueue`
2. User clicks **Start** → `POST /api/start` → `runtime.start()`
3. `RuntimeManager` spawns daemon thread, dequeues tasks sequentially
4. `is_running` becomes `True`; SSE pushes updates
5. User clicks **Stop** → `POST /api/stop` → `runtime.stop()` + queue.clear()
6. Loop exits at next boundary; UI shows **Start** button

## Project Structure

```
/home/shiinoandra/new_aureum/
├── AGENTS.md              # This file
├── docs/
│   ├── ROADMAP.md         # Feature roadmap (P0-P9)
│   └── PARAMETERS.md      # Battle parameter documentation
├── hihihori3.py           # Original reference script
├── requirements.txt       # Python dependencies
├── setup_xwayland.py      # One-time XAuthority setup for Wayland
├── tasks/                 # Self-contained task JSONs (single source of truth)
│   ├── raid.json          # Raid task definition
│   ├── quest.json         # Quest task definition
│   └── *.json             # Generated event tasks
├── data/                  # Runtime data (gitignored)
│   ├── aureum.db          # SQLite database
│   └── queue.json         # Persistent queue state
├── src/
│   ├── __init__.py
│   ├── main.py            # Legacy standalone entry point
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── global_config.py
│   │   ├── runtime_manager.py
│   │   └── queue_persistence.py
│   ├── task/
│   │   ├── __init__.py
│   │   ├── task.py
│   │   ├── task_progress.py
│   │   ├── task_manager.py
│   │   └── task_executor.py
│   ├── action/
│   │   ├── __init__.py
│   │   ├── action_context.py
│   │   ├── action_registry.py
│   │   └── actions.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── state_machine.py
│   │   └── drop_logger.py
│   └── infra/
│       ├── __init__.py
│       ├── navigator.py
│       ├── bezier_compat.py
│       └── database.py
└── ui/
    ├── app.py             # Flask web interface (main entry point)
    ├── static/
    │   ├── css/
    │   │   └── all.min.css        # Local Font Awesome CSS
    │   └── webfonts/
    │       ├── fa-solid-900.woff2
    │       ├── fa-regular-400.woff2
    │       └── fa-brands-400.woff2
    └── templates/
        ├── base.html              # Jinja base layout (HTMX + Tailwind + SSE)
        ├── index.html             # Legacy vanilla JS page (backup)
        ├── pages/
        │   ├── dashboard.html     # Main control panel
        │   ├── task_creator.html  # Task creator + event generator
        │   └── history.html       # Task history table
        └── partials/
            ├── status_header.html
            ├── queue.html
            ├── task_preview.html
            ├── raid_card.html
            ├── creator_form.html
            ├── raid_grid.html
            ├── content_list.html
            └── history_table.html
```

## Original Script Reference (hihihori3.py)

The `hihihori3.py` contains reference implementations:
- **NavigationHelper**: Click with bezier curves, scrollIntoView adjustment
- **BattleHelper**: Summon selection, battle joining, full auto battle
- **RaidHelper**: Raid picking (HP filter), popup handling, raid cleanup, HTML drop logging
- **gwHelper**: Guild war battle with popup handling
- **freeQuestHelper**: Free quest automation

---

## Key Design Decisions

### Task = Self-Contained Unit

A `Task` carries its own config AND exit condition. RuntimeManager treats them as opaque units — it does not know what a "raid" is.

### No Singletons

`ConfigManager` (singleton) was deleted. Replaced by:
- `GlobalConfig` — owned by RuntimeManager
- `TaskConfig` — owned by Task
- `TaskProgress` — owned by TaskManager

This makes testing possible and removes hidden global state.

### Single Automation Thread

Selenium WebDriver is **not thread-safe**. All automation runs in one daemon thread spawned by RuntimeManager. There is NO background observer thread for state detection.

State detection happens:
- Between raids (in `TaskManager.run()` loop) — safe, browser is stable
- During battle via `task_progress.current_state` writes from `do_battle` — write-only, no polling

### Failure Policy

| Failure Type | Behavior |
|--------------|----------|
| Action execution stuck / element not found | Task returns `"failed"`. RuntimeManager dequeues next task. |
| Network error | TaskManager retries N times. If exhausted, returns `"network_failed"`. RuntimeManager halts entire queue and notifies user. |
| CAPTCHA detected | TaskManager returns `"captcha"`. RuntimeManager hard-stops, clears entire queue, notifies user. |
| User clicks Stop | Cooperative stop at next boundary. Current task returns `"stopped"`. Queue remains for resume. |

### Drop Logging Hook

After every successful raid cycle, TaskManager checks the URL. If on a result screen (`#result_multi/*` or `#result/*`), it calls `DropLogger.capture(driver, raid_id, raid_name)`. This parses `.prt-item-list` and `.lis-treasure.btn-treasure-item` elements to extract item names, counts, and image URLs, then writes to the SQLite `drop_log` table linked to the current `task_history` row.

This is based on `hihihori3.py`'s `log_raid_results()`. DB errors during logging are caught and logged; automation continues unaffected.

### Per-Task Config Overrides

Because each `Task` carries its own `TaskConfig`, you can queue different tasks with different settings without changing global defaults:
```python
runtime.enqueue_task(Task(type="raid", task_config=TaskConfig(turn=1, refresh=True)))
runtime.enqueue_task(Task(type="raid", task_config=TaskConfig(turn=3, refresh=False)))
```

---

## Thread Safety

- `Navigator` (Selenium driver) is used by **one thread only** — the automation daemon thread
- `TaskProgress` is mutated only by `TaskManager` in that same thread
- Flask endpoints read `TaskProgress` fields directly; since Python dict reads are atomic and the automation thread only writes during its own loop, this is safe for UI display purposes
- If stricter consistency is needed later, add a `threading.Lock` around `TaskProgress` writes and Flask snapshot reads

---

## Migration Summary

| Old File | New File(s) | Reason |
|----------|-------------|--------|
| `config_manager.py` | `runtime/global_config.py` + `task/task_config.py` + `task/task_progress.py` | Split confused singleton into focused dataclasses |
| `core_engine.py` | `runtime/runtime_manager.py` + `task/task_manager.py` | Separated queue scheduling from task lifecycle |
| `task_executor.py` | `task/task_executor.py` | Stripped of exit condition logic; pure FSM only |
| `context.py` | `action/action_context.py` + `action/action_registry.py` | Split envelope from registry |
| `actions.py` | `action/actions.py` | Updated `context.config.xxx` → `context.task_progress.xxx` |
| `state_machine.py` | `domain/state_machine.py` | Domain-layer placement |
| `navigator.py` | `infra/navigator.py` | Infrastructure-layer placement |

---

## Benefits of This Design

1. **Clear ownership**: No more "who owns `raids_completed`?" — TaskManager owns TaskProgress.
2. **Queue support**: You can queue 100 raids then 50 quests without restarting the app.
3. **Per-task configs**: Different tasks can run with different battle settings.
4. **Testability**: TaskExecutor can be unit-tested with a mocked Navigator and fake ActionContext.
5. **No hidden global state**: Everything is explicitly passed via constructor.
6. **Extensible logging**: DropLogger is a clean hook; future analytics just plug into TaskManager.
7. **Failure isolation**: One bad task doesn't kill the queue (unless it's captcha).
8. **No threading hell**: Single automation thread avoids Selenium race conditions entirely.
