"""Download media from a URL. STT only needs audio — avoid YouTube 4K (403)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from pipeline.audio import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS


def cookies_text_to_file(text: str, dest: str | Path | None = None) -> Path:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty cookies text")
    dest_path = Path(dest) if dest else Path("input") / "cookies.txt"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if raw.lstrip().startswith("# Netscape") or "\t" in raw:
        body = raw if raw.endswith("\n") else raw + "\n"
    else:
        lines = ["# Netscape HTTP Cookie File"]
        for part in raw.replace("\n", " ").split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            name, value = part.split("=", 1)
            name, value = name.strip(), value.strip()
            if name:
                lines.append(f".youtube.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}")
        if len(lines) < 2:
            raise ValueError("No cookies found in pasted text")
        body = "\n".join(lines) + "\n"
    dest_path.write_text(body, encoding="utf-8")
    return dest_path


def resolve_cookies(explicit: str | Path | None = None) -> Path | None:
    pasted = (os.environ.get("CTOOL_COOKIES_TEXT") or "").strip()
    if pasted:
        return cookies_text_to_file(pasted, Path("input") / "cookies.txt")
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = (os.environ.get("CTOOL_COOKIES") or os.environ.get("YTDLP_COOKIES") or "").strip()
    if env:
        candidates.append(Path(env))
    candidates.extend((Path("input/cookies.txt"), Path("cookies.txt")))
    for path in candidates:
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


def is_url(value: str | None) -> bool:
    text = (value or "").strip()
    return text.startswith("http://") or text.startswith("https://")


def _js_runtimes() -> dict:
    runtimes = {}
    if shutil.which("deno"):
        runtimes["deno"] = {}
    if shutil.which("node"):
        runtimes["node"] = {}
    return runtimes


def _ydl_opts(
    dest_dir: Path,
    fmt: str,
    clients: list[str],
    merge: str | None,
    cookies: Path | None,
) -> dict:
    opts = {
        "format": fmt,
        "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "restrictfilenames": True,
        "overwrites": True,
        "quiet": False,
        "no_warnings": False,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 1,
        "extractor_args": {"youtube": {"player_client": clients}},
    }
    if merge:
        opts["merge_output_format"] = merge
    if cookies:
        opts["cookiefile"] = str(cookies)
        print(f"yt-dlp cookies: {cookies}")
    runtimes = _js_runtimes()
    if runtimes:
        opts["js_runtimes"] = runtimes
    return opts


def _resolve_downloaded(info: dict, ydl, dest_dir: Path) -> Path | None:
    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]
    path = None
    for item in info.get("requested_downloads") or []:
        path = item.get("filepath") or item.get("filename")
        if path:
            break
    if not path:
        path = ydl.prepare_filename(info)
    candidate = Path(path)
    if candidate.is_file():
        return candidate
    stem = candidate.stem
    for ext in (".m4a", ".webm", ".mp3", ".mp4", ".mkv", ".wav", candidate.suffix):
        alt = dest_dir / f"{stem}{ext}"
        if alt.is_file():
            return alt
    extras = sorted(
        p
        for p in dest_dir.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
    )
    return extras[-1] if extras else None


def download_media_url(
    url: str,
    dest_dir: str | Path,
    cookies: str | Path | None = None,
) -> Path:
    url = url.strip()
    if not is_url(url):
        raise ValueError(f"Not a valid URL: {url}")

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    cookie_path = resolve_cookies(cookies)

    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("yt-dlp is not installed. pip install -U yt-dlp") from exc

    # Audio first: the pipeline extracts wav anyway. Video 401+140 often 403s.
    attempts = [
        ("bestaudio[ext=m4a]/bestaudio/best", ["android", "ios"], None),
        ("bestaudio[ext=m4a]/bestaudio/best", ["tv", "mweb", "web"], None),
        ("best[height<=360]/worst", ["android", "ios", "web"], "mp4"),
    ]

    errors: list[str] = []
    for fmt, clients, merge in attempts:
        opts = _ydl_opts(dest_dir, fmt, clients, merge, cookie_path)
        print(f"yt-dlp format={fmt} clients={clients}")
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise RuntimeError("yt-dlp did not return media info.")
                found = _resolve_downloaded(info, ydl, dest_dir)
                if found:
                    return found
        except Exception as exc:
            errors.append(f"{fmt} / {clients}: {exc}")
            print(f"yt-dlp attempt failed: {exc}")

    hint = ""
    joined = "\n".join(errors)
    if "not a bot" in joined.lower() or "cookies" in joined.lower():
        hint = (
            " YouTube blocked this Colab IP. Export your YouTube cookies "
            "(Netscape cookies.txt) and pass --cookies / upload cookies.txt. "
            "https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies"
        )
    raise RuntimeError(
        "Download failed after retries." + hint + "\n" + joined
    )
