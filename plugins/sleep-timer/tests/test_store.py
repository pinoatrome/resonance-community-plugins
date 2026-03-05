"""Tests for the SleepTimerStore."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from store import SleepTimerStore


class TestSleepTimerStore:
    """Test the SleepTimerStore."""

    def test_empty_store(self, tmp_path: Path):
        store = SleepTimerStore(tmp_path)
        assert store.count == 0
        assert store.history == []

    def test_record_event(self, tmp_path: Path):
        store = SleepTimerStore(tmp_path)
        entry = store.record_timer_event(
            player_id="aa:bb:cc:dd:ee:ff",
            player_name="Test",
            duration_minutes=30,
            event_type="expired",
            fade_duration=30,
        )
        assert entry["player_id"] == "aa:bb:cc:dd:ee:ff"
        assert entry["event_type"] == "expired"
        assert store.count == 1

    def test_record_trims_old_entries(self, tmp_path: Path):
        store = SleepTimerStore(tmp_path, max_history=5)
        for i in range(10):
            store.record_timer_event(
                player_id=f"player-{i}",
                player_name=f"P{i}",
                duration_minutes=30,
                event_type="expired",
            )
        assert store.count == 5
        # Should keep last 5
        assert store.history[0]["player_id"] == "player-5"

    def test_save_and_load(self, tmp_path: Path):
        store = SleepTimerStore(tmp_path)
        store.record_timer_event(
            player_id="aa:bb:cc:dd:ee:ff",
            player_name="Test",
            duration_minutes=30,
            event_type="expired",
        )
        store.record_timer_event(
            player_id="aa:bb:cc:dd:ee:ff",
            player_name="Test",
            duration_minutes=45,
            event_type="cancelled",
        )

        # Load into fresh store
        store2 = SleepTimerStore(tmp_path)
        store2.load()
        assert store2.count == 2
        assert store2.history[0]["duration_minutes"] == 30
        assert store2.history[1]["event_type"] == "cancelled"

    def test_load_corrupt_json(self, tmp_path: Path):
        history_file = tmp_path / "sleep_timer_history.json"
        history_file.write_text("not valid json{{{", encoding="utf-8")

        store = SleepTimerStore(tmp_path)
        store.load()
        assert store.count == 0

    def test_load_nonexistent(self, tmp_path: Path):
        store = SleepTimerStore(tmp_path)
        store.load()  # Should not raise
        assert store.count == 0

    def test_clear(self, tmp_path: Path):
        store = SleepTimerStore(tmp_path)
        store.record_timer_event(
            player_id="p1", player_name="P1",
            duration_minutes=30, event_type="expired",
        )
        store.record_timer_event(
            player_id="p2", player_name="P2",
            duration_minutes=45, event_type="cancelled",
        )
        assert store.count == 2

        store.clear()
        assert store.count == 0

        # Reload to verify persistence
        store2 = SleepTimerStore(tmp_path)
        store2.load()
        assert store2.count == 0

    def test_update_max_history(self, tmp_path: Path):
        store = SleepTimerStore(tmp_path, max_history=100)
        for i in range(20):
            store.record_timer_event(
                player_id=f"p{i}", player_name=f"P{i}",
                duration_minutes=30, event_type="expired",
            )
        assert store.count == 20

        store.update_max_history(10)
        assert store.count == 10

    def test_save_creates_directory(self, tmp_path: Path):
        nested = tmp_path / "sub" / "dir"
        store = SleepTimerStore(nested)
        store.record_timer_event(
            player_id="p1", player_name="P1",
            duration_minutes=30, event_type="expired",
        )
        assert (nested / "sleep_timer_history.json").exists()

    def test_history_property(self, tmp_path: Path):
        store = SleepTimerStore(tmp_path)
        store.record_timer_event(
            player_id="p1", player_name="P1",
            duration_minutes=30, event_type="expired",
        )
        # history should return a copy
        h = store.history
        h.clear()
        assert store.count == 1  # original unchanged
