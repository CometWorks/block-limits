"""The cross-plugin API, BlockLimits.PluginApi.Limits.CanAdd, called by the
probe plugin the way another plugin would. The blocks asked about are the five
timer blocks of a template grid, which nobody built."""

from __future__ import annotations

import re

import pads
import world
from rig import Rule


def can_add(game, identity_id: int = world.PLAYER_A) -> dict:
    reply = game.a.probe(
        "canadd", pads.API_TEMPLATE.entity_id, identity_id, "TimerBlockLarge"
    )
    match = re.fullmatch(r"Probe canadd: allowed=(\w+) denied=(\d+) total=(\d+)", reply)
    assert match, reply
    return {
        "allowed": match[1] == "True",
        "denied": int(match[2]),
        "total": int(match[3]),
    }


def timers(limit: int, **kwargs) -> Rule:
    return Rule("Timers", ["TimerBlock"], limit, players=True, **kwargs)


def test_within_the_limit(game):
    game.configure([timers(5)])
    assert can_add(game) == {"allowed": True, "denied": 0, "total": 5}


def test_over_the_limit_counts_the_blocks_asked_about(game):
    """Five new timers for a player allowed two: three are too many"""
    game.configure([timers(2)])
    assert can_add(game) == {"allowed": False, "denied": 3, "total": 5}


def test_counts_what_the_player_built(game):
    game.configure([timers(5)])
    a = game.a
    assert a.place(
        pads.API_TARGET.entity_id, a.free_socket(pads.API_TARGET), "TimerBlockLarge"
    )[0]
    assert can_add(game) == {"allowed": False, "denied": 1, "total": 5}


def test_excepted_player(game):
    game.configure([timers(1, exceptions=[world.PLAYER_A])])
    assert can_add(game)["allowed"]


def test_other_player_has_counts_of_their_own(game):
    game.configure([timers(5)])
    assert can_add(game, world.PLAYER_B) == {"allowed": True, "denied": 0, "total": 5}


def test_disabled_plugin_allows_everything(game):
    game.configure([timers(0)], Enabled=False)
    assert can_add(game) == {"allowed": True, "denied": 0, "total": 5}
