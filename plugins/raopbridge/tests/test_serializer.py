# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License,
# version 2.

from dataclasses import asdict as dataclass_asdict

import pytest

from raopbridge.serializers import RaopCommonOptionsSerializer, RaopDeviceSerializer


class TestRaopDeviceSerializer:
    def test_serialize(self, raop_device_factory):
        instance = raop_device_factory()
        expected = dataclass_asdict(instance)
        s = RaopDeviceSerializer(instance=instance)
        actual = s.serialize()
        assert actual == expected

    def test_is_valid(self, raop_device_factory):
        instance = raop_device_factory()
        s = RaopDeviceSerializer(data=dataclass_asdict(instance))
        s.is_valid()
        assert instance == s.instance

    def test_is_valid_raise(self):
        s = RaopDeviceSerializer(data={})
        with pytest.raises(ValueError):
            s.is_valid()

    def test_instance_raise(self, raop_device_factory):
        s = RaopDeviceSerializer(data=dataclass_asdict(raop_device_factory()))
        with pytest.raises(AssertionError):
            getattr(s, 'instance')

    def test_parse_common(self, raop_common_factory):
        expected = raop_common_factory()
        values = {'common': dataclass_asdict(expected)}
        RaopDeviceSerializer.parse_common(values)
        assert values['common'] == expected


class TestRaopCommonOptionsSerializer:
    def test_parse_volume_mapping(self):
        expected = [(0, 1), (1, 2)]
        values = {'volume_mapping': [[0, 1], [1, 2]]}
        RaopCommonOptionsSerializer.parse_volume_mapping(values)
        assert values['volume_mapping'] == expected

    def test_is_valid(self, raop_common_factory):
        expected = raop_common_factory()
        s = RaopCommonOptionsSerializer(data=dataclass_asdict(expected))
        s.is_valid()
        assert expected == s.instance


