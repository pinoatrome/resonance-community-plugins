from __future__ import annotations

import pytest
from unittest import mock

from raopbridge import (
    raopbridge_cmd
)

import raopbridge as raopbridge_mod


class TestPluginCommandHandlers:

    @pytest.mark.asyncio
    async def test_cmd_activate(self, command_context_factory, raop_bridge_factory):

        raopbridge_mod._raop_bridge = raop_bridge_factory()
        with mock.patch.object(raopbridge_mod._raop_bridge, 'activate_bridge') as mocked:
            result = await raopbridge_cmd(command_context_factory(), ['raopbridge', 'activate'])
            assert mocked.called
        assert 'error' not in result

    @pytest.mark.asyncio
    async def test_cmd_config(self, command_context_factory, raop_bridge_factory):

        raopbridge_mod._raop_bridge = raop_bridge_factory()
        with mock.patch.object(raopbridge_mod._raop_bridge, 'generate_config') as mocked:
            result = await raopbridge_cmd(command_context_factory(), ['raopbridge', 'config'])
            assert mocked.called
        assert 'error' not in result

    @pytest.mark.asyncio
    async def test_cmd_deactivate(self, command_context_factory, raop_bridge_factory):

        raopbridge_mod._raop_bridge = raop_bridge_factory()
        with mock.patch.object(raopbridge_mod._raop_bridge, 'deactivate_bridge') as mocked:
            result = await raopbridge_cmd(command_context_factory(), ['raopbridge', 'deactivate'])
            assert mocked.called
        assert 'error' not in result

    @pytest.mark.asyncio
    async def test_cmd_restart(self, command_context_factory, raop_bridge_factory):

        raopbridge_mod._raop_bridge = raop_bridge_factory()
        new_instance = raop_bridge_factory()
        with mock.patch('raopbridge.bridge.RaopBridge.from_settings', return_value=new_instance):
            with mock.patch.object(new_instance, 'start') as mocked:
                result = await raopbridge_cmd(command_context_factory(), ['raopbridge', 'restart'])
                assert mocked.called
        assert 'error' not in result

    @pytest.mark.asyncio
    async def test_cmd_save(self, command_context_factory, raop_bridge_factory):
        raopbridge_mod._raop_bridge = raop_bridge_factory()
        with mock.patch('raopbridge.save_settings') as mocked:
            result = await raopbridge_cmd(command_context_factory(), ['raopbridge', 'save', 'bin=test'])
            assert mocked.called
        assert 'error' not in result

    @pytest.mark.asyncio
    async def test_cmd_save_update(self, command_context_factory, raop_bridge_factory):
        expected = 'test'
        raopbridge_mod._raop_bridge = raop_bridge_factory()
        with mock.patch('raopbridge.save_settings') as mocked:
            await raopbridge_cmd(command_context_factory(), ['raopbridge', 'save', f'bin={expected}'])
            assert mocked.called
        assert raopbridge_mod._raop_bridge.bin == expected
