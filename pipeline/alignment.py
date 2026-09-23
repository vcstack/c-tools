"""
Merge ASR segments with diarization labels.

whisper-jax gives segment timestamps (not word-level). Speaker is assigned
by largest temporal overlap. Ties / no-overlap → SPEAKER_00.
"""

from __future__ import annotations

from typing import Any


def assign_speaker_by_overlap(
    start: float, end: float, diarization_regions: list[tuple[float, float, str]]
) -> str:
    best_speaker = "SPEAKER_00"
    best_overlap = 0.0
    for d_start, d_end, speaker in diarization_regions:
        overlap = max(0.0, min(end, d_end) - max(start, d_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = speaker
        elif overlap == best_overlap and overlap > 0 and speaker < best_speaker:
            best_speaker = speaker
    return best_speaker


def merge_transcript_and_speakers(
    asr_result: dict,
    diarization_regions: list[tuple[float, float, str]],
) -> dict:
    segments = []
    for seg in asr_result.get("segments", []):
        speaker = assign_speaker_by_overlap(
            float(seg["start"]), float(seg["end"]), diarization_regions
        )
        segments.append(
            {
                "speaker": speaker,
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "text": (seg.get("text") or "").strip(),
            }
        )
    return {"segments": segments, "language": asr_result.get("language")}


def build_output_segments(result_diarize: dict) -> list[dict]:
    out = []
    for segment in result_diarize.get("segments", []):
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        out.append(
            {
                "speaker": segment.get("speaker", "SPEAKER_00"),
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "text": text,
            }
        )
    out.sort(key=lambda s: (s["start"], s["end"]))
    return out


def build_json_payload(
    *,
    filename: str,
    duration: float,
    result_diarize: dict,
) -> dict[str, Any]:
    segments = build_output_segments(result_diarize)
    speakers = sorted({s["speaker"] for s in segments})
    return {
        "source": {"filename": filename, "duration": round(float(duration or 0), 3)},
        "speakers": speakers,
        "segments": segments,
    }
