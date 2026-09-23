"""C-tool Gradio UI — ASR + diarization → JSON."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

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


def _media_path(media_url, media_file, use_sample: bool) -> Path:
    if use_sample:
        return _ensure_sample()
    url = (media_url or "").strip()
    if is_url(url):
        print(f"Downloading: {url}")
        return download_media_url(url, ROOT / "input")
    if media_file:
        return Path(media_file)
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
):
    try:
        input_path = _media_path(media_url, media_file, bool(use_sample))
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
                media = gr.File(
                    label="Hoặc upload file (không bắt buộc)",
                    file_types=[".mp4", ".mkv", ".mov", ".avi", ".mp3", ".wav", ".m4a", ".flac"],
                    type="filepath",
                )
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
                run_btn = gr.Button("Run", variant="primary")
            with gr.Column(scale=2):
                status = gr.Textbox(label="Status", lines=2)
                table = gr.Dataframe(
                    headers=["speaker", "start", "end", "text"],
                    label="Segments",
                    wrap=True,
                )
                json_out = gr.Code(label="JSON", language="json")
                download = gr.File(label="Download result.json")

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
            ],
            outputs=[status, json_out, table, download],
        )
    return demo


def launch_ui(share: bool = True, server_name: str = "0.0.0.0"):
    demo = build_ui()
    demo.queue()
    try:
        demo.launch(share=share, server_name=server_name, inline=True)
    except TypeError:
        demo.launch(share=share, server_name=server_name)


if __name__ == "__main__":
    launch_ui(share=False)
