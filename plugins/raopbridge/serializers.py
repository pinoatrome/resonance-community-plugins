# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License,
# version 2.

from __future__ import annotations

from typing import Any

from dataclasses import dataclass, asdict as dataclass_asdict

from .config import RaopDevice, RaopCommonOptions


class BaseSerializer:
    def __init__(self, data: dict[str, Any] = None, instance: dataclass = None):
        self._data = data
        self._instance = instance

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    @property
    def instance(self) -> dataclass:
        return self._instance

    def serialize(self) -> dict[str, Any]:
        return dataclass_asdict(self._instance)


class RaopDeviceSerializer(BaseSerializer):
    def __init__(self, data: dict[str, Any] = None, instance: RaopDevice = None):
        super().__init__(data, instance)

    def is_valid(self, raise_exception=True) -> bool:
        try:
            data = self._data.copy()
            common_data = data.pop('common')
            s = RaopCommonOptionsSerializer(data=common_data)
            s.is_valid()
            self._instance = RaopDevice(**data, common=s.instance)
        except TypeError as e:
            if raise_exception:
                raise ValueError('invalid data') from e
            return False


class RaopCommonOptionsSerializer(BaseSerializer):
    def __init__(self, data: dict[str, Any] = None, instance: RaopCommonOptions = None):
        super().__init__(data, instance)

    def is_valid(self, raise_exception=True) -> bool:
        try:
            data = self._data.copy()
            volume_mapping = data.pop('volume_mapping')
            volume_mapping = [(v[0], v[1]) for v in volume_mapping]
            self._instance = RaopCommonOptions(**data, volume_mapping=volume_mapping)
        except TypeError as e:
            if raise_exception:
                raise ValueError('invalid data') from e
            return False
