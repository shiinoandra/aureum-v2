# Battle Parameters

## Overview

This document describes the configurable parameters used in the automation script for Granblue Fantasy.

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

## Future Expansion

These parameters are for the built-in full auto battle. Future versions will support custom battle scripts with per-battle JSON configuration.