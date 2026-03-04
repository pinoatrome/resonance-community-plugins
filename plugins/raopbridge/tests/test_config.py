# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License,
# version 2.

from __future__ import annotations

import pytest

from raopbridge.config import (
    parse_config, dump_config
)


class TestRaopConfig:

    def test_parse_config(self, raw_config_factory):
        raw = raw_config_factory()
        actual = parse_config(raw)
        assert actual

    @pytest.mark.parametrize(('attribute', 'value'), [
        ('interface', '127.0.0.1'),
        ('main_log', 'warn'),
        ('log_limit', 1)
    ])
    def test_parse_config_attribute(self, attribute, value, raw_config_factory):
        raw = raw_config_factory(**{attribute: value})
        actual = parse_config(raw)
        assert getattr(actual, attribute) == value

    @pytest.mark.parametrize(('attribute', 'value'), [
        ('streambuf_size', '1'),
        ('resolution', '300x300')
    ])
    def test_parse_config_common_attribute(self, attribute, value, raw_config_factory):
        raw = raw_config_factory(**{attribute: value})
        actual = parse_config(raw).common
        assert str(getattr(actual, attribute)) == value

    def test_dump_config(self, raw_config_factory):
        expected = raw_config_factory()
        instance = parse_config(expected)
        assert dump_config(instance) == expected
