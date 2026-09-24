"""VieNeu Cloud API (V4). Not the on-device SDK — V4 is cloud-only."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_API_BASE = "https://api.vieneu.io/api/v1"
FALLBACK_VOICES = ["Ngọc Lan", "Minh Quân", "Phạm Tuyên", "Ngọc Huyền", "Mai Anh"]


def api_base() -> str:
    return (os.environ.get("VIENEU_API_BASE") or DEFAULT_API_BASE).rstrip("/")


def _request(
    method: str,
    path: str,
    api_key: str,
    *,
    body: dict | None = None,
    query: dict | None = None,
    timeout: int = 180,
) -> tuple[bytes, str]:
    url = f"{api_base()}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Accept": "*/*",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            return resp.read(), ctype
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"VieNeu API {exc.code}: {detail or exc.reason}") from exc


def list_voices(api_key: str) -> list[str]:
    raw, ctype = _request("GET", "/voices", api_key, query={"engine": "v4"}, timeout=30)
    names: list[str] = []
    if "json" in ctype or raw[:1] in (b"{", b"["):
        parsed = json.loads(raw.decode("utf-8"))
        items = parsed
        if isinstance(parsed, dict):
            items = parsed.get("data") or parsed.get("voices") or parsed.get("items") or []
        for item in items:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("id") or item.get("voice")
                if name:
                    names.append(str(name))
    return names or list(FALLBACK_VOICES)


def synthesize(
    api_key: str,
    text: str,
    voice: str,
    *,
    dest: str | Path,
    response_format: str = "mp3",
) -> Path:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty TTS text")
    body: dict[str, Any] = {
        "input": text,
        "voice": voice,
        "engine": "v4",
        "response_format": response_format,
    }
    raw, ctype = _request("POST", "/audio/speech", api_key, body=body)
    dest_path = Path(dest)
    if "wav" in ctype:
        dest_path = dest_path.with_suffix(".wav")
    elif "mpeg" in ctype or "mp3" in ctype:
        dest_path = dest_path.with_suffix(".mp3")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(raw)
    if dest_path.stat().st_size < 32:
        raise RuntimeError("VieNeu returned empty audio")
    return dest_path
