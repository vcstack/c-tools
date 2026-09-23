"""C-tool Gradio UI — ASR + diarization → JSON."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

# Colab sets MPLBACKEND=module://matplotlib_inline... which the venv matplotlib rejects
os.environ["MPLBACKEND"] = "Agg"

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.config import PipelineConfig, resolve_device
from pipeline.download import download_media_url, is_url
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


def _media_path(media_url, media_file, use_sample: bool, cookies=None) -> Path:
    if use_sample:
        return _ensure_sample()
    url = (media_url or "").strip()
    if is_url(url):
        print(f"Downloading: {url}")
        cookie_path = _as_local_path(cookies)
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
):
    try:
        input_path = _media_path(media_url, media_file, bool(use_sample), cookies_file)
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


def build_ui():
    import gradio as gr

    with gr.Blocks(title="C-tool") as demo:
        gr.Markdown(
            """
# C-tool
Video / audio URL → whisper-jax + pyannote → JSON  
Dán URL như SoniTranslate (YouTube, v.v.). Upload file chỉ là tùy chọn.
            """
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
                    file_types=[".mp4", ".mkv", ".mov", ".avi", ".mp3", ".wav", ".m4a", ".flac"],
                )
                cookies = _gr_file("YouTube cookies.txt (nếu bị chặn bot)", file_types=[".txt"])
                use_sample = gr.Checkbox(label="Dùng clip mẫu JFK (bỏ qua URL/file)", value=False)
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
                    device = gr.Dropdown(["auto", "cuda", "cpu", "tpu"], value="auto", label="Device")
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
            ],
            outputs=outputs,
        )
        test_btn.click(
            lambda hf, bs, dev: run_job("", None, True, hf, "tiny", "en", 1, 1, bs, dev),
            inputs=[hf_token, batch_size, device],
            outputs=outputs,
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
