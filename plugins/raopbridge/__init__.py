# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License,
# version 2.
"""
raopbridge — AirPlay bridge plugin for Resonance.

A port of philippe44's LMS-Raop plugin (https://github.com/philippe44/LMS-Raop).
Uses the pre-compiled squeeze2raop binary for the current platform, downloading
it on first use from philippe44's repository.

The plugin registers JSON-RPC commands, REST endpoints, SDUI pages, and listens
for server lifecycle events to manage the bridge process.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import asdict as dataclass_asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request

if TYPE_CHECKING:
    from resonance.core.events import Event
    from resonance.plugin import PluginContext
    from resonance.web.handlers import CommandContext

from resonance.ui import (
    Alert,
    Button,
    Card,
    Column,
    Form,
    Heading,
    KeyValue,
    KVItem,
    Markdown,
    Modal,
    NumberInput,
    Page,
    Row,
    Select,
    SelectOption,
    StatusBadge,
    Tab,
    Table,
    TableAction,
    TableColumn,
    Tabs,
    Text,
    TextInput,
    Toggle,
)

from . import bridge as _bridge_module
from .bridge import (
    SETTINGS_FILE,
    RaopBridge,
    default_settings,
    format_server_setting,
    save_settings,
)
from .config import RaopCommonOptions, RaopDevice
from .log_buffer import (
    clear_logs,
    get_log_stats,
    get_recent_logs,
    install_log_buffer,
    uninstall_log_buffer,
)
from .serializers import RaopCommonOptionsSerializer, RaopDeviceSerializer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level state (set during setup, cleared during teardown)
# ---------------------------------------------------------------------------

_raop_bridge: RaopBridge | None = None
_ctx: PluginContext | None = None


# ---------------------------------------------------------------------------
# SDUI constants
# ---------------------------------------------------------------------------

_VOLUME_MODE_LABELS = {0: "Ignored", 1: "Software", 2: "Hardware"}

_DEBUG_CATEGORIES = [
    SelectOption(value="all", label="All"),
    SelectOption(value="slimproto", label="Slimproto"),
    SelectOption(value="stream", label="Stream"),
    SelectOption(value="decode", label="Decode"),
    SelectOption(value="output", label="Output"),
    SelectOption(value="main", label="Main"),
    SelectOption(value="slimmain", label="Slimmain"),
    SelectOption(value="raop", label="RAOP"),
    SelectOption(value="util", label="Util"),
]

_DEBUG_LEVELS = [
    SelectOption(value="sdebug", label="Super Debug"),
    SelectOption(value="debug", label="Debug"),
    SelectOption(value="info", label="Info"),
    SelectOption(value="warn", label="Warning"),
    SelectOption(value="error", label="Error"),
]

_SAMPLE_RATE_OPTIONS = [
    SelectOption(value="44100", label="44100 Hz"),
    SelectOption(value="48000", label="48000 Hz"),
    SelectOption(value="88200", label="88200 Hz"),
    SelectOption(value="96000", label="96000 Hz"),
    SelectOption(value="176400", label="176400 Hz"),
    SelectOption(value="192000", label="192000 Hz"),
]


# ---------------------------------------------------------------------------
# Plugin lifecycle
# ---------------------------------------------------------------------------


async def setup(ctx: PluginContext) -> None:
    """Called by PluginManager during server startup.

    This function **never raises** (unless something truly catastrophic
    happens like an import error).  If the squeeze2raop binary cannot be
    downloaded or validated, the plugin still starts — the SDUI page will
    show the error and offer a "Retry Download" button.
    """
    global _raop_bridge, _ctx
    _ctx = ctx

    # Install the in-memory log buffer so we can show logs in the UI
    install_log_buffer()
    logger.info("raopbridge plugin starting up")

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

    # start() no longer raises — errors are stored in startup_error
    await _raop_bridge.start()
    if _raop_bridge.is_ready:
        logger.info(
            "RaopBridge ready (bridge still inactive — will activate on server.started)"
        )
    else:
        logger.warning(
            "RaopBridge started with errors — bridge cannot activate: %s",
            _raop_bridge.startup_error,
        )

    # 1) Register JSON-RPC command
    ctx.register_command("raopbridge", raopbridge_cmd)

    # 2) Subscribe to events (tracked — auto-unsubscribed on teardown)
    await ctx.subscribe("server.started", _on_server_started)

    # 3) Register REST routes
    ctx.register_route(define_api_router())

    # 4) Register SDUI handlers — always register so the page is reachable
    ctx.register_ui_handler(get_ui)
    ctx.register_action_handler(handle_action)

    logger.info("raopbridge plugin setup complete")


async def teardown(ctx: PluginContext) -> None:
    """Called by PluginManager during server shutdown."""
    global _raop_bridge, _ctx

    if _raop_bridge:
        await _raop_bridge.close()
    _raop_bridge = None
    _ctx = None

    # Remove the log buffer handler and free memory
    uninstall_log_buffer()


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
        logger.warning("_on_server_started called before plugin initialised — skipping")
        return

    if not _raop_bridge.is_ready:
        logger.warning(
            "raopbridge: skipping auto-activation — startup error: %s",
            _raop_bridge.startup_error,
        )
        return

    if _raop_bridge.active_at_startup:
        await _raop_bridge.activate_bridge()
        logger.info("Bridge process active: %s", _raop_bridge.is_active)


# ---------------------------------------------------------------------------
# SDUI — get_ui
# ---------------------------------------------------------------------------


async def get_ui(ctx: PluginContext) -> Page:
    """Build the SDUI page for the raopbridge plugin."""
    if _raop_bridge is None:
        return Page(
            title="AirPlay Bridge",
            icon="cast",
            refresh_interval=5,
            components=[
                Alert(
                    message="The raopbridge plugin is not initialised.",
                    severity="error",
                ),
                _build_log_card(),
            ],
        )

    # If the bridge has a startup error, show a focused diagnostics page
    if not _raop_bridge.is_ready:
        return Page(
            title="AirPlay Bridge",
            icon="cast",
            refresh_interval=10,
            components=[
                _build_startup_error_card(
                    _raop_bridge.startup_error or "Unknown error"
                ),
                _build_log_card(),
                _build_about_tab_card(),
            ],
        )

    is_active = _raop_bridge.is_active
    settings = _raop_bridge.settings

    status_tab = _build_status_tab(is_active, settings)
    devices_tab = await _build_devices_tab(is_active)
    settings_tab = _build_settings_tab(is_active, settings)
    advanced_tab = await _build_advanced_tab(is_active)
    log_tab = _build_log_tab()
    about_tab = _build_about_tab()

    return Page(
        title="AirPlay Bridge",
        icon="cast",
        refresh_interval=5,
        components=[
            Tabs(
                tabs=[
                    status_tab,
                    devices_tab,
                    settings_tab,
                    advanced_tab,
                    log_tab,
                    about_tab,
                ]
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Status Tab
# ---------------------------------------------------------------------------


def _build_startup_error_card(error_msg: str) -> Card:
    """Build the error card shown when the binary is not available."""
    return Card(
        title="⚠ Bridge Not Ready",
        children=[
            Alert(
                message=error_msg,
                severity="error",
                title="Startup Error",
            ),
            Text(
                "The squeeze2raop binary could not be downloaded or validated. "
                "The bridge cannot activate until this is resolved.",
                color="yellow",
                size="sm",
            ),
            Row(
                children=[
                    Button(
                        "Retry Download",
                        action="retry_download",
                        style="primary",
                        icon="download",
                    ),
                ],
                gap="3",
            ),
        ],
    )


def _build_log_card(*, collapsed: bool = False) -> Card:
    """Build a card showing recent plugin log entries."""
    log_entries = get_recent_logs(limit=50)
    log_stats = get_log_stats()

    children: list = []

    if not log_entries:
        children.append(Text("No log entries captured yet.", color="gray", size="sm"))
    else:
        # Build a markdown code block with the log entries
        log_lines: list[str] = []
        for entry in log_entries:
            level_icon = {
                "ERROR": "❌",
                "WARNING": "⚠️",
                "INFO": "ℹ️",
                "DEBUG": "🔍",
                "CRITICAL": "🔥",
            }.get(entry["level"], "•")
            ts_short = entry["timestamp"][11:19]  # HH:MM:SS
            log_lines.append(
                f"``{ts_short}`` {level_icon} **{entry['level']}** — {entry['message']}"
            )

        md_content = "\n\n".join(log_lines)

        if log_stats.get("dropped", 0) > 0:
            md_content = (
                f"*({log_stats['dropped']} older entries dropped)*\n\n" + md_content
            )

        children.append(Markdown(md_content))

    children.append(
        Row(
            children=[
                Button("Clear Logs", action="clear_logs", style="secondary"),
            ],
            gap="3",
            justify="end",
        )
    )

    return Card(
        title=f"Plugin Logs ({log_stats.get('count', 0)} entries)",
        collapsible=True,
        collapsed=collapsed,
        children=children,
    )


def _build_log_tab() -> Tab:
    """Build the Log tab for the tabbed interface."""
    return Tab(
        label="Logs",
        icon="scroll-text",
        children=[_build_log_card(collapsed=False)],
    )


def _build_about_tab_card() -> Card:
    """Build the About content as a standalone Card (used on the error page)."""
    md_content = (
        "## AirPlay Bridge\n\n"
        "This plugin uses **squeeze2raop** by "
        "[philippe44](https://github.com/philippe44) to make AirPlay devices "
        "available as Squeezebox players in Resonance.\n\n"
        "### Links\n\n"
        "- [squeeze2raop on GitHub](https://github.com/philippe44/LMS-Raop)\n"
        "- [Resonance Documentation](https://github.com/endegelaende/resonance-server)\n"
    )
    return Card(
        title="About",
        collapsible=True,
        collapsed=True,
        children=[Markdown(md_content)],
    )


def _build_status_tab(is_active: bool, settings: dict[str, Any]) -> Tab:
    """Build the Status tab content."""
    children: list = []

    # Check if bridge has a startup error (binary not available)
    has_startup_error = _raop_bridge is not None and not _raop_bridge.is_ready

    if has_startup_error:
        badge = StatusBadge("Not Ready", color="yellow")
    elif is_active:
        badge = StatusBadge("Active", color="green")
    else:
        badge = StatusBadge("Inactive", color="red")

    kv_items = [
        KVItem("Binary", str(settings.get("bin", "unknown"))),
        KVItem("Interface", str(settings.get("interface", "?"))),
        KVItem("Server", str(settings.get("server", "?"))),
        KVItem("Auto-start", "Yes" if settings.get("active_at_startup") else "No"),
    ]

    status_card = Card(
        title="Bridge Status",
        children=[
            Column(children=[badge]),
            KeyValue(items=kv_items),
        ],
    )
    children.append(status_card)

    # Show startup error with retry button
    if has_startup_error:
        children.append(
            _build_startup_error_card(_raop_bridge.startup_error or "Unknown error")
        )
    elif is_active:
        children.append(
            Row(
                children=[
                    Button(
                        "Deactivate", action="deactivate", style="danger", confirm=True
                    ),
                    Button(
                        "Restart", action="restart", style="secondary", confirm=True
                    ),
                ]
            )
        )
    else:
        children.append(
            Row(
                children=[
                    Button("Activate", action="activate", style="primary"),
                ]
            )
        )

    return Tab(label="Status", icon="activity", children=children)


# ---------------------------------------------------------------------------
# Devices Tab
# ---------------------------------------------------------------------------


async def _build_devices_tab(is_active: bool) -> Tab:
    """Build the Devices tab content."""
    children: list = []

    if not is_active:
        children.append(
            Alert(
                message="Activate the bridge to discover AirPlay devices.",
                severity="info",
            )
        )
        return Tab(label="Devices", icon="speaker", children=children)

    # Try to parse devices
    try:
        devices = await _raop_bridge.parse_devices()
    except Exception as exc:
        children.append(
            Alert(
                message=f"Failed to read devices: {exc}",
                severity="warning",
            )
        )
        return Tab(label="Devices", icon="speaker", children=children)

    if not devices:
        children.append(
            Alert(
                message="No AirPlay devices detected. Make sure devices are powered on and reachable.",
                severity="info",
            )
        )
        return Tab(label="Devices", icon="speaker", children=children)

    # Build table
    columns = [
        TableColumn(key="name", label="Name", variant="editable"),
        TableColumn(key="friendly_name", label="Friendly Name"),
        TableColumn(key="mac", label="MAC Address"),
        TableColumn(key="enabled", label="Enabled", variant="badge"),
        TableColumn(key="actions", label="Actions", variant="actions"),
    ]

    rows = []
    for device in devices:
        toggle_label = "Disable" if device.enabled else "Enable"
        toggle_enabled = not device.enabled

        row: dict[str, Any] = {
            "name": device.name,
            "friendly_name": device.friendly_name,
            "mac": device.mac,
            "udn": device.udn,
            "enabled": {
                "text": "Yes" if device.enabled else "No",
                "color": "green" if device.enabled else "red",
            },
            "actions": [
                {
                    "label": toggle_label,
                    "action": "toggle_device",
                    "params": {"udn": device.udn, "enabled": toggle_enabled},
                },
                {
                    "label": "Delete",
                    "action": "delete_device",
                    "params": {"udn": device.udn},
                    "style": "danger",
                    "confirm": True,
                },
            ],
        }
        rows.append(row)

    table = Table(
        columns=columns,
        rows=rows,
        title="Detected AirPlay Devices",
        edit_action="update_device",
        row_key="udn",
    )
    children.append(table)

    # Per-device settings modals
    for device in devices:
        modal = _build_device_modal(device)
        children.append(modal)

    return Tab(label="Devices", icon="speaker", children=children)


def _build_device_modal(device: RaopDevice) -> Modal:
    """Build a per-device settings modal with tabbed sections."""
    common = device.common

    # General tab
    general_children = [
        TextInput(
            name="name",
            label="Display Name",
            value=device.name,
            required=True,
        ),
        Select(
            name="volume_mode",
            label="Volume Mode",
            value=str(common.volume_mode),
            options=[
                SelectOption(value="0", label="Ignored"),
                SelectOption(value="1", label="Software"),
                SelectOption(value="2", label="Hardware"),
            ],
        ),
        KeyValue(
            items=[
                KVItem("Friendly Name", device.friendly_name),
                KVItem("MAC Address", device.mac),
                KVItem("Enabled", "Yes" if device.enabled else "No"),
            ]
        ),
    ]

    # Audio tab
    audio_children = [
        Select(
            name="sample_rate",
            label="Sample Rate",
            value=str(common.sample_rate),
            options=_SAMPLE_RATE_OPTIONS,
        ),
        TextInput(
            name="codecs",
            label="Codecs",
            value=",".join(common.codecs) if common.codecs else "",
        ),
        Toggle(name="resample", label="Resample", value=common.resample),
        Toggle(name="alac_encode", label="ALAC Encode", value=common.alac_encode),
        Toggle(name="encryption", label="Encryption", value=common.encryption),
    ]

    # Behaviour tab
    behaviour_children = [
        Toggle(name="send_metadata", label="Send Metadata", value=common.send_metadata),
        Toggle(
            name="send_coverart", label="Send Cover Art", value=common.send_coverart
        ),
        Toggle(name="mute_on_pause", label="Mute on Pause", value=common.mute_on_pause),
        Toggle(name="auto_play", label="Auto Play", value=common.auto_play),
        NumberInput(
            name="idle_timeout",
            label="Idle Timeout (seconds)",
            value=common.idle_timeout,
            min=0,
            max=3600,
        ),
    ]

    inner_tabs = Tabs(
        tabs=[
            Tab(label="General", children=general_children),
            Tab(label="Audio", children=audio_children),
            Tab(label="Behaviour", children=behaviour_children),
        ]
    )

    form = Form(
        action="update_device",
        submit_label="Save Device",
        children=[
            TextInput(
                name="udn",
                label="UDN",
                value=device.udn,
                disabled=True,
            ),
            inner_tabs,
        ],
    )

    return Modal(
        title=f"Settings — {device.name}",
        trigger_label=f"Edit {device.name}",
        size="lg",
        children=[form],
    )


# ---------------------------------------------------------------------------
# Settings Tab
# ---------------------------------------------------------------------------


def _build_settings_tab(is_active: bool, settings: dict[str, Any]) -> Tab:
    """Build the Settings tab content with an editable form."""
    children: list = []

    if is_active:
        children.append(
            Alert(
                message="Deactivate the bridge before changing settings.",
                severity="info",
            )
        )

    # Binary options
    bin_options = _bridge_module.define_valid_bin()
    current_bin = str(settings.get("bin", ""))
    if current_bin and current_bin not in bin_options:
        bin_options = [current_bin] + bin_options
    bin_select_options = [SelectOption(value=b, label=b) for b in bin_options]

    form_children = [
        Select(
            name="bin",
            label="Binary",
            value=current_bin,
            options=bin_select_options,
            disabled=is_active,
        ),
        TextInput(
            name="interface",
            label="Network Interface",
            value=str(settings.get("interface", "")),
            disabled=is_active,
        ),
        TextInput(
            name="server",
            label="Server Address",
            value=str(settings.get("server", "")),
            disabled=is_active,
        ),
        Toggle(
            name="active_at_startup",
            label="Auto-start",
            value=bool(settings.get("active_at_startup", False)),
        ),
        Toggle(
            name="logging_enabled",
            label="Enable Logging",
            value=bool(settings.get("logging_enabled", True)),
        ),
        Toggle(
            name="debug_enabled",
            label="Debug Mode",
            value=bool(settings.get("debug_enabled", False)),
        ),
        Toggle(
            name="auto_save",
            label="Auto-save Config",
            value=bool(settings.get("auto_save", True)),
        ),
        Select(
            name="debug_category",
            label="Debug Category",
            value=str(settings.get("debug_category", "all")),
            options=_DEBUG_CATEGORIES,
        ).when("debug_enabled", True),
        Select(
            name="debug_level",
            label="Debug Level",
            value=str(settings.get("debug_level", "info")),
            options=_DEBUG_LEVELS,
        ).when("debug_enabled", True),
    ]

    form = Form(
        action="save_settings",
        submit_label="Save Settings",
        disabled=is_active,
        children=form_children,
    )
    children.append(form)

    # Configuration info card (read-only)
    config_kv = KeyValue(
        items=[
            KVItem("Config File", str(settings.get("config", "squeeze2raop.xml"))),
            KVItem("PID File", str(settings.get("pid_file", "squeeze2raop.pid"))),
            KVItem(
                "Logging File", str(settings.get("logging_file", "squeeze2raop.log"))
            ),
        ]
    )
    config_card = Card(title="Configuration Info", children=[config_kv])
    children.append(config_card)

    return Tab(label="Settings", icon="settings", children=children)


# ---------------------------------------------------------------------------
# Advanced Tab
# ---------------------------------------------------------------------------


async def _build_advanced_tab(is_active: bool) -> Tab:
    """Build the Advanced tab — read-only view of common_options from bridge XML config."""
    children: list = []

    if not is_active:
        children.append(
            Alert(
                message="Activate the bridge to view advanced configuration options.",
                severity="info",
            )
        )
        return Tab(label="Advanced", icon="sliders-horizontal", children=children)

    try:
        common = await _raop_bridge.parse_common_options()
    except Exception as exc:
        children.append(
            Alert(
                message=f"Failed to parse common options: {exc}",
                severity="warning",
            )
        )
        return Tab(label="Advanced", icon="sliders-horizontal", children=children)

    if common is None:
        children.append(
            Alert(
                message="No configuration file available yet. Generate a config first.",
                severity="info",
            )
        )
        return Tab(label="Advanced", icon="sliders-horizontal", children=children)

    def _bool_str(val: bool) -> str:
        return "Yes" if val else "No"

    def _vol_mode_label(mode: int) -> str:
        return _VOLUME_MODE_LABELS.get(mode, str(mode))

    kv_items = [
        KVItem("Stream Buffer Size", str(common.streambuf_size)),
        KVItem("Output Size", str(common.output_size)),
        KVItem("Enabled", _bool_str(common.enabled)),
        KVItem("Codecs", ",".join(common.codecs) if common.codecs else "none"),
        KVItem("Sample Rate", str(common.sample_rate)),
        KVItem("Volume Mode", _vol_mode_label(common.volume_mode)),
        KVItem("Volume Feedback", _bool_str(common.volume_feedback)),
        KVItem("Mute on Pause", _bool_str(common.mute_on_pause)),
        KVItem("Send Metadata", _bool_str(common.send_metadata)),
        KVItem("Send Cover Art", _bool_str(common.send_coverart)),
        KVItem("Auto Play", _bool_str(common.auto_play)),
        KVItem("Idle Timeout", str(common.idle_timeout)),
        KVItem("Remove Timeout", _bool_str(common.remove_timeout)),
        KVItem("ALAC Encode", _bool_str(common.alac_encode)),
        KVItem("Encryption", _bool_str(common.encryption)),
        KVItem("Read Ahead", str(common.read_ahead)),
        KVItem("Server", str(common.server)),
    ]

    card = Card(
        title="Common Options",
        collapsible=True,
        collapsed=True,
        children=[
            Text(
                "Read-only view of the global common options from the bridge XML configuration."
            ),
            KeyValue(items=kv_items),
        ],
    )
    children.append(card)

    return Tab(label="Advanced", icon="sliders-horizontal", children=children)


# ---------------------------------------------------------------------------
# About Tab
# ---------------------------------------------------------------------------


def _build_about_tab() -> Tab:
    """Build the About tab with plugin information and links."""
    md_content = (
        "## AirPlay Bridge\n\n"
        "This plugin uses **squeeze2raop** by "
        "[philippe44](https://github.com/philippe44) to make AirPlay devices "
        "available as Squeezebox players in Resonance.\n\n"
        "### Links\n\n"
        "- [squeeze2raop on GitHub](https://github.com/philippe44/LMS-Raop)\n"
        "- [Resonance Documentation](https://github.com/resonance-server/resonance)\n"
    )

    card = Card(
        title="About",
        collapsible=True,
        children=[Markdown(md_content)],
    )

    return Tab(label="About", icon="info", children=[card])


# ---------------------------------------------------------------------------
# SDUI — handle_action
# ---------------------------------------------------------------------------


async def handle_action(action: str, params: dict[str, Any]) -> dict[str, Any]:
    """Handle SDUI action dispatches from the frontend."""

    # Actions that work even without a bridge instance
    match action:
        case "clear_logs":
            clear_logs()
            return {"message": "Logs cleared"}
        case "retry_download":
            return await _handle_retry_download()

    if _raop_bridge is None:
        return {"error": "raopbridge plugin not initialised"}

    match action:
        case "activate":
            return await _activate()
        case "deactivate":
            return await _deactivate()
        case "restart":
            return await _restart()
        case "save_settings":
            return await _handle_save_settings(params)
        case "delete_device":
            return await _handle_delete_device(params)
        case "toggle_device":
            return await _handle_toggle_device(params)
        case "update_device":
            return await _handle_update_device(params)
        case _:
            return {"error": f"Unknown action: {action}"}


async def _handle_retry_download() -> dict[str, Any]:
    """Handle retry_download action — re-attempt binary download."""
    if _raop_bridge is None:
        return {"error": "raopbridge plugin not initialised"}

    error = await _raop_bridge.retry_binary_download()
    if error is not None:
        return {"error": f"Download failed: {error}"}

    return {"message": "Binary downloaded and validated successfully!"}


async def _handle_save_settings(params: dict[str, Any]) -> dict[str, Any]:
    """Handle save_settings action from the Settings form."""
    if not params:
        return {"error": "No settings provided"}

    settings_list = list(params.items())
    result = _do_save_settings(settings_list)

    if "errors" in result:
        return {"error": result["errors"]}

    return {"success": True, "message": "Settings saved successfully"}


async def _handle_delete_device(params: dict[str, Any]) -> dict[str, Any]:
    """Handle delete_device action."""
    udn = params.get("udn")
    if not udn:
        return {"error": "Missing device UDN"}

    try:
        await _raop_bridge.remove_device(udn)
        return {"success": True, "message": f"Device '{udn}' removed"}
    except Exception as exc:
        return {"error": str(exc)}


async def _handle_toggle_device(params: dict[str, Any]) -> dict[str, Any]:
    """Handle toggle_device action — enable or disable a device."""
    udn = params.get("udn")
    if not udn:
        return {"error": "Missing device UDN"}

    enabled = params.get("enabled")
    if enabled is None:
        return {"error": "Missing 'enabled' value"}

    # Parse boolean
    if isinstance(enabled, str):
        enabled = enabled.lower() in ("true", "1", "yes")

    try:
        devices = await _raop_bridge.parse_devices()
        device = next((d for d in devices if d.udn == udn), None)
        if device is None:
            return {"error": f"Device not found: {udn}"}

        updated = RaopDevice(
            udn=device.udn,
            name=device.name,
            friendly_name=device.friendly_name,
            mac=device.mac,
            enabled=enabled,
            common=device.common,
        )
        await _raop_bridge.save_device(updated)

        status = "enabled" if enabled else "disabled"
        return {"success": True, "message": f"Device '{device.name}' {status}"}
    except Exception as exc:
        return {"error": str(exc)}


async def _handle_update_device(params: dict[str, Any]) -> dict[str, Any]:
    """Handle update_device action — rename, change volume mode, or override advanced fields."""
    udn = params.get("udn")
    if not udn:
        return {"error": "Missing device UDN"}

    try:
        devices = await _raop_bridge.parse_devices()
        device = next((d for d in devices if d.udn == udn), None)
        if device is None:
            return {"error": f"Device not found: {udn}"}

        # Start from existing values
        new_name = params.get("name", device.name)
        common_dict = dataclass_asdict(device.common)

        # Volume mode
        if "volume_mode" in params:
            try:
                common_dict["volume_mode"] = int(params["volume_mode"])
            except (ValueError, TypeError):
                return {"error": f"Invalid volume_mode: {params['volume_mode']}"}

        # Sample rate
        if "sample_rate" in params:
            try:
                common_dict["sample_rate"] = int(params["sample_rate"])
            except (ValueError, TypeError):
                return {"error": f"Invalid sample_rate: {params['sample_rate']}"}

        # Idle timeout
        if "idle_timeout" in params:
            try:
                common_dict["idle_timeout"] = int(params["idle_timeout"])
            except (ValueError, TypeError):
                return {"error": f"Invalid idle_timeout: {params['idle_timeout']}"}

        # Codecs
        if "codecs" in params:
            codecs_val = params["codecs"]
            if isinstance(codecs_val, list):
                common_dict["codecs"] = codecs_val
            elif isinstance(codecs_val, str):
                common_dict["codecs"] = [
                    c.strip() for c in codecs_val.split(",") if c.strip()
                ]
            else:
                common_dict["codecs"] = list(codecs_val)

        # Boolean overrides
        _BOOL_FIELDS = (
            "resample",
            "alac_encode",
            "encryption",
            "send_metadata",
            "send_coverart",
            "mute_on_pause",
            "auto_play",
        )
        for field in _BOOL_FIELDS:
            if field in params:
                val = params[field]
                if isinstance(val, str):
                    val = val.lower() in ("true", "1", "yes")
                common_dict[field] = bool(val)

        # Rebuild volume_mapping as list of tuples
        if "volume_mapping" in common_dict:
            vm = common_dict["volume_mapping"]
            common_dict["volume_mapping"] = [(v[0], v[1]) for v in vm]

        new_common = RaopCommonOptions(**common_dict)

        updated = RaopDevice(
            udn=device.udn,
            name=new_name,
            friendly_name=device.friendly_name,
            mac=device.mac,
            enabled=device.enabled,
            common=new_common,
        )
        await _raop_bridge.save_device(updated)

        return {"success": True, "message": f"Device '{new_name}' updated"}
    except Exception as exc:
        return {"error": str(exc)}


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
        return _bridge_module.define_valid_bin()

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


async def raopbridge_cmd(ctx: CommandContext, command: list[Any]) -> dict[str, Any]:
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
# Utility methods (shared by REST + JSON-RPC + SDUI)
# ---------------------------------------------------------------------------


async def _activate() -> dict[str, Any]:
    assert _raop_bridge is not None
    if not _raop_bridge.is_ready:
        return {
            "error": (
                "Cannot activate — binary not available. "
                "Use 'Retry Download' to resolve."
            )
        }
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
    """Restart the plugin (and the bridge if active_at_startup) using stored settings.

    Call ``save`` beforehand to persist any changes.
    """
    global _raop_bridge
    assert _raop_bridge is not None

    settings_path = Path(_raop_bridge.data_dir) / SETTINGS_FILE
    await _raop_bridge.close()
    _raop_bridge = RaopBridge.from_settings(settings_path)
    await _raop_bridge.start()

    if _raop_bridge.active_at_startup:
        await _raop_bridge.activate_bridge()
    return {"active": _raop_bridge.is_active}


async def _common_options() -> dict[str, Any]:
    assert _raop_bridge is not None
    common = await _raop_bridge.parse_common_options()
    return {"options": RaopCommonOptionsSerializer(instance=common).serialize()}


async def _devices() -> dict[str, Any]:
    assert _raop_bridge is not None
    devices = await _raop_bridge.parse_devices()
    return {"devices": [RaopDeviceSerializer(instance=d).serialize() for d in devices]}


async def _save_settings(settings: list[str]) -> dict[str, Any]:
    """Parse ``key=value`` pairs from the JSON-RPC command."""
    return _do_save_settings([tuple(setting.split("=", 1)) for setting in settings])


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
