# Battle Parameters

## Overview

This document describes the configurable parameters used in the automation script for Granblue Fantasy.

## Persistence

All parameters listed below are stored in `config/default.json`. When you click **Save Config** in the UI, the values are written back to this file immediately, making it the single source of truth that survives restarts.

## Battle Types

### Quest Battle
- Battle started by the player
- Must run until finished (use `until_finish=true`)
- Player controls the full loop

### Raid Battle
- Battle started by other players
- Player joins as supporter
- Can exit after N turns and join new raid (use `turn` parameter)

## Parameters

### `turn` (integer)
- **Default**: 1
- **Used for**: Raid battles
- **Description**: Number of turns to execute before exiting the raid and hopping into a new one

### `refresh` (boolean)
- **Default**: true
- **Used for**: Both quest and raid
- **Description**: Whether to refresh the browser after taking action (clicking full auto). Needed because GBF has animation sprites - refreshing cuts time and skips animation

### `until_finish` (boolean)
- **Default**: false
- **Used for**: Quest battles (primary), can be used for raid
- **Description**: When true, script stays in battle until it finishes. Used for quest battles since we started them ourselves and need to complete them

### `trigger_skip` (boolean)
- **Default**: false
- **Used for**: Both quest and raid
- **Description**: Some bosses have entrance animations. When true, refresh browser to skip the animation

### `think_time_min` (float)
- **Default**: 0.2
- **Used for**: All actions
- **Description**: Minimum delay between actions to mimic human behavior

### `think_time_max` (float)
- **Default**: 0.5
- **Used for**: All actions
- **Description**: Maximum delay between actions to mimic human behavior. Actual delay is random between min and max

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
  - `level` (string, optional): Exact level text (e.g., `"Lvl 100"`). If omitted or `null`, any level of that summon matches.
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

These parameters are for the built-in full auto battle. Future versions will support custom battle scripts with per-battle JSON configuration.
