# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License,
# version 2.

from __future__ import annotations

import os
import logging

from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RaopLogsEntry:
    """ '[11:50:05.080] sq_callback:354 [0x102d15728]: volume ignored 43' """
    timestamp: str
    category: str
    pointer: str
    msg: str

    def __str__(self) -> str:
        return f"[{self.timestamp}] {self.category} [{self.pointer}]: {self.msg}"

    @staticmethod
    def parse(line: str) -> RaopLogsEntry:
        parts = line.split(' ', 3)
        return RaopLogsEntry(
            timestamp=parts[0][1:-1],
            category=parts[1],
            pointer=parts[2][1:-2],
            msg=parts[3].strip()
        )


class RaopLogsReader:
    def __init__(self, path: Path):
        self._path = path

    def read_last_lines(self, count=50) -> list[RaopLogsEntry]:
        with open(self._path, 'r') as fp:
            lines = tail(fp, count)
        entries = []
        for line in lines:
            try:
                if line:
                    entries.append(RaopLogsEntry.parse(line))
            except Exception as ex:
                logger.warning("Unable to parse '%s': %s", line, ex)

        return entries


def tail(fp, lines=50, _buffer=4098):
    """Tail a file and get # lines from the end"""

    lines_found = []

    # block counter will be multiplied by buffer
    # to get the block size from the end
    block_counter = -1

    while len(lines_found) < lines:
        try:
            fp.seek(block_counter * _buffer, os.SEEK_END)
        except IOError:  # file is too small, too many lines requested
            fp.seek(0)
            lines_found = fp.readlines()
            break

        lines_found = fp.readlines()

        # decrement the block counter to get the next # bytes
        block_counter -= 1

    return lines_found[-lines:]
