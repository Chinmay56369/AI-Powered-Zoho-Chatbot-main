from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def parse_human_date(value: str | None) -> str | None:
    if not value:
        return None

    cleaned = value.strip().lower()
    today = date.today()
    mapping = {
        "today": today,
        "tomorrow": today + timedelta(days=1),
    }

    if cleaned in mapping:
        return mapping[cleaned].strftime("%m-%d-%Y")

    for fmt in ("%Y-%m-%d", "%m-%d-%Y", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(value.strip(), fmt)
            return parsed.strftime("%m-%d-%Y")
        except ValueError:
            continue
    return None


def iso_after_seconds(seconds: int) -> str:
    return (now_utc() + timedelta(seconds=seconds)).isoformat()

