"""Grids changing shape: merging, splitting, pasting and welding a projection.

The plugin hears only of blocks built one at a time (the game's BlockBuilt
event: the cube builder and projection welding). Merges and pastes bring
blocks in without it, see the strict xfails.
"""

from __future__ import annotations

import time

import pytest

import pads
import world
from session import DECOYS
from rig import Rule

NOT_ENFORCED = (
    "Block Limits checks only blocks built one at a time (BlockBuilt); "
    "merges and pastes are not checked"
)


def wait(condition, timeout: float, message):
    """Waits for condition to come true and returns its value. message may be
    a function, called on failure."""
    deadline = time.monotonic() + timeout
    while not (result := condition()):
        assert time.monotonic() < deadline, message() if callable(message) else message
        time.sleep(1)
    return result


def merged(game) -> bool:
    return game.a.server_blocks(pads.MERGE_SHIP_ID) == {}


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=NOT_ENFORCED)
def test_merge_over_a_grid_limit_is_refused(game):
    """Two decoys each, three allowed per grid: the merged grid would have four"""
    wait(lambda: merged(game), 120, "The ship did not merge into the station")
    blocks = game.a.server_blocks(pads.MERGE_STATION.entity_id)
    assert blocks.get("LargeDecoy", 0) <= DECOYS.limit


def test_merged_grids_count_as_one(game):
    game.configure([DECOYS])
    a = game.a
    wait(lambda: merged(game), 120, "The ship did not merge into the station")
    assert a.server_blocks(pads.MERGE_STATION.entity_id)["LargeDecoy"] == 4
    cell = a.free_socket(pads.MERGE_STATION)
    assert not a.place(pads.MERGE_STATION.entity_id, cell, "LargeDecoy")[0]


def test_split_grids_count_on_their_own(game):
    """Four decoys on a grid limited to three; once split in two, each part has
    room for one more"""
    game.configure([DECOYS])
    a = game.a
    split = pads.SPLIT.entity_id
    free, other_free = pads.SPLIT_FREE
    assert not a.place(split, free, "LargeDecoy")[0]

    a.remove(split, pads.SPLIT_BRIDGE)
    # The far part becomes a grid of its own; find it by one of its decoys
    found = wait(
        lambda: (g := a.grid_of(777_900_000_002)) and g[0] != split and g,
        60,
        "The grid did not split",
    )
    part, cell = found
    offset = [c - e for c, e in zip(cell, (9, 1, 1))]
    assert a.place(split, free, "LargeDecoy")[0]
    target = tuple(c + o for c, o in zip(other_free, offset))
    assert a.place(part, target, "LargeDecoy")[0]


# --- paste -------------------------------------------------------------------

WINDOWS = Rule("Windows", ["VerticalWindow"], 1, players=True)
PASTE_AT = (-60.0, 0.0, world.PAD_ROW_Z_M)


def paste_windows(game) -> int:
    blocks = "".join(
        world.block("CubeBlock", "LargeWindowSquare", (x, 0, 0)) for x in range(3)
    )
    pasted = game.a.api.paste_blueprint(
        xml=world.blueprint("Windows", blocks),
        position=PASTE_AT,
        display_name="Pasted windows",
        own=True,
    )
    return pasted[0]["entityId"]


@pytest.fixture(scope="module")
def pasted(game):
    game.configure([WINDOWS])
    grid = paste_windows(game)
    wait(lambda: game.a.server_blocks(grid), 30, "The pasted grid is not on the server")
    return grid


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=NOT_ENFORCED)
def test_paste_over_a_player_limit_is_refused(game, pasted):
    assert game.a.server_blocks(pasted).get("LargeWindowSquare", 0) <= WINDOWS.limit


def test_pasted_blocks_count_once_counted_again(game, pasted):
    game.configure([WINDOWS])
    a = game.a
    assert "Windows: player 3/1" in a.report()
    kept, _ = a.place(
        pads.PLAYER_A2.entity_id, a.free_socket(pads.PLAYER_A2), "LargeWindowSquare"
    )
    assert not kept


# --- projection --------------------------------------------------------------


def test_welding_a_projection_stops_at_the_limit(game):
    """A ship welder built by player A welds a projection of four heavy armor
    blocks. Two are allowed; the rest go away as soon as they are built."""
    game.configure([Rule("Heavy armor", ["HeavyArmorBlock"], 2, players=True)])
    a = game.a
    grid = pads.PROJECTION.entity_id
    before = a.mark()
    a.stand_by(pads.PROJECTION)
    a.api.set_enabled(grid, pads.WELDER_CELL, True)
    try:
        wait(
            lambda: a.server_blocks(grid).get("LargeHeavyBlockArmorBlock", 0) >= 2,
            60,
            lambda: f"The welder built nothing: {a.probe('tool', pads.WELDER_ID)}, "
            f"{a.probe('projection', pads.PROJECTOR_ID)}",
        )
        time.sleep(10)
    finally:
        a.api.set_enabled(grid, pads.WELDER_CELL, False)
        a.stand_by()
    time.sleep(3)
    assert a.server_blocks(grid)["LargeHeavyBlockArmorBlock"] == 2
    assert "Heavy armor: player 2/2" in a.report()
    denials = [t for _, t in a.chat_since(before) if "Limit reached" in t]
    assert denials, "The welder never went over the limit"
