"""SQLite index + job folders. Drive when mounted, otherwise local data/ctool."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DRIVE_ROOT = Path("/content/drive/MyDrive/ctool")
LOCAL_ROOT = Path("data") / "ctool"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  input_url TEXT,
  input_filename TEXT,
  duration_sec REAL,
  language TEXT,
  asr_model TEXT,
  min_speakers INTEGER,
  max_speakers INTEGER,
  transcript_path TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS speakers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  display_name TEXT,
  UNIQUE (job_id, label)
);

CREATE TABLE IF NOT EXISTS segments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  speaker_id INTEGER NOT NULL REFERENCES speakers(id) ON DELETE CASCADE,
  start_sec REAL NOT NULL,
  end_sec REAL NOT NULL,
  text TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_segments_job_start ON segments (job_id, start_sec);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs (created_at);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
"""


def resolve_store_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = (os.environ.get("CTOOL_STORE") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if Path("/content/drive/MyDrive").is_dir():
        return DRIVE_ROOT
    return Path.cwd() / LOCAL_ROOT


def db_path(root: str | Path | None = None) -> Path:
    return resolve_store_root(root) / "ctool.db"


def job_dir(job_id: str, root: str | Path | None = None) -> Path:
    return resolve_store_root(root) / "jobs" / job_id


def new_job_id(filename: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    stem = Path(filename or "job").stem
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", stem).strip("-._")[:40] or "job"
    return f"{stamp}-{slug}"


def connect(root: str | Path | None = None) -> sqlite3.Connection:
    base = resolve_store_root(root)
    base.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(base / "ctool.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 8000")
    # DELETE journal: safer on Google Drive than WAL extra files
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.executescript(SCHEMA)
    return conn


def save_transcript_job(
    payload: dict[str, Any],
    *,
    asr_model: str,
    min_speakers: int,
    max_speakers: int,
    input_url: str | None = None,
    language: str | None = None,
    store_root: str | Path | None = None,
) -> dict[str, Any]:
    """Write 01_transcript.json and index rows. Returns payload plus job metadata."""
    source = payload.get("source") or {}
    filename = source.get("filename") or "unknown"
    job_id = payload.get("job_id") or new_job_id(filename)
    root = resolve_store_root(store_root)
    folder = job_dir(job_id, root)
    folder.mkdir(parents=True, exist_ok=True)

    transcript_path = folder / "01_transcript.json"
    lang = language or payload.get("language")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    stored = dict(payload)
    stored["job_id"] = job_id
    stored["language"] = lang
    stored["store"] = {
        "root": str(root),
        "job_dir": str(folder),
        "transcript": str(transcript_path),
        "db": str(root / "ctool.db"),
    }
    transcript_path.write_text(
        json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    speakers = list(stored.get("speakers") or [])
    segments = list(stored.get("segments") or [])
    if not speakers:
        speakers = sorted({s.get("speaker") or "SPEAKER_00" for s in segments})

    with connect(root) as conn:
        conn.execute(
            """
            INSERT INTO jobs (
              id, status, input_url, input_filename, duration_sec, language,
              asr_model, min_speakers, max_speakers, transcript_path,
              created_at, finished_at
            ) VALUES (?, 'stt_ok', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                input_url,
                filename,
                source.get("duration"),
                lang,
                asr_model,
                int(min_speakers),
                int(max_speakers),
                str(transcript_path),
                now,
                now,
            ),
        )
        speaker_ids: dict[str, int] = {}
        for label in speakers:
            cur = conn.execute(
                "INSERT INTO speakers (job_id, label, display_name) VALUES (?, ?, ?)",
                (job_id, label, None),
            )
            speaker_ids[label] = int(cur.lastrowid)
        for seg in segments:
            label = seg.get("speaker") or "SPEAKER_00"
            if label not in speaker_ids:
                cur = conn.execute(
                    "INSERT INTO speakers (job_id, label, display_name) VALUES (?, ?, ?)",
                    (job_id, label, None),
                )
                speaker_ids[label] = int(cur.lastrowid)
            conn.execute(
                """
                INSERT INTO segments (job_id, speaker_id, start_sec, end_sec, text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    speaker_ids[label],
                    float(seg.get("start") or 0),
                    float(seg.get("end") or 0),
                    (seg.get("text") or "").strip(),
                ),
            )
        conn.commit()

    print(f"[OK] Store job {job_id} → {folder}")
    return stored


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if any(r["name"] == column for r in rows):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def list_jobs(limit: int = 40, root: str | Path | None = None) -> list[dict[str, Any]]:
    db = db_path(root)
    if not db.is_file():
        return []
    with connect(root) as conn:
        rows = conn.execute(
            """
            SELECT id, status, input_filename, created_at, transcript_path
            FROM jobs ORDER BY created_at DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


def load_transcript(
    job_id: str | None = None,
    json_path: str | Path | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    if json_path:
        path = Path(json_path)
        if not path.is_file():
            raise FileNotFoundError(f"JSON not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    jid = (job_id or "").strip()
    if not jid:
        raise ValueError("Cần job_id hoặc đường dẫn JSON transcript.")
    path = job_dir(jid, root) / "01_transcript.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    if db_path(root).is_file():
        with connect(root) as conn:
            row = conn.execute(
                "SELECT transcript_path FROM jobs WHERE id = ?", (jid,)
            ).fetchone()
        if row and row["transcript_path"] and Path(row["transcript_path"]).is_file():
            return json.loads(Path(row["transcript_path"]).read_text(encoding="utf-8"))
    raise FileNotFoundError(f"Không thấy transcript cho job {jid}")


def save_tts_job(
    job_id: str,
    manifest: dict[str, Any],
    root: str | Path | None = None,
) -> Path:
    folder = job_dir(job_id, root)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "03_tts.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if db_path(root).is_file():
        with connect(root) as conn:
            _ensure_column(conn, "jobs", "tts_path", "TEXT")
            conn.execute(
                "UPDATE jobs SET status = ?, tts_path = ?, finished_at = ? WHERE id = ?",
                ("tts_ok", str(path), now, job_id),
            )
            conn.commit()
    return path
