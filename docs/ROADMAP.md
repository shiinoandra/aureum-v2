# Aureum v2 Feature Roadmap

This document tracks planned features, their priorities, and implementation status.

## Legend

| Symbol | Meaning |
|--------|---------|
| 🟢 | Implemented |
| 🟡 | In Progress |
| 🔴 | Not Started |
| ⬜ | Deferred / Blocked |

---

## P0: Foundation — SQLite Schema & Database Layer

**Status:** 🟢 Implemented  
**Files:** `src/infra/database.py`, `data/aureum.db` (runtime), `.gitignore`  
**Prerequisite for:** P3, P5, P6, P8  
**Rationale:** All logging, history, and knowledge base features depend on a shared database.

### Implementation Notes

- `src/infra/database.py` provides connection manager, schema init, and CRUD helpers
- Tables: `summons`, `raids`, `task_history`, `drop_log`
- Simple `db_version` table for future migrations
- Database auto-initializes on first import
- `data/` directory is gitignored (runtime data)

### Schema Design (Implemented)

**`summons`** — Knowledge base for support summons
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `name` | TEXT NOT NULL | Exact GBF name |
| `level` | TEXT | e.g. "Lvl 100", "Lvl 250" |
| `element` | TEXT | fire/wind/water/earth/light/dark |
| `image_url` | TEXT | Optional icon URL |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

**`raids`** — Knowledge base for raids
| Column | Type | Notes |
|--------|------|-------|
| `raid_id` | TEXT PK | GBF internal ID (e.g. "303141") |
| `name` | TEXT NOT NULL | Display name |
| `jp_name` | TEXT | Japanese name |
| `level` | INTEGER | Raid level |
| `ap_cost` | INTEGER | AP cost to host |
| `ep_cost` | INTEGER | EP cost to host |
| `host_url` | TEXT | URL to host the raid |
| `difficulty` | TEXT | e.g. "Impossible", "Very Hard" |
| `element` | TEXT | fire/wind/water/earth/light/dark |
| `hp` | INTEGER | Optional rough HP |
| `image_url` | TEXT | Optional |
| `participant_num` | INTEGER | Max number of participants allowed |
| `min_rank` | INTEGER | Minimum player rank to join |
| `v2` | INTEGER | 1 if raid uses v2 battle system, 0 otherwise |
| `stage_id` | INTEGER | GBF stage ID for preset modal navigation |
| `difficulty_rating` | INTEGER | GBF difficulty rating for preset modal navigation |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

**`task_history`** — Completed / stopped task log
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `task_name` | TEXT NOT NULL | JSON filename |
| `task_type` | TEXT NOT NULL | "raid", "event", "quest" |
| `raid_id` | TEXT | FK to raids(raid_id), nullable |
| `start_time` | TIMESTAMP | |
| `end_time` | TIMESTAMP | |
| `target_count` | INTEGER | Original exit condition value |
| `completed_count` | INTEGER | Actual raids completed |
| `status` | TEXT | "completed", "stopped", "failed", "running" |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

**`drop_log`** — Per-raid drop results
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `task_history_id` | INTEGER NOT NULL | FK to task_history(id) |
| `raid_id` | TEXT | |
| `timestamp` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |
| `items_json` | TEXT | JSON array: `[{"name":"...", "count":1}]` |

**Database file:** `data/aureum.db`

---

## P1: Queue Persistence & Stop/Resume

**Status:** 🟢 Implemented  
**Files:** `src/runtime/queue_persistence.py`, `src/runtime/runtime_manager.py`, `ui/app.py`  
**Rationale:** Core runtime improvement. Enables safe stop/start without losing queue state.

### Implementation Notes

- Queue persisted to `data/queue.json` on every mutation (enqueue, dequeue, reorder, clear)
- Queue auto-restored on `RuntimeManager` startup
- `Task.source_file` field added to track which JSON file the task came from
- `POST /api/stop` preserves queue; `POST /api/clear_queue` explicitly clears
- Each queued task embeds its full `task_config` snapshot so edits to disk don't silently mutate queued instances
- Queue is mutable (reorder, remove, amount change) only when stopped
- Queue snapshot includes `completed`, `not_found_count`, `source_file`, `history_id`, `raid_id`, and `task_config`

### Queue File Format
```json
[
  {
    "source_file": "raid.json",
    "amount": 10,
    "completed": 3,
    "not_found_count": 0,
    "history_id": 42,
    "raid_id": "303141",
    "task_config": {
      "turn": 1,
      "refresh": true,
      "until_finish": false,
      "trigger_skip": false,
      "pre_fa": false,
      "min_hp_threshold": 60,
      "max_hp_threshold": 100,
      "min_people": 1,
      "max_people": 30,
      "summon_priority": []
    }
  }
]
```

---

## P2: Mutable Queue Sync (Frontend ↔ Backend)

**Status:** 🟢 Implemented  
**Files:** `ui/templates/partials/queue.html`, `ui/app.py`  
**Rationale:** Builds on P1. User can edit queue while stopped.

### Completed

1. **Queue mutation guards**
   - `_queue_mutable()` helper checks `is_running` only
   - All mutation endpoints (`sync_queue`, `remove`, `reorder`, `clear`) return 409 if running
   - Queue is editable only when stopped

2. **Full queue sync endpoint**
   - `POST /api/sync_queue` receives entire queue array
   - Backend preserves existing `Task` objects (including their `task_config` snapshots) by `task_id`
   - Reconstructs from disk only for brand-new queue items
   - Persists to `data/queue.json` immediately with embedded `task_config`
   - Supports reordering + amount changes in one call

3. **Drag-and-drop reordering**
   - HTML5 drag and drop API on queue items
   - Visual feedback during drag (opacity, highlight drop target)
   - On drop: calls `syncQueueOrder()` to send new state to backend

4. **Inline amount editing**
   - Number input field for each queue item's amount (when editable)
   - On change: triggers full queue sync

5. **Visual states**
   - **Editable** (stopped): drag handles, amount inputs, remove buttons, clear queue button
   - **Read-only** (running): static numbers, amount labels, no controls, slightly dimmed

6. **Clear queue button**
   - Visible only when stopped
   - Confirmation dialog before clearing

---

## P3: Task History Logging

**Status:** 🟢 Implemented  
**Files:** `src/task/task_manager.py`, `src/domain/drop_logger.py`, `src/infra/database.py`, `ui/app.py`, `ui/templates/pages/history.html`, `ui/templates/partials/history_table.html`  
**Rationale:** Straightforward once SQLite (P0) exists.

### Completed

1. **Task history database logging**
   - `TaskManager.run()` inserts `task_history` row at task start
   - Updates `completed_count` incrementally after each successful cycle
   - Finalizes with `status` and `end_time` on exit (completed / stopped / failed / captcha)
   - DB errors are caught and logged; automation continues unaffected

2. **Basic drop logging hook**
   - `DropLogger.capture()` implemented with DOM parsing for `.prt-item-list` and `.lis-treasure`
   - Writes to `drop_log` table after each successful result screen
   - Gracefully falls back to `"[]"` if parsing fails or no items found

3. **History UI page**
   - Table view with task name, type, target, completed, status, start time, duration
   - Color-coded status badges and type badges
   - HTMX partial with "Load More" pagination
   - Empty state when no history exists

4. **API endpoints**
   - `GET /api/history` — paginated JSON
   - `GET /api/history/<id>/drops` — drop logs for a task entry
   - `GET /htmx/history-table` — server-rendered table partial

---

## P4: HTMX Migration

**Status:** 🟢 Implemented  
**Files:** `ui/templates/base.html`, `pages/*.html`, `partials/*.html`, `ui/app.py`  
**Rationale:** Better DX for all future UI features. Should happen before adding more UI.

### Completed

1. **Template structure**
   - `base.html` — Jinja base layout with HTMX CDN, Tailwind, SSE adapter, navigation tabs
   - `pages/dashboard.html` — Main control panel with manual/content picker tabs
   - `pages/task_creator.html` — Task creator page
   - `pages/history.html` — Task history (placeholder)
   - `partials/status_header.html` — Status badge, buttons, progress bar
   - `partials/queue.html` — Queue list with reorder/remove buttons
   - `partials/task_preview.html` — Task preview panel (fixed outerHTML swap)
   - `partials/raid_card.html` — Current raid card with turn progress
   - `partials/creator_form.html` — Creator parameter form
   - `partials/raid_grid.html` — Interactive raid grid with star ratings and badges
   - `partials/content_list.html` — Paginated event/quest list with AP badges and cleared status

2. **Flask routes**
   - Page routes: `/`, `/creator`, `/history`
   - HTMX partial routes: `/htmx/status`, `/htmx/queue`, `/htmx/task-preview`, `/htmx/raid-card`, `/htmx/creator-load`, `/htmx/raid-grid/<category>`, `/htmx/content-list/<type>`
   - API endpoints updated to return HTMX partials when `HX-Request` header is present

3. **SSE Adapter**
   - Keeps JSON SSE format (flexible for future expansion)
   - JS adapter connects to `/api/events` and triggers HTMX refreshes on key elements
   - Auto-reconnect on disconnect and page visibility change

4. **UI Polish**
   - **Start button disabled when queue empty** — with `disabled` attribute, hover tooltip (`title`), and onclick alert
   - **Three content picker buttons** — Raid (blue/sword), Event (amber/flag), Quest (emerald/scroll) arranged in a responsive grid
   - **Unified modal system** — Single modal that switches between raid grid and event/quest list views
   - **Event/Quest list** — Vertical rows with thumbnail, name, AP cost badge, cleared status, play button; pagination at bottom

### Still Needed

1. **Task Creator event workflow**
   - Event scanning results rendering with HTMX (API exists, UI integration pending)

2. **Old `index.html` removal**
   - Keep as backup until HTMX version is fully tested in production

---

## P5: Summon Priority UI

**Status:** 🟢 Implemented  
**Files:** `ui/templates/partials/summon_picker.html`, `ui/templates/partials/creator_form.html`, `ui/app.py`  
**Rationale:** Visual summon selection with click-to-add ordering.

### Completed

1. **Summon list from SQLite**
   - Read `summons` table
   - Display with thumbnail icons (if available), name, level, element, series

2. **Click-to-add priority queue**
   - User clicks summon cards to add to priority list
   - Chips show in priority order with remove button
   - Order is saved back to task JSON's `summon_priority` field via hidden JSON input
   - Filter search for summon grid

3. **Level display**
   - Each summon card shows level tier from database
   - Selected chips preserve level in `summon_priority`

---

## P6: Raid Picker & JSON-to-Raid Association

**Status:** 🟡 In Progress  
**Files:** `ui/templates/partials/raid_grid.html`, `ui/templates/pages/task_creator.html`, `ui/templates/pages/dashboard.html`, `ui/app.py`, `src/task/task.py`, `src/runtime/queue_persistence.py`  
**Rationale:** Natural association between raids and task configs.

### Completed

1. **Raid list from SQLite**
   - Read `raids` table with category filtering (All, Standard, Impossible, Unlimited, v2)
   - Visual grid with thumbnail, name, difficulty badge, level, element
   - Case-insensitive filtering for difficulty values
   - Search by name/difficulty in modals

2. **Raid → Task JSON mapping**
   - Task JSON contains `raid_id` field matching `raids.raid_id`
   - `Task` dataclass carries `raid_id` through queue lifecycle
   - Queue persistence saves/restores `raid_id`
   - Queue display enriches with raid name, image, difficulty, level, element from DB

3. **Task creation flow (Task Creator)**
   - User picks raid from visual picker modal
   - Auto-creates task JSON with `raid_id` and default battle parameters
   - Auto-loads new task into creator form for editing
   - Dynamic dropdown update without page reload

### Still Needed

1. **Dashboard content picker integration**
   - Selecting a raid from dashboard modal should find/create task and enqueue it
   - Currently shows stub alert (`addContentToQueue`)

---

## P7: Manual Battle Operations (Turn Scripting)

**Status:** 🔴 Not Started  
**Rationale:** Most complex feature. Needs careful schema design + UI.

### Scope

1. **Turn script JSON format**
   ```json
   {
     "turn_script": {
       "1": {"skills": ["char1_skill3", "char2_skill1"], "summon": true, "attack": true},
       "2": {"skills": ["char3_skill2"], "summon": false, "attack": true},
       "default": {"skills": [], "summon": false, "attack": true}
     }
   }
   ```

2. **Skill target support (future)**
   - `"char1_skill3": {"target": "enemy_front"}`
   - Targets: `"self"`, `"enemy_front"`, `"enemy_back"`, `"ally_1"`, etc.

3. **Fallback behavior**
   - If a skill button is not found (cooldown, character dead): skip and continue
   - If script deviates too far (e.g., expected 4 chars alive but only 2): fallback to full auto
   - If turn number exceeds script entries: use `"default"` action set

4. **Task-level reference**
   - Task JSON contains `"turn_script_file": "scripts/my_rotation.json"`
   - Or inline `"turn_script": {...}` for simple cases

5. **UI for script editor**
   - Turn-by-turn accordion
   - Drag skill icons into turn slots
   - Toggle summon/attack per turn
   - Preview/export JSON

---

## P8: Drop Logging

**Status:** 🔴 Not Started  
**Rationale:** DOM parsing + SQLite writes. Needs P0 first.

### Scope

1. **Implement `domain/drop_logger.py`**
   - Parse `.prt-item-list` and `.lis-treasure.btn-treasure-item` elements
   - Extract item names and counts
   - Based on `hihihori3.py`'s `log_raid_results()`

2. **Integrate with TaskManager**
   - `_handle_post_cycle()` calls `DropLogger.capture()` on result screen
   - Writes to `drop_log` table with `task_history_id` FK

3. **Drop history UI**
   - Table view of all drops
   - Filter by raid, date, item name
   - Aggregate statistics (drop rates)

---

## P9: Interchangeable Task Switching

**Status:** 🔴 Not Started  
**Rationale:** Most complex runtime logic. Do last.

### Scope

1. **Per-task "not found" counter**
   - Track how many consecutive times `select_raid` returns `RESULT_FAILED`
   - Threshold configurable in task JSON (default: 5)

2. **Switch logic**
   - When `not_found_count >= threshold`:
     1. Save remaining count for current task
     2. Reset `not_found_count` to 0
     3. Pick another raid-type task from queue at random
     4. Switch to that task
   - When the new task also hits threshold: switch again
   - If no other raid tasks available: keep trying current one (or wait)

3. **Queue state management**
   - Queue item tracks: `task_name`, `original_amount`, `completed`, `not_found_count`
   - Switching does not dequeue — it just changes which item is "active"

4. **Example flow**
   ```
   Queue: [A×10, B×10]
   Run A 3 times → A not_found=5 → save A remaining=7, reset A not_found=0
   Switch to B
   Run B 8 times → B not_found=5 → save B remaining=2, reset B not_found=0
   Switch to A (remaining=7)
   ...
   ```

---

## Implementation Order

```
P0 → P1 → P2 → P4 → (P3, P5, P6 in parallel) → P7 → P8 → P9
     ↑    ↑    ↑
     └────┴────┘  P4 can start once P2 API is stable
```

**Why P4 before P3/P5/P6?**  
All three (history, summon picker, raid picker) need UI work. Migrating to HTMX first prevents rewriting vanilla JS later.

---

## Design Decisions Log

| Date | Decision | Reason |
|------|----------|--------|
| 2026-04-29 | Queue persistence = file (`data/queue.json`), not DB | User preference: keep runtime state separate from analytical DB |
| 2026-04-29 | `raid_id` field added to task JSON | Enables natural association between task config and knowledge base raid entry |
| 2026-04-29 | Turn scripts = separate JSON file referenced by task | Reusable across multiple raid tasks |
| 2026-04-29 | HTMX + Jinja2 chosen over React/Vue | Server-heavy state, minimal client interactivity, faster iteration |
| 2026-04-29 | Fallback on manual battle = full auto | Safety net when script state diverges from actual battle |
| 2026-04-29 | Interchangeable switching = random other raid task | No explicit `fallback_task` mapping needed |
