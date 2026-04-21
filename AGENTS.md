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
│  (orchestrates flow)  │     │   (recovery & detection)      │
│  - task definition    │     │   - detect state from URL     │
│  - action registry    │     │   - recovery handlers         │
│  - exit conditions    │     │   - state transitions         │
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
1. select_raid      → Navigate to raid list, browse, filter by HP%, select raid
2. select_summon    → On summon screen, click OK (auto-preset configured in-game)
3. join_battle      → Click start button to enter battle
4. do_battle        → Loop until conditions met:
   - config.turn turns reached, OR
   - config.until_finish=true loops until boss dies, OR
   - Boss dies early (battle ends automatically)
5. Result screen    → Browser auto-shows when battle ends
6. Back to step 1   → Repeat for next raid
```

## Two-Layer System

### Task Layer
Defines "what to do" - the sequence of actions to complete a task.
- Example: Raid task = select_raid → select_summon → join_battle → do_battle
- **exit_condition** is task-level (how many raids to complete)
- Task repeats actions 1-4 until exit_condition is met

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

Tasks are defined in JSON files in `/tasks/` directory.

### raid.json Example
```json
{
  "task_type": "raid",
  "actions": [
    {"name": "select_raid", "params": {"filter": "prefer_Lv100"}},
    {"name": "select_summon", "params": {}},
    {"name": "join_battle", "params": {}},
    {"name": "do_battle", "params": {"mode": "full_auto"}}
  ],
  "exit_condition": {"type": "raid_count", "value": 10}
}
```

### quest.json Example
```json
{
  "task_type": "quest",
  "actions": [
    {"name": "select_quest", "params": {"quest_id": "story_1"}},
    {"name": "select_summon", "params": {}},
    {"name": "join_battle", "params": {}},
    {"name": "do_battle", "params": {"mode": "full_auto"}}
  ],
  "exit_condition": {"type": "until_finish", "value": true}
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
| `refresh` | bool | true | Refresh browser to skip animation |
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
- `raids_completed`: Counter incremented when ONE raid completes (task-level, NOT reset between raids)

```python
class ActionContext:
    def __init__(self, navigator, config_manager):
        self.navigator = navigator
        self.config = config_manager
        self.current_turn = 0
        self.battle_finished = False
        self.raids_completed = 0
    
    def reset(self):
        """Reset for next raid cycle"""
        self.current_turn = 0
        self.battle_finished = False
        # raids_completed NOT reset - it's task-level
```

## Action Registry

Actions registered via decorator:
```python
@ActionRegistry.register("action_name")
def action_function(params, context: ActionContext):
    pass
```

Available actions in `src/actions.py`:
| Action | Description |
|--------|-------------|
| `select_raid` | Browse raid list, filter by HP%, select raid |
| `select_summon` | Auto-detect preset summon |
| `join_battle` | Click quest start button |
| `do_battle` | Full auto loop, increments `raids_completed` |
| `refresh_raid_list` | Click refresh button |
| `clean_raid_queue` | Process pending unclaimed raids |
| `go_to_raid_list` | Navigate to `#quest/assist` |
| `go_to_main_menu` | Navigate to `#mypage/` |

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
| "three_raid" | Clean raid queue |
| "toomuch_pending" | Clean pending raids |
| "ended" | Skip to next raid |

## Recovery System

Recovery is triggered when `ERROR_RECOVERY` state is detected:
1. Detect actual state from current URL
2. Based on state, decide recovery action

## Navigator

Browser automation module handling Selenium + PyAutoGUI.

### Key Methods
- `get_current_url()`: Returns current browser URL
- `click_element(element, fast=False)`: Human-like click using bezier curves
- `_human_move(end_pos)`: Bezier curve mouse movement
- `_fast_move(end_pos)`: Linear mouse movement
- `get_element_rect(element)`: Get element position/size
- `refresh()`: Browser refresh
- `wait(min_time, max_time)`: Random human-like delays
- `wait_for_element(by, selector, timeout)`: Wait for element
- `wait_for_clickable(by, selector, timeout)`: Wait for clickable element

## Core Engine

The `CoreEngine` orchestrates:
- `start()`: Runs main loop monitoring state
- `start_task(task_path)`: Loads and runs task in background thread
- `_run_task_loop()`: Repeatedly executes task until exit condition
- `_main_loop()`: Detects state from URL, handles recovery
- `_handle_recovery()`: Recovery logic based on detected state

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
│   ├── raid.json          # Raid task definition
│   └── quest.json         # Quest task definition
├── config/
│   └── default.json       # Global default parameters
├── src/
│   ├── __init__.py
│   ├── config_manager.py # Thread-safe config & state
│   ├── core_engine.py    # Battle orchestration
│   ├── navigator.py      # Browser automation
│   ├── state_machine.py  # State detection
│   ├── task_executor.py  # Task execution + action registry
│   └── actions.py        # All registered actions
└── ui/
    ├── app.py            # Flask web interface
    └── templates/        # HTML templates
```

## Original Script Reference (hihihori3.py)

The `hihihori3.py` contains reference implementations:
- **NavigationHelper**: Click with bezier curves, element positioning
- **BattleHelper**: Summon selection, battle joining, full auto battle
- **RaidHelper**: Raid picking (HP filter), popup handling, raid cleanup
- **gwHelper**: Guild war battle with popup handling
- **freeQuestHelper**: Free quest automation
