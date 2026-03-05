"""Shared test fakes for the sleep-timer plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock


class FakePlayerStatus:
    """Minimal player status for testing."""

    def __init__(self, volume: int = 50, state: str = "playing") -> None:
        self.volume = volume
        self.state = MagicMock()
        self.state.value = state
        self.state.name = state.upper()
        self.muted = False


class FakePlayer:
    """Minimal player mock for testing."""

    def __init__(
        self, mac: str = "aa:bb:cc:dd:ee:ff", name: str = "Test Player", volume: int = 50,
    ) -> None:
        self.mac_address = mac
        self.name = name
        self.status = FakePlayerStatus(volume=volume)

        self.set_volume = AsyncMock()
        self.pause = AsyncMock()
        self.stop = AsyncMock()
        self.set_audio_enable = AsyncMock()


class FakePlayerRegistry:
    """Minimal player registry mock."""

    def __init__(self, players: list[FakePlayer] | None = None) -> None:
        self._players = {p.mac_address: p for p in (players or [])}

    async def get_by_mac(self, mac: str) -> FakePlayer | None:
        return self._players.get(mac)

    async def get_all(self) -> list[FakePlayer]:
        return list(self._players.values())

    def __len__(self) -> int:
        return len(self._players)

    def __contains__(self, mac: str) -> bool:
        return mac in self._players


class FakeCtx:
    """Minimal PluginContext mock."""

    def __init__(
        self,
        player_registry: FakePlayerRegistry | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.plugin_id = "sleep-timer"
        self.player_registry = player_registry or FakePlayerRegistry()
        self.data_dir = data_dir or Path("/tmp/test-sleep-timer")
        self.server_info = {"host": "127.0.0.1", "port": 9000}

        self._settings: dict[str, Any] = {}
        self._commands: dict[str, Any] = {}
        self._subscriptions: list[tuple[str, Any]] = []
        self._ui_handler = None
        self._action_handler = None

        self.register_command = MagicMock(side_effect=lambda n, h: self._commands.__setitem__(n, h))
        self.register_menu_node = MagicMock()
        self.register_ui_handler = MagicMock(side_effect=lambda h: setattr(self, "_ui_handler", h))
        self.register_action_handler = MagicMock(side_effect=lambda h: setattr(self, "_action_handler", h))
        self.subscribe = AsyncMock(side_effect=lambda e, h: self._subscriptions.append((e, h)))
        self.notify_ui_update = MagicMock()
        self.ensure_data_dir = MagicMock(return_value=self.data_dir)

    def get_setting(self, key: str) -> Any:
        return self._settings.get(key)

    def set_setting(self, key: str, value: Any) -> None:
        self._settings[key] = value


class FakeCommandContext:
    """Minimal CommandContext mock for JSON-RPC tests."""

    def __init__(
        self,
        player_id: str = "aa:bb:cc:dd:ee:ff",
        player_registry: FakePlayerRegistry | None = None,
    ) -> None:
        self.player_id = player_id
        self.player_registry = player_registry or FakePlayerRegistry()
