#!/usr/bin/env python3
"""Transcribe local or remote media with StepFun StepAudio ASR.

The StepFun request format and preprocessing strategy are adapted from the
Mercury project's StepFun transcriber: mono 16 kHz MP3, time-based chunking,
title-derived hotwords, and SSE response parsing.
"""

from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator, Sequence


STEPFUN_TRANSCRIBE_URL = "https://api.stepfun.com/v1/audio/asr/sse"
STEPFUN_MODEL = "stepaudio-2.5-asr"
AUDIO_RATE = "16000"
AUDIO_BITRATE = "32k"
DEFAULT_SEGMENT_SECONDS = 600

_TITLE_SPLIT_PATTERN = re.compile(
    r"[\s,，。.!！?？:：;；、|｜/\\—–_·•（）()【】\[\]《》<>]+"
)
_EPISODE_NUMBER_PATTERN = re.compile(
    r"(?i)(?:no|ep|episode|vol)\.?\s*[-#]?\s*\d+(?:\.\d+)?|第\s*\d+\s*[期集季]"
)
_TITLE_LABELS = {
    "对话",
    "访谈",
    "专访",
    "嘉宾",
    "请到",
    "请来",
    "聊聊",
    "聊天",
    "和",
    "与",
}
_ROLE_PATTERN = re.compile(
    r"^(?P<before>.{2,16}?)(?:联合创始人|共同创始人|创始人|创作者|制作人|"
    r"打造者|主理人|作者|主播|教授|博士|导演|编剧|演员|歌手|CEO|CTO|COO|CFO)"
    r"(?P<after>.{2,10})?$",
    re.I,
)
_NOISE_PATTERNS = [
    r"[\s.，。、]*Amara\.org\s*社区提供",
    r"(?:这个)?字幕由[\s\w.]{0,15}?社区提供",
    r"请输出包含[^\n]{0,40}?的转写文本[。．]?",
    r"[※★]+",
]


class TranscriptionError(RuntimeError):
    """An expected transcription failure with a user-readable message."""


def log(message: str) -> None:
    print(f"[stepfun-asr] {message}", file=sys.stderr, flush=True)


def extract_title_hotwords(title: str, max_hotwords: int = 20) -> list[str]:
    """Extract likely names, entities, and domain phrases from a title."""
    if not title:
        return []

    normalized = _EPISODE_NUMBER_PATTERN.sub(" ", title)
    hotwords: list[str] = []

    def add(value: str) -> None:
        value = value.strip(" -—–:：,，。.!！?？")
        if (
            2 <= len(value) <= 24
            and value not in _TITLE_LABELS
            and not value.isdigit()
            and value not in hotwords
            and len(hotwords) < max_hotwords
        ):
            hotwords.append(value)

    for raw_part in _TITLE_SPLIT_PATTERN.split(normalized):
        part = raw_part.strip()
        if not part or part in _TITLE_LABELS:
            continue

        for label in sorted(_TITLE_LABELS, key=len, reverse=True):
            if part.startswith(label) and len(part) > len(label):
                part = part[len(label) :]
                break
        if not part:
            continue

        for latin_word in re.findall(r"[A-Za-z][A-Za-z0-9.+-]{1,31}", part):
            add(latin_word)

        chinese_part = re.sub(r"[A-Za-z][A-Za-z0-9.+-]*", "", part).strip()
        role_match = _ROLE_PATTERN.match(chinese_part)
        if role_match:
            add(role_match.group("before"))
            add(role_match.group("after") or "")
        add(part)

    return hotwords


def merge_hotwords(title: str, manual: Sequence[str], limit: int = 100) -> list[str]:
    """Combine explicit and title-derived hotwords, preserving stable order."""
    merged: list[str] = []
    for value in [*manual, *extract_title_hotwords(title)]:
        value = value.strip()
        if value and value not in merged:
            merged.append(value)
        if len(merged) >= limit:
            break
    return merged


def iter_sse_data(lines: Iterable[bytes | str]) -> Iterator[str]:
    """Yield complete SSE data payloads, including multi-line events."""
    data_lines: list[str] = []
    for raw_line in lines:
        line = (
            raw_line.decode("utf-8", "replace")
            if isinstance(raw_line, bytes)
            else raw_line
        ).rstrip("\r\n")
        if not line:
            if data_lines:
                yield "\n".join(data_lines)
                data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and field == "data":
            data_lines.append(value[1:] if value.startswith(" ") else value)
    if data_lines:
        yield "\n".join(data_lines)


def parse_stepfun_sse(lines: Iterable[bytes | str]) -> str:
    """Parse StepFun transcript SSE events and return the final text."""
    deltas: list[str] = []
    for payload in iter_sse_data(lines):
        if payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise TranscriptionError(
                f"StepFun returned invalid SSE data: {payload[:120]}"
            ) from exc

        event_type = event.get("type")
        if event_type == "transcript.text.delta":
            deltas.append(event.get("delta", ""))
        elif event_type == "transcript.text.done":
            text = event.get("text") or "".join(deltas)
            if not text:
                raise TranscriptionError(
                    "StepFun returned an empty transcript; check that the media "
                    "contains audible speech and that --language matches it"
                )
            return text
        elif event_type == "error":
            raise TranscriptionError(
                f"StepFun error: {event.get('message', 'unknown error')}"
            )

    raise TranscriptionError("StepFun stream ended before transcript.text.done")


def _http_error_body(error: urllib.error.HTTPError) -> str:
    try:
        return error.read(500).decode("utf-8", "replace")
    except OSError:
        return str(error.reason)


def transcribe_chunk(
    chunk_path: Path,
    api_key: str,
    language: str,
    hotwords: Sequence[str],
    max_retries: int = 5,
) -> str:
    """Transcribe one MP3 chunk through StepFun's SSE endpoint."""
    try:
        audio_data = base64.b64encode(chunk_path.read_bytes()).decode("ascii")
    except OSError as exc:
        raise TranscriptionError(f"could not read audio chunk: {exc}") from exc

    transcription: dict[str, object] = {
        "language": language,
        "model": STEPFUN_MODEL,
        "enable_itn": True,
        "enable_timestamp": False,
    }
    if hotwords:
        transcription["hotwords"] = list(hotwords)

    payload = json.dumps(
        {
            "audio": {
                "data": audio_data,
                "input": {
                    "transcription": transcription,
                    "format": {"type": "mp3"},
                },
            }
        },
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    for attempt in range(max_retries):
        request = urllib.request.Request(
            STEPFUN_TRANSCRIBE_URL,
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return parse_stepfun_sse(response)
        except urllib.error.HTTPError as exc:
            body = _http_error_body(exc)
            if exc.code == 429:
                wait = 30
            elif exc.code >= 500:
                wait = (attempt + 1) * 15
            else:
                raise TranscriptionError(
                    f"StepFun HTTP {exc.code}: {body[:200]}"
                ) from exc
            last_error = f"StepFun HTTP {exc.code}: {body[:200]}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            wait = (attempt + 1) * 15
            last_error = f"StepFun request failed: {exc}"

        if attempt < max_retries - 1:
            log(f"{last_error}; retrying in {wait}s")
            time.sleep(wait)

    raise TranscriptionError(
        f"StepFun failed after {max_retries} attempts: {last_error}"
    )


def download_media(url: str, destination: Path) -> Path:
    """Download a public media URL to a temporary local file."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output, length=1 << 16)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise TranscriptionError(f"download failed: {exc}") from exc
    log(f"downloaded {destination.stat().st_size / 1024 / 1024:.1f} MB")
    return destination


def resolve_input(source: str, tmpdir: Path) -> Path:
    """Resolve a local path or public HTTP(S) URL to a local media file."""
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in {"http", "https"}:
        suffix = Path(parsed.path).suffix.lower()
        if not suffix or len(suffix) > 8:
            suffix = ".media"
        return download_media(source, tmpdir / f"original{suffix}")
    if parsed.scheme and parsed.scheme != "file":
        raise TranscriptionError(
            "input must be a local file or a public http(s) media URL"
        )

    path = Path(urllib.request.url2pathname(parsed.path) if parsed.scheme == "file" else source)
    path = path.expanduser().resolve()
    if not path.is_file():
        raise TranscriptionError(f"input does not exist or is not a file: {path}")
    return path


def compress_and_split(
    source: Path,
    tmpdir: Path,
    segment_seconds: int = DEFAULT_SEGMENT_SECONDS,
) -> list[Path]:
    """Transcode media and emit MP3 chunks no longer than segment_seconds."""
    pattern = tmpdir / "chunk_%03d.mp3"
    transcode_and_segment = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        AUDIO_RATE,
        "-b:a",
        AUDIO_BITRATE,
        "-f",
        "segment",
        "-segment_time",
        str(segment_seconds),
        "-reset_timestamps",
        "1",
        str(pattern),
    ]
    try:
        subprocess.run(
            transcode_and_segment,
            check=True,
            capture_output=True,
            timeout=1800,
        )
    except FileNotFoundError as exc:
        raise TranscriptionError("ffmpeg not found") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", "replace")[:500]
        raise TranscriptionError(f"ffmpeg transcode/segment failed: {stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TranscriptionError("ffmpeg transcode/segment timed out") from exc

    chunks = [Path(item) for item in sorted(glob.glob(str(tmpdir / "chunk_*.mp3")))]
    if not chunks:
        raise TranscriptionError("ffmpeg produced no audio chunks")
    log(f"prepared {len(chunks)} chunk(s), up to {segment_seconds}s each")
    return chunks


def clean_transcript(text: str) -> str:
    """Remove a few bounded ASR artifacts and normalize horizontal whitespace."""
    for pattern in _NOISE_PATTERNS:
        text = re.sub(pattern, "", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def transcribe(
    source: str,
    api_key: str,
    title: str = "",
    manual_hotwords: Sequence[str] = (),
    language: str = "zh",
    segment_seconds: int = DEFAULT_SEGMENT_SECONDS,
) -> str:
    """Run the download, transcode, chunk, and transcription pipeline."""
    hotwords = merge_hotwords(title, manual_hotwords)
    if hotwords:
        log(f"using hotwords: {', '.join(hotwords)}")

    with tempfile.TemporaryDirectory(prefix="stepfun_asr_") as directory:
        tmpdir = Path(directory)
        local_source = resolve_input(source, tmpdir)
        chunks = compress_and_split(
            local_source,
            tmpdir,
            segment_seconds=segment_seconds,
        )
        parts: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            log(f"transcribing chunk {index}/{len(chunks)}")
            part = clean_transcript(
                transcribe_chunk(chunk, api_key, language, hotwords)
            )
            if not part:
                raise TranscriptionError(f"chunk {index} returned empty text")
            parts.append(part)

    transcript = "\n".join(parts).strip()
    if not transcript:
        raise TranscriptionError("empty transcript")
    return transcript


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Transcribe a local or remote media file with StepFun StepAudio ASR."
    )
    parser.add_argument("source", help="Local media path, file:// URL, or public http(s) URL")
    parser.add_argument("-o", "--output", help="Write plain transcript text to this path")
    parser.add_argument("--title", default="", help="Title used to derive ASR hotwords")
    parser.add_argument(
        "--hotword",
        action="append",
        default=[],
        help="Explicit ASR hotword; repeat for multiple terms",
    )
    parser.add_argument("--language", default="zh", help="ASR language code (default: zh)")
    parser.add_argument(
        "--segment-seconds",
        type=int,
        default=DEFAULT_SEGMENT_SECONDS,
        help=f"Maximum duration of each chunk (default: {DEFAULT_SEGMENT_SECONDS}s)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.segment_seconds <= 0:
        print("error: --segment-seconds must be positive", file=sys.stderr)
        return 2
    api_key = os.environ.get("STEPFUN_API_KEY", "").strip()
    if not api_key:
        print(
            "error: STEPFUN_API_KEY is not set; set it in your environment and retry",
            file=sys.stderr,
        )
        return 2

    try:
        transcript = transcribe(
            args.source,
            api_key,
            title=args.title,
            manual_hotwords=args.hotword,
            language=args.language,
            segment_seconds=args.segment_seconds,
        )
        if args.output:
            output = Path(args.output).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(transcript + "\n", encoding="utf-8")
            log(f"wrote {len(transcript)} characters to {output}")
        else:
            print(transcript)
        return 0
    except (TranscriptionError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
