from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


class LoginCooldownGuard:
    def __init__(
        self,
        storage_path: Path,
        *,
        cooldown_seconds: int = 2 * 60 * 60,
    ) -> None:
        self._storage_path = storage_path
        self._cooldown = timedelta(seconds=cooldown_seconds)

    def assert_allowed(self, *, school_code: str, username: str) -> None:
        state = self._load_state()
        key = self._build_key(school_code, username)
        record = state.get(key)
        if not isinstance(record, dict):
            return

        last_attempt = record.get("last_attempt_at")
        if not isinstance(last_attempt, str):
            return

        attempted_at = datetime.fromisoformat(last_attempt)
        now = datetime.now(timezone.utc)
        if now - attempted_at < self._cooldown:
            remaining = self._cooldown - (now - attempted_at)
            remaining_minutes = max(1, int(remaining.total_seconds() // 60))
            raise PermissionError(
                f"Campus auth cooldown is active; try again in about {remaining_minutes} minutes"
            )

    def record_attempt(
        self,
        *,
        school_code: str,
        username: str,
        target_system: str,
        success: bool,
    ) -> None:
        state = self._load_state()
        key = self._build_key(school_code, username)
        now = datetime.now(timezone.utc).isoformat()
        previous = state.get(key, {})
        state[key] = {
            "school_code": school_code,
            "target_system": target_system,
            "last_attempt_at": now,
            "last_success_at": now if success else previous.get("last_success_at"),
            "attempt_count": int(previous.get("attempt_count", 0)) + 1,
        }
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_state(self) -> dict[str, dict]:
        if not self._storage_path.exists():
            return {}
        try:
            return json.loads(self._storage_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _build_key(self, school_code: str, username: str) -> str:
        digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
        return f"{school_code}:{digest}"
