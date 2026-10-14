"""Grid size limits: the most blocks a small grid, a large grid, a ship and a
station may have, and the grid count limits per player.

Each test sets the limit one block above the grid's current size, so the first
block fits and the second doesn't. The other pad shows the limit leaves other
kinds of grid alone.
"""

from __future__ import annotations

import pytest

import pads

ARMOR = {"Large": "LargeBlockArmorBlock", "Small": "SmallBlockArmorBlock"}


def place_armor(game, pad) -> tuple[bool, list[str]]:
    a = game.a
    return a.place(pad.entity_id, a.free_socket(pad), ARMOR[pad.size])


@pytest.mark.parametrize(
    "option, limited, other",
    [
        ("MaxBlocksLargeGrid", pads.SIZE_LARGE_STATIC, pads.SIZE_SMALL_STATIC),
        ("MaxBlocksSmallGrid", pads.SIZE_SMALL_SHIP, pads.SIZE_LARGE_SHIP),
        ("MaxBlockSizeShips", pads.SIZE_LARGE_SHIP, pads.SIZE_LARGE_STATIC),
        ("MaxBlockSizeStations", pads.SIZE_SMALL_STATIC, pads.SIZE_SMALL_SHIP),
    ],
)
def test_grid_size_limit(game, option, limited, other):
    size = game.a.server_blocks(limited.entity_id)["total"]
    game.configure(**{option: size + 1}, DenyMessage="{LIMIT}")
    assert place_armor(game, limited)[0]
    kept, chat = place_armor(game, limited)
    assert not kept
    assert "Grid size" in chat
    assert place_armor(game, other)[0]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="MaxSmallGridsPerPlayer and MaxLargeGridsPerPlayer are counted, never enforced",
)
def test_grid_count_limit_per_player(game):
    """Player A built on many large grids already, one more is too many"""
    a = game.a
    assert game.a.probe("grids", a.identity_id) != "Probe grids: small=0 large=0"
    game.configure(MaxLargeGridsPerPlayer=1)
    assert not place_armor(game, pads.SIZE_LARGE_STATIC_2)[0]
