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

No translation, local voice cloning, or video rendering. Cloud TTS: VieNeu **V4 API** (tab **TTS VieNeu V4**).

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
2. Run **Mở UI** — mounts Drive (`MyDrive/ctool`), installs Gradio on Colab's Python, opens the form. Pipeline still runs inside the venv.

Do not install Gradio into `ctool-venv` (breaks whisper-jax pins). Local optional UI: `python app.py`.

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
| `--cookies` | Netscape `cookies.txt` for YouTube (Colab IPs often require this) |

YouTube on Colab may ask to sign in. Paste cookies into the UI box (Netscape file contents or a `Cookie:` header) or pass `--cookies`. See [yt-dlp wiki](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies).

## SQLite + Drive

After each successful run the pipeline writes:

```text
{store}/ctool.db
{store}/jobs/{job_id}/01_transcript.json
```

Default `{store}`:

1. `--store-dir` or `CTOOL_STORE`
2. `/content/drive/MyDrive/ctool` if Drive is mounted
3. `./data/ctool` locally

Colab: mount Drive, then `export CTOOL_STORE=/content/drive/MyDrive/ctool`. Skip persist with `--no-store`.

`ctool.db` holds `jobs`, `speakers`, `segments`. TTS writes `03_tts.json` + `tts/*.mp3` in the same job folder.

Colab tab **Dashboard**: job status (STT / TTS / **Final**), re-run STT, re-TTS (all or selected utterances), **Final** locks further STT/TTS. Job folder also stores `00_job_meta.json` and `source.*` (local upload) for re-STT.

## VieNeu TTS (V4 cloud)

V4 **chỉ có trên API** `https://api.vieneu.io/api/v1`. Build `VieNeu-TTS` trên Colab / `pip install vieneu` là **v3 on-device**, không phải V4.

1. Tạo key tại [vieneu.io](https://www.vieneu.io/)
2. Tab **TTS VieNeu V4** — dán key, chọn job hoặc upload JSON
3. Chọn gen **1 hoặc 2 giọng** (dropdown speaker từ JSON)
4. **Test TTS** với 1 câu mẫu

Key, giọng, số speaker lưu bảng `settings` trong `ctool.db` (cùng file SQLite trên Drive).

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
