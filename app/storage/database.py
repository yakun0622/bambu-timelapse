import sqlite3
import threading
from datetime import datetime, timezone

from app.core.config import settings


class Database:
    ACTIVE_STATUSES = ("PRINTING", "PAUSED")

    def __init__(self):
        self.path = settings.database_path
        self._lock = threading.Lock()
        self.init_schema()

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _columns(self, conn, table):
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row["name"] for row in rows}

    def _ensure_column(self, conn, table, name, definition):
        if name not in self._columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def init_schema(self):
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS print_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    initial_layer INTEGER,
                    current_layer INTEGER,
                    total_layers INTEGER,
                    progress INTEGER,
                    frame_count INTEGER NOT NULL DEFAULT 0,
                    failed_frames INTEGER NOT NULL DEFAULT 0,
                    output_dir TEXT NOT NULL,
                    video_path TEXT,
                    bambu_task_id TEXT,
                    bambu_subtask_id TEXT,
                    job_key TEXT
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    layer INTEGER NOT NULL,
                    file_path TEXT,
                    status TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    duration_ms INTEGER,
                    source TEXT,
                    frame_age_ms INTEGER,
                    frame_offset INTEGER,
                    rewind_ms INTEGER,
                    frame_before_trigger_ms INTEGER,
                    selection_mode TEXT,
                    vision_score REAL,
                    vision_stable INTEGER,
                    bed_score REAL,
                    bed_stable INTEGER,
                    bed_locator_mode TEXT,
                    aruco_id INTEGER,
                    similarity_score REAL,
                    motion_px REAL,
                    sharpness REAL,
                    align_dx REAL,
                    align_dy REAL,
                    error TEXT,
                    UNIQUE(job_id, layer)
                );

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    must_change_password INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS debug_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    layer INTEGER NOT NULL,
                    rewind_ms INTEGER NOT NULL,
                    actual_before_trigger_ms INTEGER,
                    file_path TEXT NOT NULL,
                    captured_at TEXT NOT NULL
                );
                """
            )

            # Migration path for existing installations.
            self._ensure_column(conn, "print_jobs", "bambu_task_id", "TEXT")
            self._ensure_column(conn, "print_jobs", "bambu_subtask_id", "TEXT")
            self._ensure_column(conn, "print_jobs", "job_key", "TEXT")
            self._ensure_column(conn, "snapshots", "source", "TEXT")
            self._ensure_column(conn, "snapshots", "frame_age_ms", "INTEGER")
            self._ensure_column(conn, "snapshots", "frame_offset", "INTEGER")
            self._ensure_column(conn, "snapshots", "rewind_ms", "INTEGER")
            self._ensure_column(conn, "snapshots", "selection_mode", "TEXT")
            self._ensure_column(conn, "snapshots", "vision_score", "REAL")
            self._ensure_column(conn, "snapshots", "vision_stable", "INTEGER")
            self._ensure_column(conn, "snapshots", "bed_score", "REAL")
            self._ensure_column(conn, "snapshots", "bed_stable", "INTEGER")
            self._ensure_column(conn, "snapshots", "bed_locator_mode", "TEXT")
            self._ensure_column(conn, "snapshots", "aruco_id", "INTEGER")
            self._ensure_column(conn, "snapshots", "similarity_score", "REAL")
            self._ensure_column(conn, "snapshots", "motion_px", "REAL")
            self._ensure_column(conn, "snapshots", "sharpness", "REAL")
            self._ensure_column(conn, "snapshots", "align_dx", "INTEGER")
            self._ensure_column(conn, "snapshots", "align_dy", "INTEGER")
            self._ensure_column(
                conn,
                "snapshots",
                "frame_before_trigger_ms",
                "INTEGER",
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_print_jobs_job_key "
                "ON print_jobs(job_key)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_print_jobs_status "
                "ON print_jobs(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_auth_sessions_token "
                "ON auth_sessions(token_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_debug_snapshots_job_layer "
                "ON debug_snapshots(job_id, layer)"
            )

            # One-time migration: previous-frame similarity is now the
            # primary composition-locking strategy.
            migrated = conn.execute(
                "SELECT value FROM app_settings "
                "WHERE key='vision_reference_primary_v1'"
            ).fetchone()

            if not migrated:
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """
                    INSERT INTO app_settings (key,value,updated_at)
                    VALUES ('vision_bed_locator_mode','reference',?)
                    ON CONFLICT(key) DO UPDATE SET
                        value='reference',
                        updated_at=excluded.updated_at
                    """,
                    (now,),
                )
                conn.execute(
                    """
                    INSERT INTO app_settings (key,value,updated_at)
                    VALUES ('vision_reference_primary_v1','true',?)
                    """,
                    (now,),
                )

            static_priority = conn.execute(
                "SELECT value FROM app_settings "
                "WHERE key='vision_static_priority_v1'"
            ).fetchone()

            if not static_priority:
                now = datetime.now(timezone.utc).isoformat()
                defaults = {
                    "vision_lookback_ms": "8000",
                    "vision_reference_similarity_threshold": "0.50",
                    "vision_motion_max_px": "2.5",
                    "vision_motion_stable_frames": "2",
                    "vision_sharpness_min": "60",
                }
                for key, value in defaults.items():
                    conn.execute(
                        """
                        INSERT INTO app_settings (key,value,updated_at)
                        VALUES (?,?,?)
                        ON CONFLICT(key) DO UPDATE SET
                            value=excluded.value,
                            updated_at=excluded.updated_at
                        """,
                        (key, value, now),
                    )
                conn.execute(
                    """
                    INSERT INTO app_settings (key,value,updated_at)
                    VALUES ('vision_static_priority_v1','true',?)
                    """,
                    (now,),
                )

    def get_app_setting(self, key, default=None):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key=?",
                (key,),
            ).fetchone()
            return row["value"] if row else default

    def get_app_settings(self, keys=None):
        with self.connect() as conn:
            if keys:
                placeholders = ",".join("?" for _ in keys)
                rows = conn.execute(
                    f"SELECT key,value FROM app_settings "
                    f"WHERE key IN ({placeholders})",
                    tuple(keys),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT key,value FROM app_settings"
                ).fetchall()

            return {
                row["key"]: row["value"]
                for row in rows
            }

    def set_app_settings(self, values):
        now = datetime.now(timezone.utc).isoformat()

        with self._lock, self.connect() as conn:
            for key, value in values.items():
                conn.execute(
                    """
                    INSERT INTO app_settings (key,value,updated_at)
                    VALUES (?,?,?)
                    ON CONFLICT(key) DO UPDATE SET
                        value=excluded.value,
                        updated_at=excluded.updated_at
                    """,
                    (key, str(value), now),
                )

    def add_debug_snapshot(
        self,
        job_id,
        layer,
        rewind_ms,
        actual_before_trigger_ms,
        file_path,
    ):
        now = datetime.now(timezone.utc).isoformat()

        with self._lock, self.connect() as conn:
            conn.execute(
                """
                INSERT INTO debug_snapshots
                (
                    job_id,
                    layer,
                    rewind_ms,
                    actual_before_trigger_ms,
                    file_path,
                    captured_at
                )
                VALUES (?,?,?,?,?,?)
                """,
                (
                    job_id,
                    layer,
                    rewind_ms,
                    actual_before_trigger_ms,
                    str(file_path),
                    now,
                ),
            )

    def get_debug_snapshot(self, debug_id):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM debug_snapshots WHERE id=?",
                (debug_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_debug_snapshots(self, job_id):
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM debug_snapshots
                WHERE job_id=?
                ORDER BY layer DESC, rewind_ms DESC
                """,
                (job_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_job(
        self,
        name,
        layer,
        total,
        progress,
        output_dir,
        bambu_task_id=None,
        bambu_subtask_id=None,
        job_key=None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO print_jobs (
                    name,
                    status,
                    started_at,
                    initial_layer,
                    current_layer,
                    total_layers,
                    progress,
                    output_dir,
                    bambu_task_id,
                    bambu_subtask_id,
                    job_key
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    name,
                    "PRINTING",
                    now,
                    layer,
                    layer,
                    total,
                    progress,
                    str(output_dir),
                    bambu_task_id,
                    bambu_subtask_id,
                    job_key,
                ),
            )
            return cur.lastrowid

    def update_job(self, job_id, **fields):
        if not fields:
            return

        keys = list(fields)
        sql = (
            "UPDATE print_jobs SET "
            + ", ".join(f"{key}=?" for key in keys)
            + " WHERE id=?"
        )
        values = [fields[key] for key in keys] + [job_id]

        with self._lock, self.connect() as conn:
            conn.execute(sql, values)

    def finish_job(self, job_id, status):
        now = datetime.now(timezone.utc).isoformat()
        self.update_job(
            job_id,
            status=status,
            finished_at=now,
        )

    def get_active_jobs(self):
        placeholders = ",".join("?" for _ in self.ACTIVE_STATUSES)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM print_jobs
                WHERE status IN ({placeholders})
                ORDER BY id DESC
                """,
                self.ACTIVE_STATUSES,
            ).fetchall()
            return [dict(row) for row in rows]

    def get_latest_active_job(self):
        jobs = self.get_active_jobs()
        return jobs[0] if jobs else None

    def get_job_by_key(self, job_key, active_only=False):
        if not job_key:
            return None

        with self.connect() as conn:
            if active_only:
                placeholders = ",".join("?" for _ in self.ACTIVE_STATUSES)
                row = conn.execute(
                    f"""
                    SELECT * FROM print_jobs
                    WHERE job_key=?
                      AND status IN ({placeholders})
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (job_key, *self.ACTIVE_STATUSES),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM print_jobs
                    WHERE job_key=?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (job_key,),
                ).fetchone()

            return dict(row) if row else None

    def supersede_other_active_jobs(self, keep_job_id):
        """Close duplicate active rows left by older restart behavior."""
        now = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in self.ACTIVE_STATUSES)
        params = [now, keep_job_id, *self.ACTIVE_STATUSES]

        with self._lock, self.connect() as conn:
            conn.execute(
                f"""
                UPDATE print_jobs
                SET status='SUPERSEDED', finished_at=?
                WHERE id != ?
                  AND status IN ({placeholders})
                """,
                params,
            )

    def supersede_job(self, job_id):
        now = datetime.now(timezone.utc).isoformat()
        self.update_job(
            job_id,
            status="SUPERSEDED",
            finished_at=now,
        )

    def add_snapshot(
        self,
        job_id,
        layer,
        file_path,
        status,
        duration_ms=None,
        error=None,
        source=None,
        frame_age_ms=None,
        frame_offset=None,
        rewind_ms=None,
        frame_before_trigger_ms=None,
        selection_mode=None,
        vision_score=None,
        vision_stable=None,
        bed_score=None,
        bed_stable=None,
        bed_locator_mode=None,
        aruco_id=None,
        similarity_score=None,
        motion_px=None,
        sharpness=None,
        align_dx=None,
        align_dy=None,
    ):
        now = datetime.now(timezone.utc).isoformat()

        with self._lock, self.connect() as conn:
            existing = conn.execute(
                "SELECT status FROM snapshots WHERE job_id=? AND layer=?",
                (job_id, layer),
            ).fetchone()

            conn.execute(
                """
                INSERT OR REPLACE INTO snapshots
                (
                    job_id,
                    layer,
                    file_path,
                    status,
                    captured_at,
                    duration_ms,
                    source,
                    frame_age_ms,
                    frame_offset,
                    rewind_ms,
                    frame_before_trigger_ms,
                    selection_mode,
                    vision_score,
                    vision_stable,
                    bed_score,
                    bed_stable,
                    bed_locator_mode,
                    aruco_id,
                    similarity_score,
                    motion_px,
                    sharpness,
                    align_dx,
                    align_dy,
                    error
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job_id,
                    layer,
                    str(file_path) if file_path else None,
                    status,
                    now,
                    duration_ms,
                    source,
                    frame_age_ms,
                    frame_offset,
                    rewind_ms,
                    frame_before_trigger_ms,
                    selection_mode,
                    vision_score,
                    (
                        None
                        if vision_stable is None
                        else int(bool(vision_stable))
                    ),
                    bed_score,
                    (
                        None
                        if bed_stable is None
                        else int(bool(bed_stable))
                    ),
                    bed_locator_mode,
                    aruco_id,
                    similarity_score,
                    motion_px,
                    sharpness,
                    align_dx,
                    align_dy,
                    error,
                ),
            )

            previous_status = existing["status"] if existing else None

            if status == "SUCCESS" and previous_status != "SUCCESS":
                conn.execute(
                    "UPDATE print_jobs "
                    "SET frame_count=frame_count+1 WHERE id=?",
                    (job_id,),
                )
            elif status == "FAILED" and previous_status is None:
                conn.execute(
                    "UPDATE print_jobs "
                    "SET failed_frames=failed_frames+1 WHERE id=?",
                    (job_id,),
                )

    def get_snapshot(self, snapshot_id):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM snapshots WHERE id=?",
                (snapshot_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_previous_snapshot(self, job_id, layer):
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM snapshots
                WHERE job_id=?
                  AND status='SUCCESS'
                  AND layer<?
                ORDER BY layer DESC, id DESC
                LIMIT 1
                """,
                (job_id, layer),
            ).fetchone()
            return dict(row) if row else None

    def get_latest_snapshot(self, job_id=None):
        with self.connect() as conn:
            if job_id is not None:
                row = conn.execute(
                    """
                    SELECT * FROM snapshots
                    WHERE job_id=? AND status='SUCCESS'
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (job_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM snapshots
                    WHERE status='SUCCESS'
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()

            return dict(row) if row else None

    def list_jobs(self, limit=100):
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM print_jobs
                WHERE status != 'SUPERSEDED'
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_job(self, job_id):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM print_jobs WHERE id=?",
                (job_id,),
            ).fetchone()

            if not row:
                return None

            job = dict(row)
            shots = conn.execute(
                "SELECT * FROM snapshots "
                "WHERE job_id=? ORDER BY layer",
                (job_id,),
            ).fetchall()
            job["snapshots"] = [dict(row) for row in shots]
            job["debug_snapshots"] = self.list_debug_snapshots(job_id)
            return job

    def user_count(self):
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
            return int(row["count"])

    def create_user(self, username, password_hash, must_change_password=True):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO users
                (username,password_hash,must_change_password,created_at,updated_at)
                VALUES (?,?,?,?,?)
                """,
                (
                    username,
                    password_hash,
                    1 if must_change_password else 0,
                    now,
                    now,
                ),
            )
            return cur.lastrowid

    def get_user_by_username(self, username):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username=?",
                (username,),
            ).fetchone()
            return dict(row) if row else None

    def get_user(self, user_id):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_user_password(self, user_id, password_hash, must_change_password=False):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self.connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET password_hash=?, must_change_password=?, updated_at=?
                WHERE id=?
                """,
                (
                    password_hash,
                    1 if must_change_password else 0,
                    now,
                    user_id,
                ),
            )

    def create_session(self, user_id, token_hash, created_at, expires_at):
        with self._lock, self.connect() as conn:
            conn.execute(
                """
                INSERT INTO auth_sessions
                (user_id,token_hash,created_at,expires_at)
                VALUES (?,?,?,?)
                """,
                (user_id, token_hash, created_at, expires_at),
            )

    def get_session_user(self, token_hash, now_iso):
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT u.*
                FROM auth_sessions s
                JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.expires_at>?
                LIMIT 1
                """,
                (token_hash, now_iso),
            ).fetchone()
            return dict(row) if row else None

    def delete_session(self, token_hash):
        with self._lock, self.connect() as conn:
            conn.execute(
                "DELETE FROM auth_sessions WHERE token_hash=?",
                (token_hash,),
            )

    def delete_user_sessions(self, user_id):
        with self._lock, self.connect() as conn:
            conn.execute(
                "DELETE FROM auth_sessions WHERE user_id=?",
                (user_id,),
            )

    def cleanup_expired_sessions(self, now_iso):
        with self._lock, self.connect() as conn:
            conn.execute(
                "DELETE FROM auth_sessions WHERE expires_at<=?",
                (now_iso,),
            )


db = Database()
