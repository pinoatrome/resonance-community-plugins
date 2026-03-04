# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License,
# version 2.
"""
raopbridge — AirPlay bridge plugin for Resonance.

A port of philippe44's LMS-Raop plugin (https://github.com/philippe44/LMS-Raop).
Uses the pre-compiled squeeze2raop binary for the current platform, downloading
it on first use from philippe44's repository.

The plugin registers JSON-RPC commands, REST endpoints, and listens for
server lifecycle events to manage the bridge process.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request

if TYPE_CHECKING:
    from resonance.core.events import Event
    from resonance.plugin import PluginContext
    from resonance.web.handlers import CommandContext

from .bridge import (
    SETTINGS_FILE,
    RaopBridge,
    default_settings,
    format_server_setting,
    save_settings,
)
from .config import RaopDevice
from .serializers import RaopCommonOptionsSerializer, RaopDeviceSerializer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level state (set during setup, cleared during teardown)
# ---------------------------------------------------------------------------

_raop_bridge: RaopBridge | None = None


# ---------------------------------------------------------------------------
# Plugin lifecycle
# ---------------------------------------------------------------------------


async def setup(ctx: PluginContext) -> None:
    """Called by PluginManager during server startup."""
    global _raop_bridge

    server_info = ctx.server_info or {}

    # Ensure the data directory exists and has a settings file
    data_dir = ctx.ensure_data_dir()
    path = data_dir / SETTINGS_FILE
    if not os.path.isfile(path):
        logger.info("Creating default settings file in %s", path)
        save_settings(default_settings(), path)

    server = format_server_setting(**server_info)
    _raop_bridge = RaopBridge.from_settings(path, server=server)
    logger.info("RaopBridge instance loaded using settings from %s", path)

    await _raop_bridge.start()
    logger.info("RaopBridge instance started (bridge still inactive)")

    # 1) Register JSON-RPC command
    ctx.register_command("raopbridge", raopbridge_cmd)

    # 2) Subscribe to events (tracked — auto-unsubscribed on teardown)
    await ctx.subscribe("server.started", _on_server_started)

    # 3) Register REST routes
    ctx.register_route(define_api_router())

    logger.info("raopbridge plugin setup complete")


async def teardown(ctx: PluginContext) -> None:
    """Called by PluginManager during server shutdown."""
    global _raop_bridge

    if _raop_bridge:
        await _raop_bridge.close()
    _raop_bridge = None


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


async def _on_server_started(_: Event) -> None:
    """Activate the bridge once the server is fully operational."""
    logger.info(
        "raopbridge: server is fully started — ready to activate bridge "
        "(if autostart is enabled)"
    )
    if not _raop_bridge:
        logger.warning(
            "_on_server_started called before plugin initialised — skipping"
        )
        return

    if _raop_bridge.active_at_startup:
        await _raop_bridge.activate_bridge()
        logger.info("Bridge process active: %s", _raop_bridge.is_active)


# ---------------------------------------------------------------------------
# HTTP Routes (FastAPI)
# ---------------------------------------------------------------------------


def define_api_router() -> APIRouter:
    router = APIRouter(prefix="/api/raopbridge", tags=["raopbridge"])

    @router.get("/status")
    async def get_status() -> dict[str, Any]:
        plugin_status = "enabled" if _raop_bridge else "disabled"
        bridge_status = (
            "active" if _raop_bridge and _raop_bridge.is_active else "inactive"
        )
        settings = _raop_bridge.settings if _raop_bridge else {}
        return {
            "plugin": plugin_status,
            "bridge": bridge_status,
            "settings": settings,
        }

    @router.get("/settings")
    async def get_settings() -> dict[str, Any] | None:
        if _raop_bridge:
            return {"settings": _raop_bridge.settings}
        return None

    @router.patch("/settings")
    async def patch_settings(request: Request) -> dict[str, Any] | None:
        if _raop_bridge:
            body = await request.json()
            settings = list(body.items())
            return _do_save_settings(settings)
        return None

    @router.get("/settings/advanced")
    async def get_settings_advanced() -> dict[str, Any] | None:
        if _raop_bridge:
            return await _common_options()
        return None

    @router.get("/bin-options")
    async def get_bin_options() -> list[str]:
        from .bridge import define_valid_bin

        return define_valid_bin()

    @router.post("/activate")
    async def do_activate() -> dict[str, Any] | None:
        if _raop_bridge:
            return await _activate()
        return None

    @router.post("/deactivate")
    async def do_deactivate() -> dict[str, Any] | None:
        if _raop_bridge:
            return await _deactivate()
        return None

    @router.get("/device")
    async def get_devices() -> dict[str, Any] | None:
        if _raop_bridge:
            return await _devices()
        return None

    @router.put("/device/{udn}")
    async def update_device(udn: str, request: Request) -> dict[str, Any] | None:
        if _raop_bridge:
            body = await request.json()
            if body.get("udn") != udn:
                return {"error": "UDN in body does not match URL"}
            s = RaopDeviceSerializer(data=body)
            s.is_valid()
            await _raop_bridge.save_device(s.instance)
            return s.serialize()
        return None

    @router.delete("/device/{udn}")
    async def delete_device(udn: str) -> None:
        if _raop_bridge:
            await _raop_bridge.remove_device(udn)

    return router


# ---------------------------------------------------------------------------
# JSON-RPC command dispatcher
# ---------------------------------------------------------------------------


async def raopbridge_cmd(
    ctx: CommandContext, command: list[Any]
) -> dict[str, Any]:
    """Dispatch ``raopbridge <sub-command> …`` to the appropriate handler.

    Sub-commands:
    - ``activate``   — activate the bridge (launch squeeze2raop).
    - ``config``     — generate a config file (bridge must be inactive).
    - ``deactivate`` — stop the bridge process.
    - ``devices``    — list devices detected by the bridge.
    - ``restart``    — restart the bridge with stored settings.
    - ``save``       — update and persist plugin settings.
    """
    if _raop_bridge is None:
        return {"error": "raopbridge plugin not initialised"}

    sub = str(command[1]).lower() if len(command) > 1 else ""

    match sub:
        case "activate":
            return await _activate()
        case "config":
            return await _raop_config()
        case "deactivate":
            return await _deactivate()
        case "devices":
            return await _devices()
        case "restart":
            return await _restart()
        case "save":
            return await _save_settings(command[2:])
        case _:
            return {"error": f"Unknown raopbridge sub-command: {sub}"}


# ---------------------------------------------------------------------------
# Utility methods (shared by REST + JSON-RPC)
# ---------------------------------------------------------------------------


async def _activate() -> dict[str, Any]:
    assert _raop_bridge is not None
    await _raop_bridge.activate_bridge()
    await asyncio.sleep(1)  # give it a moment to start up
    return {"result": _raop_bridge.is_active}


async def _raop_config() -> dict[str, Any]:
    assert _raop_bridge is not None
    if _raop_bridge.is_active:
        return {
            "error": (
                "The bridge is active — deactivate it first to generate "
                "a configuration file"
            )
        }
    return {"result": _raop_bridge.generate_config()}


async def _deactivate() -> dict[str, Any]:
    assert _raop_bridge is not None
    _raop_bridge.deactivate_bridge()
    await asyncio.sleep(2)  # give it a moment to shut down
    return {"result": not _raop_bridge.is_active}


async def _restart() -> dict[str, Any]:
    """Restart the bridge using stored settings.

    Call ``save`` beforehand to persist any changes.
    """
    global _raop_bridge
    assert _raop_bridge is not None

    settings_path = Path(_raop_bridge.data_dir) / SETTINGS_FILE
    await _raop_bridge.close()
    _raop_bridge = RaopBridge.from_settings(settings_path)
    await _raop_bridge.start()

    return {"active": _raop_bridge.is_active}


async def _common_options() -> dict[str, Any]:
    assert _raop_bridge is not None
    common = await _raop_bridge.parse_common_options()
    return {
        "options": RaopCommonOptionsSerializer(instance=common).serialize()
    }


async def _devices() -> dict[str, Any]:
    assert _raop_bridge is not None
    devices = await _raop_bridge.parse_devices()
    return {
        "devices": [
            RaopDeviceSerializer(instance=d).serialize() for d in devices
        ]
    }


async def _save_settings(settings: list[str]) -> dict[str, Any]:
    """Parse ``key=value`` pairs from the JSON-RPC command."""
    return _do_save_settings(
        [tuple(setting.split("=", 1)) for setting in settings]
    )


def _do_save_settings(settings: list[tuple[str, ...]]) -> dict[str, Any]:
    assert _raop_bridge is not None
    errors: list[str] = []
    valid_keys = _raop_bridge.settings.keys()

    for setting in settings:
        if setting[0] in valid_keys:
            setattr(_raop_bridge, setting[0], setting[1])
        else:
            errors.append(f"Invalid setting name: '{setting[0]}'")

    if errors:
        return {"errors": ", ".join(errors)}

    store_path = Path(_raop_bridge.data_dir) / SETTINGS_FILE
    save_settings(_raop_bridge.settings, store_path)

    return {"result": True}
