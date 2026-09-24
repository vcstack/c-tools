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
    use_sample=False,
):
    if not PY.is_file():
        return "Chưa có venv. Chạy cell Reset + cài trước.", "", None, None

    if use_sample:
        source = str(_ensure_sample())
    else:
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
    cookies = _as_path(cookies_file)
    pasted = (cookies_text or "").strip()
    if pasted:
        from pipeline.download import cookies_text_to_file

        cookies = cookies_text_to_file(pasted, ROOT / "input" / "cookies.txt")
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
    return run_job("", None, "", "tiny", "en", 1, 1, use_sample=True)


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


def _voice_choices(api_key: str | None = None) -> list[str]:
    from ctool.vieneu import FALLBACK_VOICES, list_voices

    names = list(FALLBACK_VOICES)
    key = (api_key or "").strip()
    if key:
        try:
            fetched = list_voices(key)
            if fetched:
                names = fetched
        except Exception:
            pass
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
    voices = _voice_choices(prefs.get("vieneu_api_key"))
    v0 = prefs.get("voice_0") or "Ngọc Lan"
    v1 = prefs.get("voice_1") or "Phạm Tuyên"
    if v0 not in voices:
        voices = [v0] + voices
    if v1 not in voices:
        voices = [v1] + [x for x in voices if x != v1]
    return (
        gr.update(choices=speakers, value=spk0),
        gr.update(choices=speakers, value=spk1, visible=two),
        gr.update(choices=voices, value=v0),
        gr.update(choices=voices, value=v1, visible=two),
        gr.update(visible=not two),
        gr.update(value=info),
    )


def refresh_voice_list(api_key, voice_0, voice_1):
    import gradio as gr

    voices = _voice_choices(api_key)
    v0 = voice_0 if voice_0 in voices else (voices[0] if voices else "Ngọc Lan")
    v1 = voice_1 if voice_1 in voices else (voices[1] if len(voices) > 1 else v0)
    return gr.update(choices=voices, value=v0), gr.update(choices=voices, value=v1)


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


def test_tts(api_key, voice_0, sample_text):
    from ctool.settings import save_settings
    from ctool.store import resolve_store_root
    from ctool.vieneu import synthesize

    save_settings(vieneu_api_key=api_key, voice_0=voice_0, sample_text=sample_text)
    text = (sample_text or "").strip() or "Xin chào, đây là giọng VieNeu V4."
    voice = (voice_0 or "Ngọc Lan").strip()
    dest = resolve_store_root() / "tts_test.mp3"
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
    audio = None
    rel = manifest.get("audio")
    if rel:
        cand = folder / rel
        if cand.is_file():
            audio = str(cand)
    status = (
        f"TTS OK · job {manifest.get('job_id')} · "
        f"{len(manifest.get('items', []))} utterances · {folder}"
    )
    return status, json.dumps(manifest, ensure_ascii=False, indent=2), tts_json, audio


def build_ui():
    import gradio as gr

    with gr.Blocks(title="C-tool") as demo:
        gr.Markdown("# C-tool")
        with gr.Tabs():
            with gr.Tab("STT"):
                gr.Markdown(
                    "Video / audio → whisper-jax + pyannote → JSON.\n\n"
                    "Colab IP hay bị YouTube hỏi login. Dán cookies "
                    "([yt-dlp wiki](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies)).\n\n"
                    "**Colab free:** `medium` + batch 4. `large-v2` dễ exit -9 (OOM).\n\n"
                    "Lưu: SQLite + folder job (`CTOOL_STORE=/content/drive/MyDrive/ctool`)."
                )
                with gr.Row():
                    with gr.Column(scale=1):
                        media_url = gr.Textbox(
                            label="Media URL",
                            placeholder="https://www.youtube.com/watch?v=...",
                        )
                        media = gr.File(
                            label="Hoặc upload file (không bắt buộc)",
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
                        cookies_text = gr.Textbox(
                            label="YouTube cookies (dán, không cần upload file)",
                            placeholder="Dán cookies.txt hoặc Cookie: ...",
                            lines=4,
                        )
                        cookies = gr.File(
                            label="Hoặc upload cookies.txt",
                            file_types=[".txt"],
                        )
                        hf_token = gr.Textbox(label="Hugging Face token", type="password")
                        model = gr.Dropdown(
                            ["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                            value="medium",
                            label="whisper-jax model (Colab: tránh large nếu exit -9)",
                        )
                        batch_size = gr.Number(label="Batch size", value=4, precision=0)
                        language = gr.Textbox(
                            label="Language code",
                            placeholder="auto-detect if empty (en, vi, ja, ...)",
                        )
                        with gr.Row():
                            min_speakers = gr.Number(label="Min speakers", value=1, precision=0)
                            max_speakers = gr.Number(label="Max speakers", value=10, precision=0)
                        with gr.Row():
                            run_btn = gr.Button("Run", variant="primary")
                            test_btn = gr.Button("Test (JFK)")
                    with gr.Column(scale=2):
                        status = gr.Textbox(label="Status", lines=2)
                        table = gr.Dataframe(
                            headers=["speaker", "start", "end", "text"],
                            label="Segments",
                            wrap=True,
                        )
                        json_out = gr.Code(label="JSON", language="json")
                        download = gr.File(label="Download result.json")

                outputs = [status, json_out, table, download]
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
                    ],
                    outputs=outputs,
                )
                test_btn.click(run_test, inputs=[], outputs=outputs)

            with gr.Tab("TTS VieNeu V4"):
                prefs = _tts_prefs()
                two_on = str(prefs.get("tts_count") or "1") == "2"
                gr.Markdown(
                    "Cloud **V4**. Key + giọng lưu bảng **`settings`** trong `ctool.db` "
                    "(file DB trên Drive thì tắt Colab vẫn còn).\n\n"
                    "JSON có 2 speaker vẫn chọn **gen 1 hoặc 2 giọng**."
                )
                with gr.Row():
                    with gr.Column(scale=1):
                        job_dd = gr.Dropdown(
                            choices=_job_ids(),
                            label="Job (sau khi STT + store)",
                            allow_custom_value=True,
                        )
                        refresh_btn = gr.Button("Làm mới danh sách job")
                        tts_json_in = gr.File(
                            label="Hoặc upload 01_transcript.json / result.json",
                            file_types=[".json"],
                        )
                        speaker_info = gr.Textbox(label="Speaker trong JSON", interactive=False)
                        vieneu_key = gr.Textbox(
                            label="VieNeu API key (lưu DB)",
                            type="password",
                            value=prefs.get("vieneu_api_key") or "",
                        )
                        tts_count = gr.Radio(
                            ["1", "2"],
                            value=prefs.get("tts_count") or "1",
                            label="Số giọng TTS",
                        )
                        one_mode = gr.Radio(
                            ["Cả file", "Chỉ speaker A"],
                            value=prefs.get("one_mode") or "Cả file",
                            label="Khi chọn 1 giọng",
                            visible=not two_on,
                        )
                        speaker_0 = gr.Dropdown(
                            choices=["SPEAKER_00"],
                            value="SPEAKER_00",
                            label="Speaker A (list từ JSON)",
                            allow_custom_value=True,
                        )
                        voice_0 = gr.Dropdown(
                            choices=_voice_choices(prefs.get("vieneu_api_key")),
                            value=prefs.get("voice_0") or "Ngọc Lan",
                            label="Giọng A",
                            allow_custom_value=True,
                        )
                        speaker_1 = gr.Dropdown(
                            choices=["SPEAKER_01"],
                            value="SPEAKER_01",
                            label="Speaker B (list từ JSON)",
                            allow_custom_value=True,
                            visible=two_on,
                        )
                        voice_1 = gr.Dropdown(
                            choices=_voice_choices(prefs.get("vieneu_api_key")),
                            value=prefs.get("voice_1") or "Phạm Tuyên",
                            label="Giọng B",
                            allow_custom_value=True,
                            visible=two_on,
                        )
                        load_voices_btn = gr.Button("Tải list giọng VieNeu")
                        sample_text = gr.Textbox(
                            label="Câu test TTS",
                            value=prefs.get("sample_text")
                            or "Xin chào, đây là giọng VieNeu V4.",
                            lines=2,
                        )
                        save_pref_btn = gr.Button("Lưu key + giọng vào DB")
                        with gr.Row():
                            test_tts_btn = gr.Button("Test TTS")
                            tts_btn = gr.Button("Gen TTS", variant="primary")
                    with gr.Column(scale=2):
                        tts_status = gr.Textbox(label="Status", lines=2)
                        tts_json_out = gr.Code(label="03_tts.json", language="json")
                        tts_json_dl = gr.File(label="Download 03_tts.json")
                        tts_audio = gr.Audio(label="Audio", type="filepath")
                speaker_outs = [speaker_0, speaker_1, voice_0, voice_1, one_mode, speaker_info]
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
                load_voices_btn.click(
                    refresh_voice_list,
                    inputs=[vieneu_key, voice_0, voice_1],
                    outputs=[voice_0, voice_1],
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
    try:
        demo.launch(share=share, server_name=server_name, inline=True)
    except TypeError:
        demo.launch(share=share, server_name=server_name)


if __name__ == "__main__":
    launch_ui(share=True)
