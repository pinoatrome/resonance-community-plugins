from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class SleepTimer:
    """Represents an active sleep timer for a single player."""

    player_id: str
    player_name: str
    duration_minutes: int
    fade_duration_seconds: int
    fade_steps: int
    stop_action: str  # "pause" or "stop"
    restore_volume: bool

    # Runtime state (nicht persistiert)
    original_volume: int = 50
    started_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    is_fading: bool = False
    _task: asyncio.Task[None] | None = field(default=None, repr=False)
    _generation: int = 0

    def __post_init__(self) -> None:
        if self.expires_at == 0.0:
            self.expires_at = self.started_at + (self.duration_minutes * 60)

    @property
    def remaining_seconds(self) -> float:
        """Remaining time in seconds (0 if expired)."""
        remaining = self.expires_at - time.time()
        return max(0.0, remaining)

    @property
    def remaining_minutes(self) -> float:
        """Remaining time in minutes."""
        return self.remaining_seconds / 60.0

    @property
    def elapsed_seconds(self) -> float:
        """Elapsed time since timer start."""
        return time.time() - self.started_at

    @property
    def progress(self) -> float:
        """Progress as fraction 0.0–1.0 (1.0 = expired)."""
        total = self.duration_minutes * 60
        if total <= 0:
            return 1.0
        return min(1.0, self.elapsed_seconds / total)

    @property
    def is_active(self) -> bool:
        """True if the timer is still running."""
        return self.remaining_seconds > 0 and self._task is not None and not self._task.done()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API responses / persistence."""
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "duration_minutes": self.duration_minutes,
            "fade_duration_seconds": self.fade_duration_seconds,
            "stop_action": self.stop_action,
            "restore_volume": self.restore_volume,
            "original_volume": self.original_volume,
            "started_at": self.started_at,
            "expires_at": self.expires_at,
            "remaining_seconds": round(self.remaining_seconds, 1),
            "remaining_minutes": round(self.remaining_minutes, 1),
            "is_fading": self.is_fading,
            "progress": round(self.progress, 3),
            "is_active": self.is_active,
        }


class SleepTimerManager:
    """Manages sleep timers for all players.

    Owns the asyncio tasks, handles fade-out, and coordinates with
    the PlayerRegistry.
    """

    def __init__(
        self,
        get_player: Callable[[str], Awaitable[Any]],
        on_timer_expired: Callable[[SleepTimer], Awaitable[None]] | None = None,
        on_ui_update: Callable[[], None] | None = None,
    ) -> None:
        self._get_player = get_player
        self._on_timer_expired = on_timer_expired
        self._on_ui_update = on_ui_update
        self._timers: dict[str, SleepTimer] = {}  # player_id -> SleepTimer
        self._generation: int = 0

    @property
    def active_timers(self) -> dict[str, SleepTimer]:
        """All currently active timers."""
        return {pid: t for pid, t in self._timers.items() if t.is_active}

    @property
    def all_timers(self) -> dict[str, SleepTimer]:
        """All timers including expired ones."""
        return dict(self._timers)

    def get_timer(self, player_id: str) -> SleepTimer | None:
        """Get the timer for a specific player."""
        timer = self._timers.get(player_id)
        if timer and timer.is_active:
            return timer
        return None

    async def start_timer(
        self,
        player_id: str,
        player_name: str,
        duration_minutes: int,
        original_volume: int,
        fade_duration_seconds: int = 30,
        fade_steps: int = 15,
        stop_action: str = "pause",
        restore_volume: bool = True,
    ) -> SleepTimer:
        """Start a new sleep timer for a player.

        Cancels any existing timer for the same player first.
        """
        # Cancel existing timer
        await self.cancel_timer(player_id)

        self._generation += 1
        timer = SleepTimer(
            player_id=player_id,
            player_name=player_name,
            duration_minutes=duration_minutes,
            fade_duration_seconds=fade_duration_seconds,
            fade_steps=fade_steps,
            stop_action=stop_action,
            restore_volume=restore_volume,
            original_volume=original_volume,
            _generation=self._generation,
        )

        generation = self._generation
        timer._task = asyncio.create_task(
            self._timer_worker(timer, generation),
            name=f"sleep-timer-{player_id}",
        )
        self._timers[player_id] = timer

        logger.info(
            "Sleep timer started: %s (%s) — %d min, fade %ds, action=%s",
            player_name, player_id, duration_minutes,
            fade_duration_seconds, stop_action,
        )

        if self._on_ui_update:
            self._on_ui_update()

        return timer

    async def cancel_timer(self, player_id: str) -> bool:
        """Cancel an active timer for a player.

        Returns True if a timer was cancelled, False if none was active.
        """
        timer = self._timers.pop(player_id, None)
        if timer is None:
            return False

        if timer._task is not None and not timer._task.done():
            timer._task.cancel()
            try:
                await timer._task
            except asyncio.CancelledError:
                pass

        # Restore volume if we were mid-fade
        if timer.is_fading and timer.restore_volume:
            await self._restore_volume(timer)

        logger.info("Sleep timer cancelled: %s (%s)", timer.player_name, player_id)

        if self._on_ui_update:
            self._on_ui_update()

        return True

    async def cancel_all(self) -> int:
        """Cancel all active timers. Returns count of cancelled timers."""
        player_ids = list(self._timers.keys())
        count = 0
        for pid in player_ids:
            if await self.cancel_timer(pid):
                count += 1
        return count

    async def _timer_worker(self, timer: SleepTimer, generation: int) -> None:
        """Main timer coroutine — waits, fades, stops."""
        try:
            fade_start = timer.duration_minutes * 60 - timer.fade_duration_seconds
            pre_fade_wait = max(0, fade_start)

            # Phase 1: Wait until fade should start
            if pre_fade_wait > 0:
                await asyncio.sleep(pre_fade_wait)

            # Check if still valid (not cancelled/replaced)
            if timer._generation != generation:
                return
            if timer.player_id not in self._timers:
                return

            # Phase 2: Fade-out
            if timer.fade_duration_seconds > 0:
                await self._do_fade_out(timer, generation)

            # Check again after fade
            if timer._generation != generation:
                return
            if timer.player_id not in self._timers:
                return

            # Phase 3: Stop/Pause
            await self._do_stop(timer)

            # Phase 4: Restore volume
            if timer.restore_volume:
                # Small delay to ensure stop is processed before volume restore
                await asyncio.sleep(0.5)
                await self._restore_volume(timer)

            # Notify expiry
            if self._on_timer_expired:
                await self._on_timer_expired(timer)

            logger.info(
                "Sleep timer expired: %s (%s) — %s after %d min",
                timer.player_name, timer.player_id,
                timer.stop_action, timer.duration_minutes,
            )

        except asyncio.CancelledError:
            logger.debug("Sleep timer task cancelled: %s", timer.player_id)
            return
        except Exception:
            logger.exception(
                "Sleep timer worker failed for %s", timer.player_id
            )
        finally:
            # Cleanup
            self._timers.pop(timer.player_id, None)
            if self._on_ui_update:
                self._on_ui_update()

    async def _do_fade_out(self, timer: SleepTimer, generation: int) -> None:
        """Gradually reduce volume to 0."""
        timer.is_fading = True
        if self._on_ui_update:
            self._on_ui_update()

        player = await self._get_player(timer.player_id)
        if player is None:
            logger.warning("Player %s not found during fade-out", timer.player_id)
            return

        current_volume = player.status.volume
        if current_volume <= 0:
            return

        steps = max(1, timer.fade_steps)
        interval = timer.fade_duration_seconds / steps
        volume_step = current_volume / steps

        for i in range(1, steps + 1):
            await asyncio.sleep(interval)

            # Re-check validity
            if timer._generation != generation:
                return
            if timer.player_id not in self._timers:
                return

            new_volume = max(0, int(current_volume - (volume_step * i)))

            player = await self._get_player(timer.player_id)
            if player is None:
                return

            try:
                await player.set_volume(new_volume)
                logger.debug(
                    "Fade step %d/%d: volume %d -> %d on %s",
                    i, steps, current_volume, new_volume, timer.player_name,
                )
            except Exception:
                logger.exception("Failed to set volume during fade-out on %s", timer.player_id)
                return

    async def _do_stop(self, timer: SleepTimer) -> None:
        """Stop or pause the player."""
        player = await self._get_player(timer.player_id)
        if player is None:
            logger.warning("Player %s not found at timer expiry", timer.player_id)
            return

        try:
            if timer.stop_action == "stop":
                await player.stop()
                logger.info("Stopped playback on %s", timer.player_name)
            else:
                await player.pause()
                logger.info("Paused playback on %s", timer.player_name)
        except Exception:
            logger.exception("Failed to %s player %s", timer.stop_action, timer.player_id)

    async def _restore_volume(self, timer: SleepTimer) -> None:
        """Restore the player's original volume."""
        player = await self._get_player(timer.player_id)
        if player is None:
            return

        try:
            await player.set_volume(timer.original_volume)
            logger.info(
                "Restored volume to %d on %s",
                timer.original_volume, timer.player_name,
            )
        except Exception:
            logger.exception("Failed to restore volume on %s", timer.player_id)

    def shutdown(self) -> None:
        """Cancel all tasks synchronously (for use in teardown).

        Does NOT restore volumes — just cancels tasks.
        """
        for timer in self._timers.values():
            if timer._task is not None and not timer._task.done():
                timer._task.cancel()
        self._timers.clear()
