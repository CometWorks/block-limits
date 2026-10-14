"""Importing the world's vanilla block type limits. The test world limits
collectors to three per player (BlockLimitsEnabled PER_PLAYER). The game
enforces that limit itself, so these tests look at what the plugin makes of
it: its rule list and its counts."""

from __future__ import annotations

import pads

VANILLA_RULE = [
    "Vanilla Collector",
    "Blocks: Collector",
    "GridType: AllGrids",
    "Limit: 3",
    "PlayerLimit: True",
    "FactionLimit: False",
    "GridLimit: False",
]


def test_vanilla_limits_are_left_out_by_default(game):
    game.configure()
    assert game.b.command("!blocklimit limits") == "No block limits found"


def test_vanilla_limits_imported(game):
    game.configure(UseVanillaLimits=True)
    assert game.b.command("!blocklimit limits").splitlines() == ["", *VANILLA_RULE]


def test_vanilla_limit_counts(game):
    game.configure(UseVanillaLimits=True)
    a = game.a
    assert a.place(pads.VANILLA.entity_id, a.free_socket(pads.VANILLA), "Collector")[0]
    assert a.command("!blocklimit mylimit") == "Vanilla Collector: player 1/3"
