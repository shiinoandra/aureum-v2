# AGENTS.md

## General Workflow and Guideline
1. Analyze project, read docs, understand tech stacks and requirements
2. Guide, assist, give feedback on code and implementation
3. **CANNOT edit code directly** (plan mode) — provide snippets for user to implement
4. Build-mode agents may edit code directly when explicitly authorized
5. After user implements, review and evaluate for correctness
6. Update AGENTS.md to document progress and design decisions
7. Suggest better approaches if needed
8. Thanks for the collaboration

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
┌─────────────────────────────────────────────────────────────────┐
│                         UI Layer                                 │
│            (Vanilla JS + HTML, SSE client)                       │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTP / SSE
┌─────────────────────────▼───────────────────────────────────────┐
│                    Flask (ui/app.py)                             │
│  - Owns CoreEngine + Navigator                                   │
│  - /api/start, /api/stop, /api/config, /api/progress            │
│  - /api/events (SSE)                                             │
└─────────────────────────┬───────────────────────────────────────┘
                          │ reads / writes
┌─────────────────────────▼───────────────────────────────────────┐
│              ConfigManager (Thread-safe Singleton)               │
│  ┌─────────────────────┐    ┌─────────────────────────────────┐ │
│  │   BattleConfig      │    │      RuntimeState               │ │
│  │  (static settings)  │    │  (live automation state)        │ │
│  │  - turn, refresh    │    │  - is_running                   │ │
│  │  - until_finish     │    │  - current_state                │ │
│  │  - think_time_*     │    │  - raids_completed / target     │ │
│  │  - summon_priority  │    │  - current_turn / target        │ │
│  │  - min/max hp & ppl │    │  - last_known_url               │ │
│  └─────────────────────┘    └─────────────────────────────────┘ │
└──────────┬──────────────────────────────┬───────────────────────┘
           │ writes                       │ writes
           ▼                              ▼
┌───────────────────────┐    ┌───────────────────────────────┐
│     Task Executor      │    │      State Machine            │
│  (FSM-based flow)      │    │   (recovery & detection)      │
│  - task definition     │    │   - detect state from URL    │
│  - action registry     │    │   - recovery handlers        │
│  - transitions        │    │   - state transitions        │
└───────────┬───────────┘    └───────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Core Engine                                 │
│              (Task execution + state management)                │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                    Navigator                                     │
│         (Browser automation: Selenium + PyAutoGUI)                │
└─────────────────────────────────────────────────────────────────┘
```

## Entry Point

**Flask is the main entry point.** Run:
```bash
python ui/app.py
```

This starts Flask on `http://127.0.0.1:5000` and launches the browser in a background thread. `src/main.py` remains as a legacy standalone entry point but is not the primary path.

## Data Flow & State Ownership

### Single Source of Truth: ConfigManager

`ConfigManager` is a thread-safe singleton that owns **all** data crossing the automation/UI boundary. It is divided into two dataclasses:

| Dataclass | Purpose | Thread Lock | Persisted |
|-----------|---------|-------------|-----------|
| `BattleConfig` | Static user settings (turn, refresh, etc.) | `_config_lock` | Yes → `config/default.json` |
| `RuntimeState` | Live automation state (progress, is_running, etc.) | `_runtime_lock` | No (in-memory only) |

### Who Writes What

| Field | Writer | Reader |
|-------|--------|--------|
| `BattleConfig.*` | Flask `POST /api/config` | Actions via `get_battle_config()` |
| `RuntimeState.is_running` | `CoreEngine._run_task_loop` | Flask SSE / API |
| `RuntimeState.current_state` | `CoreEngine._run_task_loop` (URL detection) | Flask SSE / API |
| `RuntimeState.raids_completed` | `action_do_battle` via `context.config` | Flask SSE / API |
| `RuntimeState.current_turn` | `action_do_battle` via `context.config` | Flask SSE / API |
| `RuntimeState.raids_target` | `CoreEngine._run_task_loop` (from task JSON) | Flask SSE / API |
| `RuntimeState.turn_target` | `CoreEngine._run_task_loop` (from `BattleConfig.turn`) | Flask SSE / API |

### ActionContext (Transient FSM State Only)

`ActionContext` now holds **only** per-raid-cycle transient state:
- `navigator`: Navigator instance
- `config`: ConfigManager singleton (for writing progress directly)
- `battle_finished`: Flag set when battle ends
- `last_result`: Last action result for transition logic

**Removed from ActionContext:** `current_turn` and `raids_completed` — these now live in `ConfigManager.RuntimeState`.

### Why This Design

- **Unidirectional data flow**: Actions write to ConfigManager → Flask reads from ConfigManager
- **No sync step**: `CoreEngine` no longer copies `ctx.raids_completed → config.raids_completed`
- **Thread-safe**: All UI-visible state is protected by `_runtime_lock`
- **Flask isolation**: Flask never touches `engine._running` or `ctx` directly

## Battle Flow (Raid)

```
1. refresh_raid_list → Refresh raid list to get latest raids
2. select_raid       → Browse list, filter by HP%, select raid
3. select_summon     → On summon screen, click OK (auto-preset)
4. join_battle       → Click start button to enter battle
5. do_battle         → Loop until conditions met:
   - config.turn turns reached, OR
   - config.until_finish=true loops until boss dies, OR
   - Boss dies early (battle ends automatically)
   - Writes current_turn and raids_completed directly to ConfigManager
6. Result screen     → Browser auto-shows when battle ends
7. Back to step 1   → Repeat for next raid (via core_engine loop)
```

### do_battle Flow Detail

Each turn in battle:
1. Write `context.config.current_turn = current_turn`
2. Click full auto button
3. Wait for attack button to appear (display-on)
4. Check if attack button is `display-off` (turn processing)
5. If `display-off`: turn completed
   - If `refresh=true`: refresh browser immediately, fullauto_clicked=0, next turn
   - If `refresh=false`: wait for attack button to reappear, fullauto_clicked=1, next turn
6. Click attack button (triggers full auto action sequence)
7. On battle end: `context.config.raids_completed += 1`
8. Loop until turn limit or boss dies

## Two-Layer System

### Task Layer (FSM-based)
Defines "what to do" using finite state machine with transitions.
- Actions have `transitions` dict mapping result → next action
- Example: `{"success": "select_summon", "failed": "refresh_raid_list"}`
- Actions return `RESULT_SUCCESS` or `RESULT_FAILED`
- `exit_condition` is task-level (how many raids to complete)
- **execute_task runs ONE raid cycle, then returns**

### State Machine Layer
Defines "where am I" - used for recovery when errors occur.
- Detects current state from URL
- Recovery: if error, detect current URL → decide next action
- **Actively updated during `_run_task_loop`** via `detect_state(url)` each raid cycle

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
  "exit_condition": {"type": "raid_count", "value": 10}
}
```

## Exit Conditions (Task-Level)

| Type | Value | Meaning |
|------|-------|---------|
| `raid_count` | Integer (e.g., 10) | Number of raids to complete |
| `until_finish` | boolean | Stay until battle completes (for quests) |

**Note**: `turns` is NOT a task-level exit condition. Turns are:
- A **battle parameter** (`config.turn`) - controls per-battle turn limit
- Tracked in **`RuntimeState.current_turn`** during the battle loop

## Battle Parameters (Config-Level)

Used inside `do_battle` action, read from `config/default.json`:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `turn` | int | 1 | Max turns per single battle |
| `refresh` | bool | true | Refresh browser after each turn |
| `until_finish` | bool | false | Loop until boss dies (ignore turn limit) |
| `trigger_skip` | bool | false | Skip boss entrance animation |
| `think_time_min` | float | 0.2 | Min delay between actions |
| `think_time_max` | float | 0.5 | Max delay between actions |
| `pre_fa` | bool | false | Click on-the-spot before battle starts |
| `min_hp_threshold` | int | 60 | Minimum HP % for raid selection |
| `max_hp_threshold` | int | 100 | Maximum HP % for raid selection |
| `min_people` | int | 1 | Minimum player count for raid selection |
| `max_people` | int | 30 | Maximum player count for raid selection |
| `summon_priority` | List[dict] | [] | Preferred support summons (name + optional level) |

### Persistence
`POST /api/config` updates `BattleConfig` **and immediately writes back** to `config/default.json`. This makes the JSON file the single source of truth that survives restarts.

## ActionContext

Passed to all actions. Contains:
- `navigator`: Navigator instance for browser interaction
- `config`: ConfigManager singleton (actions write progress directly here)
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
    # Write progress: context.config.raids_completed += 1
    return ActionContext.RESULT_SUCCESS
```

### Available Actions

| Action | Description | Transitions |
|--------|-------------|-------------|
| `select_raid` | Browse raid list, filter by HP%, select raid | success→select_summon, failed→refresh_raid_list |
| `select_summon` | Auto-detect preset summon | success→join_battle, failed→select_raid |
| `join_battle` | Click quest start button | success→do_battle, failed→select_raid |
| `do_battle` | Full auto loop, writes to `config.raids_completed` | success/failed (follows transitions) |
| `refresh_raid_list` | Click refresh button | success→select_raid, failed→refresh_raid_list |
| `clean_raid_queue` | Process pending unclaimed raids | success/failed |
| `go_to_raid_list` | Navigate to `#quest/assist` | success |
| `go_to_main_menu` | Navigate to `#mypage/` | success |

## Task Executor (FSM-based)

Task executor reads task JSON and executes actions based on transitions:

1. Start from first action in list
2. Execute action, get result
3. Look up transition for that result
4. Jump to next action (can loop back)
5. **When last action in list returns RESULT_SUCCESS, exit and return True**
6. Caller (core_engine) checks exit condition

```python
def execute_task(self, task: dict) -> bool:
    """
    Execute ONE raid cycle.
    
    Returns:
        True - task cycle completed successfully
        False - stopped early (error/captcha)
    """
    actions = task.get("actions", [])
    action_map = {a["name"]: a for a in actions}
    current_name = actions[0]["name"]

    while current_name and self._running:
        # Check popup, execute action, get result...
        
        # If last action AND result is SUCCESS, exit loop
        if action_def == actions[-1] and result == ActionContext.RESULT_SUCCESS:
            return True
        
        # Otherwise, follow transitions to next action
        ...
```

### Exit Condition Check
```python
def check_exit_condition(self, task: dict) -> bool:
    exit_cond = task.get("exit_condition")
    cond_type = exit_cond.get("type")
    cond_value = exit_cond.get("value")
    
    if cond_type == "raid_count":
        return self.config.raids_completed >= cond_value
    elif cond_type == "until_finish":
        return self.context.battle_finished
    return False
```

## Core Engine

The `CoreEngine` orchestrates:
- `start()`: Legacy main loop (not used when Flask owns the engine)
- `start_task(task_path)`: Loads and runs task in background thread
- `_run_task_loop()`: Repeatedly calls execute_task until exit condition met
- `_main_loop()`: Detects state from URL, handles recovery (legacy standalone path)

### Task Loop Flow
```
while running and task:
    # State detection & runtime stats
    config.last_known_url = navigator.get_current_url()
    config.current_state = detect_state(url)
    config.turn_target = config.get_battle_config().turn
    config.raids_target = task.exit_condition.value
    
    # Reset transient state
    task_executor.context.reset()
    config.current_turn = 0
    
    # Execute ONE raid cycle
    execute_task()
    
    if not result:     # Error/captcha
        break
    if check_exit_condition():  # config.raids_completed >= target?
        break
    # Continue to next raid
```

## Popup Handling

Popups are handled centrally by `task_executor.execute_task()` between actions.

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

## Navigator

Browser automation module handling Selenium + PyAutoGUI.

### Key Methods
- `get_current_url()`: Returns current browser URL
- `click_element(element, fast=False)`: Human-like click using bezier curves with scrollIntoView
- `_human_move(end_pos)`: Bezier curve mouse movement
- `_fast_move(end_pos)`: Linear mouse movement with overshoot
- `get_element_rect(element)`: Get element position/size
- `refresh()`: Browser refresh
- `wait(min_time, max_time)`: Random human-like delays
- `wait_for_element(by, selector, timeout)`: Wait for element
- `wait_for_clickable(by, selector, timeout)`: Wait for clickable element
- `click_onthespot()`: Click at current mouse position after a short delay

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
| `/` | GET | Main control panel |
| `/api/status` | GET | Engine ready state + any init error |
| `/api/config` | GET | Get current `BattleConfig` + `RuntimeState` snapshot |
| `/api/config` | POST | Update `BattleConfig` **and persist to `default.json`** |
| `/api/progress` | GET | Running status + progress (reads `RuntimeState`) |
| `/api/start` | POST | Start automation task (reads `task_type` from JSON body) |
| `/api/stop` | POST | Stop automation gracefully (cooperative) |
| `/api/events` | GET | **SSE stream** for live progress updates |

### Real-Time Updates (SSE)
A background thread (`_progress_monitor`) pushes `RuntimeState` snapshots to all connected SSE clients every 500ms. The frontend auto-reconnects on disconnect.

### Start/Stop Control Flow
1. User clicks **Start** → `POST /api/start` → `engine.start_task(path)`
2. `CoreEngine` spawns daemon thread running `_run_task_loop()`
3. `RuntimeState.is_running` becomes `True`
4. SSE pushes updates; UI shows **Stop** button
5. User clicks **Stop** → `POST /api/stop` → `engine.stop()`
6. `_running` flags set to `False`; loop exits at next boundary
7. `RuntimeState.is_running` becomes `False`; UI shows **Start** button

## Project Structure

```
/home/shiinoandra/new_aureum/
├── AGENTS.md              # This file
├── docs/
│   └── PARAMETERS.md      # Battle parameter documentation
├── hihihori3.py           # Original reference script
├── requirements.txt       # Python dependencies
├── tasks/
│   ├── raid.json          # Raid task definition (FSM-based)
│   └── quest.json         # Quest task definition
├── config/
│   └── default.json       # Global default parameters (auto-persisted)
├── src/
│   ├── __init__.py
│   ├── config_manager.py  # Thread-safe singleton: BattleConfig + RuntimeState
│   ├── context.py         # ActionContext (transient FSM) & ActionRegistry
│   ├── core_engine.py     # Battle orchestration
│   ├── navigator.py       # Browser automation
│   ├── state_machine.py   # State detection
│   ├── task_executor.py   # FSM-based task execution
│   └── actions.py         # All registered actions
└── ui/
    ├── app.py             # Flask web interface (main entry point)
    └── templates/         # HTML templates
        └── index.html
```

## Original Script Reference (hihihori3.py)

The `hihihori3.py` contains reference implementations:
- **NavigationHelper**: Click with bezier curves, scrollIntoView adjustment
- **BattleHelper**: Summon selection, battle joining, full auto battle
- **RaidHelper**: Raid picking (HP filter), popup handling, raid cleanup
- **gwHelper**: Guild war battle with popup handling
- **freeQuestHelper**: Free quest automation
