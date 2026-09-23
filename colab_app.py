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
import urllib.request
from pathlib import Path

ROOT = Path("/content/c-tools")
if not ROOT.is_dir():
    ROOT = Path(__file__).resolve().parent
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


def run_job(
    media_url,
    media_file,
    hf_token,
    model,
    language,
    min_speakers,
    max_speakers,
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
    env = os.environ.copy()
    token = (hf_token or "").strip()
    env["HF_TOKEN"] = token
    env["HUGGING_FACE_HUB_TOKEN"] = token
    env["MPLBACKEND"] = "Agg"

    cmd = [
        str(PY),
        str(ROOT / "main.py"),
        "--input",
        source,
        "--output",
        str(OUT),
        "--model",
        model or "large-v2",
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

    print(" ".join(cmd), flush=True)
    code = subprocess.call(cmd, env=env, cwd=str(ROOT))
    if code != 0 or not OUT.is_file():
        return f"Pipeline failed (exit {code})", "", None, None

    data = json.loads(OUT.read_text(encoding="utf-8"))
    rows = [
        [seg.get("speaker"), seg.get("start"), seg.get("end"), seg.get("text")]
        for seg in data.get("segments", [])
    ]
    status = (
        f"{data.get('source', {}).get('filename')} · "
        f"{len(data.get('speakers', []))} speakers · "
        f"{len(rows)} segments"
    )
    pretty = json.dumps(data, ensure_ascii=False, indent=2)
    return status, pretty, rows, str(OUT)


def run_test():
    # JFK clip, tiny, 1 speaker — no HF token needed
    return run_job("", None, "", "tiny", "en", 1, 1, use_sample=True)


def build_ui():
    import gradio as gr

    with gr.Blocks(title="C-tool") as demo:
        gr.Markdown(
            "# C-tool\n"
            "Video / audio URL → whisper-jax + pyannote → JSON"
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
                hf_token = gr.Textbox(label="Hugging Face token", type="password")
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
            ],
            outputs=outputs,
        )
        test_btn.click(run_test, inputs=[], outputs=outputs)
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
