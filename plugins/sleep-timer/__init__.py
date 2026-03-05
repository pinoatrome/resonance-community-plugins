"""
Sleep Timer — configurable sleep timer with fade-out for Resonance.

Features:
- Per-player sleep timers with configurable duration
- Smooth volume fade-out before stopping/pausing
- SDUI dashboard with live countdown
- JSON-RPC commands for programmatic control
- Jive menu integration for hardware players
- Timer history
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from resonance.core.events import Event
    from resonance.plugin import PluginContext
    from resonance.web.handlers import CommandContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_ctx: PluginContext | None = None
_timer_mgr: Any | None = None  # SleepTimerManager
_store: Any | None = None  # SleepTimerStore


# ---------------------------------------------------------------------------
# Settings helper
# ---------------------------------------------------------------------------


def _setting(key: str, default: Any = None) -> Any:
    """Read a plugin setting with fallback."""
    if _ctx is None:
        return default
    try:
        val = _ctx.get_setting(key)
        return val if val is not None else default
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def setup(ctx: PluginContext) -> None:
    """Plugin setup — called by PluginManager at startup."""
    global _ctx, _timer_mgr, _store

    from .store import SleepTimerStore
    from .timer import SleepTimerManager

    _ctx = ctx
    data_dir = ctx.ensure_data_dir()

    # Initialize store
    max_history = int(_setting("max_history", 50) or 50)
    _store = SleepTimerStore(data_dir, max_history=max_history)
    _store.load()

    # Initialize timer manager
    async def get_player(player_id: str) -> Any:
        return await ctx.player_registry.get_by_mac(player_id)

    _timer_mgr = SleepTimerManager(
        get_player=get_player,
        on_timer_expired=_on_timer_expired,
        on_ui_update=lambda: ctx.notify_ui_update(),
    )

    # ── Commands ────────────────────────────────────────────────
    ctx.register_command("sleeptimer.set", cmd_set)
    ctx.register_command("sleeptimer.status", cmd_status)
    ctx.register_command("sleeptimer.cancel", cmd_cancel)

    # ── Events ──────────────────────────────────────────────────
    await ctx.subscribe("player.disconnected", _on_player_disconnected)

    # ── Jive Menu ───────────────────────────────────────────────
    ctx.register_menu_node(
        node_id="sleepTimer",
        parent="home",
        text="Sleep Timer",
        weight=85,
        actions={
            "go": {
                "cmd": ["sleeptimer.status"],
                "params": {"menu": 1},
            },
        },
    )

    # ── SDUI ────────────────────────────────────────────────────
    ctx.register_ui_handler(get_ui)
    ctx.register_action_handler(handle_action)

    logger.info(
        "Sleep Timer plugin started — fade %ds, action=%s",
        _setting("fade_duration", 30),
        _setting("stop_action", "pause"),
    )


async def teardown(ctx: PluginContext) -> None:
    """Plugin teardown — cancel all timers, persist state."""
    global _ctx, _timer_mgr, _store

    if _timer_mgr is not None:
        _timer_mgr.shutdown()
        logger.info("Sleep Timer: all timers cancelled")

    if _store is not None:
        _store.save()

    _timer_mgr = None
    _store = None
    _ctx = None


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


async def _on_player_disconnected(event: Event) -> None:
    """Cancel timer when a player disconnects."""
    if _timer_mgr is None:
        return

    player_id = getattr(event, "player_id", None)
    if player_id and _timer_mgr.get_timer(player_id):
        await _timer_mgr.cancel_timer(player_id)
        logger.info("Sleep timer cancelled for disconnected player %s", player_id)


async def _on_timer_expired(timer: Any) -> None:
    """Called when a timer expires — record in history."""
    if _store is None:
        return

    _store.record_timer_event(
        player_id=timer.player_id,
        player_name=timer.player_name,
        duration_minutes=timer.duration_minutes,
        event_type="expired",
        fade_duration=timer.fade_duration_seconds,
    )

    if _ctx is not None:
        _ctx.notify_ui_update()


# ---------------------------------------------------------------------------
# SDUI
# ---------------------------------------------------------------------------


async def get_ui(ctx: PluginContext) -> Any:
    """Build the SDUI page."""
    from resonance.ui import Page, Tabs

    timer_tab = await _build_timer_tab(ctx)
    settings_tab = _build_settings_tab()
    about_tab = _build_about_tab()

    return Page(
        title="Sleep Timer",
        icon="moon",
        refresh_interval=5,
        components=[
            Tabs(tabs=[timer_tab, settings_tab, about_tab]),
        ],
    )


async def _build_timer_tab(ctx: PluginContext) -> Any:
    """Build the main Timer tab."""
    from resonance.ui import (
        Alert,
        Button,
        Card,
        Column,
        KeyValue,
        KVItem,
        NumberInput,
        Progress,
        Row,
        Select,
        SelectOption,
        StatusBadge,
        Tab,
        Table,
        TableColumn,
        Text,
    )

    children: list[Any] = []

    # ── Active Timers Summary ──────────────────────────────────
    active = _timer_mgr.active_timers if _timer_mgr else {}

    if active:
        badges = []
        for pid, timer in active.items():
            remaining = timer.remaining_minutes
            if timer.is_fading:
                color = "yellow"
                status_text = "Fading..."
            elif remaining < 5:
                color = "red"
                status_text = f"{remaining:.0f}m left"
            else:
                color = "green"
                status_text = f"{remaining:.0f}m left"

            badges.append(
                StatusBadge(
                    label=timer.player_name or timer.player_id,
                    status=status_text,
                    color=color,
                )
            )
        children.append(
            Card(
                title="Active Timers",
                children=[
                    Row(gap="md", children=badges),
                ],
            )
        )
    else:
        children.append(
            Alert(
                message="No active sleep timers. Select a player and duration below to start one.",
                severity="info",
            )
        )

    # ── Player Selector ────────────────────────────────────────
    players = await ctx.player_registry.get_all()
    if players:
        player_options = [
            SelectOption(value=p.mac_address, label=p.name or p.mac_address)
            for p in players
        ]

        default_player = players[0].mac_address if players else ""

        children.append(
            Card(
                title="Start Sleep Timer",
                children=[
                    Select(
                        name="player_id",
                        label="Player",
                        value=default_player,
                        options=player_options,
                    ),
                    # Duration presets as buttons
                    Row(
                        gap="sm",
                        children=[
                            Button(
                                label="15 min",
                                action="start_timer",
                                params={"duration": 15},
                                style="secondary",
                                icon="moon",
                            ),
                            Button(
                                label="30 min",
                                action="start_timer",
                                params={"duration": 30},
                                style="primary",
                                icon="moon",
                            ),
                            Button(
                                label="45 min",
                                action="start_timer",
                                params={"duration": 45},
                                style="secondary",
                                icon="moon",
                            ),
                            Button(
                                label="60 min",
                                action="start_timer",
                                params={"duration": 60},
                                style="secondary",
                                icon="moon",
                            ),
                            Button(
                                label="90 min",
                                action="start_timer",
                                params={"duration": 90},
                                style="secondary",
                                icon="moon",
                            ),
                        ],
                    ),
                    # Custom duration
                    Row(
                        gap="md",
                        children=[
                            NumberInput(
                                name="custom_duration",
                                label="Custom (minutes)",
                                value=int(_setting("default_duration", 30) or 30),
                                min=1,
                                max=480,
                            ),
                            Button(
                                label="Start Custom",
                                action="start_timer_custom",
                                style="primary",
                                icon="play",
                            ),
                        ],
                    ),
                ],
            )
        )
    else:
        children.append(Alert(message="No players connected.", severity="warning"))

    # ── Active Timer Details ───────────────────────────────────
    for pid, timer in active.items():
        total_seconds = timer.duration_minutes * 60
        remaining = timer.remaining_seconds
        elapsed_min = timer.elapsed_seconds / 60

        children.append(
            Card(
                title=f"⏱ {timer.player_name or timer.player_id}",
                children=[
                    Progress(
                        value=round(timer.progress * 100),
                        label=f"{remaining / 60:.0f}m {remaining % 60:.0f}s remaining",
                    ),
                    KeyValue(
                        items=[
                            KVItem(
                                key="Duration", value=f"{timer.duration_minutes} min"
                            ),
                            KVItem(key="Elapsed", value=f"{elapsed_min:.1f} min"),
                            KVItem(
                                key="Remaining",
                                value=f"{remaining / 60:.0f}m {remaining % 60:.0f}s",
                                color="red" if remaining < 300 else "green",
                            ),
                            KVItem(
                                key="Fade-Out", value=f"{timer.fade_duration_seconds}s"
                            ),
                            KVItem(
                                key="Status",
                                value="Fading out..." if timer.is_fading else "Running",
                                color="yellow" if timer.is_fading else "green",
                            ),
                            KVItem(
                                key="Original Volume", value=str(timer.original_volume)
                            ),
                            KVItem(key="Action", value=timer.stop_action.capitalize()),
                        ]
                    ),
                    Row(
                        gap="md",
                        children=[
                            Button(
                                label="Cancel Timer",
                                action="cancel_timer",
                                params={"player_id": pid},
                                style="danger",
                                icon="x-circle",
                                confirm=True,
                            ),
                            Button(
                                label="+15 min",
                                action="extend_timer",
                                params={"player_id": pid, "minutes": 15},
                                style="secondary",
                                icon="plus-circle",
                            ),
                        ],
                    ),
                ],
            )
        )

    # ── History (collapsible) ──────────────────────────────────
    if _store and _store.count > 0:
        history_rows = []
        for entry in reversed(_store.history[-10:]):
            ts = entry.get("timestamp", 0)
            time_str = _format_timestamp(ts) if ts else "—"
            event_type = entry.get("event_type", "?")
            icon = "✅" if event_type == "expired" else "❌"

            history_rows.append(
                {
                    "event": f"{icon} {event_type.capitalize()}",
                    "player": entry.get("player_name", entry.get("player_id", "?")),
                    "duration": f"{entry.get('duration_minutes', '?')} min",
                    "time": time_str,
                }
            )

        children.append(
            Card(
                title="Recent Timer History",
                collapsible=True,
                collapsed=True,
                children=[
                    Table(
                        columns=[
                            TableColumn(key="event", label="Event"),
                            TableColumn(key="player", label="Player"),
                            TableColumn(key="duration", label="Duration"),
                            TableColumn(key="time", label="Time"),
                        ],
                        rows=history_rows,
                        row_key="time",
                    ),
                    Button(
                        label="Clear History",
                        action="clear_history",
                        style="danger",
                        confirm=True,
                        icon="trash-2",
                    ),
                ],
            )
        )

    return Tab(label="Timer", children=children)


def _build_settings_tab() -> Any:
    """Build the Settings tab."""
    from resonance.ui import (
        Card,
        Form,
        NumberInput,
        Select,
        SelectOption,
        Tab,
        Toggle,
    )

    return Tab(
        label="Settings",
        children=[
            Card(
                title="Timer Configuration",
                children=[
                    Form(
                        action="save_settings",
                        submit_label="Save Settings",
                        children=[
                            Select(
                                name="default_duration",
                                label="Default Duration",
                                value=str(_setting("default_duration", "30")),
                                options=[
                                    SelectOption(value="15", label="15 minutes"),
                                    SelectOption(value="30", label="30 minutes"),
                                    SelectOption(value="45", label="45 minutes"),
                                    SelectOption(
                                        value="60", label="60 minutes (1 hour)"
                                    ),
                                    SelectOption(
                                        value="90", label="90 minutes (1.5 hours)"
                                    ),
                                ],
                                help_text="Default timer duration for the preset button highlight",
                            ),
                            NumberInput(
                                name="fade_duration",
                                label="Fade-Out Duration (seconds)",
                                value=int(_setting("fade_duration", 30) or 30),
                                min=0,
                                max=120,
                                help_text="Set to 0 to disable fade-out (hard stop)",
                            ),
                            NumberInput(
                                name="fade_steps",
                                label="Fade Steps",
                                value=int(_setting("fade_steps", 15) or 15),
                                min=3,
                                max=30,
                                help_text="More steps = smoother fade, but more commands to the player",
                            ),
                            Select(
                                name="stop_action",
                                label="When Timer Expires",
                                value=str(_setting("stop_action", "pause")),
                                options=[
                                    SelectOption(value="pause", label="Pause playback"),
                                    SelectOption(value="stop", label="Stop playback"),
                                ],
                                help_text="Pause keeps your place in the queue; Stop clears the buffer",
                            ),
                            Toggle(
                                name="restore_volume",
                                label="Restore Volume After Sleep",
                                value=bool(_setting("restore_volume", True)),
                                help_text="Bring volume back to the original level after stopping",
                            ),
                            NumberInput(
                                name="max_history",
                                label="Max History Entries",
                                value=int(_setting("max_history", 50) or 50),
                                min=0,
                                max=500,
                                help_text="Set to 0 to disable timer history",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def _build_about_tab() -> Any:
    """Build the About tab."""
    from resonance.ui import Card, Markdown, Tab

    return Tab(
        label="About",
        children=[
            Card(
                children=[
                    Markdown(
                        content="""## 🌙 Sleep Timer

**Version:** 1.0.0
**Author:** Resonance Community
**Category:** Tools

---

### What It Does

Sleep Timer lets you set a timer to automatically stop or pause music
playback after a configured duration. Perfect for falling asleep to music.

### Features

- ⏱ **Configurable timer** — Choose from presets (15/30/45/60/90 min) or set a custom duration
- 🔊 **Smooth fade-out** — Volume gradually decreases before stopping
- 🔁 **Volume restore** — Original volume is restored after the timer expires
- 📊 **Multi-player** — Set independent timers for different players
- 📜 **Timer history** — Track your sleep timer usage

### Usage

1. Select a player from the dropdown
2. Click a preset duration or enter a custom time
3. The timer starts immediately — you'll see a live countdown
4. Music will fade out and stop/pause when the timer expires

### JSON-RPC Commands

| Command | Description |
|---|---|
| `sleeptimer.set <player_id> <minutes>` | Start a timer |
| `sleeptimer.status [player_id]` | Query timer status |
| `sleeptimer.cancel <player_id>` | Cancel a timer |

### Jive Menu

The plugin adds a "Sleep Timer" entry to the home menu on
Squeezebox hardware (Touch, Radio, Boom, Controller).
"""
                    ),
                ]
            ),
        ],
    )


def _format_timestamp(ts: float) -> str:
    """Format a Unix timestamp to a human-readable string."""
    import time as _time

    try:
        local = _time.localtime(ts)
        now = _time.localtime()

        if local.tm_yday == now.tm_yday and local.tm_year == now.tm_year:
            return _time.strftime("Today %H:%M", local)
        elif local.tm_yday == now.tm_yday - 1 and local.tm_year == now.tm_year:
            return _time.strftime("Yesterday %H:%M", local)
        else:
            return _time.strftime("%Y-%m-%d %H:%M", local)
    except Exception:
        return str(ts)


# ---------------------------------------------------------------------------
# Action Handler
# ---------------------------------------------------------------------------


async def handle_action(
    action: str, params: dict[str, Any], ctx: PluginContext
) -> dict[str, Any] | None:
    """Handle SDUI actions from the frontend."""
    match action:
        case "start_timer":
            return await _handle_start_timer(params, ctx)
        case "start_timer_custom":
            return await _handle_start_timer_custom(params, ctx)
        case "cancel_timer":
            return await _handle_cancel_timer(params, ctx)
        case "extend_timer":
            return await _handle_extend_timer(params, ctx)
        case "cancel_all":
            return await _handle_cancel_all()
        case "save_settings":
            return _handle_save_settings(params, ctx)
        case "clear_history":
            return _handle_clear_history()
        case _:
            return {"error": f"Unknown action: {action}"}


async def _handle_start_timer(
    params: dict[str, Any], ctx: PluginContext
) -> dict[str, Any]:
    """Start a sleep timer from a preset button."""
    if _timer_mgr is None:
        return {"error": "Timer manager not initialized"}

    player_id = params.get("player_id")
    if not player_id:
        return {"error": "No player selected"}

    duration = params.get("duration")
    if not duration:
        return {"error": "No duration specified"}

    try:
        duration_minutes = int(duration)
    except (ValueError, TypeError):
        return {"error": f"Invalid duration: {duration}"}

    if duration_minutes < 1 or duration_minutes > 480:
        return {"error": "Duration must be between 1 and 480 minutes"}

    # Look up player
    player = await ctx.player_registry.get_by_mac(player_id)
    if player is None:
        return {"error": f"Player not found: {player_id}"}

    # Read settings
    fade_duration = int(_setting("fade_duration", 30) or 30)
    fade_steps = int(_setting("fade_steps", 15) or 15)
    stop_action = str(_setting("stop_action", "pause") or "pause")
    restore_volume = bool(_setting("restore_volume", True))

    # Start timer
    timer = await _timer_mgr.start_timer(
        player_id=player_id,
        player_name=player.name or player_id,
        duration_minutes=duration_minutes,
        original_volume=player.status.volume,
        fade_duration_seconds=fade_duration,
        fade_steps=fade_steps,
        stop_action=stop_action,
        restore_volume=restore_volume,
    )

    return {
        "message": f"Sleep timer set: {duration_minutes} min on {player.name or player_id}"
    }


async def _handle_start_timer_custom(
    params: dict[str, Any], ctx: PluginContext
) -> dict[str, Any]:
    """Start a sleep timer with custom duration from NumberInput."""
    custom_duration = params.get("custom_duration")
    if custom_duration is None:
        return {"error": "No custom duration specified"}

    params["duration"] = custom_duration
    return await _handle_start_timer(params, ctx)


async def _handle_cancel_timer(
    params: dict[str, Any], ctx: PluginContext
) -> dict[str, Any]:
    """Cancel a specific player's timer."""
    if _timer_mgr is None:
        return {"error": "Timer manager not initialized"}

    player_id = params.get("player_id")
    if not player_id:
        return {"error": "No player specified"}

    timer = _timer_mgr.get_timer(player_id)
    if timer is None:
        return {"error": "No active timer for this player"}

    # Record cancellation in history
    if _store:
        _store.record_timer_event(
            player_id=timer.player_id,
            player_name=timer.player_name,
            duration_minutes=timer.duration_minutes,
            event_type="cancelled",
            fade_duration=timer.fade_duration_seconds,
        )

    cancelled = await _timer_mgr.cancel_timer(player_id)
    if cancelled:
        return {"message": f"Timer cancelled for {timer.player_name}"}
    else:
        return {"error": "No timer to cancel"}


async def _handle_extend_timer(
    params: dict[str, Any], ctx: PluginContext
) -> dict[str, Any]:
    """Extend an active timer by additional minutes."""
    if _timer_mgr is None:
        return {"error": "Timer manager not initialized"}

    player_id = params.get("player_id")
    minutes = int(params.get("minutes", 15))

    timer = _timer_mgr.get_timer(player_id)
    if timer is None:
        return {"error": "No active timer to extend"}

    new_duration = int(timer.remaining_minutes + minutes)
    player = await ctx.player_registry.get_by_mac(player_id)
    if player is None:
        return {"error": "Player not found"}

    await _timer_mgr.start_timer(
        player_id=player_id,
        player_name=timer.player_name,
        duration_minutes=new_duration,
        original_volume=timer.original_volume,
        fade_duration_seconds=timer.fade_duration_seconds,
        fade_steps=timer.fade_steps,
        stop_action=timer.stop_action,
        restore_volume=timer.restore_volume,
    )

    return {
        "message": f"Timer extended by {minutes} min (now {new_duration} min total)"
    }


async def _handle_cancel_all() -> dict[str, Any]:
    """Cancel all active timers."""
    if _timer_mgr is None:
        return {"error": "Timer manager not initialized"}

    count = await _timer_mgr.cancel_all()
    return {"message": f"Cancelled {count} timer(s)"}


def _handle_save_settings(params: dict[str, Any], ctx: PluginContext) -> dict[str, Any]:
    """Save settings from the SDUI settings form."""
    saved: list[str] = []

    setting_keys = [
        ("default_duration", str),
        ("fade_duration", int),
        ("fade_steps", int),
        ("stop_action", str),
        ("restore_volume", bool),
        ("max_history", int),
    ]

    for key, cast_fn in setting_keys:
        if key in params:
            try:
                value = cast_fn(params[key])
                ctx.set_setting(key, value)
                saved.append(key)

                # Live-apply max_history
                if key == "max_history" and _store is not None:
                    _store.update_max_history(int(value))
            except (ValueError, TypeError):
                return {"error": f"Invalid value for {key}"}

    if _ctx is not None:
        _ctx.notify_ui_update()

    return (
        {"message": f"Saved: {', '.join(saved)}"}
        if saved
        else {"message": "No changes"}
    )


def _handle_clear_history() -> dict[str, Any]:
    """Clear timer history."""
    if _store is None:
        return {"error": "Store not available"}

    count = _store.count
    _store.clear()

    if _ctx is not None:
        _ctx.notify_ui_update()

    return {"message": f"Cleared {count} history entries"}


# ---------------------------------------------------------------------------
# JSON-RPC Commands
# ---------------------------------------------------------------------------


async def cmd_set(ctx: CommandContext, command: list[Any]) -> dict[str, Any]:
    """Set a sleep timer.

    Usage:
        sleeptimer.set <player_id> <minutes>
        sleeptimer.set <minutes>              (uses ctx.player_id)
    """
    if _timer_mgr is None:
        return {"error": "Sleep timer not initialized"}

    # Parse arguments
    if len(command) >= 3:
        player_id = str(command[1])
        minutes = int(command[2])
    elif len(command) >= 2:
        player_id = ctx.player_id
        minutes = int(command[1])
    else:
        return {"error": "Usage: sleeptimer.set [player_id] <minutes>"}

    if player_id == "-":
        return {"error": "No player specified"}

    if minutes < 1 or minutes > 480:
        return {"error": "Duration must be 1–480 minutes"}

    player = await ctx.player_registry.get_by_mac(player_id)
    if player is None:
        return {"error": f"Player not found: {player_id}"}

    fade_duration = int(_setting("fade_duration", 30) or 30)
    fade_steps = int(_setting("fade_steps", 15) or 15)
    stop_action = str(_setting("stop_action", "pause") or "pause")
    restore_volume = bool(_setting("restore_volume", True))

    timer = await _timer_mgr.start_timer(
        player_id=player_id,
        player_name=player.name or player_id,
        duration_minutes=minutes,
        original_volume=player.status.volume,
        fade_duration_seconds=fade_duration,
        fade_steps=fade_steps,
        stop_action=stop_action,
        restore_volume=restore_volume,
    )

    return {
        "message": f"Sleep timer set: {minutes} min",
        "player_id": player_id,
        "duration_minutes": minutes,
        "remaining_seconds": round(timer.remaining_seconds, 1),
    }


async def cmd_status(ctx: CommandContext, command: list[Any]) -> dict[str, Any]:
    """Query sleep timer status.

    Usage:
        sleeptimer.status                   -> all timers
        sleeptimer.status <player_id>       -> specific player
        sleeptimer.status menu:1            -> Jive menu format
    """
    if _timer_mgr is None:
        return {"error": "Sleep timer not initialized"}

    # Check for menu mode via tagged params
    menu_mode = False
    for arg in command[1:]:
        s = str(arg)
        if s == "menu:1" or s == "menu:true":
            menu_mode = True
            break

    # Specific player
    target_player = None
    if len(command) >= 2 and ":" not in str(command[1]):
        target_player = str(command[1])
    elif ctx.player_id != "-":
        target_player = ctx.player_id

    if menu_mode:
        return _build_jive_timer_menu(target_player)

    if target_player:
        timer = _timer_mgr.get_timer(target_player)
        if timer:
            return {"timer": timer.to_dict()}
        else:
            return {"timer": None, "message": "No active timer"}

    # All timers
    active = _timer_mgr.active_timers
    return {
        "count": len(active),
        "timers": [t.to_dict() for t in active.values()],
    }


async def cmd_cancel(ctx: CommandContext, command: list[Any]) -> dict[str, Any]:
    """Cancel a sleep timer.

    Usage:
        sleeptimer.cancel                   (uses ctx.player_id)
        sleeptimer.cancel <player_id>
    """
    if _timer_mgr is None:
        return {"error": "Sleep timer not initialized"}

    if len(command) >= 2:
        player_id = str(command[1])
    elif ctx.player_id != "-":
        player_id = ctx.player_id
    else:
        return {"error": "No player specified"}

    timer = _timer_mgr.get_timer(player_id)
    if timer and _store:
        _store.record_timer_event(
            player_id=timer.player_id,
            player_name=timer.player_name,
            duration_minutes=timer.duration_minutes,
            event_type="cancelled",
            fade_duration=timer.fade_duration_seconds,
        )

    cancelled = await _timer_mgr.cancel_timer(player_id)
    if cancelled:
        return {"message": "Timer cancelled", "player_id": player_id}
    else:
        return {"message": "No active timer", "player_id": player_id}


# ---------------------------------------------------------------------------
# Jive Menu
# ---------------------------------------------------------------------------


def _build_jive_timer_menu(player_id: str | None = None) -> dict[str, Any]:
    """Build Jive-compatible menu response for sleeptimer.status menu:1."""

    presets = [
        ("15 minutes", 15),
        ("30 minutes", 30),
        ("45 minutes", 45),
        ("1 hour", 60),
        ("90 minutes", 90),
    ]

    items: list[dict[str, Any]] = []

    # Show current timer status if active
    if player_id and _timer_mgr:
        timer = _timer_mgr.get_timer(player_id)
        if timer:
            remaining = timer.remaining_minutes
            items.append(
                {
                    "text": f"Active: {remaining:.0f}m remaining",
                    "style": "itemplay",
                    "icon-id": "/html/images/timer_icon.png",
                }
            )

    # Preset options
    for label, minutes in presets:
        items.append(
            {
                "text": f"Sleep in {label}",
                "nextWindow": "parent",
                "actions": {
                    "do": {
                        "cmd": ["sleeptimer.set", str(minutes)],
                        "player": 0,
                    },
                },
            }
        )

    # Cancel option
    items.append(
        {
            "text": "Cancel Sleep Timer",
            "nextWindow": "parent",
            "actions": {
                "do": {
                    "cmd": ["sleeptimer.cancel"],
                    "player": 0,
                },
            },
        }
    )

    return {
        "count": len(items),
        "offset": 0,
        "item_loop": items,
    }
