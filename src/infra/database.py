import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

# Database path: project_root/data/aureum.db
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "aureum.db"

SCHEMA_SQL = """
-- Migration tracking
CREATE TABLE IF NOT EXISTS db_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Summons knowledge base
CREATE TABLE IF NOT EXISTS summons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    level TEXT,
    element TEXT,
    image_url TEXT,
    series TEXT,
    hp INTEGER,
    attack INTEGER,
    tags TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Raids knowledge base
CREATE TABLE IF NOT EXISTS raids (
    raid_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    jp_name TEXT,
    level INTEGER,
    ap_cost INTEGER,
    ep_cost INTEGER,
    host_url TEXT,
    difficulty TEXT,
    element TEXT,
    hp INTEGER,
    image_url TEXT,
    participant_num INTEGER,
    min_rank INTEGER,
    v2 INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Task execution history
CREATE TABLE IF NOT EXISTS task_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT NOT NULL,
    task_type TEXT NOT NULL,
    raid_id TEXT,
    quest_id TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    target_count INTEGER,
    completed_count INTEGER,
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (raid_id) REFERENCES raids(raid_id)
);

-- Per-raid drop results
CREATE TABLE IF NOT EXISTS drop_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_history_id INTEGER NOT NULL,
    raid_id TEXT,
    quest_id TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    items_json TEXT NOT NULL,
    FOREIGN KEY (task_history_id) REFERENCES task_history(id)
);

-- Initial version
INSERT OR IGNORE INTO db_version (version) VALUES (1);
"""


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Apply migrations to existing databases."""
    # Migration 1: Add participant_num and min_rank to raids table
    cursor = conn.execute("PRAGMA table_info(raids)")
    columns = {row[1] for row in cursor.fetchall()}
    if "participant_num" not in columns:
        conn.execute("ALTER TABLE raids ADD COLUMN participant_num INTEGER")
    if "min_rank" not in columns:
        conn.execute("ALTER TABLE raids ADD COLUMN min_rank INTEGER")
    if "v2" not in columns:
        conn.execute("ALTER TABLE raids ADD COLUMN v2 INTEGER DEFAULT 0")
    conn.commit()


def init_db() -> None:
    """Initialize the database schema if it doesn't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA_SQL)
        _run_migrations(conn)
        conn.commit()


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db_version() -> int:
    """Return current database schema version."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT MAX(version) as v FROM db_version")
        row = cursor.fetchone()
        return row["v"] if row and row["v"] else 0


# ---------------------------------------------------------------------------
# Summons CRUD
# ---------------------------------------------------------------------------

def insert_summon(
    name: str,
    level: Optional[str] = None,
    element: Optional[str] = None,
    image_url: Optional[str] = None,
    series: Optional[str] = None,
    hp: Optional[int] = None,
    attack: Optional[int] = None,
    tags: Optional[str] = None,
) -> int:
    """Insert a summon and return its ID."""
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO summons
               (name, level, element, image_url, series, hp, attack, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, level, element, image_url, series, hp, attack, tags),
        )
        return cursor.lastrowid


def get_all_summons() -> List[Dict[str, Any]]:
    """Return all summons as dicts."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM summons ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]


def get_summon_by_id(summon_id: int) -> Optional[Dict[str, Any]]:
    """Return a single summon by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM summons WHERE id = ?", (summon_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Raids CRUD
# ---------------------------------------------------------------------------

def insert_raid(
    raid_id: str,
    name: str,
    jp_name: Optional[str] = None,
    level: Optional[int] = None,
    ap_cost: Optional[int] = None,
    ep_cost: Optional[int] = None,
    host_url: Optional[str] = None,
    difficulty: Optional[str] = None,
    element: Optional[str] = None,
    hp: Optional[int] = None,
    image_url: Optional[str] = None,
    participant_num: Optional[int] = None,
    min_rank: Optional[int] = None,
    v2: bool = False,
) -> None:
    """Insert or replace a raid entry."""
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO raids
               (raid_id, name, jp_name, level, ap_cost, ep_cost, host_url,
                difficulty, element, hp, image_url, participant_num, min_rank, v2)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (raid_id, name, jp_name, level, ap_cost, ep_cost, host_url,
             difficulty, element, hp, image_url, participant_num, min_rank,
             1 if v2 else 0),
        )


def get_all_raids() -> List[Dict[str, Any]]:
    """Return all raids as dicts."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM raids ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]


def get_raid_by_id(raid_id: str) -> Optional[Dict[str, Any]]:
    """Return a single raid by raid_id."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM raids WHERE raid_id = ?", (raid_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Task History CRUD
# ---------------------------------------------------------------------------

def insert_task_history(
    task_name: str,
    task_type: str,
    raid_id: Optional[str] = None,
    quest_id: Optional[str] = None,
    target_count: Optional[int] = None,
) -> int:
    """Start tracking a task. Returns the history ID."""
    import datetime
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO task_history
               (task_name, task_type, raid_id, quest_id,
                start_time, target_count, completed_count, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_name, task_type, raid_id, quest_id,
             datetime.datetime.now(), target_count, 0, "running"),
        )
        return cursor.lastrowid


def update_task_history(
    history_id: int,
    completed_count: Optional[int] = None,
    status: Optional[str] = None,
    raid_id: Optional[str] = None,
    quest_id: Optional[str] = None,
) -> None:
    """Update a task history entry on completion/stop."""
    import datetime
    fields = []
    values = []
    if completed_count is not None:
        fields.append("completed_count = ?")
        values.append(completed_count)
    if status is not None:
        fields.append("status = ?")
        values.append(status)
        if status in ("completed", "stopped", "failed"):
            fields.append("end_time = ?")
            values.append(datetime.datetime.now())
    if raid_id is not None:
        fields.append("raid_id = ?")
        values.append(raid_id)
    if quest_id is not None:
        fields.append("quest_id = ?")
        values.append(quest_id)
    if not fields:
        return
    values.append(history_id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE task_history SET {', '.join(fields)} WHERE id = ?",
            tuple(values),
        )


def get_task_history(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """Return task history ordered by most recent."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM task_history ORDER BY start_time DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Drop Log CRUD
# ---------------------------------------------------------------------------

def insert_drop_log(
    task_history_id: int,
    items_json: str,
    raid_id: Optional[str] = None,
    quest_id: Optional[str] = None,
) -> int:
    """Log drops from a single raid result. Returns the drop log ID."""
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO drop_log
               (task_history_id, raid_id, quest_id, items_json)
               VALUES (?, ?, ?, ?)""",
            (task_history_id, raid_id, quest_id, items_json),
        )
        return cursor.lastrowid


def get_drops_by_task_history(task_history_id: int) -> List[Dict[str, Any]]:
    """Return all drop logs for a given task history."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM drop_log WHERE task_history_id = ? ORDER BY timestamp",
            (task_history_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


# Auto-init on first import
init_db()
