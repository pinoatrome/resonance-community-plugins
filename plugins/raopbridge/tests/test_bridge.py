# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License,
# version 2.

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from raopbridge import RaopBridge, default_settings, format_server_setting


class TestBridge:

    def test_default_preferences(self):
        expected = 'test-static'
        with mock.patch('raopbridge.bridge.define_valid_bin', return_value=[expected, 'test']) as mocked:
            actual = default_settings()
            assert mocked.called
        assert actual['bin'] == expected

    def test_default_preferences_invalid(self):
        with mock.patch('raopbridge.bridge.define_valid_bin', return_value=[]) as mocked:
            actual = default_settings()
            assert mocked.called
        assert actual['bin'] is None

    def test_format_server_setting_empty(self):
        expected = '?'
        actual = format_server_setting()
        assert actual == expected

    def test_format_server_setting_generic(self):
        expected = '127.0.0.1:3456'
        actual = format_server_setting(host='0.0.0.0', port=3456)
        assert actual == expected

    def test_format_server_setting_complete(self):
        expected = '127.0.0.2:3456'
        actual = format_server_setting(host='127.0.0.2', port=3456)
        assert actual == expected

    def test_from_settings(self) -> None:
        with mock.patch('raopbridge.bridge.load_settings', return_value=default_settings()) as mocked:
            instance = RaopBridge.from_settings(Path('/tmp'))
            assert mocked.called
        assert instance.data_dir == str(Path('/tmp').parent)

    def test_build_bin_args(self, raop_bridge_factory) -> None:
        p = raop_bridge_factory()
        expected = f'-Z -I -p {p.pid_file} -b {p.interface} -s {p.server} -f {p.logging_file} -x {p.config}'.split(' ')
        actual = p.build_bin_args()
        assert actual == expected

    @pytest.mark.asyncio
    async def test_start_active(self, raop_bridge_factory, popen_factory) -> None:
        p = raop_bridge_factory(active_at_startup=True)
        with mock.patch('raopbridge.bridge.ensure_binary') as mocked_ensure:
            with mock.patch('raopbridge.bridge.check_valid_bin') as mocked_bin:
                await p.start()
                assert mocked_ensure.called
                assert mocked_bin.called
        with mock.patch('raopbridge.bridge.call_executable', return_value=popen_factory()) as mocked_exec:
            await p.activate_bridge()
            assert mocked_exec.called
        assert p.is_active

    @pytest.mark.asyncio
    async def test_start_inactive(self, raop_bridge_factory, popen_factory) -> None:
        p = raop_bridge_factory(active_at_startup=False)
        with mock.patch('raopbridge.bridge.check_valid_bin') as mocked_bin:
            with mock.patch('raopbridge.bridge.ensure_binary') as mocked_ensure:
                await p.start()
                assert mocked_ensure.called
                assert mocked_bin.called
        assert not p.is_active

    @pytest.mark.asyncio
    async def test_close(self, raop_bridge_factory) -> None:
        p = raop_bridge_factory(started=True)
        await p.close()
        assert p.is_active is False

    @pytest.mark.asyncio
    async def test_save_device(self, raop_bridge_factory, raop_config_factory) -> None:
        p = raop_bridge_factory()
        raop_config = raop_config_factory()
        device = raop_config.devices[0]
        with mock.patch.object(p, 'save_config', return_value=raop_config) as mocked_write:
            with mock.patch('raopbridge.bridge.read_squeeze2raop_config', return_value=raop_config) as mocked_read:
                await p.save_device(device)
                assert mocked_read.called
            assert mocked_write.called

    @pytest.mark.asyncio
    async def test_save_device_new(self, raop_bridge_factory, raop_config_factory, raop_device_factory) -> None:
        p = raop_bridge_factory()
        raop_config = raop_config_factory()
        device = raop_device_factory()
        with mock.patch.object(p, 'save_config', return_value=raop_config) as mocked_write:
            with mock.patch('raopbridge.bridge.read_squeeze2raop_config', return_value=raop_config) as mocked_read:
                await p.save_device(device)
                assert mocked_read.called
            assert mocked_write.called

    @pytest.mark.asyncio
    async def test_remove_device(self, raop_bridge_factory, raop_config_factory, raop_device_factory) -> None:
        p = raop_bridge_factory()
        raop_config = raop_config_factory()
        device = raop_config.devices[0]
        with mock.patch.object(p, 'save_config', return_value=raop_config) as mocked_write:
            with mock.patch('raopbridge.bridge.read_squeeze2raop_config', return_value=raop_config) as mocked_read:
                await p.remove_device(device.udn)
                assert mocked_read.called
            assert mocked_write.called

    def test_save_config_stale(self, tmp_path, raop_bridge_factory, raop_config_factory, raop_device_factory) -> None:
        import tempfile
        with tempfile.NamedTemporaryFile(dir=tmp_path, suffix='.xml') as fp:
            path = Path(fp.name)
            p = raop_bridge_factory(data_dir=path.parent.name, config=path.name)
            raop_config = raop_config_factory()
            # Use an explicitly old timestamp so the check is reliable even on
            # filesystems with low mtime resolution (e.g. Windows FAT/NTFS).
            old_timestamp = 1_000_000_000.0  # 2001-09-09
            p.save_config(raop_config)  # config file modified well after old_timestamp
            try:
                with pytest.raises(ValueError):
                    p.save_config(raop_config, timestamp=old_timestamp)
            finally:
                import os
                os.remove(Path(p.data_dir) / p.config)
                import shutil
                shutil.rmtree(p.data_dir)
