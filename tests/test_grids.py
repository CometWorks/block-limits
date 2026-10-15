"""Grids changing shape: merging, splitting, pasting and welding a projection.

Blocks built one at a time reach the plugin through the game's BlockBuilt
event (the cube builder and projection welding). Merges and pastes have hooks
of their own, which refuse them as a whole.
"""

from __future__ import annotations

import time

import pytest

import pads
import rig
import world
from session import DECOYS
from rig import Rule

# The denial message the tests ask for: the limit, the count, the blocks
DENY = "{LIMIT}|{BC}|{BL}"


def wait(condition, timeout: float, message):
    """Waits for condition to come true and returns its value. message may be
    a function, called on failure."""
    deadline = time.monotonic() + timeout
    while not (result := condition()):
        assert time.monotonic() < deadline, message() if callable(message) else message
        time.sleep(1)
    return result


def switch_on_merge_block(game, station, ship_id: int) -> set:
    """Switches the ship's merge block on, standing next to it, and returns the
    chat mark from before"""
    a = game.a
    before = a.mark()
    a.stand_by(station, pads.MERGE_CELL)
    try:
        a.api.set_enabled(ship_id, (0, 0, 0), True)
        time.sleep(3)
    finally:
        a.stand_by()
    return before


def test_merge_over_a_grid_limit_is_refused(game):
    """Two decoys each, three allowed per grid: the merged grid would have four.
    The ship's merge block goes off, its owner hears why."""
    game.configure([DECOYS], DenyMessage=DENY)
    a = game.a
    before = switch_on_merge_block(game, pads.MERGE_STATION, pads.MERGE_SHIP_ID)
    denial = wait(
        lambda: [t for _, t in a.chat_since(before) if t.startswith("Grid decoys|")],
        30,
        "No denial for the merge",
    )
    assert denial[0] == "Grid decoys|1|Decoy", denial
    assert a.probe("enabled", pads.MERGE_SHIP_BLOCK_ID) == "Probe enabled: False"
    assert a.probe("enabled", pads.MERGE_BLOCK_ID) == "Probe enabled: True"
    time.sleep(5)
    assert a.server_blocks(pads.MERGE_SHIP_ID).get("LargeDecoy") == 2
    assert a.server_blocks(pads.MERGE_STATION.entity_id)["LargeDecoy"] == 2


def denials(a, before) -> list[str]:
    return [t for _, t in a.chat_since(before) if t.startswith("Grid decoys|")]


def test_merge_messages_come_at_most_every_ten_seconds(game):
    """The merge blocks keep trying while a player switches them back on; the
    owner hears of it once per 10 seconds for the same two grids"""
    game.configure([DECOYS], DenyMessage=DENY)
    a = game.a
    # Out of the 10 seconds of the refusal in the test before
    time.sleep(11)
    before = switch_on_merge_block(game, pads.MERGE_STATION, pads.MERGE_SHIP_ID)
    wait(lambda: denials(a, before), 30, "No denial for the merge")
    first = time.monotonic()

    before = switch_on_merge_block(game, pads.MERGE_STATION, pads.MERGE_SHIP_ID)
    time.sleep(2)
    # Refused again, the merge block is off again, without a message
    assert a.probe("enabled", pads.MERGE_SHIP_BLOCK_ID) == "Probe enabled: False"
    assert a.server_blocks(pads.MERGE_SHIP_ID).get("LargeDecoy") == 2
    assert not denials(a, before)

    time.sleep(max(0.0, first + 11 - time.monotonic()))
    before = switch_on_merge_block(game, pads.MERGE_STATION, pads.MERGE_SHIP_ID)
    wait(lambda: denials(a, before), 30, "No denial after 10 seconds")


def test_merged_grids_count_as_one(game):
    """One and two decoys merge into a grid with the three allowed"""
    game.configure([DECOYS])
    a = game.a
    station = pads.MERGE_OK.entity_id
    switch_on_merge_block(game, pads.MERGE_OK, pads.MERGE_OK_SHIP_ID)
    wait(
        lambda: a.server_blocks(pads.MERGE_OK_SHIP_ID) == {},
        60,
        "The ship did not merge into the station",
    )
    assert a.server_blocks(station)["LargeDecoy"] == 3
    assert not a.place(station, a.free_socket(pads.MERGE_OK), "LargeDecoy")[0]


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


# --- stations touching -------------------------------------------------------


def station_with_decoys(decoys: int) -> str:
    """Armor at the origin, the decoys along +z. (Along -x the game finds the
    area occupied.)"""
    return world.block("CubeBlock", "LargeBlockArmorBlock", (0, 0, 0)) + "".join(
        world.block("Decoy", "LargeDecoy", (0, 0, 1 + i)) for i in range(decoys)
    )


def bridge_to(game, pad, name: str, decoys: int):
    """Pastes a station one cell away from the pad's armor, its armor at the
    pad's cell (-2, 1, 1), and places the block between them. A pasted station
    can't touch another grid: the game's placement check refuses it. Returns
    the pasted station's id."""
    a = game.a
    at = tuple(p + 2.5 * c for p, c in zip(pad.position, (-2, 1, 1)))
    grid = a.paste(name, station_with_decoys(decoys), at, static=True)
    assert grid is not None, "The paste was refused"
    wait(lambda: a.server_blocks(grid), 30, "The pasted station is not on the server")
    # Not Player.place: once merged, the grid the block went onto is gone
    built = a.api.character_build_block(grid, (1, 0, 0), "LargeBlockArmorBlock")
    assert built.get("sent"), built
    return grid


def test_touching_stations_over_a_grid_limit_stay_apart(game):
    """A station with two decoys gets connected to a station with two, three
    allowed per grid: the block is built, the merge after it is refused"""
    game.configure([DECOYS], DenyMessage=DENY)
    a = game.a
    before = a.mark()
    grid = bridge_to(game, pads.STATIC_MERGE, "Touching decoys", 2)
    wait(lambda: denials(a, before), 30, "No denial for the merge")
    assert denials(a, before)[0] == "Grid decoys|1|Decoy"
    assert a.server_blocks(grid).get("LargeDecoy") == 2
    assert a.server_blocks(pads.STATIC_MERGE.entity_id)["LargeDecoy"] == 2


def test_touching_stations_within_the_limits_merge(game):
    game.configure([DECOYS])
    a = game.a
    grid = bridge_to(game, pads.STATIC_MERGE_OK, "Touching decoy", 1)
    station = pads.STATIC_MERGE_OK.entity_id
    wait(
        lambda: a.server_blocks(station).get("LargeDecoy") == 3,
        30,
        lambda: f"No merge: {a.server_blocks(station)}, {a.server_blocks(grid)}",
    )
    assert a.server_blocks(grid) == {}


# --- paste -------------------------------------------------------------------

PASTE_AT = (-60.0, 0.0, world.PAD_ROW_Z_M)


def windows(limit: int) -> Rule:
    return Rule("Windows", ["VerticalWindow"], limit, players=True)


def paste_windows(game, name: str, spinner: bool = False):
    """Pastes a grid of three windows owned by player A. Returns the pasted
    grid's id, or None if the server refused the paste."""
    blocks = "".join(
        world.block("CubeBlock", "LargeWindowSquare", (x, 0, 0)) for x in range(3)
    )
    return game.a.paste(name, blocks, PASTE_AT, spinner=spinner)


def test_paste_over_a_player_limit_is_refused(game):
    """Three windows with one allowed: the paste fails as a whole. The player
    sees the game's own notice, and the paste spinner goes away."""
    game.configure([windows(1)], DenyMessage=DENY)
    a = game.a
    before = a.mark()
    latest = a.api.get_hud_notifications()["latest"]
    assert paste_windows(game, "Refused windows", spinner=True) is None
    chat = [t for _, t in a.chat_since(before)]
    assert "Windows|2|VerticalWindow" in chat, chat
    assert not a.grid_named("Refused windows")
    assert "Windows: player 0/1" in a.report()
    assert any("Paste operation failed" in t for t in a.hud_since(latest))
    assert a.api.get_hud_notifications()["rotatingWheel"] is False


def test_paste_over_a_grid_size_limit_is_refused(game):
    game.configure(MaxBlocksLargeGrid=2, DenyMessage=DENY)
    a = game.a
    before = a.mark()
    assert paste_windows(game, "Big windows") is None
    chat = [t for _, t in a.chat_since(before)]
    assert any(t.startswith("Grid size|3|") for t in chat), chat
    assert not a.grid_named("Big windows")


def test_pasted_blocks_count(game):
    """A paste within the limit goes through and holds its places"""
    game.configure([windows(3)])
    a = game.a
    grid = paste_windows(game, "Pasted windows")
    assert grid is not None, "The paste was refused"
    wait(lambda: a.server_blocks(grid), 30, "The pasted grid is not on the server")
    game.configure([windows(3)])
    assert "Windows: player 3/3" in a.report()
    kept, _ = a.place(
        pads.PLAYER_A2.entity_id, a.free_socket(pads.PLAYER_A2), "LargeWindowSquare"
    )
    assert not kept


# --- paste onto a grid ------------------------------------------------------


def decoys(count: int) -> str:
    """Decoys two cells apart, one per socket"""
    return "".join(
        world.block("Decoy", "LargeDecoy", (2 * i, 0, 0)) for i in range(count)
    )


def test_paste_onto_a_grid_over_a_grid_limit_is_refused(game):
    """Two more decoys onto a grid with two, three allowed per grid"""
    game.configure([DECOYS], DenyMessage=DENY)
    a = game.a
    pad = pads.PASTE_TARGET
    before = a.mark()
    assert a.paste_onto(pad, pad.socket_cell(2), decoys(2)) is None
    chat = [t for _, t in a.chat_since(before)]
    assert "Grid decoys|1|Decoy" in chat, chat
    assert a.server_blocks(pad.entity_id)["LargeDecoy"] == 2


def test_paste_onto_a_grid_within_the_limit(game):
    game.configure([DECOYS])
    a = game.a
    pad = pads.PASTE_TARGET
    assert a.paste_onto(pad, pad.socket_cell(2), decoys(1)) is not None
    assert a.server_blocks(pad.entity_id)["LargeDecoy"] == 3
    assert not a.place(pad.entity_id, a.free_socket(pad), "LargeDecoy")[0]


# --- projection --------------------------------------------------------------


@pytest.mark.skipif(rig.SURVIVAL, reason="the welder has no components in survival")
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
