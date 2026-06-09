from __future__ import annotations

from datetime import datetime, timezone


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
