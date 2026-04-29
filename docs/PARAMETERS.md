# Battle Parameters

## Overview

This document describes the configurable parameters used in task JSONs for Granblue Fantasy automation.

## Where Parameters Live

**`task_config` is embedded inside each task JSON** (e.g. `tasks/raid.json`, `tasks/20260429_gw_meat.json`).

There is no global `config/default.json`. Each task carries its own settings, allowing different tasks to run with different configurations without restarting the app.

## Editing Parameters

Use the **Task Creator** tab in the UI:
1. Load an existing task JSON or create a new one
2. Adjust battle parameters in the form
3. Click **Save JSON** to write to `tasks/`

## Parameters

### `turn` (integer)
- **Default**: 1
- **Used for**: Raid battles, event battles
- **Description**: Number of turns to execute before exiting the battle and starting the next cycle

### `refresh` (boolean)
- **Default**: true
- **Used for**: Both quest and raid
- **Description**: Whether to refresh the browser after each turn. Needed because GBF has animation sprites — refreshing cuts time and skips animation

### `until_finish` (boolean)
- **Default**: false
- **Used for**: Quest battles (primary), can be used for raid
- **Description**: When true, script stays in battle until it finishes. Used for quests since we started them ourselves and need to complete them

### `trigger_skip` (boolean)
- **Default**: false
- **Used for**: Both quest and raid
- **Description**: Some bosses have entrance animations. When true, refresh browser to skip the animation

### `pre_fa` (boolean)
- **Default**: false
- **Used for**: Both quest and raid
- **Description**: Click on-the-spot (at current mouse position) before battle starts. Useful for skipping initial dialog or triggering pre-battle full auto

### `min_hp_threshold` (integer)
- **Default**: 60
- **Used for**: Raid battles
- **Description**: Minimum HP % for a raid to be considered eligible when browsing the raid list

### `max_hp_threshold` (integer)
- **Default**: 100
- **Used for**: Raid battles
- **Description**: Maximum HP % for a raid to be considered eligible

### `min_people` (integer)
- **Default**: 1
- **Used for**: Raid battles
- **Description**: Minimum player count for a raid to be considered eligible

### `max_people` (integer)
- **Default**: 30
- **Used for**: Raid battles
- **Description**: Maximum player count for a raid to be considered eligible

### `summon_priority` (array of objects)
- **Default**: `[]`
- **Used for**: Both quest and raid
- **Description**: Priority-ordered list of preferred support summons. Checked from first to last. If none are found, falls back to the first available summon in the type0 tab.
  Each object supports:
  - `name` (string, required): Exact summon name
  - `level` (string, optional): Exact level text (e.g. `"Lvl 100"`). If omitted or `null`, any level of that summon matches.
  Example:
  ```json
  "summon_priority": [
    {"name": "Huanglong", "level": "Lvl 100"},
    {"name": "Kaguya", "level": "Lvl 100"},
    {"name": "Shiva"}
  ]
  ```

## How Level-less Matching Works
```python
if level:
    # Strict: both name AND level must match
    xpath = f"""
    //div[contains(@class, 'supporter-summon') and
        .//span[@class='txt-summon-level' and normalize-space(text())='{level}'] and
        .//span[@class='js-summon-name' and normalize-space(text())='{name}']]
    """
else:
    # Loose: name only
    xpath = f"""
    //div[contains(@class, 'supporter-summon') and
        .//span[@class='js-summon-name' and normalize-space(text())='{name}']]
    """
```

## Future Expansion

Future versions will support custom battle scripts with per-turn JSON configuration (e.g. skill sequences, CA timing).
