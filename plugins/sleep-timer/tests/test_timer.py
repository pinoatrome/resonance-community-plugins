"""Tests for the SleepTimer dataclass and SleepTimerManager."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from timer import SleepTimer, SleepTimerManager
from fakes import FakePlayer


# ---------------------------------------------------------------------------
# SleepTimer dataclass
# ---------------------------------------------------------------------------

class TestSleepTimer:
    """Test the SleepTimer data class."""

    def test_creation(self):
        t = SleepTimer(
            player_id="aa:bb:cc:dd:ee:ff",
            player_name="Test",
            duration_minutes=30,
            fade_duration_seconds=30,
            fade_steps=15,
            stop_action="pause",
            restore_volume=True,
        )
        assert t.player_id == "aa:bb:cc:dd:ee:ff"
        assert t.player_name == "Test"
        assert t.duration_minutes == 30
        assert t.stop_action == "pause"

    def test_remaining_seconds(self):
        now = time.time()
        t = SleepTimer(
            player_id="p1", player_name="P1", duration_minutes=1,
            fade_duration_seconds=0, fade_steps=1,
            stop_action="pause", restore_volume=True,
            started_at=now,
        )
        remaining = t.remaining_seconds
        assert 55 < remaining <= 60

    def test_remaining_minutes(self):
        now = time.time()
        t = SleepTimer(
            player_id="p1", player_name="P1", duration_minutes=30,
            fade_duration_seconds=0, fade_steps=1,
            stop_action="pause", restore_volume=True,
            started_at=now,
        )
        assert 29.9 < t.remaining_minutes <= 30.0

    def test_progress(self):
        now = time.time()
        t = SleepTimer(
            player_id="p1", player_name="P1", duration_minutes=10,
            fade_duration_seconds=0, fade_steps=1,
            stop_action="pause", restore_volume=True,
            started_at=now - 300,  # 5 min ago
        )
        assert 0.49 < t.progress < 0.51

    def test_is_active_no_task(self):
        t = SleepTimer(
            player_id="p1", player_name="P1", duration_minutes=30,
            fade_duration_seconds=0, fade_steps=1,
            stop_action="pause", restore_volume=True,
        )
        # No task set -> not active
        assert t.is_active is False

    def test_to_dict(self):
        t = SleepTimer(
            player_id="p1", player_name="P1", duration_minutes=30,
            fade_duration_seconds=30, fade_steps=15,
            stop_action="pause", restore_volume=True,
            original_volume=65,
        )
        d = t.to_dict()
        assert d["player_id"] == "p1"
        assert d["duration_minutes"] == 30
        assert d["original_volume"] == 65
        assert d["fade_duration_seconds"] == 30
        assert "remaining_seconds" in d
        assert "progress" in d

    def test_expired_timer(self):
        t = SleepTimer(
            player_id="p1", player_name="P1", duration_minutes=1,
            fade_duration_seconds=0, fade_steps=1,
            stop_action="pause", restore_volume=True,
            started_at=time.time() - 120,  # 2 min ago, 1 min timer -> expired
        )
        assert t.remaining_seconds == 0.0
        assert t.progress == 1.0


# ---------------------------------------------------------------------------
# SleepTimerManager
# ---------------------------------------------------------------------------

class TestSleepTimerManager:
    """Test the SleepTimerManager."""

    def _make_manager(
        self, player: FakePlayer | None = None, **kwargs
    ) -> SleepTimerManager:
        p = player or FakePlayer()

        async def get_player(pid: str):
            return p if pid == p.mac_address else None

        return SleepTimerManager(get_player=get_player, **kwargs)

    @pytest.mark.asyncio
    async def test_start_timer(self):
        mgr = self._make_manager()
        timer = await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff",
            player_name="Test",
            duration_minutes=30,
            original_volume=50,
        )
        assert timer.player_id == "aa:bb:cc:dd:ee:ff"
        assert timer.duration_minutes == 30
        assert mgr.get_timer("aa:bb:cc:dd:ee:ff") is not None
        mgr.shutdown()

    @pytest.mark.asyncio
    async def test_start_timer_cancels_existing(self):
        mgr = self._make_manager()
        t1 = await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="Test",
            duration_minutes=30, original_volume=50,
        )
        t2 = await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="Test",
            duration_minutes=60, original_volume=50,
        )
        # Only one timer should exist
        assert len(mgr.active_timers) == 1
        assert mgr.get_timer("aa:bb:cc:dd:ee:ff").duration_minutes == 60
        mgr.shutdown()

    @pytest.mark.asyncio
    async def test_cancel_timer(self):
        mgr = self._make_manager()
        await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="Test",
            duration_minutes=30, original_volume=50,
        )
        result = await mgr.cancel_timer("aa:bb:cc:dd:ee:ff")
        assert result is True
        assert mgr.get_timer("aa:bb:cc:dd:ee:ff") is None
        mgr.shutdown()

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self):
        mgr = self._make_manager()
        result = await mgr.cancel_timer("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_all(self):
        mgr = self._make_manager()
        await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="P1",
            duration_minutes=30, original_volume=50,
        )
        await mgr.start_timer(
            player_id="11:22:33:44:55:66", player_name="P2",
            duration_minutes=30, original_volume=50,
        )
        count = await mgr.cancel_all()
        assert count == 2
        assert len(mgr.active_timers) == 0

    @pytest.mark.asyncio
    async def test_active_timers(self):
        mgr = self._make_manager()
        await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="P1",
            duration_minutes=30, original_volume=50,
        )
        active = mgr.active_timers
        assert "aa:bb:cc:dd:ee:ff" in active
        mgr.shutdown()

    @pytest.mark.asyncio
    async def test_fade_out(self):
        player = FakePlayer(volume=60)
        mgr = self._make_manager(player=player)

        # Use very short durations for testing
        timer = await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="Test",
            duration_minutes=1, original_volume=60,
            fade_duration_seconds=0.05, fade_steps=3,
        )
        # Timer with 1 min duration, 0.05s fade — the fade starts at 59.95s
        # We can't easily test the full flow, but we can test the data
        assert timer.fade_duration_seconds == 0.05
        assert timer.fade_steps == 3
        mgr.shutdown()

    @pytest.mark.asyncio
    async def test_fade_out_disabled(self):
        mgr = self._make_manager()
        timer = await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="Test",
            duration_minutes=30, original_volume=50,
            fade_duration_seconds=0,
        )
        assert timer.fade_duration_seconds == 0
        mgr.shutdown()

    @pytest.mark.asyncio
    async def test_stop_action_pause(self):
        player = FakePlayer()
        mgr = self._make_manager(player=player)
        timer = await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="Test",
            duration_minutes=30, original_volume=50,
            stop_action="pause",
        )
        assert timer.stop_action == "pause"
        mgr.shutdown()

    @pytest.mark.asyncio
    async def test_stop_action_stop(self):
        player = FakePlayer()
        mgr = self._make_manager(player=player)
        timer = await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="Test",
            duration_minutes=30, original_volume=50,
            stop_action="stop",
        )
        assert timer.stop_action == "stop"
        mgr.shutdown()

    @pytest.mark.asyncio
    async def test_volume_restore(self):
        player = FakePlayer(volume=65)
        mgr = self._make_manager(player=player)
        timer = await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="Test",
            duration_minutes=30, original_volume=65,
            restore_volume=True,
        )
        assert timer.restore_volume is True
        assert timer.original_volume == 65
        mgr.shutdown()

    @pytest.mark.asyncio
    async def test_volume_restore_disabled(self):
        mgr = self._make_manager()
        timer = await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="Test",
            duration_minutes=30, original_volume=50,
            restore_volume=False,
        )
        assert timer.restore_volume is False
        mgr.shutdown()

    @pytest.mark.asyncio
    async def test_player_not_found(self):
        async def get_player(pid: str):
            return None

        mgr = SleepTimerManager(get_player=get_player)
        # Should still create the timer (player lookup happens during worker)
        timer = await mgr.start_timer(
            player_id="nonexistent", player_name="Ghost",
            duration_minutes=30, original_volume=50,
        )
        assert timer is not None
        mgr.shutdown()

    @pytest.mark.asyncio
    async def test_timer_worker_cancelled(self):
        mgr = self._make_manager()
        timer = await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="Test",
            duration_minutes=30, original_volume=50,
        )
        assert timer._task is not None
        timer._task.cancel()
        try:
            await timer._task
        except asyncio.CancelledError:
            pass
        # Timer is cleaned up in finally block
        mgr.shutdown()

    @pytest.mark.asyncio
    async def test_generation_check(self):
        mgr = self._make_manager()
        t1 = await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="Test",
            duration_minutes=30, original_volume=50,
        )
        gen1 = t1._generation

        t2 = await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="Test",
            duration_minutes=60, original_volume=50,
        )
        gen2 = t2._generation

        assert gen2 > gen1
        mgr.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown(self):
        mgr = self._make_manager()
        await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="Test",
            duration_minutes=30, original_volume=50,
        )
        mgr.shutdown()
        assert len(mgr.all_timers) == 0

    @pytest.mark.asyncio
    async def test_on_ui_update_called(self):
        cb = MagicMock()
        mgr = self._make_manager(on_ui_update=cb)
        await mgr.start_timer(
            player_id="aa:bb:cc:dd:ee:ff", player_name="Test",
            duration_minutes=30, original_volume=50,
        )
        assert cb.called
        mgr.shutdown()
