"""Tests for JSON-RPC commands."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from fakes import (
    FakeCommandContext, FakeCtx, FakePlayer, FakePlayerRegistry,
)


def _reset_module_state():
    """Reset the module-level state in __init__.py."""
    import sleep_timer as mod
    mod._ctx = None
    mod._timer_mgr = None
    mod._store = None


# ---------------------------------------------------------------------------
# sleeptimer.set
# ---------------------------------------------------------------------------

class TestCmdSet:

    @pytest.mark.asyncio
    async def test_set_timer(self, fake_ctx: FakeCtx, cmd_ctx: FakeCommandContext):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        result = await mod.cmd_set(cmd_ctx, ["sleeptimer.set", "30"])
        assert "message" in result
        assert result["duration_minutes"] == 30

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_set_timer_player_id_in_params(self, fake_ctx: FakeCtx, cmd_ctx: FakeCommandContext):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        result = await mod.cmd_set(
            cmd_ctx,
            ["sleeptimer.set", "aa:bb:cc:dd:ee:ff", "45"],
        )
        assert "message" in result
        assert result["duration_minutes"] == 45

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_set_invalid_duration(self, fake_ctx: FakeCtx, cmd_ctx: FakeCommandContext):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        result = await mod.cmd_set(cmd_ctx, ["sleeptimer.set", "999"])
        assert "error" in result

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_set_no_player(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        cmd_ctx = FakeCommandContext(player_id="-", player_registry=fake_ctx.player_registry)
        result = await mod.cmd_set(cmd_ctx, ["sleeptimer.set", "30"])
        assert "error" in result

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_set_no_args(self, fake_ctx: FakeCtx, cmd_ctx: FakeCommandContext):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        result = await mod.cmd_set(cmd_ctx, ["sleeptimer.set"])
        assert "error" in result

        await mod.teardown(fake_ctx)


# ---------------------------------------------------------------------------
# sleeptimer.status
# ---------------------------------------------------------------------------

class TestCmdStatus:

    @pytest.mark.asyncio
    async def test_status_no_timers(self, fake_ctx: FakeCtx, cmd_ctx: FakeCommandContext):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        result = await mod.cmd_status(cmd_ctx, ["sleeptimer.status"])
        # Should return timer: None for specific player
        assert result.get("timer") is None or result.get("count") == 0

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_status_with_timer(self, fake_ctx: FakeCtx, cmd_ctx: FakeCommandContext):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        # Start a timer first
        await mod.cmd_set(cmd_ctx, ["sleeptimer.set", "30"])

        result = await mod.cmd_status(cmd_ctx, ["sleeptimer.status"])
        assert result.get("timer") is not None
        assert result["timer"]["duration_minutes"] == 30

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_status_all_timers(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        # Use a dash player_id to get all timers
        cmd_ctx = FakeCommandContext(player_id="-", player_registry=fake_ctx.player_registry)
        result = await mod.cmd_status(cmd_ctx, ["sleeptimer.status"])
        assert "count" in result
        assert "timers" in result

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_status_jive_menu(self, fake_ctx: FakeCtx, cmd_ctx: FakeCommandContext):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        result = await mod.cmd_status(cmd_ctx, ["sleeptimer.status", "menu:1"])
        assert "item_loop" in result
        assert result["count"] >= 6  # 5 presets + cancel

        await mod.teardown(fake_ctx)


# ---------------------------------------------------------------------------
# sleeptimer.cancel
# ---------------------------------------------------------------------------

class TestCmdCancel:

    @pytest.mark.asyncio
    async def test_cancel_active(self, fake_ctx: FakeCtx, cmd_ctx: FakeCommandContext):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        # Start a timer first
        await mod.cmd_set(cmd_ctx, ["sleeptimer.set", "30"])

        result = await mod.cmd_cancel(cmd_ctx, ["sleeptimer.cancel"])
        assert result["message"] == "Timer cancelled"

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_cancel_no_timer(self, fake_ctx: FakeCtx, cmd_ctx: FakeCommandContext):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        result = await mod.cmd_cancel(cmd_ctx, ["sleeptimer.cancel"])
        assert "No active timer" in result["message"]

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_cancel_no_player(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        cmd_ctx = FakeCommandContext(player_id="-", player_registry=fake_ctx.player_registry)
        result = await mod.cmd_cancel(cmd_ctx, ["sleeptimer.cancel"])
        assert "error" in result

        await mod.teardown(fake_ctx)
