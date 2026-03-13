from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone


def parse_timezone_offset(offset: str) -> timezone:
    sign = 1 if offset.startswith("+") else -1
    hours_text, minutes_text = offset[1:].split(":", maxsplit=1)
    delta = timedelta(hours=int(hours_text), minutes=int(minutes_text))
    return timezone(sign * delta)


def resolve_now(current_time: str | None = None, timezone_offset: str = "+08:00") -> datetime:
    if current_time:
        return datetime.fromisoformat(current_time)
    return datetime.now(parse_timezone_offset(timezone_offset))


def build_task_id(decision_id: str, channel: str, delivery_timing: str) -> str:
    payload = f"{decision_id}:{channel}:{delivery_timing}".encode("utf-8")
    return f"task_{hashlib.sha1(payload).hexdigest()[:12]}"


def build_dedupe_key(decision_id: str, channel: str, delivery_timing: str) -> str:
    return f"{decision_id}:{channel}:{delivery_timing}"


def build_digest_job_id(user_id: str, window_key: str) -> str:
    payload = f"{user_id}:{window_key}".encode("utf-8")
    return f"job_{hashlib.sha1(payload).hexdigest()[:12]}"


def build_log_id(override: str | None = None) -> str:
    if override:
        return override
    return f"dlv_{uuid.uuid4().hex[:12]}"


def build_provider_message_id(channel: str, task_id: str, override: str | None = None) -> str:
    if override:
        return override
    payload = f"{channel}:{task_id}".encode("utf-8")
    return f"msg_{hashlib.sha1(payload).hexdigest()[:10]}"


def resolve_digest_window(
    current_time: datetime,
    digest_hour: int = 20,
    digest_minute: int = 0,
) -> tuple[str, str]:
    scheduled = current_time.replace(
        hour=digest_hour,
        minute=digest_minute,
        second=0,
        microsecond=0,
    )
    if current_time >= scheduled:
        scheduled += timedelta(days=1)

    return scheduled.date().isoformat(), scheduled.isoformat()
