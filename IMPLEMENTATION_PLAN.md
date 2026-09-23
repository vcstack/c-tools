# SoniTranslate → ASR + Diarization JSON pipeline (implementation plan)

## 1. SoniTranslate files to reuse

| Concern | Source | Reuse strategy |
|--------|--------|------------------|
| FFmpeg audio extraction | `soni_translate/preprocessor.py` (`audio_preprocessor`) | Adapted in `pipeline/audio.py` (same ffmpeg PCM 44.1kHz stereo) |
| WhisperX ASR | `soni_translate/speech_segmentation.py` (`transcribe_speech`) | Vendored in `sonitr_st/speech_segmentation.py` |
| Timestamp alignment | `speech_segmentation.py` (`align_speech`) + `EXTRA_ALIGN` | Vendored in `sonitr_st/align_languages.py` (no SoniTranslate checkout) |
| pyannote diarization | `speech_segmentation.py` (`diarize_speech`, `DiarizationPipeline`) | Same vendored module |
| ASR + diarization merge | `whisperx.assign_word_speakers` via `diarize_speech` | Kept; `pipeline/alignment.py` splits segments on word-level speaker changes |
| Speaker ID normalization | `reencode_speakers` in `speech_segmentation.py` | Kept |
| Device selection | `app_rvc.py` (`SONITR_DEVICE` = cuda if available else cpu) | `pipeline/config.py` |
| HF token errors | `diarize_speech` license hints | Preserved |
| Logging / pyannote noise | `logging_setup.py` | Vendored in `sonitr_st/logging_setup.py` |
| Shell ffmpeg helpers | `utils.py` (`run_command`) | `sonitr_st/media_utils.py` |

## 2. SoniTranslate areas not included

- `app_rvc.py`, Gradio UI, `voice_main.py`, `vci_pipeline.py`, `lib/` (RVC)
- `translate_segments.py`, `text_to_speech.py`, `mdx_net.py` (vocal separation)
- `postprocessor.py` (dub/sub burn), `text_multiformat_processor.py` (TTS/video merge)
- `audio_segments.py` (dub mixing), OpenAI API transcription path (optional, omitted)

## 3. Python dependencies (trimmed)

- `torch`, `torchaudio` (CPU or CUDA)
- `whisperX` (R3gm fork, same as SoniTranslate `requirements_base.txt`)
- `pyannote-audio` (R3gm fork 3.1.1)
- `ctranslate2`, `transformers`, `soundfile`, `numpy`
- `python-dotenv`
- System: **FFmpeg** on PATH

## 4. ASR

WhisperX `load_model` + `transcribe`, then `whisperx.align` when the detected language has an alignment model (SoniTranslate `align_speech` logic).

Default model: `large-v3` (CLI `--model`), overridable.

## 5. Diarization

`whisperx.DiarizationPipeline` with default **`pyannote/speaker-diarization-3.1`** (SoniTranslate `pyannote_3.1`). Token from **`HF_TOKEN`** env (SoniTranslate used `YOUR_HF_TOKEN` in the app).

## 6. Merge algorithm

1. **Primary:** `whisperx.assign_word_speakers(diarize_segments, aligned_result)` (SoniTranslate).
2. **Export:** For each segment, if `words[]` contains per-word `speaker` labels, split into sub-segments when the speaker changes (deterministic, ordered by time). Text is rebuilt from word tokens in each sub-segment.
3. **Fallback:** If no word-level speakers, use segment `speaker` with segment `start`/`end`.
4. **Overlap rule (segment-level fallback only):** Assign speaker with maximum temporal overlap vs. diarization regions.

## 7. JSON schema

```json
{
  "source": { "filename": "...", "duration": 0.0 },
  "speakers": ["SPEAKER_00"],
  "segments": [
    { "speaker": "SPEAKER_00", "start": 0.0, "end": 1.0, "text": "..." }
  ]
}
```

Segments sorted by `start`; timestamps in seconds (float).
