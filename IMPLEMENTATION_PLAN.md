# C-tool pipeline

```text
Input video/audio
       ↓
FFmpeg → WAV
       ↓
whisper-jax (FlaxWhisperPipline, task=transcribe)
       ↓
pyannote speaker diarization
       ↓
Overlap-merge transcript + speaker
       ↓
JSON
```

## Modules

| Stage | Code |
|--------|------|
| FFmpeg extract | `pipeline/audio.py` |
| ASR | `ctool/asr.py` → `pipeline/transcription.py` |
| pyannote | `ctool/diarize.py` → `pipeline/diarization.py` |
| Merge | largest timestamp overlap in `pipeline/alignment.py` |

whisper-jax has segment timestamps, not word-level alignment. If one ASR segment overlaps two speakers, the speaker with more overlap wins.

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
