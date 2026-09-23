"""
Merge ASR segments with diarization labels for JSON export.

Primary merge is performed by WhisperX `assign_word_speakers` (see diarization).
This module refines output using word-level speaker tags when present.
"""

from __future__ import annotations

from typing import Any


def _word_text(word: dict) -> str:
    return word.get("word") or word.get("text") or ""


def _split_segment_by_word_speakers(segment: dict) -> list[dict]:
    words = segment.get("words") or []
    usable = [
        w
        for w in words
        if w.get("speaker") and w.get("start") is not None and w.get("end") is not None
    ]
    if not usable:
        speaker = segment.get("speaker", "SPEAKER_00")
        return [
            {
                "speaker": speaker,
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "text": (segment.get("text") or "").strip(),
            }
        ]

    chunks: list[dict] = []
    current_speaker = usable[0]["speaker"]
    current_words: list[dict] = [usable[0]]

    for word in usable[1:]:
        if word["speaker"] == current_speaker:
            current_words.append(word)
        else:
            chunks.append(_words_to_segment(current_speaker, current_words))
            current_speaker = word["speaker"]
            current_words = [word]
    chunks.append(_words_to_segment(current_speaker, current_words))
    return [c for c in chunks if c["text"]]


def _words_to_segment(speaker: str, words: list[dict]) -> dict:
    text = "".join(_word_text(w) for w in words).strip()
    if not text:
        text = " ".join(_word_text(w).strip() for w in words if _word_text(w)).strip()
    return {
        "speaker": speaker,
        "start": float(words[0]["start"]),
        "end": float(words[-1]["end"]),
        "text": text,
    }


def assign_speaker_by_overlap(
    start: float, end: float, diarization_regions: list[tuple[float, float, str]]
) -> str:
    """Deterministic fallback: speaker with largest temporal overlap."""
    best_speaker = "SPEAKER_00"
    best_overlap = -1.0
    for d_start, d_end, speaker in diarization_regions:
        overlap = max(0.0, min(end, d_end) - max(start, d_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = speaker
    return best_speaker


def build_output_segments(result_diarize: dict) -> list[dict]:
    segments_out: list[dict] = []
    for segment in result_diarize.get("segments", []):
        segments_out.extend(_split_segment_by_word_speakers(segment))

    segments_out.sort(key=lambda s: (s["start"], s["end"]))
    return segments_out


def build_json_payload(
    *,
    filename: str,
    duration: float,
    result_diarize: dict,
) -> dict[str, Any]:
    segments = build_output_segments(result_diarize)
    speakers = sorted({s["speaker"] for s in segments})
    return {
        "source": {"filename": filename, "duration": round(duration, 3)},
        "speakers": speakers,
        "segments": segments,
    }
