import sqlite3
import threading
from datetime import datetime, timezone

from app.core.config import settings


class Database:
    def __init__(self):
        self.path = settings.database_path
        self._lock = threading.Lock()
        self.init_schema()

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

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
                    video_path TEXT
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

    def create_job(self, name, layer, total, progress, output_dir):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO print_jobs
                (name,status,started_at,initial_layer,current_layer,total_layers,progress,output_dir)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (name, "PRINTING", now, layer, layer, total, progress, str(output_dir)),
            )
            return cur.lastrowid

    def update_job(self, job_id, **fields):
        if not fields:
            return
        keys = list(fields)
        sql = "UPDATE print_jobs SET " + ", ".join(f"{k}=?" for k in keys) + " WHERE id=?"
        values = [fields[k] for k in keys] + [job_id]
        with self._lock, self.connect() as conn:
            conn.execute(sql, values)

    def finish_job(self, job_id, status):
        now = datetime.now(timezone.utc).isoformat()
        self.update_job(job_id, status=status, finished_at=now)

    def add_snapshot(self, job_id, layer, file_path, status, duration_ms=None, error=None):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO snapshots
                (job_id,layer,file_path,status,captured_at,duration_ms,error)
                VALUES (?,?,?,?,?,?,?)
                """,
                (job_id, layer, str(file_path) if file_path else None, status, now, duration_ms, error),
            )
            if status == "SUCCESS":
                conn.execute("UPDATE print_jobs SET frame_count=frame_count+1 WHERE id=?", (job_id,))
            elif status == "FAILED":
                conn.execute("UPDATE print_jobs SET failed_frames=failed_frames+1 WHERE id=?", (job_id,))

    def list_jobs(self, limit=100):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM print_jobs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_job(self, job_id):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM print_jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return None
            job = dict(row)
            shots = conn.execute(
                "SELECT * FROM snapshots WHERE job_id=? ORDER BY layer", (job_id,)
            ).fetchall()
            job["snapshots"] = [dict(r) for r in shots]
            return job


db = Database()
