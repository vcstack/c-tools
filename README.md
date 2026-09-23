# SoniTranslate ASR + Diarization (JSON only)

Standalone pipeline derived from [SoniTranslate](https://github.com/R3gm/SoniTranslate). It runs **speech-to-text**, **WhisperX alignment**, **pyannote speaker diarization**, and writes a merged **JSON** file. There is **no** translation, TTS, voice cloning, or dubbing.

See [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) for which SoniTranslate modules were reused.

## Prerequisites

1. **Python 3.10+**
2. **FFmpeg** on your `PATH` (`ffmpeg -version`)
3. **PyTorch** matching your machine (CPU or CUDA). Install from [pytorch.org](https://pytorch.org/) if the default `pip install torch` wheel is not suitable.
4. **Hugging Face token** for pyannote diarization (when `max_speakers > 1`)

### Hugging Face / pyannote setup

1. Create a token at [https://hf.co/settings/tokens](https://hf.co/settings/tokens)
2. Accept the user conditions for:
   - [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
   - [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
3. Copy `.env.example` to `.env` and set:

```env
HF_TOKEN=your_token_here
```

## Google Colab

Mở file [`ASR_Diarization_Colab.ipynb`](./ASR_Diarization_Colab.ipynb) trên Colab:

1. Runtime → **GPU (T4)**.
2. Chạy các cell lần lượt: cài FFmpeg/WhisperX/pyannote → tạo project → dán `HF_TOKEN`.
3. Upload video/audio hoặc dùng mẫu JFK.
4. Chạy pipeline, tải `result.json`.

Không cài TTS / translation. Accept license pyannote trước khi diarization nhiều speaker.

## Install

```bash
cd d:\C-Tools
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

The repo includes a shallow clone of SoniTranslate under `./SoniTranslate` for alignment language maps (`EXTRA_ALIGN`). Keep that folder or clone SoniTranslate beside this project.

## Usage

```bash
python main.py --input ./input/video.mp4 --output ./output/result.json
```

Optional:

```bash
python main.py \
  --input ./input/video.mp4 \
  --output ./output/result.json \
  --model large-v3 \
  --device auto
```

Fast local test (CPU, small model, single speaker — no HF token):

```bash
python main.py --input ./input/test.wav --output ./output/result.json --model tiny --max-speakers 1
```

### CLI options

| Flag | Description |
|------|-------------|
| `--model` | Whisper model (`tiny`, `base`, `large-v3`, …) |
| `--device` | `auto`, `cuda`, or `cpu` |
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

Speaker assignment uses WhisperX `assign_word_speakers` (same as SoniTranslate). When word-level speaker tags exist, segments are split on speaker changes before export.

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
├── sonitr_st/          # Vendored SoniTranslate ASR/diarization core
├── SoniTranslate/      # Upstream clone (alignment language config)
├── input/
├── output/
├── .env.example
└── requirements.txt
```

## License

SoniTranslate is MIT-licensed; pyannote and Whisper models have their own terms on Hugging Face.
