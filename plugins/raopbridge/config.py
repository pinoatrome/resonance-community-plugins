# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License,
# version 2.

from __future__ import annotations

from typing import Any
from dataclasses import dataclass, field, asdict as dataclass_asdict

from xml.etree.ElementTree import Element, fromstring as root_fromstring

import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RaopCommonOptions:

    streambuf_size: int = 2097152
    output_size: int = 1764000
    enabled: bool = True
    codecs: list[str] = field(default_factory=lambda: ['aac', 'ogg', 'ops', 'ogf', 'flc', 'alc', 'wav', 'aif', 'pcm', 'mp3'])
    sample_rate: int = 96000
    resolution: str | None = None
    resample: bool = True
    resample_options: str | None = None

    # ignored (0), translated to AirPlay commands (2 = hardware) or gain shall be applied on samples (1= software)
    volume_mode: int = 2
    player_volume: int = -1
    volume_mapping: list[tuple[int, int,]] = field(default_factory=lambda: [(-30, 1,), (-15, 50,), (0, 100,)])
    volume_feedback: bool = True
    mute_on_pause: bool = True
    send_metadata: bool = True
    send_coverart: bool = True
    auto_play: bool = False
    idle_timeout: int = 30
    remove_timeout: bool = False
    alac_encode: bool = False
    encryption: bool = False
    read_ahead: int = 1000
    server: str = '?'


@dataclass(frozen=True, slots=True)
class RaopDevice:
    """A device managed by the bridge.
    Attributes are coming from raop config xml file:
    <device>
    <udn>100E0D1D1A01@Beoplay M3._raop._tcp.local</udn>
    <name>Beoplay-M3-28977299</name>
    <friendly_name>Beoplay-M3-28977299</friendly_name>
    <mac>aa:aa:d8:00:25:39</mac>
    <enabled>1</enabled>
    ... # all the common properties as optional fields
    </device>
    """

    udn: str
    """Unique identifier (e.g. '100E0D1D1A01@Beoplay M3._raop._tcp.local')."""

    name: str
    """Display name as preferred by the user (e.g. 'Beoplay M3 Bathroom')."""

    friendly_name: str
    """Device name as configured in the device settings (e.g. 'Beoplay-M3-28977299')."""

    mac: str
    """Mac Address (e.g. 'aa:aa:d8:00:25:39')."""

    enabled: bool
    """1 for True, 0 for False"""

    common: RaopCommonOptions


@dataclass(frozen=True, slots=True)
class RaopConfig:
    common: RaopCommonOptions | None = None
    interface: str = '?'
    slimproto_log: str = 'info'
    stream_log: str = 'warn'
    output_log: str = 'info'
    decode_log: str = 'warn'
    main_log: str = 'info'
    slimmain_log: str = 'info'
    raop_log: str = 'info'
    util_log: str = 'info'
    log_limit: int = -1
    migration: int = 3
    ports: tuple[int, int] = field(default_factory=lambda: (0, 0,))
    devices: list[RaopDevice] | None = None


def parse_config(raw) -> RaopConfig:
    def parse_str(el: Element, tag: str) -> str | None:
        child = el.find(tag)
        if child is not None:
            return child.text

    def parse_array_int(el: Element, tag: str, sep=':') -> [int] | None:
        child = el.find(tag)
        value = child.text if child is not None else None
        return [int(v) for v in value.split(sep)] if value else []

    def parse_array_str(el: Element, tag: str, sep=',') -> [str] | None:
        child = el.find(tag)
        value = child.text if child is not None else None
        return value.split(sep) if value else None

    def parse_int(el: Element, tag: str) -> int | None:
        child = el.find(tag)
        if child is not None:
            value = child.text
            return int(value) if value else None

    def parse_bool(el: Element, tag: str) -> bool | None:
        child = el.find(tag)
        if child is not None:
            value = child.text
            return value == '1'

    def parse_volume_mapping_value(value: str, sep: str) -> list[tuple[int, ...]] | None:
        values = [v.strip() for v in value.split(sep) if v]
        return [tuple(int(v) for v in value.split(':')) for value in values] if values else None

    def parse_volume_mapping(el: Element, tag: str, sep=',') -> list[tuple[int, int]] | None:
        """'-30:1, -15:50, 0:100' -> [(-30, 1,), (-15, 50,), (-15, 50,)]"""
        child = el.find(tag)
        return parse_volume_mapping_value(child.text, sep) if child is not None else None

    def parse_common_options_values(element: Element) -> dict[str, Any]:
        value = dict(
            streambuf_size=parse_int(element, 'streambuf_size'),
            output_size=parse_int(element, 'output_size'),
            enabled=parse_bool(element, 'enabled'),
            codecs=parse_array_str(element, 'codecs'),
            sample_rate=parse_int(element, 'sample_rate'),
            resolution=parse_str(element, 'resolution'),
            resample=parse_bool(element, 'resample'),
            resample_options=parse_str(element, 'resample_options'),
            player_volume=parse_int(element, 'player_volume'),
            volume_mapping=parse_volume_mapping(element, 'volume_mapping'),
            volume_feedback=parse_bool(element, 'volume_feedback'),
            volume_mode=parse_int(element, 'volume_mode'),
            mute_on_pause=parse_bool(element, 'mute_on_pause'),
            send_metadata=parse_bool(element, 'send_metadata'),
            send_coverart=parse_bool(element, 'send_coverart'),
            auto_play=parse_bool(element, 'auto_play'),
            idle_timeout=parse_int(element, 'idle_timeout'),
            remove_timeout=parse_bool(element, 'remove_timeout'),
            alac_encode=parse_bool(element, 'alac_encode'),
            encryption=parse_bool(element, 'encryption'),
            read_ahead=parse_int(element, 'read_ahead'),
            server=parse_str(element, 'server')
        )
        return dict([k, v] for k, v in value.items() if v is not None)

    def parse_device_values(element: Element) -> dict[str, Any]:
        return dict(
            udn=parse_str(element, 'udn'),
            name=parse_str(element, 'name'),
            friendly_name=parse_str(element, 'friendly_name'),
            mac=parse_str(element, 'mac'),
            enabled=parse_bool(element, 'enabled')
        )

    root = root_fromstring(raw)
    node = root.find('common')

    common = RaopCommonOptions(**parse_common_options_values(node))

    devices: list[RaopDevice] = []
    for device in root.iter('device'):
        device_values = parse_device_values(device)
        common_values = dataclass_asdict(common)
        overridden_values = parse_common_options_values(device)
        overridden_values.pop('enabled', None)
        if overridden_values:
            common_values.update(overridden_values)
        common_device = RaopCommonOptions(**common_values)
        device = RaopDevice(**device_values, common=common_device)
        devices.append(device)

    ports: list[int] = parse_array_int(root, 'ports')
    config = RaopConfig(
        devices=devices,
        common=common,
        interface=parse_str(root, 'interface'),
        slimproto_log=parse_str(root, 'slimproto_log'),
        stream_log=parse_str(root, 'stream_log'),
        output_log=parse_str(root, 'output_log'),
        decode_log=parse_str(root, 'decode_log'),
        main_log=parse_str(root, 'main_log'),
        slimmain_log=parse_str(root, 'slimmain_log'),
        raop_log=parse_str(root, 'raop_log'),
        util_log=parse_str(root, 'util_log'),
        log_limit=parse_int(root, 'log_limit'),
        migration=parse_int(root, 'migration'),
        ports=(ports[0], ports[1],) if ports else (0, 0, )
    )
    return config


def dump_config(config: RaopConfig) -> str:
    def format_str(value: str | None) -> str | None:
        return value or ''

    def format_array_int(values: [int], sep=':') -> str:
        return sep.join([str(v) for v in values]) if values else ''

    def format_array_str(values: [str], sep=',') -> str:
        return sep.join(values) if values else ''

    def format_int(value: int | None) -> str:
        return str(value) if value is not None else ''

    def format_bool(value: bool | None) -> str:
        return '1' if value else '0'

    def format_volume_mapping_value(value: list[tuple[int, int]], sep: str) -> str:
        values = [f'{couple[0]}:{couple[1]}' for couple in value]
        return sep.join(values)

    def format_volume_mapping(value: list, sep=', ') -> str:
        """[(-30, 1,), (-15, 50,), (-15, 50,)] -> '-30:1, -15:50, 0:100'"""
        return format_volume_mapping_value(value, sep) if value else ''

    def format_common_options_values(values: dict[str, Any]) -> [str]:
        _rows = []
        if 'streambuf_size' in values:
            _rows.append(f"<streambuf_size>{format_int(values.get('streambuf_size'))}</streambuf_size>")
        if 'output_size' in values:
            _rows.append(f"<output_size>{format_int(values.get('output_size'))}</output_size>")
        if 'enabled' in values:
            _rows.append(f"<enabled>{format_bool(values.get('enabled'))}</enabled>")
        if 'codecs' in values:
            _rows.append(f"<codecs>{format_array_str(values.get('codecs'))}</codecs>")
        if 'sample_rate' in values:
            _rows.append(f"<sample_rate>{format_int(values.get('sample_rate'))}</sample_rate>")
        if 'resolution' in values:
            _rows.append(f"<resolution>{format_str(values.get('resolution'))}</resolution>")
        if 'resample' in values:
            _rows.append(f"<resample>{format_bool(values.get('resample'))}</resample>")
        if 'resample_options' in values:
            _rows.append(f"<resample_options>{format_str(values.get('resample_options'))}</resample_options>")
        if 'player_volume' in values:
            _rows.append(f"<player_volume>{format_int(values.get('player_volume'))}</player_volume>")
        if 'volume_mapping' in values:
            _rows.append(f"<volume_mapping>{format_volume_mapping(values.get('volume_mapping'))}</volume_mapping>")
        if 'volume_feedback' in values:
            _rows.append(f"<volume_feedback>{format_bool(values.get('volume_feedback'))}</volume_feedback>")
        if 'volume_mode' in values:
            _rows.append(f"<volume_mode>{format_int(values.get('volume_mode'))}</volume_mode>")
        if 'mute_on_pause' in values:
            _rows.append(f"<mute_on_pause>{format_bool(values.get('mute_on_pause'))}</mute_on_pause>")
        if 'send_metadata' in values:
            _rows.append(f"<send_metadata>{format_bool(values.get('send_metadata'))}</send_metadata>")
        if 'send_coverart' in values:
            _rows.append(f"<send_coverart>{format_bool(values.get('send_coverart'))}</send_coverart>")
        if 'auto_play' in values:
            _rows.append(f"<auto_play>{format_bool(values.get('auto_play'))}</auto_play>")
        if 'idle_timeout' in values:
            _rows.append(f"<idle_timeout>{format_int(values.get('idle_timeout'))}</idle_timeout>")
        if 'remove_timeout' in values:
            _rows.append(f"<remove_timeout>{format_bool(values.get('remove_timeout'))}</remove_timeout>")
        if 'alac_encode' in values:
            _rows.append(f"<alac_encode>{format_bool(values.get('alac_encode'))}</alac_encode>")
        if 'encryption' in values:
            _rows.append(f"<encryption>{format_bool(values.get('encryption'))}</encryption>")
        if 'read_ahead' in values:
            _rows.append(f"<read_ahead>{format_int(values.get('read_ahead'))}</read_ahead>")
        if 'server' in values:
            _rows.append(f"<server>{format_str(values.get('server'))}</server>")
        return _rows

    def format_device_values(values: dict[str, Any]) -> [str]:
        return [
            f"<udn>{format_str(values.get('udn'))}</udn>",
            f"<name>{format_str(values.get('name'))}</name>",
            f"<friendly_name>{format_str(values.get('friendly_name'))}</friendly_name>",
            f"<mac>{format_str(values.get('mac'))}</mac>",
            f"<enabled>{format_bool(values.get('enabled'))}</enabled>"
        ]

    rows = ['<?xml version="1.0"?>', '<squeeze2raop>', '<common>']
    rows.extend(format_common_options_values(dataclass_asdict(config.common)))
    rows.extend([
        f'</common>',
        f'<interface>{format_str(config.interface)}</interface>',
        f'<slimproto_log>{format_str(config.slimproto_log)}</slimproto_log>',
        f'<stream_log>{format_str(config.stream_log)}</stream_log>',
        f'<output_log>{format_str(config.output_log)}</output_log>',
        f'<decode_log>{format_str(config.decode_log)}</decode_log>',
        f'<main_log>{format_str(config.main_log)}</main_log>',
        f'<slimmain_log>{format_str(config.slimmain_log)}</slimmain_log>',
        f'<raop_log>{format_str(config.raop_log)}</raop_log>',
        f'<util_log>{format_str(config.util_log)}</util_log>',
        f'<log_limit>{format_int(config.log_limit)}</log_limit>',
        f'<migration>{format_int(config.migration)}</migration>',
        f'<ports>{format_array_int(config.ports)}</ports>',
    ])

    for device in config.devices:
        rows.append('<device>')
        rows.extend(format_device_values(dataclass_asdict(device)))
        # store only the device values that differs from the default (in commons)
        device_common_values = dataclass_asdict(device.common)
        common_values = dataclass_asdict(config.common)
        keys = list(common_values.keys())
        for key in keys:
            if str(device_common_values[key]) == str(common_values[key]):
                del device_common_values[key]
        if device_common_values:
            logger.debug(f"Device (un)common values: {device_common_values}")
            rows.extend(format_common_options_values(device_common_values))
        rows.append('</device>')

    rows.append('</squeeze2raop>\n')
    return '\n'.join(rows)
