from __future__ import annotations

from pathlib import Path

import pytest

from fakes import (
    FakeCommandContext,
    FakeCtx,
    FakePlayer,
    FakePlayerRegistry,
)


@pytest.fixture
def fake_player() -> FakePlayer:
    return FakePlayer()


@pytest.fixture
def fake_registry(fake_player: FakePlayer) -> FakePlayerRegistry:
    return FakePlayerRegistry([fake_player])


@pytest.fixture
def fake_ctx(fake_registry: FakePlayerRegistry, tmp_path: Path) -> FakeCtx:
    return FakeCtx(player_registry=fake_registry, data_dir=tmp_path)


@pytest.fixture
def cmd_ctx(fake_registry: FakePlayerRegistry) -> FakeCommandContext:
    return FakeCommandContext(player_registry=fake_registry)
