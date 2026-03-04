# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License,
# version 2.
"""
Bridge module for the raopbridge plugin.

Manages the squeeze2raop binary lifecycle: platform detection, on-demand
download from philippe44's LMS-Raop repository, and process management.

Binaries are downloaded once into the plugin's data directory (``bin/``)
and reused on subsequent starts.  No binaries are shipped with the plugin
ZIP — they are fetched at runtime from:

    https://raw.githubusercontent.com/philippe44/LMS-Raop/master/plugin/Bin/
"""

from __future__ import annotations

import json
import logging
import os
import platform
import stat
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import (
    RaopCommonOptions,
    RaopConfig,
    RaopDevice,
    dump_config,
)

logger = logging.getLogger(__name__)

PLUGIN_NAME = "raopbridge"
SETTINGS_FILE = "raopbridge.json"

# ---------------------------------------------------------------------------
# philippe44's upstream binary repository
# ---------------------------------------------------------------------------

_UPSTREAM_BIN_URL = (
    "https://raw.githubusercontent.com/philippe44/LMS-Raop/master/plugin/Bin"
)

# Windows DLL dependencies that must be downloaded alongside the .exe
_WINDOWS_DLLS = ["libcrypto-1_1.dll", "libssl-1_1.dll"]


# ---------------------------------------------------------------------------
# Platform → binary name mapping
# ---------------------------------------------------------------------------


def define_valid_bin() -> list[str]:
    """Return a list of squeeze2raop binary names valid for the current OS/arch.

    The first entry is the preferred (static) build; fallbacks follow.
    """
    system = platform.system()
    machine = platform.machine()

    if system == "Darwin":
        if machine == "arm64":
            return ["squeeze2raop-macos-arm64-static", "squeeze2raop-macos-arm64"]
        if machine == "x86_64":
            return ["squeeze2raop-macos-x86_64-static", "squeeze2raop-macos-x86_64"]
        return ["squeeze2raop-macos-static", "squeeze2raop-macos"]

    if system == "FreeBSD":
        return ["squeeze2raop-freebsd-x86_64-static", "squeeze2raop-freebsd-x86_64"]

    if system == "Windows":
        return ["squeeze2raop-static.exe", "squeeze2raop.exe"]

    if system == "Linux":
        if machine == "x86_64":
            return ["squeeze2raop-linux-x86_64-static", "squeeze2raop-linux-x86_64"]
        if machine in ("i386", "i686"):
            return ["squeeze2raop-linux-x86-static", "squeeze2raop-linux-x86"]
        if machine == "aarch64":
            return ["squeeze2raop-linux-aarch64-static", "squeeze2raop-linux-aarch64"]
        if machine.startswith("arm"):
            return [
                "squeeze2raop-linux-arm-static",
                "squeeze2raop-linux-arm",
                "squeeze2raop-linux-armv6-static",
                "squeeze2raop-linux-armv6",
                "squeeze2raop-linux-armv5-static",
                "squeeze2raop-linux-armv5",
            ]
        if machine == "powerpc":
            return ["squeeze2raop-linux-powerpc-static", "squeeze2raop-linux-powerpc"]
        if machine.startswith("sparc"):
            return ["squeeze2raop-linux-sparc64-static", "squeeze2raop-linux-sparc64"]
        if machine == "mips":
            return ["squeeze2raop-linux-mips-static", "squeeze2raop-linux-mips"]

    logger.warning(
        "Unable to determine squeeze2raop binary for platform: %s %s",
        system,
        machine,
    )
    return []


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------


def default_settings(**kwargs: Any) -> dict[str, Any]:
    valid_bin_array = define_valid_bin()
    return {
        "bin": valid_bin_array[0] if valid_bin_array else None,
        "interface": kwargs.pop("interface", "127.0.0.1"),
        "server": kwargs.pop("server", "?"),
        "active_at_startup": kwargs.pop("active_at_startup", True),
        **kwargs,
    }


def format_server_setting(**kwargs: Any) -> str:
    try:
        port = kwargs["port"]
        host = kwargs["host"]
        if host == "0.0.0.0":
            host = "127.0.0.1"
        return f"{host}:{port}"
    except KeyError:
        return "?"


def load_settings(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as config_file:
        prefs = json.load(config_file)
    return dict(prefs)


def save_settings(settings: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as configfile:
        configfile.write(json.dumps(settings, indent=2, ensure_ascii=False))
    tmp.replace(path)  # Atomic rename


# ---------------------------------------------------------------------------
# Binary download
# ---------------------------------------------------------------------------


async def _download_file(url: str, dest: Path) -> None:
    """Download *url* to *dest* using httpx (available in Resonance)."""
    import httpx

    logger.info("Downloading %s → %s", url, dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".download")
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with open(tmp, "wb") as fp:
                    async for chunk in response.aiter_bytes(chunk_size=65_536):
                        fp.write(chunk)
        tmp.replace(dest)
        logger.info("Downloaded %s (%d bytes)", dest.name, dest.stat().st_size)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


async def ensure_binary(bin_name: str, bin_dir: Path) -> Path:
    """Make sure the squeeze2raop binary exists in *bin_dir*.

    Downloads from philippe44's repository if missing.  On Unix the
    executable bit is set automatically.

    Returns the full path to the binary.
    """
    bin_path = bin_dir / bin_name
    if bin_path.is_file() and os.access(bin_path, os.X_OK if os.name != "nt" else os.F_OK):
        logger.debug("Binary already present: %s", bin_path)
        return bin_path

    # Download the binary
    url = f"{_UPSTREAM_BIN_URL}/{bin_name}"
    await _download_file(url, bin_path)

    # On Unix, make executable
    if os.name != "nt":
        current = bin_path.stat().st_mode
        bin_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        logger.debug("Set executable permission on %s", bin_path)

    # On Windows, also grab the OpenSSL DLLs if needed
    if platform.system() == "Windows":
        for dll in _WINDOWS_DLLS:
            dll_path = bin_dir / dll
            if not dll_path.is_file():
                dll_url = f"{_UPSTREAM_BIN_URL}/{dll}"
                try:
                    await _download_file(dll_url, dll_path)
                except Exception as exc:
                    logger.warning("Could not download %s: %s", dll, exc)

    return bin_path


# ---------------------------------------------------------------------------
# Config file helpers
# ---------------------------------------------------------------------------


def read_squeeze2raop_config(config_path: Path) -> RaopConfig:
    from .config import parse_config

    with open(str(config_path), "r") as fp:
        raw = fp.read()
    return parse_config(raw)


def check_valid_bin(path: Path | None) -> None:
    if path is None:
        raise RuntimeError("No binary selected for squeeze2raop: check settings")
    if not path.is_file():
        raise RuntimeError(f'Invalid value for squeeze2raop: unable to find "{path}"')
    if os.name != "nt" and not os.access(path, os.X_OK):
        raise RuntimeError(f'Invalid value for squeeze2raop: unable to execute "{path}"')


def build_path_bin(bin_name: str | None, data_dir: str) -> Path | None:
    """Resolve the full path to a binary inside the plugin's data directory."""
    if not bin_name:
        return None
    return Path(data_dir) / "bin" / bin_name


def identify_renderers(
    executable: Path,
    args: list[str] | None = None,
    config_path: Path | None = None,
    timeout: int | None = None,
) -> int:
    """Run squeeze2raop in interactive mode to discover devices and save config."""
    process_args = [str(executable)]
    if config_path:
        process_args += ["-x", str(config_path)]
    if args:
        process_args += args
    command = f"save {config_path}\nexit\n".encode("utf-8")
    try:
        result = subprocess.run(
            process_args,
            input=command,
            timeout=timeout or 30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        logger.debug("%s exited with code %d", executable, result.returncode)
        return result.returncode
    except subprocess.TimeoutExpired:
        logger.warning("%s timed out after %d seconds", executable, timeout or 30)
        return -1


def call_executable(*args: Any, **kwargs: Any) -> subprocess.Popen:  # type: ignore[type-arg]
    return subprocess.Popen(*args, **kwargs)


# ---------------------------------------------------------------------------
# RaopBridge dataclass
# ---------------------------------------------------------------------------


@dataclass
class RaopBridge:
    bin: str
    interface: str
    server: str
    active_at_startup: bool = field(init=True, default=False)
    config: str = "squeeze2raop.xml"
    auto_save: bool = True
    logging_enabled: bool = True
    debug_enabled: bool = False
    debug_category: str = "all"
    debug_level: str = "info"
    logging_file: str = "squeeze2raop.log"
    pid_file: str = "squeeze2raop.pid"
    data_dir: str = field(init=True, kw_only=True)
    raop_config: RaopConfig | None = field(
        init=False, default=None, kw_only=True
    )
    bridge_process: subprocess.Popen | None = field(  # type: ignore[type-arg]
        init=False, default=None, kw_only=True
    )

    @classmethod
    def from_settings(cls, path: Path, **kwargs: Any) -> "RaopBridge":
        logger.debug("Loading settings from %s", path)
        options = load_settings(path)
        if kwargs:
            options.update(**kwargs)
        options["data_dir"] = str(path.parent)
        instance = RaopBridge(**options)
        logger.info("Loaded plugin from %s", path)
        return instance

    @property
    def settings(self) -> dict[str, Any]:
        """Return the plugin settings (suitable for JSON serialisation)."""
        prefs = self.__dict__.copy()
        for attr in ("bridge_process", "data_dir", "raop_config"):
            prefs.pop(attr, None)
        return prefs

    @property
    def is_active(self) -> bool:
        """``True`` when the bridge subprocess is running."""
        return self.bridge_process is not None and self.bridge_process.poll() is None

    async def start(self) -> None:
        """Validate the binary and prepare for activation.

        Downloads the binary from philippe44's repository if it is not
        already present in the data directory.
        """
        logger.debug("Checking bin value: %s", self.bin)
        bin_dir = Path(self.data_dir) / "bin"

        # Download binary if missing
        if self.bin:
            try:
                await ensure_binary(self.bin, bin_dir)
            except Exception as exc:
                logger.error(
                    "Failed to download squeeze2raop binary '%s': %s",
                    self.bin,
                    exc,
                )
                raise RuntimeError(
                    f"Could not obtain squeeze2raop binary '{self.bin}'. "
                    f"Check your internet connection or download it manually "
                    f"from {_UPSTREAM_BIN_URL}/{self.bin} into {bin_dir}"
                ) from exc

        bin_path = build_path_bin(self.bin, self.data_dir)
        check_valid_bin(bin_path)

        config_path = Path(self.data_dir) / self.config
        if config_path.is_file():
            logger.debug("Bridge will use config from %s", config_path)
        else:
            logger.info(
                "No raop config file found — the bridge will create one "
                "(if autosave is enabled) in %s",
                config_path,
            )
        logger.debug(
            "RaopBridge started inactive — bridge will activate "
            "(if autostart) after server.started event"
        )

    async def activate_bridge(self) -> None:
        if self.is_active:
            logger.warning("Bridge is already active")
            return
        if self.bridge_process:
            logger.warning(
                "activate_bridge: cleaning up dead bridge (rc=%s)",
                self.bridge_process.returncode,
            )
            self.deactivate_bridge()
        bin_path = build_path_bin(self.bin, self.data_dir)
        args = self.build_bin_args()
        logger.debug("Starting %s %s", bin_path, " ".join(args))
        self.bridge_process = call_executable(
            [str(bin_path)] + args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.debug("Bridge process started (pid=%s)", self.bridge_process.pid)

    def deactivate_bridge(self) -> None:
        if self.bridge_process:
            logger.debug("Deactivating bridge")
            self.bridge_process.kill()
            self.bridge_process = None

    def build_bin_args(self, interactive: bool | None = None) -> list[str]:
        args = "" if interactive else "-Z"
        if self.auto_save:
            args += " -I"
        if self.pid_file:
            pid_path = Path(self.data_dir) / self.pid_file
            args += f" -p {pid_path}"
        if self.interface:
            args += f" -b {self.interface}"
        if self.server:
            args += f" -s {self.server}"
        if self.logging_enabled:
            logging_path = Path(self.data_dir) / self.logging_file
            args += f" -f {logging_path}"
            logger.debug("Logging to %s", logging_path)
            if self.debug_enabled:
                logger.debug(
                    "Debug: %s=%s", self.debug_category, self.debug_level
                )
                args += f" -d {self.debug_category}={self.debug_level}"
        if self.config:
            config_path = Path(self.data_dir) / self.config
            args += f" -x {config_path}"
        return args.split(" ")

    def save_config(
        self, raop_config: RaopConfig, timestamp: float | None = None
    ) -> None:
        config_path = Path(self.data_dir) / self.config
        if timestamp is not None:
            file_mod_time = os.stat(config_path).st_mtime
            if timestamp < file_mod_time:
                raise ValueError("Configuration file modified: reload")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = config_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as configfile:
            configfile.write(dump_config(raop_config))
        tmp.replace(config_path)  # Atomic rename

    def generate_config(self) -> bool:
        logger.info("Generating bridge config file %s", self.config)
        args = self.build_bin_args(interactive=True)
        bin_path = build_path_bin(self.bin, self.data_dir)
        logger.debug("Executing %s %s", bin_path, " ".join(args))
        return_value = identify_renderers(bin_path, args=args)
        return return_value == 0

    async def parse_common_options(self) -> RaopCommonOptions | None:
        """Parse the common device options from the bridge config."""
        config_path = Path(self.data_dir) / self.config
        raop_config = read_squeeze2raop_config(config_path)
        return raop_config.common

    async def parse_devices(self) -> list[RaopDevice] | None:
        """Parse the discovered devices from the bridge config."""
        config_path = Path(self.data_dir) / self.config
        raop_config = read_squeeze2raop_config(config_path)
        return raop_config.devices

    async def save_device(self, device: RaopDevice) -> None:
        """Add or update a device in the bridge configuration file."""
        config_path = Path(self.data_dir) / self.config
        raop_config = read_squeeze2raop_config(config_path)
        timestamp = time.time()
        index = -1
        for idx, item in enumerate(raop_config.devices):
            if item.udn == device.udn:
                index = idx
                break
        if index == -1:
            raop_config.devices.append(device)
        else:
            raop_config.devices[index] = device
        self.save_config(raop_config, timestamp=timestamp)

    async def remove_device(self, udn: str) -> None:
        config_path = Path(self.data_dir) / self.config
        raop_config = read_squeeze2raop_config(config_path)
        timestamp = time.time()
        index = -1
        for idx, item in enumerate(raop_config.devices):
            if item.udn == udn:
                index = idx
                break
        if index == -1:
            raise ValueError(f"Device not found: {udn}")
        del raop_config.devices[index]
        self.save_config(raop_config, timestamp=timestamp)

    async def close(self) -> None:
        self.deactivate_bridge()
        logger.debug("RaopBridge closed")
