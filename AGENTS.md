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
- **Math**: `bezier` + `numpy` for curve generation

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
2. select_raid       → Browse list, filter by HP% and player count, select raid
3. select_summon     → On summon screen, detect auto-preset or pick preferred summon
4. join_battle       → Click start button to enter battle
5. do_battle         → Loop until conditions met:
   - config.turn turns reached, OR
   - config.until_finish=true loops until boss dies, OR
   - Boss dies early (battle ends automatically)
6. Result screen     → Browser auto-shows when battle ends
7. Back to step 1   → Repeat for next raid (via core_engine loop)
```

### do_battle Flow Detail

**Important:** The script does **NOT** click the attack button. GBF's in-game full auto system executes the skill queue and auto-triggers the attack server-side. The script only toggles full auto and waits for the attack button to disappear (`display-off`).

Each turn in battle:

1. **Check battle ended?** (multi-layer detection)
   - URL navigated to `#result_multi/*` or `#result/*`
   - `.prt-result-cnt` container is visible
   - Victory popup (`.pop-exp`) with OK button
   - `"Battle has ended"` popup (`.pop-usual.pop-rematch-fail`)
   - If detected: click dismiss button, increment `raids_completed`, return SUCCESS

2. **Turn limit check**
   - If `until_finish=false` and `current_turn > turn`: exit battle, increment counter

3. **Click full auto button** (if `fullauto_clicked == 0`)
   - Find `.btn-auto` and click it
   - Set `fullauto_clicked = 1`
   - Move cursor away from button

4. **Check attack button state** (CRITICAL: on same page, before refresh)
   - Find `.btn-attack-start` and check class for `display-off`
   - If `display-off`: turn completed
     - Increment `current_turn`
     - Reset `fullauto_clicked = 0`
     - **Always refresh once** to skip attack animation / reset UI
     - Wait for `.btn-attack-start.display-on` to restore
     - Loop back to step 1

5. **`refresh=true` behavior**
   - Refresh browser to skip skill animations
   - Reset `fullauto_clicked = 0` (page reloads, button state resets)
   - Wait for battle UI to restore
   - Loop back to step 1

6. **`refresh=false` behavior**
   - Let animations play out naturally
   - Wait and loop back to step 4

**`pre_fa` (experimental):** If `pre_fa=true`, the script clicks at the current mouse position (`click_onthespot`) before entering the battle UI wait loop. This is a timing-based workaround for GBF's pre-battle full auto toggle screen, which has no detectable DOM elements during the fade transition.

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
- **Note:** `_main_loop` and `_handle_recovery` exist in `core_engine.py` but are **not currently wired into the active execution path** (unused dead code).

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

### quest.json (Planned, Not Implemented)
`quest.json` exists but references `select_quest` action which is not yet implemented. Quest automation will be added in a future milestone.

## Exit Conditions (Task-Level)

| Type | Value | Meaning |
|------|-------|---------|
| `raid_count` | Integer (e.g., 10) | Number of raids to complete |
| `until_finish` | boolean | Stay until battle completes (for quests) |

**Note**: `turns` is NOT a task-level exit condition. Turns are:
- A **battle parameter** (config.turn) - controls per-battle turn limit
- An **internal variable** (context.current_turn) - tracks current turn during battle loop

The counter `context.raids_completed` is **only incremented inside `do_battle`** when:
- Battle ends naturally (boss dies)
- Turn limit is reached
- `"Battle has ended"` popup is dismissed

`execute_task` returns `True` after one cycle, then `_run_task_loop` checks `check_exit_condition()`.

## Battle Parameters (Config-Level)

Used inside `do_battle` action, read from `config/default.json`:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `turn` | int | 1 | Max turns per single battle |
| `refresh` | bool | true | Refresh browser after clicking full auto to skip animations |
| `until_finish` | bool | false | Loop until boss dies (ignore turn limit) |
| `trigger_skip` | bool | false | Skip boss entrance animation by refreshing |
| `think_time_min` | float | 0.2 | Min delay between actions |
| `think_time_max` | float | 0.5 | Max delay between actions |
| `pre_fa` | bool | false | **Experimental.** Click at current cursor position before battle UI wait |
| `min_hp_threshold` | int | 60 | Minimum HP% for raid selection filter |
| `max_hp_threshold` | int | 100 | Maximum HP% for raid selection filter |
| `min_people` | int | 1 | Minimum player count for raid selection filter |
| `max_people` | int | 1 | Maximum player count for raid selection filter |
| `summon_priority` | List[dict] | [] | Priority-ordered list of preferred support summons. Each object has `name` (required) and `level` (optional). If level omitted, any level matches. |

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

### reset() Behavior
Called by `_run_task_loop` before each new raid cycle:
- Resets `current_turn = 0`
- Resets `battle_finished = False`
- Resets `last_result = None`
- **Does NOT reset `raids_completed`** — this is intentional; it accumulates across cycles

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
| `select_raid` | Browse raid list, filter by HP range, player count, and optional name filter | success→select_summon, failed→refresh_raid_list |
| `select_summon` | Auto-detect preset summon, or pick from `summon_priority` list, or fallback to first available | success→join_battle, failed→select_raid |
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
- `start()`: Runs main loop monitoring state (recovery mode) — **currently unused**
- `start_task(task_path)`: Loads and runs task in background thread
- `_run_task_loop()`: Repeatedly calls execute_task until exit condition met
- `_main_loop()`: Detects state from URL, handles recovery — **currently unused**
- `_handle_recovery()`: Recovery logic based on detected state — **currently unused**

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

Checks these selectors in order:
1. `.common-pop-error.pop-show`
2. `.pop-usual.pop-result-assist-raid.pop-show`
3. `.pop-usual.pop-rematch-fail.pop-show`
4. Fallback: generic `.pop-usual.pop-show` with text filter (ignores victory/reward popups)

### Popup Recovery
`_handle_popup_recovery(popup_type)` now returns `(can_continue, redirect_action)`:
- `can_continue`: False = stop automation
- `redirect_action`: None = continue current action; str = jump to action name instead

| Popup Text | Recovery Action | Redirect |
|------------|----------------|----------|
| "captcha" | Stop automation | — |
| "raid_full" | Refresh raid list | `refresh_raid_list` |
| "not_enough_ap" | Wait 10-20s, then refresh | `refresh_raid_list` |
| "three_raid" | Wait 5-10s, then refresh | `refresh_raid_list` |
| "toomuch_pending" | Clean raid queue, then refresh | `refresh_raid_list` |
| "ended" | Skip to next raid | `refresh_raid_list` |

## Navigator

Browser automation module handling Selenium + PyAutoGUI.

### Key Methods
- `get_current_url()`: Returns current browser URL
- `click_element(element, fast=False)`: Human-like click
- `click_onthespot()`: Clicks at current mouse position after 0.5-0.8s wait (for `pre_fa`)
- `wait_for_element(by, selector, timeout)`: Wait for element presence
- `wait_for_clickable(by, selector, timeout)`: Wait for element to be clickable
- `refresh()`: Browser refresh
- `wait(min_time, max_time)`: Random human-like delays

### Click Element Behavior (`fast=False`)
1. `scrollIntoView({block: 'center', inline: 'nearest'})` — bring element into view
2. Random scroll offset `(-20 to +20)` — humans rarely stop perfectly aligned
3. Small pause (`0.05-0.1s`) as if to locate element
4. Calculate element center with sigma-based offset (10% of element size)
5. `_human_move()` — bezier curve mouse movement (0.05-0.35s depending on distance)
6. 1-2 micro-jitter corrections (`±2px`, 0.01-0.02s)
7. `mouseDown()` → `time.sleep(0.03-0.08)` → `mouseUp()` — variable hold click
8. 50% chance to `_move_away()` after click

### Click Element Behavior (`fast=True`)
1. Steps 1-4 same as above
2. `_fast_move()` — 2-step overshoot-and-snap:
   - Step 1: Move 80% toward overshoot point (±15px random)
   - Step 2: Snap to actual target
   - Total: ~0.04-0.07s
3. `mouseDown()` → `time.sleep(0.03-0.08)` → `mouseUp()`
4. No micro-jitter

### `_move_away` Behavior
- Calculates random point within radius (80-150px) from **element center**
- Random angle (0-360°)
- Clamped with 50px screen padding (prevents snapping to window borders)
- Uses `_fast_move` for quick departure

### `_human_move` Behavior
- Distance-based bezier curve with cubic control points
- 3-8 steps depending on distance
- Slower at start/end of movement for natural feel

### `_fast_move` Behavior
- Overshoot by 5-15px in random direction
- Move 80% to overshoot point, then snap to target
- Total duration: ~0.04-0.07s
- Faster than linear interpolation but retains biological "correction" feel

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
│   └── quest.json         # Quest task definition (planned, not implemented)
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
│   ├── actions.py        # All registered actions
│   └── main.py           # Entry point (legacy, not used when Flask is active)
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

---

