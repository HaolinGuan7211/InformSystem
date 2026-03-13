from __future__ import annotations

from typing import Any


class MemoryConfigCache:
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def invalidate(self, prefix: str | None = None) -> None:
        if prefix is None:
            self._store.clear()
            return

        keys = [
            key
            for key in self._store
            if key == prefix or key.startswith(f"{prefix}:")
        ]
        for key in keys:
            self._store.pop(key, None)
