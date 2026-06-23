from __future__ import annotations

from datetime import datetime, timezone


def word_wrap(text: str, max_chars: int) -> list[str]:
    """Split *text* into lines of at most *max_chars* characters, breaking on spaces."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words: list[str] = paragraph.split(" ")
        line: list[str] = []
        for word in words:
            if sum(len(w) for w in line) + len(line) + len(word) > max_chars:
                lines.append(" ".join(line))
                line = [word]
            else:
                line.append(word)
        if line:
            lines.append(" ".join(line))
    return lines or [""]


def human_size(num_bytes: int) -> str:
    """Format a byte count as a short human-readable string (e.g. "34 MB")."""
    size: float = float(max(num_bytes, 0))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.0f} {unit}" if size >= 10 else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.0f} GB"


def human_time(ts: datetime) -> str:
    now: datetime = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta_seconds: float = (now - ts).total_seconds()
    if delta_seconds < 0:
        delta_seconds = 0
    if delta_seconds < 60:
        return "just now"
    if delta_seconds < 3600:
        minutes: int = int(delta_seconds / 60)
        return f"{minutes}m ago"
    if delta_seconds < 86400:
        hours: int = int(delta_seconds / 3600)
        return f"{hours}h ago"
    if delta_seconds < 604800:
        days: int = int(delta_seconds / 86400)
        return f"{days} days ago" if days != 1 else "1 day ago"
    month_names: list[str] = [
        "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    day: int = ts.day
    if ts.year == now.year:
        return f"{month_names[ts.month]} {day}"
    return f"{month_names[ts.month]} {day}, {ts.year}"
