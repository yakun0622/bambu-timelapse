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
                    error TEXT,
                    UNIQUE(job_id, layer)
                );
                """
            )

            # Migration path for existing installations.
            self._ensure_column(conn, "print_jobs", "bambu_task_id", "TEXT")
            self._ensure_column(conn, "print_jobs", "bambu_subtask_id", "TEXT")
            self._ensure_column(conn, "print_jobs", "job_key", "TEXT")

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_print_jobs_job_key "
                "ON print_jobs(job_key)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_print_jobs_status "
                "ON print_jobs(status)"
            )

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
                (job_id,layer,file_path,status,captured_at,duration_ms,error)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    job_id,
                    layer,
                    str(file_path) if file_path else None,
                    status,
                    now,
                    duration_ms,
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
            return job


db = Database()
