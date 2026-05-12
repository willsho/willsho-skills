#!/usr/bin/env python3
"""
Extract Claude Code session content for work digest.

Scans ~/.claude/projects/ for session transcripts, extracts both user messages
and key assistant responses per session, and outputs structured data for Claude
to summarize into a work digest report.

Usage:
    python3 summarize_sessions.py [OPTIONS]

Options:
    --range <spec>       Time range: today, week, month, YYYY-MM-DD, or YYYY-MM-DD:YYYY-MM-DD
    --project <keyword>  Filter sessions by project path keyword
    --json               Output JSON (default: plain text summary)
    --max-turns <n>      Max conversation turns per session to include (default: 30)
"""

import json
import sys
import argparse
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Time range
# ---------------------------------------------------------------------------
def resolve_range(spec: str):
    """Return (start_dt, end_dt) as naive local datetimes."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if spec == "today":
        return today, today + timedelta(days=1)
    if spec == "week":
        monday = today - timedelta(days=today.weekday())
        return monday, today + timedelta(days=1)
    if spec == "month":
        first = today.replace(day=1)
        return first, today + timedelta(days=1)
    if ":" in spec:
        parts = spec.split(":")
        return datetime.fromisoformat(parts[0]), datetime.fromisoformat(parts[1]) + timedelta(days=1)
    d = datetime.fromisoformat(spec)
    return d, d + timedelta(days=1)


def parse_iso_ts(ts_str) -> Optional[datetime]:
    if not ts_str or not isinstance(ts_str, str):
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Project name cleanup
# ---------------------------------------------------------------------------
def friendly_project(raw: str) -> str:
    """Turn the escaped project directory name into something readable."""
    raw = re.sub(r'^-Users-[^-]+-?', '', raw)
    if raw:
        return raw.replace('-', '/')
    return "~"


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------
def extract_text_from_content(content) -> str:
    """Extract plain text from message content (string or list of parts)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", "").strip())
                # Skip tool_use and tool_result — too noisy
        return "\n".join(p for p in parts if p)
    return ""


def is_trivial_user_message(text: str) -> bool:
    """Return True for short filler messages that add no information."""
    stripped = text.strip()
    if len(stripped) <= 6:
        return True
    trivial = {"继续", "好的", "ok", "好", "嗯", "是的", "对", "没问题", "谢谢", "确认", "yes", "no", "retry", "重试"}
    return stripped.lower() in trivial


def truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


# ---------------------------------------------------------------------------
# Core scan
# ---------------------------------------------------------------------------
def scan_sessions(projects_dir: Path, start_dt: datetime, end_dt: datetime,
                  project_filter: Optional[str], max_turns: int):
    """Scan JSONL files and return session data with conversation turns."""
    start_epoch = start_dt.timestamp()
    end_epoch = end_dt.timestamp()

    all_files = []
    for p in projects_dir.rglob("*.jsonl"):
        mtime = p.stat().st_mtime
        if mtime < start_epoch or mtime >= end_epoch:
            continue
        is_sub = "subagents" in str(p)
        if is_sub:
            continue
        project_raw = p.parent.name
        if project_filter and project_filter.lower() not in project_raw.lower():
            continue
        all_files.append({
            "path": p,
            "session_id": p.stem,
            "project_raw": project_raw,
        })

    sessions = {}
    for finfo in all_files:
        sid = finfo["session_id"]
        session = {
            "session_id": sid,
            "project_raw": finfo["project_raw"],
            "project": friendly_project(finfo["project_raw"]),
            "first_ts": None,
            "last_ts": None,
            # Each turn: {"role": "user"|"assistant", "text": str}
            "turns": [],
            "total_user_messages": 0,
            "total_assistant_messages": 0,
        }

        try:
            with open(finfo["path"], "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    ts = parse_iso_ts(data.get("timestamp"))
                    if ts:
                        if session["first_ts"] is None or ts < session["first_ts"]:
                            session["first_ts"] = ts
                        if session["last_ts"] is None or ts > session["last_ts"]:
                            session["last_ts"] = ts

                    msg_type = data.get("type")

                    # --- User messages ---
                    if msg_type == "user":
                        msg = data.get("message", {})
                        if not isinstance(msg, dict):
                            continue
                        content = msg.get("content", "")
                        text = extract_text_from_content(content)
                        if not text:
                            continue
                        session["total_user_messages"] += 1
                        if is_trivial_user_message(text):
                            continue
                        if len(session["turns"]) < max_turns:
                            session["turns"].append({
                                "role": "user",
                                "text": truncate(text, 500),
                            })

                    # --- Assistant messages ---
                    elif msg_type == "assistant":
                        msg = data.get("message", {})
                        if not isinstance(msg, dict):
                            continue
                        content = msg.get("content", [])
                        text = extract_text_from_content(content)
                        if not text:
                            continue
                        session["total_assistant_messages"] += 1
                        if len(session["turns"]) < max_turns:
                            session["turns"].append({
                                "role": "assistant",
                                "text": truncate(text, 800),
                            })

        except Exception:
            continue

        # Only include sessions with actual content
        if session["turns"]:
            sessions[sid] = session

    return sessions


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def output_json(sessions: dict, range_label: str):
    result = {
        "range": range_label,
        "session_count": len(sessions),
        "sessions": [],
    }
    for sid, s in sorted(sessions.items(), key=lambda x: str(x[1].get("first_ts") or "")):
        result["sessions"].append({
            "session_id": sid[:8],
            "project": s["project"],
            "date": s["first_ts"].strftime("%Y-%m-%d %H:%M") if s["first_ts"] else "unknown",
            "total_user_messages": s["total_user_messages"],
            "total_assistant_messages": s["total_assistant_messages"],
            "turns": s["turns"],
        })
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


def output_text(sessions: dict, range_label: str):
    sorted_sessions = sorted(sessions.items(), key=lambda x: str(x[1].get("first_ts") or ""))
    print(f"=== Claude Code 工作记录 — {range_label} ===")
    print(f"共 {len(sessions)} 个 session\n")

    for sid, s in sorted_sessions:
        date_str = s["first_ts"].strftime("%m/%d %H:%M") if s["first_ts"] else "N/A"
        print(f"--- [{date_str}] {s['project']} ({sid[:8]}) ---")
        print(f"用户消息: {s['total_user_messages']}  助手消息: {s['total_assistant_messages']}")
        for turn in s["turns"]:
            role_label = "👤" if turn["role"] == "user" else "🤖"
            preview = turn["text"][:200].replace("\n", " ")
            print(f"  {role_label} {preview}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Extract Claude Code session content for digest")
    parser.add_argument("--range", default="week",
                        help="Time range: today, week, month, YYYY-MM-DD, or YYYY-MM-DD:YYYY-MM-DD")
    parser.add_argument("--project", default=None,
                        help="Filter by project keyword")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON format")
    parser.add_argument("--max-turns", type=int, default=30,
                        help="Max conversation turns per session (default: 30)")
    args = parser.parse_args()

    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        print("Error: ~/.claude/projects/ not found.", file=sys.stderr)
        sys.exit(1)

    start_dt, end_dt = resolve_range(args.range)
    range_label = f"{start_dt.strftime('%Y/%m/%d')} ~ {(end_dt - timedelta(days=1)).strftime('%Y/%m/%d')}"

    sessions = scan_sessions(projects_dir, start_dt, end_dt, args.project, args.max_turns)

    if not sessions:
        print(f"No sessions found for range: {range_label}")
        sys.exit(0)

    if args.json:
        output_json(sessions, range_label)
    else:
        output_text(sessions, range_label)


if __name__ == "__main__":
    main()
