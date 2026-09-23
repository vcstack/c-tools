"""Download media from a URL (YouTube and other sites), same idea as SoniTranslate + yt-dlp."""

from __future__ import annotations

from pathlib import Path

from pipeline.audio import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS


def is_url(value: str | None) -> bool:
    text = (value or "").strip()
    return text.startswith("http://") or text.startswith("https://")


def download_media_url(url: str, dest_dir: str | Path) -> Path:
    url = url.strip()
    if not is_url(url):
        raise ValueError(f"Not a valid URL: {url}")

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("yt-dlp is not installed. pip install yt-dlp") from exc

    out_tmpl = str(dest_dir / "%(id)s.%(ext)s")
    opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "outtmpl": out_tmpl,
        "noplaylist": True,
        "restrictfilenames": True,
        "overwrites": True,
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": False,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise RuntimeError("yt-dlp did not return media info.")
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
    for ext in (".mp4", ".mkv", ".webm", ".m4a", ".mp3", candidate.suffix):
        alt = dest_dir / f"{stem}{ext}"
        if alt.is_file():
            return alt

    extras = sorted(
        p
        for p in dest_dir.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
    )
    if extras:
        return extras[-1]
    raise RuntimeError(f"Download finished but no media file was found for {url}")
