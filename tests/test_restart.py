"""What survives a server restart: the config the commands changed, the
counts, which the plugin takes again from the saved world, and a broken config
file, which the plugin sets aside for the defaults.

These tests restart the server and join the clients again; conftest.py runs
them last.
"""

from __future__ import annotations

import pads
from rig import Rule

BEDS = Rule("Beds", ["LargeBlockBedFree"], 2, players=True)


def restart(game) -> None:
    for client in (game.a.client, game.b.client):
        client.stop()
    game.server.stop()
    game.server.start()
    game.rejoin()


def test_config_and_counts_survive_a_restart(game):
    game.configure([BEDS])
    a = game.a
    pad = pads.PERSIST
    assert a.place(pad.entity_id, a.free_socket(pad), "LargeBlockBedFree")[0]
    assert a.place(pad.entity_id, a.free_socket(pad), "LargeBlockBedFree")[0]
    assert a.command("!blocklimit enable false") == "BlockLimits Disabled"

    restart(game)
    a, b = game.a, game.b
    assert b.command("!blocklimit limits") == "Plugin disabled"
    assert a.command("!blocklimit enable true") == "BlockLimits Enabled"
    assert a.command("!blocklimit mylimit") == "Beds: player 2/2"
    assert not a.place(pad.entity_id, a.free_socket(pad), "LargeBlockBedFree")[0]


def test_broken_config_is_set_aside(game):
    data = game.server.data
    for old in data.glob("BlockLimits.cfg.corrupted.*"):
        old.unlink()
    game.a.client.stop()
    game.b.client.stop()
    game.server.stop()
    game.server.plugin_cfg.write_text("<PluginConfig><Limits>", encoding="utf-8")
    game.server.start()
    game.rejoin()

    assert len(list(data.glob("BlockLimits.cfg.corrupted.*.txt"))) == 1
    assert "<LimitRule>" not in game.server.plugin_cfg.read_text(encoding="utf-8")
    assert game.b.command("!blocklimit limits") == "No block limits found"
