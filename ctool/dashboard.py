"""Job dashboard: status, re-STT, partial TTS, Final lock."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ctool.job_meta import read_meta
from ctool.store import (
    JOB_STATUS_FINAL,
    assert_job_editable,
    delete_job,
    get_job,
    job_dir,
    list_jobs_dashboard,
    load_tts_manifest,
    mark_job_final,
    segment_dashboard_rows,
    status_label,
    _resolve_stt_input,
)


def jobs_overview_table(root: str | Path | None = None) -> list[list]:
    rows: list[list] = []
    for job in list_jobs_dashboard(root=root):
        rows.append(
            [
                job.get("id"),
                job.get("input_filename") or "",
                job.get("status_label") or status_label(job.get("status")),
                job.get("seg_count") or 0,
                job.get("tts_item_count") or 0,
                (job.get("created_at") or "")[:19],
            ]
        )
    return rows


def job_detail_text(job_id: str | None, root: str | Path | None = None) -> str:
    jid = (job_id or "").strip()
    if not jid:
        return "Chọn job."
    row = get_job(jid, root)
    if not row:
        return f"Không thấy job {jid}."
    folder = job_dir(jid, root)
    meta = read_meta(folder)
    manifest = load_tts_manifest(jid, root)
    locked = row.get("status") == JOB_STATUS_FINAL
    lines = [
        f"**Job:** `{jid}`",
        f"**Trạng thái:** {status_label(row.get('status'))}",
        f"**File:** {row.get('input_filename') or '—'}",
        f"**STT:** {'✓' if row.get('transcript_path') else '—'} · model {row.get('asr_model') or meta.get('asr_model') or '—'}",
        f"**TTS:** {'✓ ' + str(len(manifest.get('items') or [])) + ' câu' if manifest else '—'}",
        f"**Final:** {'✓ khóa STT/TTS' if locked else 'Chưa'}",
    ]
    if row.get("input_url"):
        lines.append(f"**URL gốc:** có (re-STT được)")
    elif (folder / "source.m4a").exists() or list(folder.glob("source.*")):
        lines.append("**File nguồn:** có trong job folder")
    else:
        lines.append("**Nguồn re-STT:** chỉ URL hoặc file đã lưu — nếu thiếu, upload STT lại.")
    return "\n\n".join(lines)


def segment_choices(job_id: str | None, root: str | Path | None = None) -> list[str]:
    jid = (job_id or "").strip()
    if not jid:
        return []
    out: list[str] = []
    for row in segment_dashboard_rows(jid, root):
        uid, _spk, start, _end, text, tts = row
        mark = "✓" if tts.startswith("✓") else "○"
        out.append(f"{uid} · {mark} · {start}s · {text}")
    return out


def stt_rerun_command(
    job_id: str,
    *,
    python_bin: str | Path,
    main_py: str | Path,
    output_json: str | Path,
    store_dir: str | Path | None,
    root: str | Path | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Build subprocess argv + env patches for re-STT."""
    jid = (job_id or "").strip()
    assert_job_editable(jid, root)
    row = get_job(jid, root)
    if not row:
        raise ValueError(f"Không thấy job {jid}")
    folder = job_dir(jid, root)
    meta = read_meta(folder)
    source = _resolve_stt_input(row, folder)

    cmd = [
        str(python_bin),
        str(main_py),
        "--input",
        source,
        "--output",
        str(output_json),
        "--job-id",
        jid,
        "--replace-job",
        "--model",
        str(meta.get("asr_model") or row.get("asr_model") or "medium"),
        "--batch-size",
        str(int(meta.get("batch_size") or 4)),
        "--min-speakers",
        str(int(meta.get("min_speakers") or row.get("min_speakers") or 1)),
        "--max-speakers",
        str(int(meta.get("max_speakers") or row.get("max_speakers") or 10)),
        "--device",
        "auto",
    ]
    lang = (meta.get("language") or row.get("language") or "").strip()
    if lang:
        cmd.extend(["--language", lang])
    auto_chunk = meta.get("auto_chunk")
    if auto_chunk is None:
        auto_chunk = bool((meta.get("chunk_cuts") or "").strip())
    if auto_chunk:
        cmd.append("--auto-chunk")
        cuts = (meta.get("chunk_cuts") or "").strip()
        if cuts:
            cmd.extend(["--chunk-cuts", cuts])
    if store_dir:
        cmd.extend(["--store-dir", str(store_dir)])
    return cmd, {}


def voice_map_from_prefs(prefs: dict[str, Any], payload: dict[str, Any], two_voices: bool) -> dict[str, str]:
    from ctool.settings import speakers_from_payload

    speakers = speakers_from_payload(payload)
    v0 = (prefs.get("voice_0") or "Ngọc Lan").strip()
    v1 = (prefs.get("voice_1") or v0).strip()
    spk0 = speakers[0]
    mapping = {spk0: v0}
    if two_voices and len(speakers) > 1:
        mapping[speakers[1]] = v1
    elif len(speakers) > 1:
        mapping[speakers[1]] = v1
    return mapping


def finalize_job(job_id: str | None, root: str | Path | None = None) -> str:
    jid = (job_id or "").strip()
    if not jid:
        raise ValueError("Chọn job.")
    row = get_job(jid, root)
    if not row:
        raise ValueError(f"Không thấy job {jid}")
    if row.get("status") == JOB_STATUS_FINAL:
        return f"Job {jid} đã Final rồi."
    mark_job_final(jid, root)
    return f"Đã Final job {jid} — không chạy lại STT/TTS."


def purge_job(job_id: str | None, root: str | Path | None = None) -> str:
    jid = (job_id or "").strip()
    if not jid:
        raise ValueError("Chọn job.")
    delete_job(jid, root)
    return f"Đã xóa hết job {jid}: DB + folder (transcript, TTS, source)."
