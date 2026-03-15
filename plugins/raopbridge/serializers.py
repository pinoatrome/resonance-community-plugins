# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License,
# version 2.

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

from dataclasses import dataclass, asdict as dataclass_asdict

from .config import RaopDevice, RaopCommonOptions


class BaseSerializer(ABC):
    def __init__(self, data: dict[str, Any] = None, instance: dataclass = None):
        self._data = data
        self._instance = instance

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    @property
    def instance(self) -> Any:
        assert self._instance, (
            'Cannot call `.instance` as no `instance=` keyword argument was '
            'passed when instantiating the serializer instance nor is_valid has been '
            'invoked to validate the initial data'
        )
        return self._instance

    def is_valid(self, raise_exception=True) -> bool:
        try:
            self._instance = self.parse(self._data.copy())
            return True
        except (KeyError, TypeError) as e:
            if raise_exception:
                raise ValueError('invalid data') from e
            return False

    @abstractmethod
    def parse(self, values: dict[str, Any]) -> Any:
        pass

    @abstractmethod
    def serialize(self) -> dict[str, Any]:
        pass


class DataclassSerializer(BaseSerializer, ABC):

    @property
    def instance(self) -> dataclass:
        return super().instance

    def serialize(self) -> dict[str, Any]:
        return dataclass_asdict(self._instance)


class RaopDeviceSerializer(DataclassSerializer):

    def __init__(self, data: dict[str, Any] = None, instance: RaopDevice = None):
        super().__init__(data, instance)

    @staticmethod
    def parse_common(values) -> None:
        common_data = values.pop('common')
        s = RaopCommonOptionsSerializer(data=common_data)
        s.is_valid()
        values['common'] = s.instance

    def parse(self, values) -> RaopDevice:
        self.parse_common(values)
        return RaopDevice(**values)


class RaopCommonOptionsSerializer(DataclassSerializer):

    def __init__(self, data: dict[str, Any] = None, instance: RaopCommonOptions = None):
        super().__init__(data, instance)

    @staticmethod
    def parse_volume_mapping(values) -> None:
        volume_mapping = values.pop('volume_mapping')
        values['volume_mapping'] = [(v[0], v[1]) for v in volume_mapping]

    def parse(self, values) -> RaopCommonOptions:
        self.parse_volume_mapping(values)
        return RaopCommonOptions(**values)
