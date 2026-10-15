"""Grid size limits: the most blocks a small grid, a large grid, a ship and a
station may have, and the grid count limits per player.

Each size test sets the limit one block above the grid's current size, so the
first block fits and the second doesn't. The other pad shows the limit leaves
other kinds of grid alone.

The count tests start new grids with the cube builder's request, which Remote
sends for the client: a headless client has no placement gizmo to aim.
"""

from __future__ import annotations

import re
import time

import pytest

import pads
import rig
import world
from se_remote import SetOp

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


# Free spots beside the row of pads for new grids, one per request
_spots = iter(
    (-80.0 - 10.0 * (i % 4), 0.0, world.PAD_ROW_Z_M - 10.0 * (i // 4))
    for i in range(100)
)
OPTION = {"Large": "MaxLargeGridsPerPlayer", "Small": "MaxSmallGridsPerPlayer"}


def grid_count(game, size: str, player: int = world.PLAYER_A) -> int:
    """A player's grids of this size, as counted when the config was last put
    in"""
    reply = game.a.probe("grids", player)
    match = re.fullmatch(r"Probe grids: small=(\d+) large=(\d+)", reply)
    assert match, reply
    return int(match[2] if size == "Large" else match[1])


def counted(game, size: str, expected: int, player: int = world.PLAYER_A, **options):
    """Waits until the count of the player's grids is the expected one"""
    deadline = time.monotonic() + 30
    while True:
        game.configure(**options)
        count = grid_count(game, size, player)
        if count == expected:
            return
        assert time.monotonic() < deadline, f"{count} {size} grids, not {expected}"
        time.sleep(1)


def new_grid(player, size: str) -> bool | None:
    """Starts a new station of one armor block the way the cube builder does,
    and returns the server's answer"""
    report = player.api.character_build_grid(
        ARMOR[size], next(_spots), timeout_seconds=15
    )
    assert report["sent"], report
    return report["reply"]


def denied(player, before, text: str) -> None:
    deadline = time.monotonic() + 15
    while text not in [t for _, t in player.chat_since(before)]:
        assert time.monotonic() < deadline, f"No {text!r} in the chat"
        time.sleep(0.5)


@pytest.mark.parametrize("size", ["Large", "Small"])
def test_grid_count_limit_per_player(game, size):
    """At the limit, a new grid from the cube builder and a pasted grid are
    refused; one more allowed lets the next one in"""
    a = game.a
    game.configure()
    count = grid_count(game, size)
    assert new_grid(a, size) is True
    counted(game, size, count + 1)

    limit = {OPTION[size]: count + 1, "DenyMessage": "{LIMIT}"}
    game.configure(**limit)
    message = f"{size} grids per player"
    before = a.mark()
    assert new_grid(a, size) is False
    denied(a, before, message)

    before = a.mark()
    blocks = world.block("CubeBlock", ARMOR[size], (0, 0, 0))
    name = f"Pasted {size} grid"
    assert a.paste(name, blocks, next(_spots), size) is None
    denied(a, before, message)
    assert not a.grid_named(name)
    counted(game, size, count + 1, **limit)

    limit[OPTION[size]] = count + 2
    game.configure(**limit)
    assert new_grid(a, size) is True
    counted(game, size, count + 2, **limit)


def test_grid_count_limit_of_a_player_without_rights(game):
    """Player B, no admin and no creative tools, builds with materials in a
    survival world"""
    b = game.b
    game.configure()
    if rig.SURVIVAL:
        assert game.a.probe("give", world.PLAYER_B, "SteelPlate", 200).startswith(
            "Probe give: "
        )
    count = grid_count(game, "Large", world.PLAYER_B)
    limit = {"MaxLargeGridsPerPlayer": count + 1, "DenyMessage": "{LIMIT}"}
    game.configure(**limit)
    assert new_grid(b, "Large") is True
    counted(game, "Large", count + 1, world.PLAYER_B, **limit)

    before = b.mark()
    assert new_grid(b, "Large") is False
    denied(b, before, "Large grids per player")


def test_split_over_the_grid_limit_is_allowed(game):
    """Player A's grid splits in two at the limit: both parts stay, and the next
    new grid is refused"""
    a = game.a
    game.configure()
    count = grid_count(game, "Large")
    limit = {"MaxLargeGridsPerPlayer": count, "DenyMessage": "{LIMIT}"}
    game.configure(**limit)
    a.remove(pads.SPLIT_A.entity_id, pads.SPLIT_BRIDGE)
    counted(game, "Large", count + 1, **limit)

    before = a.mark()
    assert new_grid(a, "Large") is False
    denied(a, before, "Large grids per player")


def test_taking_over_a_grid_at_the_limit_is_allowed(game):
    """Player A takes over a grid nobody owns while at the limit: the grid is
    A's, and the next new grid is refused"""
    a = game.a
    game.configure()
    count = grid_count(game, "Large")
    limit = {"MaxLargeGridsPerPlayer": count, "DenyMessage": "{LIMIT}"}
    game.configure(**limit)
    pad = pads.CLAIM
    a.stand_by(pad)
    try:
        a.api.batch(
            sets=[
                SetOp.owner(
                    pad.entity_id, pad.socket_cell(0), identity_id=a.identity_id
                )
            ]
        ).set(0)
        counted(game, "Large", count + 1, **limit)
    finally:
        a.stand_by()

    before = a.mark()
    assert new_grid(a, "Large") is False
    denied(a, before, "Large grids per player")
