"""C-tool Gradio UI — ASR + diarization → JSON."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

# Colab sets MPLBACKEND=module://matplotlib_inline... which the venv matplotlib rejects
os.environ["MPLBACKEND"] = "Agg"

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.config import PipelineConfig, resolve_device
from pipeline.download import cookies_text_to_file, download_media_url, is_url
from pipeline.pipeline import run_pipeline

SAMPLE_URL = "https://github.com/openai/whisper/raw/main/tests/jfk.flac"
SAMPLE_PATH = ROOT / "input" / "jfk.flac"


def _ensure_sample() -> Path:
    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SAMPLE_PATH.is_file() or SAMPLE_PATH.stat().st_size == 0:
        urllib.request.urlretrieve(SAMPLE_URL, SAMPLE_PATH)
    return SAMPLE_PATH


def _as_local_path(media_file) -> Path | None:
    if media_file is None:
        return None
    if isinstance(media_file, dict):
        media_file = media_file.get("name") or media_file.get("path")
    elif not isinstance(media_file, (str, Path)):
        media_file = getattr(media_file, "name", None)
    if not media_file:
        return None
    path = Path(media_file)
    return path if path.is_file() else None


def _media_path(media_url, media_file, use_sample: bool, cookies=None, cookies_text=None) -> Path:
    if use_sample:
        return _ensure_sample()
    url = (media_url or "").strip()
    if is_url(url):
        print(f"Downloading: {url}")
        cookie_path = _as_local_path(cookies)
        pasted = (cookies_text or "").strip()
        if pasted:
            cookie_path = cookies_text_to_file(pasted, ROOT / "input" / "cookies.txt")
        return download_media_url(url, ROOT / "input", cookies=cookie_path)
    local = _as_local_path(media_file)
    if local:
        return local
    raise ValueError("Paste a video/audio URL (YouTube, etc.) or upload a file.")


def run_job(
    media_url,
    media_file,
    use_sample,
    hf_token,
    model,
    language,
    min_speakers,
    max_speakers,
    batch_size,
    device,
    cookies_file=None,
    cookies_text=None,
):
    try:
        input_path = _media_path(
            media_url, media_file, bool(use_sample), cookies_file, cookies_text
        )
    except ValueError as exc:
        return str(exc), "", None, None

    token = (hf_token or "").strip() or None
    if token:
        os.environ["HF_TOKEN"] = token
        os.environ["HUGGING_FACE_HUB_TOKEN"] = token

    out_dir = ROOT / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{input_path.stem}.json"

    cfg = PipelineConfig(
        asr_model=model,
        batch_size=int(batch_size),
        source_language=(language or "").strip() or None,
        min_speakers=int(min_speakers),
        max_speakers=int(max_speakers),
        device=resolve_device(device),
        work_dir=str(ROOT / ".cache" / "pipeline"),
        hf_token=token,
    )

    try:
        result = run_pipeline(str(input_path), str(output_path), cfg)
    except SystemExit as exc:
        return f"Error: {exc}", "", None, None
    except Exception as exc:
        return f"Error: {exc}", "", None, None

    rows = [
        [seg["speaker"], seg["start"], seg["end"], seg["text"]]
        for seg in result.get("segments", [])
    ]
    status = (
        f"OK · {result['source']['filename']} · "
        f"{result['source']['duration']}s · "
        f"{len(result.get('speakers', []))} speakers · "
        f"{len(rows)} segments"
        + (f" · job {result.get('job_id')}" if result.get("job_id") else "")
    )
    pretty = json.dumps(result, ensure_ascii=False, indent=2)
    return status, pretty, rows, str(output_path)


def _gr_file(label: str, **kwargs):
    import gradio as gr

    kwargs.pop("type", None)
    try:
        return gr.File(label=label, type="file", **kwargs)
    except (ValueError, TypeError):
        return gr.File(label=label, **kwargs)


def _job_ids():
    from ctool.store import list_jobs

    return [row["id"] for row in list_jobs()]


def _save_tts_prefs(api_key, voice_0, voice_1, tts_count, sample_text):
    from ctool.settings import save_settings

    save_settings(
        vieneu_api_key=api_key,
        voice_0=voice_0,
        voice_1=voice_1,
        tts_count=tts_count,
        sample_text=sample_text,
    )
    return "Đã lưu key + giọng vào bảng settings (ctool.db)."


def _test_tts(api_key, voice_0, sample_text):
    from ctool.settings import save_settings
    from ctool.vieneu import synthesize

    save_settings(vieneu_api_key=api_key, voice_0=voice_0, sample_text=sample_text)
    dest = Path(tempfile.gettempdir()) / "ctool_tts_test.mp3"
    try:
        path = synthesize(
            api_key,
            (sample_text or "").strip() or "Xin chào, đây là giọng VieNeu V4.",
            (voice_0 or "Ngọc Lan").strip(),
            dest=dest,
        )
    except Exception as exc:
        return f"Test TTS failed: {exc}", None
    return f"Test OK · {voice_0}", str(path)


def run_tts_job(job_id, json_file, api_key, tts_count, speaker_0, speaker_1, voice_0, voice_1):
    from ctool.settings import save_settings
    from ctool.tts_job import run_vieneu_tts

    save_settings(vieneu_api_key=api_key, voice_0=voice_0, voice_1=voice_1, tts_count=tts_count)
    json_path = _as_local_path(json_file)
    jid = (job_id or "").strip() or None
    two = str(tts_count).strip().startswith("2")
    v0 = (voice_0 or "Ngọc Lan").strip()
    try:
        if two:
            mapping = {(speaker_0 or "SPEAKER_00").strip(): v0}
            spk1 = (speaker_1 or "").strip()
            if spk1 and spk1 not in mapping:
                mapping[spk1] = (voice_1 or v0).strip()
            manifest = run_vieneu_tts(
                api_key,
                job_id=jid,
                json_path=json_path,
                default_voice=v0,
                voice_map=mapping,
                only_speakers=list(mapping.keys()),
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
    audio = folder / manifest["audio"] if manifest.get("audio") else None
    status = f"TTS OK · job {manifest.get('job_id')} · {len(manifest.get('items', []))} utterances"
    return (
        status,
        json.dumps(manifest, ensure_ascii=False, indent=2),
        manifest["store"]["tts_json"],
        str(audio) if audio and audio.is_file() else None,
    )


def build_ui():
    import gradio as gr

    with gr.Blocks(title="C-tool") as demo:
        gr.Markdown("# C-tool")
        with gr.Tabs():
            with gr.Tab("STT"):
                gr.Markdown(
                    "Video / audio URL → whisper-jax + pyannote → JSON. "
                    "Upload file chỉ là tùy chọn."
                )
                with gr.Row():
                    with gr.Column(scale=1):
                        media_url = gr.Textbox(
                            label="Media URL",
                            placeholder="https://www.youtube.com/watch?v=...",
                            lines=1,
                        )
                        media = _gr_file(
                            "Hoặc upload file (không bắt buộc)",
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
                            placeholder="Dán cookies.txt hoặc header Cookie: ...",
                            lines=4,
                        )
                        cookies = _gr_file("Hoặc upload cookies.txt", file_types=[".txt"])
                        use_sample = gr.Checkbox(
                            label="Dùng clip mẫu JFK (bỏ qua URL/file)", value=False
                        )
                        hf_token = gr.Textbox(
                            label="Hugging Face token",
                            type="password",
                            placeholder="Required when max speakers > 1",
                        )
                        model = gr.Dropdown(
                            ["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                            value="large-v2",
                            label="whisper-jax model",
                        )
                        language = gr.Textbox(
                            label="Language code",
                            placeholder="auto-detect if empty (en, vi, ja, ...)",
                        )
                        with gr.Row():
                            min_speakers = gr.Number(label="Min speakers", value=1, precision=0)
                            max_speakers = gr.Number(label="Max speakers", value=10, precision=0)
                        with gr.Row():
                            batch_size = gr.Number(label="Batch size", value=8, precision=0)
                            device = gr.Dropdown(
                                ["auto", "cuda", "cpu", "tpu"], value="auto", label="Device"
                            )
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
                        download = _gr_file("Download result.json")

                outputs = [status, json_out, table, download]
                run_btn.click(
                    run_job,
                    inputs=[
                        media_url,
                        media,
                        use_sample,
                        hf_token,
                        model,
                        language,
                        min_speakers,
                        max_speakers,
                        batch_size,
                        device,
                        cookies,
                        cookies_text,
                    ],
                    outputs=outputs,
                )
                test_btn.click(
                    lambda hf, bs, dev: run_job("", None, True, hf, "tiny", "en", 1, 1, bs, dev),
                    inputs=[hf_token, batch_size, device],
                    outputs=outputs,
                )

            with gr.Tab("TTS VieNeu V4"):
                from ctool.settings import load_settings

                prefs = load_settings()
                two_on = str(prefs.get("tts_count") or "1") == "2"
                gr.Markdown(
                    "Key + giọng lưu bảng **settings** trong `ctool.db`. "
                    "Gen 1 hoặc 2 giọng dù JSON có 2 speaker."
                )
                job_dd = gr.Dropdown(choices=_job_ids(), label="Job", allow_custom_value=True)
                refresh_btn = gr.Button("Làm mới job")
                tts_json_in = _gr_file("Hoặc JSON transcript", file_types=[".json"])
                vieneu_key = gr.Textbox(
                    label="VieNeu API key (lưu DB)",
                    type="password",
                    value=prefs.get("vieneu_api_key") or "",
                )
                tts_count = gr.Radio(
                    ["1", "2"], value=prefs.get("tts_count") or "1", label="Số giọng TTS"
                )
                speaker_0 = gr.Dropdown(
                    ["SPEAKER_00"], value="SPEAKER_00", label="Speaker A", allow_custom_value=True
                )
                voice_0 = gr.Textbox(label="Giọng A", value=prefs.get("voice_0") or "Ngọc Lan")
                speaker_1 = gr.Dropdown(
                    ["SPEAKER_01"],
                    value="SPEAKER_01",
                    label="Speaker B",
                    allow_custom_value=True,
                    visible=two_on,
                )
                voice_1 = gr.Textbox(
                    label="Giọng B",
                    value=prefs.get("voice_1") or "Phạm Tuyên",
                    visible=two_on,
                )
                sample_text = gr.Textbox(
                    label="Câu test TTS",
                    value=prefs.get("sample_text") or "Xin chào, đây là giọng VieNeu V4.",
                )
                save_pref_btn = gr.Button("Lưu key + giọng vào DB")
                test_tts_btn = gr.Button("Test TTS")
                tts_btn = gr.Button("Gen TTS", variant="primary")
                tts_status = gr.Textbox(label="Status", lines=2)
                tts_json_out = gr.Code(label="03_tts.json", language="json")
                tts_json_dl = _gr_file("Download 03_tts.json")
                tts_audio = gr.Audio(label="Audio", type="filepath")
                refresh_btn.click(lambda: gr.update(choices=_job_ids()), outputs=[job_dd])
                save_pref_btn.click(
                    _save_tts_prefs,
                    inputs=[vieneu_key, voice_0, voice_1, tts_count, sample_text],
                    outputs=[tts_status],
                )
                test_tts_btn.click(
                    _test_tts,
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
                    ],
                    outputs=[tts_status, tts_json_out, tts_json_dl, tts_audio],
                )
    return demo


def launch_ui(share: bool = True, server_name: str = "0.0.0.0"):
    import subprocess

    try:
        rev = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
        print(f"C-tool commit: {rev}")
    except Exception:
        print("C-tool commit: unknown")
    demo = build_ui()
    demo.queue()
    try:
        demo.launch(share=share, server_name=server_name, inline=True)
    except TypeError:
        demo.launch(share=share, server_name=server_name)


if __name__ == "__main__":
    try:
        import gradio  # noqa: F401
    except ImportError:
        raise SystemExit(
            "Gradio is not in this interpreter.\n"
            "Colab: run the notebook cell 'Mở UI' (Colab Python + colab_app.py).\n"
            "Do not run this file with /content/ctool-venv/bin/python."
        )
    launch_ui(share=False)
