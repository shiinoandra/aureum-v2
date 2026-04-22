# AGENTS.md

## General Workflow and Guideline
1. Analyze project, read docs, understand tech stacks and requirements
2. Guide, assist, give feedback on code and implementation
3. **CANNOT edit code directly** - provide snippets for user to implement
4. After user implements, review and evaluate for correctness
5. Update AGENTS.md to document progress and design decisions
6. Suggest better approaches if needed
7. Thanks for the collaboration

## Project Overview

Browser automation project for automating Granblue Fantasy. Transformed from a single script (`hihihori3.py`) into a modular application.

## Technology Stack

- **Core**: Python (background automation)
- **UI**: Flask (minimalist web interface, local only)
- **Browser**: Selenium with undetected-chromedriver
- **Automation**: PyAutoGUI for human-like mouse movement

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         UI Layer                                 │
│                    (Flask - local only)                          │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTP / Events
┌─────────────────────────▼───────────────────────────────────────┐
│                    Config Manager                                │
│            (Thread-safe singleton: state + params)              │
└─────────────────────────┬───────────────────────────────────────┘
                          │
        ┌─────────────────┴─────────────────┐
        ▼                                   ▼
┌───────────────────────┐     ┌───────────────────────────────┐
│     Task Executor      │     │      State Machine            │
│  (FSM-based flow)    │     │   (recovery & detection)      │
│  - task definition    │     │   - detect state from URL    │
│  - action registry    │     │   - recovery handlers        │
│  - transitions       │     │   - state transitions        │
└───────────┬───────────┘     └───────────────────────────────┘
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
6. Result screen     → Browser auto-shows when battle ends
7. Back to step 1   → Repeat for next raid (via core_engine loop)
```

### do_battle Flow Detail

Each turn in battle:
1. Click full auto button
2. Wait for attack button to appear (display-on)
3. Check if attack button is `display-off` (turn processing)
4. If `display-off`: turn completed
   - If `refresh=true`: refresh browser immediately, fullauto_clicked=0, next turn
   - If `refresh=false`: wait for attack button to reappear, fullauto_clicked=1, next turn
5. Click attack button (triggers full auto action sequence)
6. Loop until turn limit or boss dies

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
- A **battle parameter** (config.turn) - controls per-battle turn limit
- An **internal variable** (context.current_turn) - tracks current turn during battle loop

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

## ActionContext

Passed to all actions, contains:
- `navigator`: Navigator instance for browser interaction
- `config`: ConfigManager instance for reading params
- `current_turn`: Internal turn counter (ONLY for do_battle, reset each battle)
- `battle_finished`: Flag set when battle ends
- `raids_completed`: Counter incremented when ONE raid completes (task-level)
- `last_result`: Last action result (success/failed)

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
    return ActionContext.RESULT_SUCCESS  # or RESULT_FAILED
```

### Available Actions

| Action | Description | Transitions |
|--------|-------------|-------------|
| `select_raid` | Browse raid list, filter by HP%, select raid | success→select_summon, failed→refresh_raid_list |
| `select_summon` | Auto-detect preset summon | success→join_battle, failed→select_raid |
| `join_battle` | Click quest start button | success→do_battle, failed→select_raid |
| `do_battle` | Full auto loop, increments `raids_completed` | success/failed (follows transitions) |
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

## Core Engine

The `CoreEngine` orchestrates:
- `start()`: Runs main loop monitoring state
- `start_task(task_path)`: Loads and runs task in background thread
- `_run_task_loop()`: Repeatedly calls execute_task until exit condition met
- `_main_loop()`: Detects state from URL, handles recovery
- `_handle_recovery()`: Recovery logic based on detected state

### Task Loop Flow
```
while running and task:
    execute_task()      # Runs ONE raid cycle, returns True/False
    if not result:     # Error/captcha
        break
    if check_exit_condition():  # raids_completed >= target?
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
- `_fast_move(end_pos)`: Linear mouse movement
- `get_element_rect(element)`: Get element position/size
- `refresh()`: Browser refresh
- `wait(min_time, max_time)`: Random human-like delays
- `wait_for_element(by, selector, timeout)`: Wait for element
- `wait_for_clickable(by, selector, timeout)`: Wait for clickable element

### Click Element Behavior
1. `scrollIntoView({block: 'nearest', inline: 'nearest'})` - bring element into view
2. Random scroll offset `(-3 to +3)` - humans rarely stop perfectly aligned
3. Small pause as if to locate element
4. Calculate element center with sigma-based offset (10% of element size)
5. Move mouse using bezier curve (or fast linear for `fast=True`)
6. Click

## Flask UI

HTTP endpoints for UI↔core communication:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main control panel |
| `/api/config` | GET | Get current config + state |
| `/api/config` | POST | Update config |
| `/api/state` | GET | Get current state |

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
│   └── default.json       # Global default parameters
├── src/
│   ├── __init__.py
│   ├── config_manager.py # Thread-safe config & state
│   ├── context.py        # ActionContext & ActionRegistry
│   ├── core_engine.py    # Battle orchestration
│   ├── navigator.py      # Browser automation
│   ├── state_machine.py  # State detection
│   ├── task_executor.py  # FSM-based task execution
│   └── actions.py        # All registered actions
└── ui/
    ├── app.py            # Flask web interface
    └── templates/        # HTML templates
```

## Original Script Reference (hihihori3.py)

The `hihihori3.py` contains reference implementations:
- **NavigationHelper**: Click with bezier curves, scrollIntoView adjustment
- **BattleHelper**: Summon selection, battle joining, full auto battle
- **RaidHelper**: Raid picking (HP filter), popup handling, raid cleanup
- **gwHelper**: Guild war battle with popup handling
- **freeQuestHelper**: Free quest automation
