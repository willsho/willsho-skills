#!/usr/bin/env python3
"""
Fetch YouTube transcript directly using youtube-transcript-api (primary) or yt-dlp (fallback).
Usage: fetch_transcript.py VIDEO_ID [LANG]
Output: JSON with video_id, lang, source, title, plain_text, items
"""

import html
import json
import re
import sys
import urllib.request
from typing import Any, Optional

LANG_PRIORITY = ["en", "zh-CN", "zh-TW"]
TIMESTAMP_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})"
)
TAG_RE = re.compile(r"<[^>]+>")


def main():
    if len(sys.argv) < 2:
        _exit_error("Usage: fetch_transcript.py VIDEO_ID [LANG]")

    video_id = sys.argv[1]
    lang = sys.argv[2] if len(sys.argv) > 2 else None

    langs_to_try = [lang] if lang else LANG_PRIORITY

    primary_error: Optional[str] = None

    # Primary: youtube-transcript-api
    try:
        result = _fetch_with_youtube_transcript_api(video_id, langs_to_try)
        print(json.dumps(result, ensure_ascii=False))
        return
    except Exception as exc:
        primary_error = f"{type(exc).__name__}: {exc}"

    # Fallback: yt-dlp
    try:
        result = _fetch_with_ytdlp(video_id, langs_to_try)
        print(json.dumps(result, ensure_ascii=False))
        return
    except Exception as exc:
        _exit_error(
            f"Both methods failed. primary={primary_error}; fallback={type(exc).__name__}: {exc}"
        )


def _fetch_with_youtube_transcript_api(video_id: str, langs: list[str]) -> dict:
    from youtube_transcript_api import YouTubeTranscriptApi

    raw_items: list[dict[str, Any]]
    used_lang: str

    if hasattr(YouTubeTranscriptApi, "get_transcript"):
        raw_items = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
        used_lang = langs[0]
    else:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id, languages=langs)
        used_lang = getattr(transcript, "language_code", langs[0])
        if hasattr(transcript, "to_raw_data"):
            raw_items = transcript.to_raw_data()
        else:
            raw_items = [
                {"text": item.text, "start": item.start, "duration": item.duration}
                for item in transcript
            ]

    items = [
        {"text": str(r.get("text", "")).strip(), "start": float(r.get("start", 0)), "duration": float(r.get("duration", 0))}
        for r in raw_items
        if str(r.get("text", "")).strip()
    ]
    if not items:
        raise RuntimeError("Empty transcript")

    return {
        "video_id": video_id,
        "lang": used_lang,
        "source": "youtube-transcript-api",
        "title": None,
        "plain_text": " ".join(i["text"] for i in items),
        "items": items,
    }


def _fetch_with_ytdlp(video_id: str, langs: list[str]) -> dict:
    from yt_dlp import YoutubeDL

    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if not isinstance(info, dict):
        raise RuntimeError("yt-dlp returned unexpected response")

    title: Optional[str] = info.get("title")
    track = None
    used_lang = langs[0]

    for lang in langs:
        track = _select_track(info.get("subtitles") or {}, lang)
        if track:
            used_lang = lang
            break

    if track is None:
        for lang in langs:
            track = _select_track(info.get("automatic_captions") or {}, lang)
            if track:
                used_lang = lang
                break

    if track is None:
        raise RuntimeError("No caption track found")

    body = _fetch_url(track["url"])
    ext = str(track.get("ext", "")).lower()
    items = _parse_json3(body) if ext == "json3" else _parse_vtt(body)

    if not items:
        raise RuntimeError("Parsed empty transcript")

    return {
        "video_id": video_id,
        "lang": used_lang,
        "source": "yt-dlp",
        "title": title,
        "plain_text": " ".join(i["text"] for i in items),
        "items": items,
    }


def _select_track(captions: dict, lang: str) -> Optional[dict]:
    exact = [k for k in captions if k.lower() == lang.lower()]
    regional = [k for k in captions if k.lower().startswith(f"{lang.lower()}-")]
    for key in exact + regional:
        tracks = captions.get(key) or []
        for preferred in ("json3", "vtt", "srv3", "ttml"):
            for t in tracks:
                if t.get("url") and str(t.get("ext", "")).lower() == preferred:
                    return t
        for t in tracks:
            if t.get("url"):
                return t
    return None


def _fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_json3(body: str) -> list[dict]:
    data = json.loads(body)
    items = []
    for event in data.get("events", []):
        text = "".join(s.get("utf8", "") for s in (event.get("segs") or []))
        text = _clean(text)
        if not text:
            continue
        items.append({
            "text": text,
            "start": float(event.get("tStartMs", 0)) / 1000,
            "duration": float(event.get("dDurationMs", 0)) / 1000,
        })
    return items


def _parse_vtt(body: str) -> list[dict]:
    items = []
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        m = TIMESTAMP_RE.search(lines[i])
        if m is None:
            i += 1
            continue
        start = _ts(m.group("start"))
        end = _ts(m.group("end"))
        i += 1
        text_lines = []
        while i < len(lines) and lines[i].strip():
            text_lines.append(lines[i].strip())
            i += 1
        text = _clean(" ".join(text_lines))
        if text:
            items.append({"text": text, "start": start, "duration": max(0.0, end - start)})
        i += 1
    return items


def _ts(value: str) -> float:
    h, m, s = value.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _clean(value: str) -> str:
    value = TAG_RE.sub("", value)
    value = html.unescape(value)
    return " ".join(value.replace("\n", " ").split())


def _exit_error(message: str):
    print(json.dumps({"error": message}, ensure_ascii=False))
    sys.exit(1)


if __name__ == "__main__":
    main()
