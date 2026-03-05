"""Tests for lifecycle, SDUI, and action handlers."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fakes import FakeCtx, FakePlayer, FakePlayerRegistry


def _reset_module_state():
    """Reset the module-level state in __init__.py."""
    import sleep_timer as mod
    mod._ctx = None
    mod._timer_mgr = None
    mod._store = None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    """Test setup/teardown."""

    @pytest.mark.asyncio
    async def test_setup_registers_commands(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()

        await mod.setup(fake_ctx)

        assert "sleeptimer.set" in fake_ctx._commands
        assert "sleeptimer.status" in fake_ctx._commands
        assert "sleeptimer.cancel" in fake_ctx._commands

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_setup_registers_menu(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()

        await mod.setup(fake_ctx)

        fake_ctx.register_menu_node.assert_called_once()
        call_kwargs = fake_ctx.register_menu_node.call_args
        assert call_kwargs[1]["node_id"] == "sleepTimer" or call_kwargs.kwargs.get("node_id") == "sleepTimer"

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_setup_subscribes_events(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()

        await mod.setup(fake_ctx)

        events = [e for e, _ in fake_ctx._subscriptions]
        assert "player.disconnected" in events

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_setup_initializes_store(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()

        await mod.setup(fake_ctx)

        assert mod._store is not None
        assert mod._timer_mgr is not None

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_teardown_clears_state(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()

        await mod.setup(fake_ctx)
        await mod.teardown(fake_ctx)

        assert mod._ctx is None
        assert mod._timer_mgr is None
        assert mod._store is None


# ---------------------------------------------------------------------------
# Action Handler
# ---------------------------------------------------------------------------

class TestActionHandler:
    """Test SDUI action handlers."""

    @pytest.mark.asyncio
    async def test_start_timer(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        result = await mod.handle_action(
            "start_timer",
            {"player_id": "aa:bb:cc:dd:ee:ff", "duration": 30},
            fake_ctx,
        )
        assert "message" in result
        assert "30 min" in result["message"]

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_start_timer_no_player(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        result = await mod.handle_action(
            "start_timer",
            {"duration": 30},
            fake_ctx,
        )
        assert "error" in result

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_cancel_timer(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        # Start first
        await mod.handle_action(
            "start_timer",
            {"player_id": "aa:bb:cc:dd:ee:ff", "duration": 30},
            fake_ctx,
        )

        # Cancel
        result = await mod.handle_action(
            "cancel_timer",
            {"player_id": "aa:bb:cc:dd:ee:ff"},
            fake_ctx,
        )
        assert "message" in result
        assert "cancelled" in result["message"].lower()

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_extend_timer(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        # Start first
        await mod.handle_action(
            "start_timer",
            {"player_id": "aa:bb:cc:dd:ee:ff", "duration": 30},
            fake_ctx,
        )

        # Extend
        result = await mod.handle_action(
            "extend_timer",
            {"player_id": "aa:bb:cc:dd:ee:ff", "minutes": 15},
            fake_ctx,
        )
        assert "message" in result
        assert "extended" in result["message"].lower()

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_save_settings(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        result = await mod.handle_action(
            "save_settings",
            {"fade_duration": 45, "stop_action": "stop"},
            fake_ctx,
        )
        assert "message" in result
        assert fake_ctx.get_setting("fade_duration") == 45
        assert fake_ctx.get_setting("stop_action") == "stop"

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_clear_history(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        # Add some history
        mod._store.record_timer_event(
            player_id="p1", player_name="P1",
            duration_minutes=30, event_type="expired",
        )

        result = await mod.handle_action("clear_history", {}, fake_ctx)
        assert "message" in result
        assert mod._store.count == 0

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_unknown_action(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        result = await mod.handle_action("nonexistent", {}, fake_ctx)
        assert "error" in result

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_start_timer_custom(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        result = await mod.handle_action(
            "start_timer_custom",
            {"player_id": "aa:bb:cc:dd:ee:ff", "custom_duration": 42},
            fake_ctx,
        )
        assert "message" in result
        assert "42 min" in result["message"]

        await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_cancel_all(self, fake_ctx: FakeCtx):
        import sleep_timer as mod
        _reset_module_state()
        await mod.setup(fake_ctx)

        # Start a timer
        await mod.handle_action(
            "start_timer",
            {"player_id": "aa:bb:cc:dd:ee:ff", "duration": 30},
            fake_ctx,
        )

        result = await mod.handle_action("cancel_all", {}, fake_ctx)
        assert "message" in result

        await mod.teardown(fake_ctx)


# ---------------------------------------------------------------------------
# SDUI get_ui
# ---------------------------------------------------------------------------

class TestGetUI:
    """Test SDUI page building."""

    @pytest.mark.asyncio
    async def test_get_ui_returns_page(self, fake_ctx: FakeCtx):
        # Mock resonance.ui module
        mock_ui = _create_mock_ui()
        with patch.dict(sys.modules, {"resonance.ui": mock_ui}):
            import sleep_timer as mod
            _reset_module_state()
            await mod.setup(fake_ctx)

            page = await mod.get_ui(fake_ctx)
            assert page is not None

            await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_timer_tab_no_timers(self, fake_ctx: FakeCtx):
        mock_ui = _create_mock_ui()
        with patch.dict(sys.modules, {"resonance.ui": mock_ui}):
            import sleep_timer as mod
            _reset_module_state()
            await mod.setup(fake_ctx)

            page = await mod.get_ui(fake_ctx)
            # Should have been called — just check it doesn't crash
            assert page is not None

            await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_timer_tab_with_active(self, fake_ctx: FakeCtx):
        mock_ui = _create_mock_ui()
        with patch.dict(sys.modules, {"resonance.ui": mock_ui}):
            import sleep_timer as mod
            _reset_module_state()
            await mod.setup(fake_ctx)

            # Start a timer
            await mod.handle_action(
                "start_timer",
                {"player_id": "aa:bb:cc:dd:ee:ff", "duration": 30},
                fake_ctx,
            )

            page = await mod.get_ui(fake_ctx)
            assert page is not None

            await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_settings_tab(self, fake_ctx: FakeCtx):
        mock_ui = _create_mock_ui()
        with patch.dict(sys.modules, {"resonance.ui": mock_ui}):
            import sleep_timer as mod
            _reset_module_state()
            await mod.setup(fake_ctx)

            # _build_settings_tab is called internally by get_ui
            page = await mod.get_ui(fake_ctx)
            assert page is not None

            await mod.teardown(fake_ctx)

    @pytest.mark.asyncio
    async def test_about_tab(self, fake_ctx: FakeCtx):
        mock_ui = _create_mock_ui()
        with patch.dict(sys.modules, {"resonance.ui": mock_ui}):
            import sleep_timer as mod
            _reset_module_state()
            await mod.setup(fake_ctx)

            page = await mod.get_ui(fake_ctx)
            assert page is not None

            await mod.teardown(fake_ctx)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_mock_ui():
    """Create a mock resonance.ui module with all needed widgets."""
    mock_ui = MagicMock()

    # All widget classes just need to be callable and return something
    widget_names = [
        "Alert", "Button", "Card", "Column", "Form", "KeyValue", "KVItem",
        "Markdown", "NumberInput", "Page", "Progress", "Row", "Select",
        "SelectOption", "StatusBadge", "Tab", "Table", "TableColumn",
        "Tabs", "Text", "Toggle",
    ]
    for name in widget_names:
        setattr(mock_ui, name, MagicMock(name=name))

    return mock_ui
