from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SleepTimerStore:
    """Persists timer history to a JSON file.

    Does NOT persist active timers — only completed/cancelled timer events.
    """

    def __init__(self, data_dir: Path, max_history: int = 50) -> None:
        self._path = data_dir / "sleep_timer_history.json"
        self._max_history = max_history
        self._history: list[dict[str, Any]] = []

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    @property
    def count(self) -> int:
        return len(self._history)

    def load(self) -> None:
        """Load history from disk. Silently handles missing/corrupt files."""
        if not self._path.exists():
            return

        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._history = data.get("history", [])
            logger.debug("Loaded %d history entries", len(self._history))
        except (json.JSONDecodeError, KeyError):
            logger.warning("Corrupt sleep timer history file, starting fresh")
            self._history = []

    def save(self) -> None:
        """Save history to disk with atomic write."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        data = {"history": self._history[-self._max_history:]}

        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp_path.replace(self._path)

    def record_timer_event(
        self,
        player_id: str,
        player_name: str,
        duration_minutes: int,
        event_type: str,  # "expired", "cancelled"
        fade_duration: int = 0,
    ) -> dict[str, Any]:
        """Record a timer event in history."""
        import time

        entry = {
            "player_id": player_id,
            "player_name": player_name,
            "duration_minutes": duration_minutes,
            "event_type": event_type,
            "fade_duration": fade_duration,
            "timestamp": time.time(),
        }

        self._history.append(entry)

        # Trim if over limit
        if self._max_history > 0 and len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        self.save()
        return entry

    def clear(self) -> None:
        """Clear all history."""
        self._history.clear()
        self.save()

    def update_max_history(self, new_max: int) -> None:
        """Update max history setting and trim if needed."""
        self._max_history = new_max
        if new_max > 0 and len(self._history) > new_max:
            self._history = self._history[-new_max:]
            self.save()
