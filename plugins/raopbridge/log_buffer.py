# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License,
# version 2.
"""
In-memory ring-buffer log handler for the raopbridge plugin.

Captures log records from the plugin's logger hierarchy into a
fixed-size deque so they can be displayed in the SDUI diagnostics
tab without requiring the user to dig through server log files.

Usage::

    from .log_buffer import install_log_buffer, get_recent_logs, clear_logs

    # In setup():
    install_log_buffer()          # attach handler to 'resonance_plugins.raopbridge'

    # In get_ui():
    entries = get_recent_logs()   # list of {"timestamp", "level", "message"}

    # In teardown():
    clear_logs()                  # free memory, remove handler
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_CAPACITY = 200
"""Maximum number of log entries kept in memory."""

_MIN_LEVEL = logging.DEBUG
"""Minimum log level to capture (captures everything; the UI can filter)."""

# The logger name used by the plugin when loaded by PluginManager.
# PluginManager imports plugins as ``resonance_plugins.<name>``, so
# ``logging.getLogger(__name__)`` inside the plugin yields
# ``resonance_plugins.raopbridge``.  We attach our handler to that
# logger so we also capture records from sub-modules (bridge, config, …).
_LOGGER_NAME = "resonance_plugins.raopbridge"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LogEntry:
    """One captured log record."""

    timestamp: str
    """ISO-8601 formatted timestamp (UTC)."""

    level: str
    """Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL)."""

    message: str
    """Formatted log message (including any exception info)."""

    logger_name: str
    """Name of the logger that emitted the record."""

    def to_dict(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
            "logger": self.logger_name,
        }


# ---------------------------------------------------------------------------
# Ring-buffer handler
# ---------------------------------------------------------------------------


class RingBufferHandler(logging.Handler):
    """A :class:`logging.Handler` backed by a bounded :class:`deque`.

    Records beyond *capacity* are silently dropped (oldest first).
    Thread-safe through the built-in :class:`logging.Handler` lock.
    """

    def __init__(self, capacity: int = _DEFAULT_CAPACITY) -> None:
        super().__init__(level=_MIN_LEVEL)
        self._buffer: deque[LogEntry] = deque(maxlen=capacity)
        self._dropped: int = 0

    # -- logging.Handler interface ------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Format the timestamp in UTC ISO-8601
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created))

            # Build the message (includes exception traceback if present)
            message = self.format(record)

            entry = LogEntry(
                timestamp=ts,
                level=record.levelname,
                message=message,
                logger_name=record.name,
            )

            was_full = len(self._buffer) == self._buffer.maxlen
            self._buffer.append(entry)
            if was_full:
                self._dropped += 1

        except Exception:
            self.handleError(record)

    # -- Public API ---------------------------------------------------------

    @property
    def entries(self) -> list[LogEntry]:
        """Return a snapshot of all buffered entries (oldest first)."""
        return list(self._buffer)

    @property
    def count(self) -> int:
        """Number of entries currently buffered."""
        return len(self._buffer)

    @property
    def dropped(self) -> int:
        """Number of entries dropped due to buffer overflow."""
        return self._dropped

    def clear(self) -> None:
        """Discard all buffered entries and reset the drop counter."""
        self._buffer.clear()
        self._dropped = 0


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_handler: RingBufferHandler | None = None


def install_log_buffer(capacity: int = _DEFAULT_CAPACITY) -> RingBufferHandler:
    """Attach a :class:`RingBufferHandler` to the plugin's logger tree.

    Safe to call multiple times — only one handler is installed.
    Returns the handler instance.
    """
    global _handler

    if _handler is not None:
        return _handler

    _handler = RingBufferHandler(capacity=capacity)
    # Use a concise format — the timestamp is already in the LogEntry
    _handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))

    target_logger = logging.getLogger(_LOGGER_NAME)
    target_logger.addHandler(_handler)

    return _handler


def uninstall_log_buffer() -> None:
    """Remove the handler from the logger tree and discard buffered data."""
    global _handler

    if _handler is None:
        return

    target_logger = logging.getLogger(_LOGGER_NAME)
    target_logger.removeHandler(_handler)
    _handler.clear()
    _handler = None


def get_recent_logs(
    limit: int = 50,
    *,
    min_level: str | None = None,
) -> list[dict[str, str]]:
    """Return the most recent log entries as plain dicts.

    Args:
        limit: Maximum number of entries to return (newest last).
        min_level: Optional minimum level filter (e.g. ``"WARNING"``).
                   If ``None``, all captured entries are returned.

    Returns:
        List of ``{"timestamp", "level", "message", "logger"}`` dicts,
        ordered oldest-first.
    """
    if _handler is None:
        return []

    entries = _handler.entries

    if min_level is not None:
        threshold = getattr(logging, min_level.upper(), logging.DEBUG)
        entries = [e for e in entries if getattr(logging, e.level, 0) >= threshold]

    # Return the *last* ``limit`` entries (newest at the end)
    if limit and len(entries) > limit:
        entries = entries[-limit:]

    return [e.to_dict() for e in entries]


def get_log_stats() -> dict[str, Any]:
    """Return summary statistics about the log buffer."""
    if _handler is None:
        return {"installed": False, "count": 0, "dropped": 0, "capacity": 0}

    return {
        "installed": True,
        "count": _handler.count,
        "dropped": _handler.dropped,
        "capacity": _handler._buffer.maxlen or 0,
    }


def clear_logs() -> None:
    """Clear the log buffer without removing the handler."""
    if _handler is not None:
        _handler.clear()
