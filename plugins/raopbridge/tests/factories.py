# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License,
# version 2.

from __future__ import annotations

import os
import re
from typing import Any

import pytest

from raopbridge.bridge import RaopBridge
from raopbridge.config import RaopCommonOptions, RaopConfig, RaopDevice, parse_config
from raopbridge.logs import RaopLogsEntry, RaopLogsReader


@pytest.fixture
def popen_factory():
    class MockPopen:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.pid = kwargs.get('pid', 12345)
            self.returncode = kwargs.get('returncode', None)

        def kill(self) -> None:
            pass

        def poll(self) -> None:
            return self.kwargs.get('poll')

    def _make(**kwargs):
        return MockPopen(**kwargs)
    return _make


@pytest.fixture
def file_pointer_factory():
    class MockFilePointer:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.dim = kwargs.get('dim', 1024)
            self.lines = kwargs.get('lines')

        def seek(self, position: int, direction=os.SEEK_END) -> None:
            if abs(position) > self.dim:
                raise IOError('MockFilePointer')

        def readlines(self) -> list[str]:
            return self.lines

    def _make(**kwargs):
        return MockFilePointer(**kwargs)
    return _make


@pytest.fixture
def logs_entry_raw_factory():
    def _make(**kwargs) -> str:
        timestamp = kwargs.pop('timestamp') if 'timestamp' in kwargs else '11:50:05.069'
        category = kwargs.pop('category') if 'category' in kwargs else 'sendHELO:107'
        pointer = kwargs.pop('pointer') if 'pointer' in kwargs else '0x102cba280'
        msg = kwargs.pop('msg') if 'msg' in kwargs else 'cap: CanHTTPS=1,Model=squeezelite,ModelName=RaopBridge'
        return f"[{timestamp}] {category} [{pointer}]: {msg}"
    return _make


@pytest.fixture
def logs_entry_factory(logs_entry_raw_factory):
    def _make(**kwargs) -> RaopLogsEntry:
        raw_line = logs_entry_raw_factory(**kwargs)
        return RaopLogsEntry.parse(raw_line)
    return _make


@pytest.fixture
def logs_reader_factory():
    def _make(**kwargs) -> RaopLogsReader:
        path = kwargs.pop('path') if 'path' in kwargs else '/dev/null'
        return RaopLogsReader(path)
    return _make


@pytest.fixture
def logs_entry_factory():
    def _make(**kwargs) -> RaopLogsEntry:
        timestamp = kwargs.pop('timestamp') if 'timestamp' in kwargs else '11:50:05.069'
        category = kwargs.pop('category') if 'category' in kwargs else 'sendHELO:107'
        pointer = kwargs.pop('pointer') if 'pointer' in kwargs else '0x102cba280'
        msg = kwargs.pop('msg') if 'msg' in kwargs else 'cap: CanHTTPS=1,Model=squeezelite,ModelName=RaopBridge'
        return RaopLogsEntry(timestamp=timestamp,
                             category=category,
                             pointer=pointer,
                             msg=msg)
    return _make


@pytest.fixture
def raop_bridge_factory(popen_factory):
    def _make(**kwargs) -> RaopBridge:
        _started = kwargs.pop('started', False)
        b_value = kwargs.pop('bin') if 'bin' in kwargs else 'squeeze2raop'
        i_value = kwargs.pop('interface') if 'interface' in kwargs else '127.0.0.1'
        s_value = kwargs.pop('server') if 'server' in kwargs else '?'
        dd_value = kwargs.pop('data_dir') if 'data_dir' in kwargs else '.'
        aat_value = kwargs.pop('active_at_startup') if 'active_at_startup' in kwargs else _started
        instance = RaopBridge(
            bin=b_value,
            interface=i_value,
            server=s_value,
            data_dir=dd_value,
            active_at_startup=aat_value,
            **kwargs
        )
        if _started and instance.active_at_startup:
            instance.bridge_process = popen_factory()
        return instance

    return _make


@pytest.fixture
def raop_common_factory():
    def _make(**kwargs) -> RaopCommonOptions:
        return RaopCommonOptions(**kwargs)
    return _make


@pytest.fixture
def raop_device_factory(raop_common_factory):
    def _make(**kwargs) -> RaopDevice:
        udn = kwargs.pop('udn') if 'udn' in kwargs else 'udn'
        name = kwargs.pop('name') if 'name' in kwargs else 'name'
        friendly_name = kwargs.pop('friendly_name') if 'friendly_name' in kwargs else 'friendly_name'
        mac = kwargs.pop('mac') if 'mac' in kwargs else 'aa:aa:d8:00:25:39'
        enabled = kwargs.pop('enabled') if 'enabled' in kwargs else True
        common = kwargs.pop('common') if 'common' in kwargs else raop_common_factory()
        instance = RaopDevice(
            udn=udn,
            name=name,
            friendly_name=friendly_name,
            mac=mac,
            enabled=enabled,
            common=common
        )
        return instance

    return _make


@pytest.fixture
def raw_config_factory():
    def _make(**kwargs) -> str:
        from .fixtures.config import full_config
        for key in kwargs:
            value = kwargs[key]
            full_config = re.sub(f'<{key}>(.*)</{key}>', f'<{key}>{value}</{key}>', full_config)
        return full_config

    return _make


@pytest.fixture
def raop_config_factory(raw_config_factory):
    def _make(**kwargs) -> RaopConfig:
        raw = raw_config_factory(**kwargs)
        return parse_config(raw)
    return _make


@pytest.fixture
def command_context_factory():
    def _make(**kwargs) -> Any:
        return None
    return _make
