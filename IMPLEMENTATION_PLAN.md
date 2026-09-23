# C-tool pipeline

```text
Input video/audio
       ↓
FFmpeg → WAV
       ↓
WhisperX speech-to-text
       ↓
WhisperX timestamp alignment
       ↓
pyannote speaker diarization
       ↓
Merge transcript + speaker + timestamps
       ↓
JSON
```

## Modules

| Stage | Code |
|--------|------|
| FFmpeg extract | `pipeline/audio.py` |
| WhisperX ASR | `ctool/speech_segmentation.py` → `pipeline/transcription.py` |
| Alignment | `ctool/speech_segmentation.py` + `ctool/align_languages.py` |
| pyannote | `ctool/speech_segmentation.py` → `pipeline/diarization.py` |
| Merge / JSON | `whisperx.assign_word_speakers` + `pipeline/alignment.py` |
| Device | `CTOOL_DEVICE` (`cuda` if available, else `cpu`) |
| Token | `HF_TOKEN` |

## Merge

1. `whisperx.assign_word_speakers` assigns speakers to words/segments.
2. If `words[].speaker` changes mid-segment, export splits into sub-segments.
3. Fallback: segment-level speaker; if needed, largest timestamp overlap.

## JSON

```json
{
  "source": { "filename": "...", "duration": 0.0 },
  "speakers": ["SPEAKER_00"],
  "segments": [
    { "speaker": "SPEAKER_00", "start": 0.0, "end": 1.0, "text": "..." }
  ]
}
```
