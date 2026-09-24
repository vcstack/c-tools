#!/usr/bin/env python3
"""Colab Gradio UI — runs on Colab's Python, not the whisper-jax venv.

Install Gradio into the notebook kernel, then:
    python colab_app.py

The pipeline still runs as /content/ctool-venv/bin/python main.py
so huggingface-hub / JAX pins stay isolated.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

os.environ["MPLBACKEND"] = "Agg"
try:
    import matplotlib

    matplotlib.use("Agg")
except Exception:
    pass

ROOT = Path("/content/c-tools")
if not ROOT.is_dir():
    ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from ctool.runtime_env import pipeline_env  # noqa: E402

PY = Path("/content/ctool-venv/bin/python")
OUT = ROOT / "output" / "result.json"
SAMPLE_URL = "https://github.com/openai/whisper/raw/main/tests/jfk.flac"
SAMPLE_PATH = ROOT / "input" / "jfk.flac"


def _ensure_sample() -> Path:
    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SAMPLE_PATH.is_file() or SAMPLE_PATH.stat().st_size == 0:
        urllib.request.urlretrieve(SAMPLE_URL, SAMPLE_PATH)
    return SAMPLE_PATH


def _as_path(media_file) -> Path | None:
    if media_file is None:
        return None
    if isinstance(media_file, dict):
        media_file = media_file.get("name") or media_file.get("path")
    elif not isinstance(media_file, (str, Path)):
        media_file = getattr(media_file, "name", None)
    if not media_file:
        return None
    path = Path(str(media_file))
    return path if path.is_file() else None


def _resolve_cookies_path(cookies_file, cookies_text) -> Path | None:
    cookies = _as_path(cookies_file)
    pasted = (cookies_text or "").strip()
    if pasted:
        from pipeline.download import cookies_text_to_file

        cookies = cookies_text_to_file(pasted, ROOT / "input" / "cookies.txt")
    return cookies


def _chunk_panel_hidden():
    import gradio as gr
    from pipeline.chunking import MAX_CUT_SLIDERS

    hidden = gr.update(visible=False)
    parts: list = []
    for _ in range(MAX_CUT_SLIDERS):
        parts.extend([hidden, hidden, hidden])
    return (hidden, "", None, *parts)


def load_chunk_panel(media_url, media_file, cookies_file, cookies_text, auto_chunk):
    import gradio as gr
    from pipeline.chunking import (
        MAX_CUT_SLIDERS,
        boundary_slider_limits,
        default_boundaries,
        format_mmss,
        needs_chunking,
        probe_media_duration,
    )

    url = (media_url or "").strip()
    local = _as_path(media_file)
    if not url and not local:
        return _chunk_panel_hidden()
    source = url if url else str(local)
    cookies = _resolve_cookies_path(cookies_file, cookies_text)
    dur = probe_media_duration(source, cookies)
    if dur is None:
        return (
            gr.update(visible=False),
            "Không đo được độ dài (thử upload file hoặc kiểm tra URL/cookies).",
            None,
            *(_chunk_panel_hidden()[3:]),
        )
    if not auto_chunk:
        long = needs_chunking(dur)
        hint = (
            f"Độ dài ~**{format_mmss(dur)}** — **không cắt** (chưa bật tự động cắt). "
            "File dài dễ OOM trên Colab free."
            if long
            else f"Độ dài ~**{format_mmss(dur)}** — STT một lần."
        )
        return (
            gr.update(visible=long),
            hint,
            dur,
            *(_chunk_panel_hidden()[3:]),
        )

    if not needs_chunking(dur):
        return (
            gr.update(visible=False),
            f"Độ dài ~**{format_mmss(dur)}** — dưới 8 phút, STT một lần (không cắt).",
            dur,
            *(_chunk_panel_hidden()[3:]),
        )

    bounds = default_boundaries(dur)
    n = len(bounds)
    info = (
        f"Độ dài ~**{format_mmss(dur)}** → **{n + 1} phần** (số phần cố định). "
        "Kéo **mép cắt**, **Nghe quanh mép** để kiểm tra, rồi **Run**. "
        f"Mỗi phần tối đa 10 phút, chồng {3:.0f}s khi STT."
    )
    row_updates = []
    for i in range(MAX_CUT_SLIDERS):
        if i < n:
            lo, hi = boundary_slider_limits(dur, bounds, i)
            row_updates.extend(
                [
                    gr.update(visible=True),
                    gr.update(
                        visible=True,
                        value=bounds[i],
                        minimum=lo,
                        maximum=hi,
                        step=0.5,
                        label=f"Mép {i + 1}/{n} · {format_mmss(bounds[i])}",
                    ),
                    gr.update(visible=True),
                ]
            )
        else:
            row_updates.extend([gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)])
    return (gr.update(visible=True), info, dur, *row_updates)


def preview_cut_audio(media_url, media_file, cut_sec):
    from pipeline.chunking import extract_preview_clip, format_mmss

    local = _as_path(media_file)
    if not local:
        return None, "Preview cần **upload file** (URL vẫn Run được, nhưng không nghe thử trước)."
    try:
        center = float(cut_sec)
    except (TypeError, ValueError):
        return None, "Chọn mép cắt trước."
    out = Path(tempfile.gettempdir()) / f"ctool_cut_preview_{os.getpid()}.wav"
    try:
        extract_preview_clip(local, out, center, window_sec=10.0)
    except Exception as exc:
        return None, f"Preview lỗi: {exc}"
    return str(out), f"Nghe quanh **{format_mmss(center)}** (±5s)."


def _chunk_cuts_for_cli(source, use_sample, cookies, auto_chunk, slider_values):
    from pipeline.chunking import default_boundaries, needs_chunking, probe_media_duration, validate_boundaries

    if use_sample or not auto_chunk:
        return None, None
    dur = probe_media_duration(source, cookies)
    if dur is None or not needs_chunking(dur):
        return None, None
    n = len(default_boundaries(dur))
    cuts = [float(slider_values[i]) for i in range(n)]
    try:
        cuts = validate_boundaries(dur, cuts)
    except ValueError as exc:
        return None, str(exc)
    return ",".join(f"{c:.2f}" for c in cuts), None


def _pipeline_exit_message(code: int) -> str:
    if code in (-9, 137):
        return (
            "Colab kill process (exit -9): hết RAM/VRAM khi load/chạy whisper. "
            "Thử model small hoặc medium, batch size 2–4, Runtime → Restart runtime, "
            "rồi Run lại. large-v2/large-v3 dễ OOM trên Colab free."
        )
    return f"Pipeline failed (exit {code})"


def run_job(
    media_url,
    media_file,
    hf_token,
    model,
    language,
    min_speakers,
    max_speakers,
    cookies_file=None,
    cookies_text=None,
    batch_size=4,
    auto_chunk=False,
    *cut_sliders,
):
    if not PY.is_file():
        return "Chưa có venv. Chạy cell Reset + cài trước.", "", None, None

    url = (media_url or "").strip()
    local = _as_path(media_file)
    if url:
        source = url
    elif local:
        source = str(local)
    else:
        return "Dán Media URL (YouTube, ...) hoặc upload file. Hoặc bấm Test.", "", None, None

    OUT.parent.mkdir(parents=True, exist_ok=True)
    env = pipeline_env(os.environ.copy())
    token = (hf_token or "").strip()
    env["HF_TOKEN"] = token
    env["HUGGING_FACE_HUB_TOKEN"] = token

    cmd = [
        str(PY),
        str(ROOT / "main.py"),
        "--input",
        source,
        "--output",
        str(OUT),
        "--model",
        model or "medium",
        "--batch-size",
        str(max(1, int(batch_size or 4))),
        "--min-speakers",
        str(int(min_speakers or 1)),
        "--max-speakers",
        str(int(max_speakers or 10)),
        "--device",
        "auto",
    ]
    lang = (language or "").strip()
    if lang:
        cmd.extend(["--language", lang])
    cookies = _resolve_cookies_path(cookies_file, cookies_text)
    if auto_chunk:
        cmd.append("--auto-chunk")
    cuts_str, cut_err = _chunk_cuts_for_cli(source, False, cookies, auto_chunk, cut_sliders)
    if cut_err:
        return cut_err, "", None, None
    if cuts_str:
        cmd.extend(["--chunk-cuts", cuts_str])
    if cookies:
        cmd.extend(["--cookies", str(cookies)])
    store_dir = (os.environ.get("CTOOL_STORE") or "").strip()
    if store_dir:
        cmd.extend(["--store-dir", store_dir])

    print(" ".join(cmd), flush=True)
    code = subprocess.call(cmd, env=env, cwd=str(ROOT))
    if code != 0 or not OUT.is_file():
        return _pipeline_exit_message(code), "", None, None

    data = json.loads(OUT.read_text(encoding="utf-8"))
    rows = [
        [seg.get("speaker"), seg.get("start"), seg.get("end"), seg.get("text")]
        for seg in data.get("segments", [])
    ]
    job_id = data.get("job_id") or ""
    store = (data.get("store") or {}).get("job_dir") or ""
    status = (
        f"{data.get('source', {}).get('filename')} · "
        f"{len(data.get('speakers', []))} speakers · "
        f"{len(rows)} segments"
        + (f" · job {job_id}" if job_id else "")
        + (f" · {store}" if store else "")
    )
    pretty = json.dumps(data, ensure_ascii=False, indent=2)
    return status, pretty, rows, str(OUT)


def run_test():
    # JFK clip, tiny, 1 speaker — no HF token needed
    return _run_sample_job()


def _run_sample_job():
    if not PY.is_file():
        return "Chưa có venv. Chạy cell Reset + cài trước.", "", None, None
    source = str(_ensure_sample())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    env = pipeline_env(os.environ.copy())
    cmd = [
        str(PY),
        str(ROOT / "main.py"),
        "--input",
        source,
        "--output",
        str(OUT),
        "--model",
        "tiny",
        "--batch-size",
        "1",
        "--min-speakers",
        "1",
        "--max-speakers",
        "1",
        "--device",
        "auto",
        "--language",
        "en",
    ]
    store_dir = (os.environ.get("CTOOL_STORE") or "").strip()
    if store_dir:
        cmd.extend(["--store-dir", store_dir])
    print(" ".join(cmd), flush=True)
    code = subprocess.call(cmd, env=env, cwd=str(ROOT))
    if code != 0 or not OUT.is_file():
        return _pipeline_exit_message(code), "", None, None
    data = json.loads(OUT.read_text(encoding="utf-8"))
    rows = [
        [seg.get("speaker"), seg.get("start"), seg.get("end"), seg.get("text")]
        for seg in data.get("segments", [])
    ]
    job_id = data.get("job_id") or ""
    status = (
        f"{data.get('source', {}).get('filename')} · "
        f"{len(data.get('speakers', []))} speakers · "
        f"{len(rows)} segments"
        + (f" · job {job_id}" if job_id else "")
    )
    return status, json.dumps(data, ensure_ascii=False, indent=2), rows, str(OUT)


def dash_refresh_table():
    from ctool.dashboard import jobs_overview_table

    return jobs_overview_table()


MAX_SEG_ROWS = 8


def _dash_action_response(message: str, job_id, page=0):
    parts = dash_select_job(job_id, page)
    return (message,) + tuple(parts[:-1])


def _seg_row_updates(job_id, page=0):
    import gradio as gr
    from ctool.segments import list_segment_records
    from ctool.store import JOB_STATUS_FINAL, get_job

    jid = (job_id or "").strip()
    locked = False
    recs: list = []
    if jid:
        row = get_job(jid)
        locked = bool(row and row.get("status") == JOB_STATUS_FINAL)
        try:
            recs = list_segment_records(jid)
        except Exception:
            recs = []
    page = max(0, int(page or 0))
    max_page = max(0, (len(recs) - 1) // MAX_SEG_ROWS) if recs else 0
    page = min(page, max_page)
    start = page * MAX_SEG_ROWS
    shown = recs[start : start + MAX_SEG_ROWS]
    info = (
        f"Câu **{start + 1}–{start + len(shown)}** / {len(recs)} (trang {page + 1}/{max_page + 1})"
        if recs
        else "Chưa có câu."
    )
    prefs = _tts_prefs()
    voices, _ok = fetch_voice_catalog(prefs.get("vieneu_api_key"))
    fallback = (prefs.get("voice_0") or (voices[0] if voices else "Ngọc Lan")).strip()
    updates: list = [info, page]
    for i in range(MAX_SEG_ROWS):
        if i < len(shown):
            r = shown[i]
            voice = r.get("voice") or fallback
            row_voices = list(voices)
            if voice not in row_voices:
                row_voices = [voice] + row_voices
            updates.extend(
                [
                    gr.update(visible=True),
                    gr.update(value=r["id"]),
                    gr.update(
                        value=f"**{r['id']}** · {r['speaker']} · {r['start']:.1f}s · {r['tts']}"
                    ),
                    gr.update(value=r["text"], interactive=not locked),
                    gr.update(choices=row_voices, value=voice, visible=True, interactive=not locked),
                    gr.update(visible=True, interactive=not locked),
                    gr.update(visible=True, interactive=not locked),
                    gr.update(visible=True, interactive=not locked),
                ]
            )
        else:
            updates.extend(
                [
                    gr.update(visible=False),
                    gr.update(value=""),
                    gr.update(value=""),
                    gr.update(value=""),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False),
                ]
            )
    return tuple(updates)


def dash_select_job(job_id, page=0):
    import gradio as gr
    from ctool.dashboard import job_detail_text
    from ctool.store import JOB_STATUS_FINAL, get_job

    jid = (job_id or "").strip()
    detail = job_detail_text(jid) if jid else "Chọn job bên trái."
    row = get_job(jid) if jid else None
    locked = bool(row and row.get("status") == JOB_STATUS_FINAL)
    lock_msg = "Job đã Final — STT/TTS/sửa bị khóa." if locked else ""
    btn = gr.update(interactive=not locked)
    return (
        detail,
        btn,
        btn,
        btn,
        jid,
        *_seg_row_updates(jid, page),
        lock_msg,
    )


def dash_open_job(job_id):
    return dash_select_job(job_id, 0)


def _as_table_rows(data) -> list:
    if data is None:
        return []
    if hasattr(data, "values"):
        try:
            return data.values.tolist()
        except Exception:
            pass
    if isinstance(data, dict):
        if "data" in data:
            return list(data.get("data") or [])
        cols = data.get("value")
        if isinstance(cols, list):
            return cols
    if isinstance(data, list):
        return data
    return []


def dash_table_select(evt, table_data=None):
    rows = _as_table_rows(table_data) or dash_refresh_table()
    jid = None
    if evt is not None:
        idx = getattr(evt, "index", None)
        row_i = idx[0] if isinstance(idx, (list, tuple)) else idx
        try:
            jid = rows[int(row_i)][0]
        except (TypeError, ValueError, IndexError):
            val = getattr(evt, "value", None)
            if isinstance(val, str) and val.strip():
                jid = val.strip()
    import gradio as gr

    parts = dash_select_job(jid, 0)
    return tuple(parts) + (gr.update(value=jid or None),)


def dash_close_panel():
    parts = dash_select_job(None)
    return ("",) + tuple(parts[:-1])


def dash_seg_select(evt, job_id):
    from ctool.store import segment_dashboard_rows

    jid = (job_id or "").strip()
    if not jid or evt is None:
        return "", ""
    try:
        rows = segment_dashboard_rows(jid)
    except Exception:
        return "", ""
    idx = getattr(evt, "index", None)
    row_i = idx[0] if isinstance(idx, (list, tuple)) else idx
    try:
        row_i = int(row_i)
    except (TypeError, ValueError):
        return "", ""
    if row_i < 0 or row_i >= len(rows):
        return "", ""
    uid = rows[row_i][0]
    return uid, f"Đã chọn **{uid}** — bấm Gen lại câu này."


def dash_rerun_stt(job_id, hf_token):
    from ctool.dashboard import stt_rerun_command
    from ctool.store import job_dir

    if not PY.is_file():
        return _dash_action_response("Chưa có venv.", job_id)
    jid = (job_id or "").strip()
    if not jid:
        return _dash_action_response("Chọn job.", job_id)
    try:
        out = job_dir(jid) / "01_transcript.json"
        store_dir = (os.environ.get("CTOOL_STORE") or "").strip()
        cmd, _extra = stt_rerun_command(
            jid,
            python_bin=PY,
            main_py=ROOT / "main.py",
            output_json=out,
            store_dir=store_dir or None,
        )
    except ValueError as exc:
        return _dash_action_response(str(exc), job_id)
    env = pipeline_env(os.environ.copy())
    token = (hf_token or "").strip()
    env["HF_TOKEN"] = token
    env["HUGGING_FACE_HUB_TOKEN"] = token
    code = subprocess.call(cmd, env=env, cwd=str(ROOT))
    if code != 0:
        return _dash_action_response(_pipeline_exit_message(code), job_id)
    return _dash_action_response(f"Re-STT xong · job {jid}", job_id)


def _dash_tts(job_id, api_key, selected_ids, all_segments: bool, voice: str | None = None):
    from ctool.dashboard import voice_map_from_prefs
    from ctool.settings import load_settings
    from ctool.store import assert_job_editable, load_transcript
    from ctool.tts_job import run_vieneu_tts

    jid = (job_id or "").strip()
    if not jid:
        raise ValueError("Chọn job.")
    assert_job_editable(jid)
    prefs = load_settings()
    payload = load_transcript(jid)
    two = str(prefs.get("tts_count") or "1") == "2"
    mapping = voice_map_from_prefs(prefs, payload, two)
    chosen = (voice or "").strip()
    only_ids = None
    if not all_segments:
        only_ids = []
        for raw in selected_ids or []:
            uid = str(raw).split("·", 1)[0].strip()
            if uid:
                only_ids.append(uid)
        if not only_ids:
            raise ValueError("Chọn ít nhất một câu (hoặc bấm Gen TTS toàn bộ).")
    run_vieneu_tts(
        api_key,
        job_id=jid,
        default_voice=chosen or prefs.get("voice_0") or "Ngọc Lan",
        voice_map=None if chosen else mapping,
        only_speakers=None if chosen else list(mapping.keys()),
        single_voice=chosen or None,
        only_item_ids=only_ids,
    )


def dash_rerun_tts_all(job_id, api_key, voice=None):
    try:
        _dash_tts(job_id, api_key, [], True, voice=voice)
        msg = f"Gen TTS toàn bộ xong · {(voice or '').strip() or 'map giọng settings'}."
    except Exception as exc:
        return _dash_action_response(str(exc), job_id)
    return _dash_action_response(msg, job_id)


def dash_edit_seg():
    import gradio as gr

    return gr.update(interactive=True), gr.update(visible=True)


def dash_save_seg(job_id, uid, text, page):
    from ctool.segments import update_segment_text

    jid = (job_id or "").strip()
    try:
        update_segment_text(jid, (uid or "").strip(), text)
        msg = f"Đã lưu {(uid or '').strip()}."
    except Exception as exc:
        return _dash_action_response(str(exc), jid, page)
    return _dash_action_response(msg, jid, page)


def dash_del_seg(job_id, uid, page):
    from ctool.segments import delete_segment

    jid = (job_id or "").strip()
    try:
        delete_segment(jid, (uid or "").strip())
        msg = f"Đã xóa {(uid or '').strip()}."
    except Exception as exc:
        return _dash_action_response(str(exc), jid, page)
    return _dash_action_response(msg, jid, page)


def dash_tts_seg(job_id, api_key, uid, voice, page):
    jid = (job_id or "").strip()
    try:
        _dash_tts(jid, api_key, [(uid or "").strip()], False, voice=voice)
        msg = f"TTS {(uid or '').strip()} · {(voice or '').strip() or 'giọng mặc định'} xong."
    except Exception as exc:
        return _dash_action_response(str(exc), jid, page)
    return _dash_action_response(msg, jid, page)


def dash_page_nav(job_id, page, delta):
    from ctool.segments import list_segment_records

    jid = (job_id or "").strip()
    recs = []
    if jid:
        try:
            recs = list_segment_records(jid)
        except Exception:
            recs = []
    max_page = max(0, (len(recs) - 1) // MAX_SEG_ROWS) if recs else 0
    p = min(max_page, max(0, int(page or 0) + int(delta)))
    return _dash_action_response("", jid, p)


def dash_page_prev(job_id, page):
    return dash_page_nav(job_id, page, -1)


def dash_page_next(job_id, page):
    return dash_page_nav(job_id, page, 1)


def dash_rerun_tts_pick(job_id, api_key, selected, utt_id=None, voice=None):
    picks = list(selected or [])
    uid = (utt_id or "").strip()
    if not picks and uid:
        picks = [uid]
    try:
        _dash_tts(job_id, api_key, picks, False, voice=voice)
        msg = f"Gen lại {len(picks)} câu xong · {(voice or '').strip() or 'map giọng settings'}."
    except Exception as exc:
        return _dash_action_response(str(exc), job_id)
    return _dash_action_response(msg, job_id)


def dash_finalize(job_id):
    from ctool.dashboard import finalize_job

    try:
        msg = finalize_job(job_id)
    except ValueError as exc:
        return _dash_action_response(str(exc), job_id)
    return _dash_action_response(msg, job_id)


def dash_delete_job(job_id, confirm):
    import gradio as gr
    from ctool.dashboard import purge_job

    keep_confirm = gr.update()
    jid = (job_id or "").strip()
    if not jid:
        return (
            *_dash_action_response("Chọn job rồi bấm Mở chi tiết.", job_id),
            dash_refresh_table(),
            keep_confirm,
            refresh_jobs(),
        )
    if not confirm:
        return (
            *_dash_action_response("Tick **Xác nhận xóa** rồi bấm Xóa job.", job_id),
            dash_refresh_table(),
            keep_confirm,
            refresh_jobs(),
        )
    try:
        msg = purge_job(jid)
    except Exception as exc:
        return (
            *_dash_action_response(str(exc), job_id),
            dash_refresh_table(),
            keep_confirm,
            refresh_jobs(),
        )
    ids = _job_ids()
    return (
        *_dash_action_response(msg, None),
        dash_refresh_table(),
        gr.update(value=False),
        gr.update(choices=ids, value=None),
    )


def _job_ids() -> list[str]:
    from ctool.store import list_jobs

    return [row["id"] for row in list_jobs()]


def refresh_jobs():
    ids = _job_ids()
    value = ids[0] if ids else None
    try:
        import gradio as gr

        return gr.update(choices=ids, value=value)
    except Exception:
        return ids


def _tts_prefs():
    from ctool.settings import load_settings

    return load_settings()


def fetch_voice_catalog(api_key: str | None = None) -> tuple[list[str], bool]:
    """Return (voices, ok). ok=True only when the VieNeu API returned a list."""
    from ctool.vieneu import FALLBACK_VOICES, list_voices

    key = (api_key or "").strip()
    if not key:
        return list(FALLBACK_VOICES), False
    try:
        fetched = list_voices(key)
        if fetched:
            return fetched, True
    except Exception:
        pass
    return list(FALLBACK_VOICES), False


def _voice_choices(api_key: str | None = None) -> list[str]:
    names, _ok = fetch_voice_catalog(api_key)
    return names


def load_job_speakers(job_id, json_file, tts_count):
    from ctool.settings import load_settings, speakers_from_payload
    from ctool.store import load_transcript
    import gradio as gr

    prefs = load_settings()
    try:
        payload = load_transcript((job_id or "").strip() or None, _as_path(json_file))
        speakers = speakers_from_payload(payload)
    except Exception:
        speakers = ["SPEAKER_00"]
    two = str(tts_count).strip().startswith("2")
    spk0 = speakers[0]
    spk1 = speakers[1] if len(speakers) > 1 else speakers[0]
    info = " + ".join(speakers) if len(speakers) > 1 else f"{spk0} (JSON 1 speaker)"
    voices, _ok = fetch_voice_catalog(prefs.get("vieneu_api_key"))
    v0 = prefs.get("voice_0") or "Ngọc Lan"
    v1 = prefs.get("voice_1") or "Phạm Tuyên"
    if v0 not in voices:
        voices = [v0] + voices
    if v1 not in voices:
        voices = [v1] + [x for x in voices if x != v1]
    has_source = bool((job_id or "").strip()) or bool(_as_path(json_file))
    return (
        gr.update(choices=speakers, value=spk0),
        gr.update(choices=speakers, value=spk1, visible=two),
        gr.update(choices=voices, value=v0),
        gr.update(choices=voices, value=v1, visible=two),
        gr.update(visible=not two),
        gr.update(value=info),
        gr.update(visible=has_source),
    )


def refresh_voice_list(api_key, voice_0, voice_1):
    import gradio as gr

    voices, ok = fetch_voice_catalog(api_key)
    v0 = voice_0 if voice_0 in voices else (voices[0] if voices else "Ngọc Lan")
    v1 = voice_1 if voice_1 in voices else (voices[1] if len(voices) > 1 else v0)
    status = "Đã tải list giọng VieNeu." if ok else "Không tải được list giọng. Bấm Tải lại sau khi kiểm tra API key."
    return (
        gr.update(choices=voices, value=v0),
        gr.update(choices=voices, value=v1),
        gr.update(visible=not ok),
        status,
    )


def persist_tts_settings(api_key, voice_0, voice_1, tts_count, sample_text, one_mode):
    from ctool.settings import save_settings

    save_settings(
        vieneu_api_key=api_key,
        voice_0=voice_0,
        voice_1=voice_1,
        tts_count=tts_count,
        sample_text=sample_text,
        one_mode=one_mode,
    )
    return "Đã lưu key + giọng vào bảng settings (ctool.db)."


def _copy_for_gradio(src: Path) -> Path:
    import shutil
    import tempfile

    dest = Path(tempfile.gettempdir()) / src.name
    shutil.copy2(src, dest)
    return dest


def test_tts(api_key, voice_0, sample_text):
    from ctool.settings import save_settings
    from ctool.vieneu import synthesize

    save_settings(vieneu_api_key=api_key, voice_0=voice_0, sample_text=sample_text)
    text = (sample_text or "").strip() or "Xin chào, đây là giọng VieNeu V4."
    voice = (voice_0 or "Ngọc Lan").strip()
    dest = Path(tempfile.gettempdir()) / "ctool_tts_test.mp3"
    try:
        path = synthesize(api_key, text, voice, dest=dest)
    except Exception as exc:
        return f"Test TTS failed: {exc}", None
    return f"Test OK · {voice} · {text[:80]}", str(path)


def run_tts_job(
    job_id, json_file, api_key, tts_count, speaker_0, speaker_1, voice_0, voice_1, one_mode
):
    from ctool.settings import save_settings
    from ctool.tts_job import run_vieneu_tts

    save_settings(
        vieneu_api_key=api_key,
        voice_0=voice_0,
        voice_1=voice_1,
        tts_count=tts_count,
        one_mode=one_mode,
    )
    json_path = _as_path(json_file)
    jid = (job_id or "").strip() or None
    two = str(tts_count).strip().startswith("2")
    spk0 = (speaker_0 or "SPEAKER_00").strip()
    v0 = (voice_0 or "Ngọc Lan").strip()
    try:
        if two:
            spk1 = (speaker_1 or "").strip() or spk0
            mapping = {spk0: v0}
            if spk1 != spk0:
                mapping[spk1] = (voice_1 or v0).strip()
            manifest = run_vieneu_tts(
                api_key,
                job_id=jid,
                json_path=json_path,
                default_voice=v0,
                voice_map=mapping,
                only_speakers=list(mapping.keys()),
            )
        elif "Chỉ" in str(one_mode or ""):
            manifest = run_vieneu_tts(
                api_key,
                job_id=jid,
                json_path=json_path,
                default_voice=v0,
                single_voice=v0,
                only_speakers=[spk0],
            )
        else:
            manifest = run_vieneu_tts(
                api_key,
                job_id=jid,
                json_path=json_path,
                default_voice=v0,
                single_voice=v0,
            )
    except Exception as exc:
        return str(exc), "", None, None

    folder = Path(manifest["store"]["job_dir"])
    tts_json = manifest["store"]["tts_json"]
    if tts_json and Path(tts_json).is_file():
        tts_json = str(_copy_for_gradio(Path(tts_json)))
    audio = None
    rel = manifest.get("audio")
    if rel:
        cand = folder / rel
        if cand.is_file():
            audio = str(_copy_for_gradio(cand))
    status = (
        f"TTS OK · job {manifest.get('job_id')} · "
        f"{len(manifest.get('items', []))} utterances · {folder}"
    )
    return status, json.dumps(manifest, ensure_ascii=False, indent=2), tts_json, audio


_UI_CSS = """
.gradio-container { max-width: 1180px !important; }
#dash-detail {
  border: 1px solid rgba(15, 23, 42, 0.10);
  border-radius: 12px;
  padding: 8px 10px 4px;
  background: #f8fafc;
}
#dash-jobs .table-wrap { max-height: 420px; overflow: auto; }
.seg-line textarea { min-height: 42px !important; }
"""


def _gradio_theme():
    import gradio as gr

    try:
        return gr.themes.Soft(primary_hue="indigo", secondary_hue="slate")
    except Exception:
        return None


def build_ui():
    import gradio as gr
    from pipeline.chunking import MAX_CUT_SLIDERS

    theme = _gradio_theme()
    blocks_kw = {"title": "C-tool", "css": _UI_CSS}
    if theme is not None:
        blocks_kw["theme"] = theme

    with gr.Blocks(**blocks_kw) as demo:
        gr.Markdown(
            "# C-tool\n"
            "STT → TTS → quản lý job trên Drive. "
            "**Colab free:** `medium` + batch 4."
        )
        with gr.Tabs():
            with gr.Tab("STT"):
                with gr.Row():
                    with gr.Column(scale=1, elem_id="stt-main"):
                        media_url = gr.Textbox(
                            label="Media URL",
                            placeholder="https://www.youtube.com/watch?v=...",
                        )
                        media = gr.File(
                            label="Hoặc upload file",
                            file_types=[
                                ".mp4",
                                ".mkv",
                                ".mov",
                                ".avi",
                                ".mp3",
                                ".wav",
                                ".m4a",
                                ".flac",
                            ],
                        )
                        auto_chunk_cb = gr.Checkbox(
                            label="Tự động cắt file dài (> ~8 phút)",
                            value=False,
                        )
                        chunk_duration = gr.State(None)
                        with gr.Group(visible=False) as chunk_group:
                            chunk_info = gr.Markdown("")
                            cut_rows: list = []
                            cut_sliders: list = []
                            cut_preview_btns: list = []
                            for idx in range(MAX_CUT_SLIDERS):
                                with gr.Row(visible=False) as cut_row:
                                    cut_rows.append(cut_row)
                                    cut_sliders.append(
                                        gr.Slider(
                                            minimum=0,
                                            maximum=100,
                                            step=0.5,
                                            visible=False,
                                            label=f"Mép cắt {idx + 1}",
                                        )
                                    )
                                    cut_preview_btns.append(
                                        gr.Button("Nghe quanh mép", size="sm", visible=False)
                                    )
                            chunk_preview_audio = gr.Audio(
                                label="Nghe thử quanh mép",
                                type="filepath",
                                interactive=False,
                            )
                            chunk_preview_status = gr.Textbox(
                                label="Preview",
                                interactive=False,
                                lines=1,
                            )
                        with gr.Row():
                            run_btn = gr.Button("Run STT", variant="primary")
                            test_btn = gr.Button("Test (JFK)")
                        with gr.Accordion("Nâng cao (cookies, model, speaker)", open=False):
                            cookies_text = gr.Textbox(
                                label="YouTube cookies",
                                placeholder="Dán cookies.txt hoặc Cookie: ...",
                                lines=3,
                            )
                            cookies = gr.File(
                                label="Hoặc upload cookies.txt",
                                file_types=[".txt"],
                            )
                            hf_token = gr.Textbox(label="Hugging Face token", type="password")
                            model = gr.Dropdown(
                                ["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                                value="medium",
                                label="whisper-jax model",
                            )
                            batch_size = gr.Number(label="Batch size", value=4, precision=0)
                            language = gr.Textbox(
                                label="Language code",
                                placeholder="trống = auto (en, vi, ja, ...)",
                            )
                            with gr.Row():
                                min_speakers = gr.Number(label="Min speakers", value=1, precision=0)
                                max_speakers = gr.Number(label="Max speakers", value=10, precision=0)
                    with gr.Column(scale=2):
                        status = gr.Textbox(label="Status", lines=2)
                        table = gr.Dataframe(
                            headers=["speaker", "start", "end", "text"],
                            label="Segments",
                            wrap=True,
                        )
                        download = gr.File(label="Download result.json")
                        with gr.Accordion("JSON đầy đủ", open=False):
                            json_out = gr.Code(label="JSON", language="json")

                outputs = [status, json_out, table, download]
                chunk_panel_outputs = [
                    chunk_group,
                    chunk_info,
                    chunk_duration,
                    *[
                        x
                        for i in range(MAX_CUT_SLIDERS)
                        for x in (cut_rows[i], cut_sliders[i], cut_preview_btns[i])
                    ],
                ]
                chunk_inputs = [media_url, media, cookies, cookies_text, auto_chunk_cb]
                media_url.change(load_chunk_panel, inputs=chunk_inputs, outputs=chunk_panel_outputs)
                media.change(load_chunk_panel, inputs=chunk_inputs, outputs=chunk_panel_outputs)
                cookies_text.change(load_chunk_panel, inputs=chunk_inputs, outputs=chunk_panel_outputs)
                cookies.change(load_chunk_panel, inputs=chunk_inputs, outputs=chunk_panel_outputs)
                auto_chunk_cb.change(load_chunk_panel, inputs=chunk_inputs, outputs=chunk_panel_outputs)
                for i, btn in enumerate(cut_preview_btns):
                    btn.click(
                        preview_cut_audio,
                        inputs=[media_url, media, cut_sliders[i]],
                        outputs=[chunk_preview_audio, chunk_preview_status],
                    )
                run_btn.click(
                    run_job,
                    inputs=[
                        media_url,
                        media,
                        hf_token,
                        model,
                        language,
                        min_speakers,
                        max_speakers,
                        cookies,
                        cookies_text,
                        batch_size,
                        auto_chunk_cb,
                        *cut_sliders,
                    ],
                    outputs=outputs,
                )
                test_btn.click(run_test, inputs=[], outputs=outputs)

            with gr.Tab("TTS VieNeu V4"):
                prefs = _tts_prefs()
                two_on = str(prefs.get("tts_count") or "1") == "2"
                init_voices, voices_ok = fetch_voice_catalog(prefs.get("vieneu_api_key"))
                with gr.Row():
                    with gr.Column(scale=1):
                        job_dd = gr.Dropdown(
                            choices=_job_ids(),
                            label="Chọn job đã STT",
                            allow_custom_value=True,
                        )
                        refresh_btn = gr.Button("Làm mới danh sách")
                        tts_json_in = gr.File(
                            label="Hoặc upload transcript JSON",
                            file_types=[".json"],
                        )
                        with gr.Group(visible=False, elem_id="tts-map") as tts_map:
                            speaker_info = gr.Textbox(label="Speaker trong JSON", interactive=False)
                            tts_count = gr.Radio(
                                ["1", "2"],
                                value=prefs.get("tts_count") or "1",
                                label="Số giọng",
                            )
                            one_mode = gr.Radio(
                                ["Cả file", "Chỉ speaker A"],
                                value=prefs.get("one_mode") or "Cả file",
                                label="Khi 1 giọng",
                                visible=not two_on,
                            )
                            speaker_0 = gr.Dropdown(
                                choices=["SPEAKER_00"],
                                value="SPEAKER_00",
                                label="Speaker A",
                                allow_custom_value=True,
                            )
                            voice_0 = gr.Dropdown(
                                choices=init_voices,
                                value=prefs.get("voice_0")
                                if prefs.get("voice_0") in init_voices
                                else (init_voices[0] if init_voices else "Ngọc Lan"),
                                label="Giọng A",
                                allow_custom_value=True,
                            )
                            speaker_1 = gr.Dropdown(
                                choices=["SPEAKER_01"],
                                value="SPEAKER_01",
                                label="Speaker B",
                                allow_custom_value=True,
                                visible=two_on,
                            )
                            voice_1 = gr.Dropdown(
                                choices=init_voices,
                                value=prefs.get("voice_1")
                                if prefs.get("voice_1") in init_voices
                                else (init_voices[1] if len(init_voices) > 1 else init_voices[0]),
                                label="Giọng B",
                                allow_custom_value=True,
                                visible=two_on,
                            )
                            tts_btn = gr.Button("Gen TTS", variant="primary")
                        with gr.Accordion("API key + test giọng", open=False):
                            vieneu_key = gr.Textbox(
                                label="VieNeu API key",
                                type="password",
                                value=prefs.get("vieneu_api_key") or "",
                            )
                            load_voices_btn = gr.Button(
                                "Tải lại list giọng",
                                visible=not voices_ok,
                            )
                            sample_text = gr.Textbox(
                                label="Câu test",
                                value=prefs.get("sample_text")
                                or "Xin chào, đây là giọng VieNeu V4.",
                                lines=2,
                            )
                            save_pref_btn = gr.Button("Lưu key + giọng")
                            test_tts_btn = gr.Button("Test TTS")
                    with gr.Column(scale=2):
                        tts_status = gr.Textbox(label="Status", lines=2)
                        tts_audio = gr.Audio(label="Audio", type="filepath")
                        tts_json_dl = gr.File(label="Download 03_tts.json")
                        with gr.Accordion("03_tts.json", open=False):
                            tts_json_out = gr.Code(label="03_tts.json", language="json")
                speaker_outs = [speaker_0, speaker_1, voice_0, voice_1, one_mode, speaker_info, tts_map]
                refresh_btn.click(refresh_jobs, outputs=[job_dd])
                job_dd.change(
                    load_job_speakers,
                    inputs=[job_dd, tts_json_in, tts_count],
                    outputs=speaker_outs,
                )
                tts_json_in.change(
                    load_job_speakers,
                    inputs=[job_dd, tts_json_in, tts_count],
                    outputs=speaker_outs,
                )
                tts_count.change(
                    load_job_speakers,
                    inputs=[job_dd, tts_json_in, tts_count],
                    outputs=speaker_outs,
                )
                key_evt = getattr(vieneu_key, "blur", None) or vieneu_key.change
                key_evt(
                    refresh_voice_list,
                    inputs=[vieneu_key, voice_0, voice_1],
                    outputs=[voice_0, voice_1, load_voices_btn, tts_status],
                )
                load_voices_btn.click(
                    refresh_voice_list,
                    inputs=[vieneu_key, voice_0, voice_1],
                    outputs=[voice_0, voice_1, load_voices_btn, tts_status],
                )
                save_pref_btn.click(
                    persist_tts_settings,
                    inputs=[vieneu_key, voice_0, voice_1, tts_count, sample_text, one_mode],
                    outputs=[tts_status],
                )
                test_tts_btn.click(
                    test_tts,
                    inputs=[vieneu_key, voice_0, sample_text],
                    outputs=[tts_status, tts_audio],
                )
                tts_btn.click(
                    run_tts_job,
                    inputs=[
                        job_dd,
                        tts_json_in,
                        vieneu_key,
                        tts_count,
                        speaker_0,
                        speaker_1,
                        voice_0,
                        voice_1,
                        one_mode,
                    ],
                    outputs=[tts_status, tts_json_out, tts_json_dl, tts_audio],
                )

            with gr.Tab("Dashboard"):
                dash_job = gr.Textbox(visible=False, value="")
                dash_page = gr.State(0)
                _dash_voices, _ = fetch_voice_catalog(_tts_prefs().get("vieneu_api_key"))
                _voice0 = _tts_prefs().get("voice_0")
                if _voice0 not in (_dash_voices or []):
                    _voice0 = (_dash_voices or ["Ngọc Lan"])[0]
                with gr.Row():
                    with gr.Column(scale=2, min_width=260, elem_id="dash-jobs"):
                        with gr.Row():
                            dash_pick = gr.Dropdown(
                                choices=_job_ids(),
                                label="Job",
                                allow_custom_value=True,
                                scale=3,
                            )
                            dash_refresh = gr.Button("Làm mới", scale=1)
                        dash_table = gr.Dataframe(
                            headers=["job", "file", "status", "seg", "tts", "created"],
                            label="Jobs",
                            interactive=True,
                            wrap=True,
                        )
                    with gr.Column(scale=5, elem_id="dash-detail"):
                        dash_detail = gr.Markdown("Chọn job bên trái.")
                        dash_status = gr.Textbox(show_label=False, lines=1, placeholder="Status")
                        with gr.Row():
                            dash_stt_btn = gr.Button("Re-STT")
                            dash_tts_all_btn = gr.Button("TTS all")
                            dash_voice = gr.Dropdown(
                                choices=_dash_voices or ["Ngọc Lan"],
                                value=_voice0,
                                label="Giọng all",
                                allow_custom_value=True,
                                scale=2,
                            )
                            dash_final_btn = gr.Button("Final", variant="primary")
                            dash_confirm_del = gr.Checkbox(label="Xóa job?", value=False)
                            dash_delete_btn = gr.Button("Xóa", variant="stop")
                        with gr.Row():
                            dash_seg_info = gr.Markdown("Chưa có câu.")
                            dash_prev = gr.Button("←")
                            dash_next = gr.Button("→")
                        seg_rows_ui: list = []
                        seg_uids: list = []
                        seg_labels: list = []
                        seg_texts: list = []
                        seg_voices: list = []
                        seg_save_btns: list = []
                        seg_tts_btns: list = []
                        seg_del_btns: list = []
                        for _idx in range(MAX_SEG_ROWS):
                            with gr.Row(visible=False, elem_classes=["seg-line"]) as seg_row:
                                seg_rows_ui.append(seg_row)
                                seg_uids.append(gr.Textbox(visible=False, value=""))
                                seg_labels.append(gr.Markdown("", elem_classes=["seg-id"]))
                                seg_texts.append(
                                    gr.Textbox(
                                        show_label=False,
                                        lines=2,
                                        scale=4,
                                        placeholder="Nội dung câu",
                                    )
                                )
                                seg_voices.append(
                                    gr.Dropdown(
                                        choices=_dash_voices or ["Ngọc Lan"],
                                        value=_voice0,
                                        show_label=False,
                                        allow_custom_value=True,
                                        scale=2,
                                    )
                                )
                                seg_save_btns.append(gr.Button("Lưu", scale=1))
                                seg_tts_btns.append(gr.Button("TTS", scale=1))
                                seg_del_btns.append(gr.Button("Xóa", variant="stop", scale=1))
                        with gr.Accordion("Token", open=False):
                            dash_vieneu = gr.Textbox(
                                label="VieNeu API key",
                                type="password",
                                value=_tts_prefs().get("vieneu_api_key") or "",
                            )
                            dash_hf = gr.Textbox(label="HF token (re-STT)", type="password")

                seg_row_outs = [
                    x
                    for i in range(MAX_SEG_ROWS)
                    for x in (
                        seg_rows_ui[i],
                        seg_uids[i],
                        seg_labels[i],
                        seg_texts[i],
                        seg_voices[i],
                        seg_save_btns[i],
                        seg_tts_btns[i],
                        seg_del_btns[i],
                    )
                ]
                select_outs = [
                    dash_detail,
                    dash_stt_btn,
                    dash_tts_all_btn,
                    dash_final_btn,
                    dash_job,
                    dash_seg_info,
                    dash_page,
                    *seg_row_outs,
                    dash_status,
                ]
                dash_action_outputs = [
                    dash_status,
                    dash_detail,
                    dash_stt_btn,
                    dash_tts_all_btn,
                    dash_final_btn,
                    dash_job,
                    dash_seg_info,
                    dash_page,
                    *seg_row_outs,
                ]

                dash_refresh.click(dash_refresh_table, outputs=[dash_table])
                dash_refresh.click(refresh_jobs, outputs=[dash_pick])
                demo.load(dash_refresh_table, outputs=[dash_table])
                dash_pick.change(dash_open_job, inputs=[dash_pick], outputs=select_outs)
                dash_table.select(
                    dash_table_select,
                    inputs=[dash_table],
                    outputs=[*select_outs, dash_pick],
                )
                dash_prev.click(
                    dash_page_prev,
                    inputs=[dash_job, dash_page],
                    outputs=dash_action_outputs,
                )
                dash_next.click(
                    dash_page_next,
                    inputs=[dash_job, dash_page],
                    outputs=dash_action_outputs,
                )
                for i in range(MAX_SEG_ROWS):
                    seg_save_btns[i].click(
                        dash_save_seg,
                        inputs=[dash_job, seg_uids[i], seg_texts[i], dash_page],
                        outputs=dash_action_outputs,
                    )
                    seg_del_btns[i].click(
                        dash_del_seg,
                        inputs=[dash_job, seg_uids[i], dash_page],
                        outputs=dash_action_outputs,
                    )
                    seg_tts_btns[i].click(
                        dash_tts_seg,
                        inputs=[dash_job, dash_vieneu, seg_uids[i], seg_voices[i], dash_page],
                        outputs=dash_action_outputs,
                    )
                dash_stt_btn.click(
                    dash_rerun_stt,
                    inputs=[dash_job, dash_hf],
                    outputs=dash_action_outputs,
                )
                dash_tts_all_btn.click(
                    dash_rerun_tts_all,
                    inputs=[dash_job, dash_vieneu, dash_voice],
                    outputs=dash_action_outputs,
                )
                dash_final_btn.click(
                    dash_finalize,
                    inputs=[dash_job],
                    outputs=dash_action_outputs,
                )
                dash_delete_btn.click(
                    dash_delete_job,
                    inputs=[dash_job, dash_confirm_del],
                    outputs=[*dash_action_outputs, dash_table, dash_confirm_del, dash_pick],
                )
    return demo


def launch_ui(share: bool = True, server_name: str = "0.0.0.0") -> None:
    if not PY.is_file():
        raise SystemExit("Chưa có venv. Chạy cell Reset + cài trước.")
    try:
        import gradio  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Gradio must be installed on Colab's Python, not the venv:\n"
            "  import sys\n"
            '  !{sys.executable} -m pip install -q "gradio>=4.44,<6"\n'
            "  !{sys.executable} /content/c-tools/colab_app.py"
        ) from exc

    demo = build_ui()
    try:
        demo.queue()
    except Exception:
        pass
    from ctool.store import resolve_store_root

    allowed = [str(ROOT), "/tmp", str(resolve_store_root())]
    drive = Path("/content/drive/MyDrive")
    if drive.is_dir():
        allowed.append(str(drive))
    launch_kw = {"share": share, "server_name": server_name, "allowed_paths": allowed}
    try:
        demo.launch(inline=True, **launch_kw)
    except TypeError:
        try:
            demo.launch(**launch_kw)
        except TypeError:
            demo.launch(share=share, server_name=server_name)


if __name__ == "__main__":
    launch_ui(share=True)
