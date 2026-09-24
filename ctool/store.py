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
  tts_path TEXT,
  source_path TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT,
  finalized_at TEXT
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
    _migrate_jobs(conn)
    return conn


def _migrate_jobs(conn: sqlite3.Connection) -> None:
    for column, decl in (
        ("tts_path", "TEXT"),
        ("source_path", "TEXT"),
        ("finalized_at", "TEXT"),
    ):
        _ensure_column(conn, table="jobs", column=column, decl=decl)


JOB_STATUS_STT = "stt_ok"
JOB_STATUS_TTS = "tts_ok"
JOB_STATUS_FINAL = "final"


def status_label(status: str | None) -> str:
    mapping = {
        JOB_STATUS_STT: "Đã STT",
        JOB_STATUS_TTS: "Đã TTS",
        JOB_STATUS_FINAL: "Hoàn tất (khóa)",
    }
    return mapping.get((status or "").strip(), status or "?")


def get_job(job_id: str, root: str | Path | None = None) -> dict[str, Any] | None:
    jid = (job_id or "").strip()
    if not jid or not db_path(root).is_file():
        return None
    with connect(root) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
    return dict(row) if row else None


def assert_job_editable(job_id: str, root: str | Path | None = None) -> dict[str, Any]:
    row = get_job(job_id, root)
    if not row:
        raise ValueError(f"Không thấy job {job_id}")
    if row.get("status") == JOB_STATUS_FINAL:
        raise ValueError("Job đã **Final** — không chạy lại STT/TTS.")
    return row


def mark_job_final(job_id: str, root: str | Path | None = None) -> None:
    jid = (job_id or "").strip()
    row = get_job(jid, root)
    if not row:
        raise ValueError(f"Không thấy job {jid}")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with connect(root) as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, finalized_at = ?, finished_at = ? WHERE id = ?",
            (JOB_STATUS_FINAL, now, now, jid),
        )
        conn.commit()


def _safe_job_id(job_id: str) -> str:
    jid = (job_id or "").strip()
    if not jid or "/" in jid or "\\" in jid or ".." in jid:
        raise ValueError("job_id không hợp lệ.")
    return jid


def delete_job(job_id: str, root: str | Path | None = None) -> dict[str, Any]:
    """Erase job even if Final: SQLite rows + entire job folder. Nothing kept."""
    import shutil

    jid = _safe_job_id(job_id)
    row = get_job(jid, root)
    folder = job_dir(jid, root)
    extras: list[Path] = []
    if row:
        for key in ("transcript_path", "tts_path", "source_path"):
            raw = row.get(key)
            if raw:
                extras.append(Path(str(raw)))

    if db_path(root).is_file():
        with connect(root) as conn:
            conn.execute("DELETE FROM segments WHERE job_id = ?", (jid,))
            conn.execute("DELETE FROM speakers WHERE job_id = ?", (jid,))
            conn.execute("DELETE FROM jobs WHERE id = ?", (jid,))
            conn.commit()

    errors: list[str] = []
    if folder.is_dir():
        try:
            shutil.rmtree(folder)
        except OSError as exc:
            errors.append(f"folder: {exc}")

    store = resolve_store_root(root).resolve()
    jobs_root = (store / "jobs").resolve()
    folder_resolved = folder.resolve()
    for path in extras:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved == folder_resolved or folder_resolved in resolved.parents:
            continue
        if jobs_root not in resolved.parents and resolved.parent != jobs_root:
            continue
        try:
            if resolved.is_file():
                resolved.unlink()
            elif resolved.is_dir():
                shutil.rmtree(resolved)
        except OSError as exc:
            errors.append(f"{resolved.name}: {exc}")

    leftover = folder.is_dir()
    if leftover:
        errors.append("folder còn lại trên disk")
    if db_path(root).is_file() and get_job(jid, root):
        errors.append("còn dòng trong DB")
        leftover = True
    if leftover:
        raise RuntimeError(
            f"Xóa job {jid} chưa sạch: " + "; ".join(errors or ["còn file"])
        )
    return {"job_id": jid, "deleted": True}


def _archive_source_media(source: str | Path | None, folder: Path) -> str | None:
    if not source:
        return None
    src = Path(source)
    if not src.is_file():
        return None
    dest = folder / f"source{src.suffix.lower() or '.bin'}"
    if dest.is_file() and dest.stat().st_size > 0:
        return str(dest)
    try:
        import shutil

        shutil.copy2(src, dest)
        return str(dest)
    except OSError:
        return None


def _resolve_stt_input(row: dict[str, Any], folder: Path) -> str:
    from ctool.job_meta import read_meta

    meta = read_meta(folder)
    url = (row.get("input_url") or meta.get("input_url") or "").strip()
    if url:
        return url
    for key in ("source_path", "source_file"):
        rel = row.get(key) or meta.get(key)
        if rel:
            p = Path(str(rel))
            if not p.is_file():
                p = folder / Path(str(rel)).name
            if p.is_file():
                return str(p)
    archived = folder / "source.m4a"
    for cand in folder.glob("source.*"):
        if cand.is_file():
            return str(cand)
    raise ValueError(
        "Job không có URL/file nguồn để chạy lại STT. "
        "Chạy STT mới với cùng file hoặc lưu URL lần đầu."
    )


def save_transcript_job(
    payload: dict[str, Any],
    *,
    asr_model: str,
    min_speakers: int,
    max_speakers: int,
    input_url: str | None = None,
    language: str | None = None,
    store_root: str | Path | None = None,
    job_id: str | None = None,
    replace: bool = False,
    source_media_path: str | Path | None = None,
    stt_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write 01_transcript.json and index rows. Returns payload plus job metadata."""
    from ctool.job_meta import merge_meta

    source = payload.get("source") or {}
    filename = source.get("filename") or "unknown"
    jid = (job_id or payload.get("job_id") or "").strip() or new_job_id(filename)
    if replace:
        assert_job_editable(jid, store_root)

    root = resolve_store_root(store_root)
    folder = job_dir(jid, root)
    folder.mkdir(parents=True, exist_ok=True)

    archived = _archive_source_media(source_media_path, folder)
    transcript_path = folder / "01_transcript.json"
    lang = language or payload.get("language")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    stored = dict(payload)
    stored["job_id"] = jid
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

    meta_patch = {
        "input_url": input_url,
        "asr_model": asr_model,
        "min_speakers": int(min_speakers),
        "max_speakers": int(max_speakers),
        "language": lang,
        "source_file": Path(archived).name if archived else None,
    }
    if stt_meta:
        meta_patch.update(stt_meta)
    merge_meta(folder, meta_patch)

    with connect(root) as conn:
        if replace:
            conn.execute("DELETE FROM segments WHERE job_id = ?", (jid,))
            conn.execute("DELETE FROM speakers WHERE job_id = ?", (jid,))
            conn.execute(
                """
                UPDATE jobs SET
                  status = ?, input_url = ?, input_filename = ?, duration_sec = ?,
                  language = ?, asr_model = ?, min_speakers = ?, max_speakers = ?,
                  transcript_path = ?, source_path = ?, tts_path = NULL,
                  finished_at = ?, error = NULL
                WHERE id = ?
                """,
                (
                    JOB_STATUS_STT,
                    input_url,
                    filename,
                    source.get("duration"),
                    lang,
                    asr_model,
                    int(min_speakers),
                    int(max_speakers),
                    str(transcript_path),
                    archived,
                    now,
                    jid,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO jobs (
                  id, status, input_url, input_filename, duration_sec, language,
                  asr_model, min_speakers, max_speakers, transcript_path, source_path,
                  created_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    jid,
                    JOB_STATUS_STT,
                    input_url,
                    filename,
                    source.get("duration"),
                    lang,
                    asr_model,
                    int(min_speakers),
                    int(max_speakers),
                    str(transcript_path),
                    archived,
                    now,
                    now,
                ),
            )
        speaker_ids: dict[str, int] = {}
        for label in speakers:
            cur = conn.execute(
                "INSERT INTO speakers (job_id, label, display_name) VALUES (?, ?, ?)",
                (jid, label, None),
            )
            speaker_ids[label] = int(cur.lastrowid)
        for seg in segments:
            label = seg.get("speaker") or "SPEAKER_00"
            if label not in speaker_ids:
                cur = conn.execute(
                    "INSERT INTO speakers (job_id, label, display_name) VALUES (?, ?, ?)",
                    (jid, label, None),
                )
                speaker_ids[label] = int(cur.lastrowid)
            conn.execute(
                """
                INSERT INTO segments (job_id, speaker_id, start_sec, end_sec, text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    jid,
                    speaker_ids[label],
                    float(seg.get("start") or 0),
                    float(seg.get("end") or 0),
                    (seg.get("text") or "").strip(),
                ),
            )
        conn.commit()

    print(f"[OK] Store job {jid} → {folder}")
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


def list_jobs_dashboard(limit: int = 50, root: str | Path | None = None) -> list[dict[str, Any]]:
    db = db_path(root)
    if not db.is_file():
        return []
    with connect(root) as conn:
        rows = conn.execute(
            """
            SELECT
              j.id,
              j.status,
              j.input_filename,
              j.input_url,
              j.created_at,
              j.finished_at,
              j.finalized_at,
              j.transcript_path,
              j.tts_path,
              j.duration_sec,
              (SELECT COUNT(*) FROM segments s WHERE s.job_id = j.id) AS seg_count
            FROM jobs j
            ORDER BY j.created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["status_label"] = status_label(item.get("status"))
        tts_items = 0
        tpath = item.get("tts_path")
        if tpath and Path(tpath).is_file():
            try:
                manifest = json.loads(Path(tpath).read_text(encoding="utf-8"))
                tts_items = len(manifest.get("items") or [])
            except (json.JSONDecodeError, OSError):
                tts_items = 0
        item["tts_item_count"] = tts_items
        out.append(item)
    return out


def load_tts_manifest(job_id: str, root: str | Path | None = None) -> dict[str, Any] | None:
    row = get_job(job_id, root)
    if not row:
        return None
    path = row.get("tts_path")
    if path and Path(path).is_file():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    folder = job_dir(job_id, root)
    fallback = folder / "03_tts.json"
    if fallback.is_file():
        return json.loads(fallback.read_text(encoding="utf-8"))
    return None


def segment_dashboard_rows(job_id: str, root: str | Path | None = None) -> list[list]:
    """Rows for UI: [id, speaker, start, end, text, tts]."""
    payload = load_transcript(job_id, root=root)
    manifest = load_tts_manifest(job_id, root) or {}
    done_ids = {it.get("id") for it in (manifest.get("items") or []) if it.get("id")}
    rows: list[list] = []
    for i, seg in enumerate(payload.get("segments") or []):
        uid = f"u{i:04d}"
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        tts = "✓ TTS" if uid in done_ids else "—"
        rows.append(
            [
                uid,
                seg.get("speaker") or "SPEAKER_00",
                round(float(seg.get("start") or 0), 2),
                round(float(seg.get("end") or 0), 2),
                text[:120] + ("…" if len(text) > 120 else ""),
                tts,
            ]
        )
    return rows


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
            row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row and row["status"] == JOB_STATUS_FINAL:
                raise ValueError("Job đã Final — không gen TTS.")
            conn.execute(
                "UPDATE jobs SET status = ?, tts_path = ?, finished_at = ? WHERE id = ?",
                (JOB_STATUS_TTS, str(path), now, job_id),
            )
            conn.commit()
    return path
