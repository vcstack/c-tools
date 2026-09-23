# C-tool

Video/audio → transcript + speaker labels → JSON.

```text
URL hoặc file
      ↓
yt-dlp (nếu URL)
      ↓
Extract audio (FFmpeg)
      ↓
Speech-to-Text (whisper-jax)
      ↓
Speaker diarization (pyannote)
      ↓
JSON
```

No translation, TTS, voice cloning, or video rendering.

## Prerequisites

1. **Python 3.10+**
2. **FFmpeg** on your `PATH`
3. **JAX** (`pip install -U "jax[cuda12]"` on GPU) then whisper-jax
4. **Hugging Face token** when `max_speakers > 1`

### Hugging Face / pyannote

1. Create a token at [https://hf.co/settings/tokens](https://hf.co/settings/tokens)
2. Accept:
   - [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
   - [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
3. Copy `.env.example` to `.env`:

```env
HF_TOKEN=your_token_here
```

## Google Colab

Open [`CTool_Colab.ipynb`](./CTool_Colab.ipynb) on Colab (GPU T4).

1. Run **Reset + cài** — creates Python 3.10 venv (whisper-jax cannot use Colab 3.13).
2. Run **Chạy C-tool** — paste a media URL, set token/model, run. JSON downloads in the notebook.

No Gradio on Colab (avoids FastAPI/Pydantic/Jinja conflicts). Local optional UI: `python app.py`.

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```bash
python main.py --input ./input/video.mp4 --output ./output/result.json
```

```bash
python main.py \
  --input ./input/video.mp4 \
  --output ./output/result.json \
  --model large-v2 \
  --device auto
```

Quick test (single speaker, no HF token):

```bash
python main.py --input ./input/test.wav --output ./output/result.json --model tiny --max-speakers 1
```

### CLI

| Flag | Description |
|------|-------------|
| `--model` | whisper-jax (`tiny`, `base`, `large-v2`, …) |
| `--device` | `auto`, `cuda`, `cpu`, or `tpu` |
| `--language` | ISO language code (optional) |
| `--min-speakers` / `--max-speakers` | Diarization bounds |
| `--diarization-model` | `pyannote_3.1` (default), `pyannote_2.1`, or `disable` |

## Output JSON

```json
{
  "source": { "filename": "example.mp4", "duration": 125.4 },
  "speakers": ["SPEAKER_00", "SPEAKER_01"],
  "segments": [
    {
      "speaker": "SPEAKER_00",
      "start": 0.52,
      "end": 3.81,
      "text": "Hello everyone."
    }
  ]
}
```

Transcript stays in the original language (`task=transcribe`). Speakers come from pyannote. A segment that overlaps two speakers gets the speaker with more overlap.

## Project layout

```text
├── main.py
├── pipeline/
│   ├── audio.py
│   ├── transcription.py
│   ├── diarization.py
│   ├── alignment.py
│   ├── pipeline.py
│   └── config.py
├── ctool/
├── input/
├── output/
├── .env.example
└── requirements.txt
```

## License

pyannote and Whisper models have their own terms on Hugging Face.
