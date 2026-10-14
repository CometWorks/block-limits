"""The !blocklimit chat commands: what they answer, who may use them, and bad
input. Player A is an administrator, player B has no rights."""

from __future__ import annotations

import re
import time

import pads
from rig import Rule

LIGHTS = Rule("Command lights", ["InteriorLight"], 2, players=True)
NO_PERMISSION = "You do not have permission to use that command."


def test_limits_lists_rules_and_grid_limits(game):
    game.configure([LIGHTS], MaxBlocksSmallGrid=5, MaxLargeGridsPerPlayer=2)
    reply = game.b.command("!blocklimit limits")
    assert reply.splitlines() == [
        "Small Grid Size Limit = 5 blocks",
        "Large Grids Limit = 2 per player",
        "",
        "Command lights",
        "Blocks: InteriorLight",
        "GridType: AllGrids",
        "Limit: 2",
        "PlayerLimit: True",
        "FactionLimit: False",
        "GridLimit: False",
    ]


def test_limits_without_any(game):
    game.configure()
    assert game.b.command("!blocklimit limits") == "No block limits found"


def test_mylimit_without_a_limit(game):
    game.configure()
    assert game.b.command("!blocklimit mylimit") == "You have no block within set limit"


def test_pairnames_of_one_type(game):
    reply = game.b.command("!blocklimit pairnames InteriorLight")
    lines = reply.splitlines()
    assert re.fullmatch(r"\[\d+ Vanilla blocks\]", lines[0])
    assert {"InteriorLight", "CornerLight"} <= set(lines)
    assert "BatteryBlock" not in lines


def test_pairnames_of_every_type(game):
    lines = game.b.command("!blocklimit pairnames").splitlines()
    assert {"InteriorLight", "BatteryBlock", "LightArmorBlock"} <= set(lines)


def test_pairnames_without_a_match(game):
    assert game.b.command("!blocklimit pairnames NoSuchType") == "No definitions found"


def test_update_needs_a_moderator(game):
    assert game.b.command("!blocklimit update") == NO_PERMISSION
    assert game.a.command("!blocklimit update") == "Limits updated"


def test_enable_needs_an_admin(game):
    game.configure([LIGHTS])
    assert game.b.command("!blocklimit enable false") == NO_PERMISSION
    assert game.b.command("!blocklimit limits") != "Plugin disabled"


def test_disabling_and_enabling(game):
    """The command changes the config, and the plugin saves it"""
    game.configure([Rule("Command masses", ["VirtualMass"], 0, players=True)])
    a, b = game.a, game.b
    pad = pads.COMMANDS
    assert a.command("!blocklimit enable false") == "BlockLimits Disabled"
    assert b.command("!blocklimit limits") == "Plugin disabled"
    assert b.command("!blocklimit mylimit") == "Plugin disabled"
    assert a.place(pad.entity_id, a.free_socket(pad), "VirtualMassLarge")[0]
    assert saved(game, "<Enabled>false</Enabled>")

    assert a.command("!blocklimit enable") == "BlockLimits Enabled"
    assert not a.place(pad.entity_id, a.free_socket(pad), "VirtualMassLarge")[0]
    # Enabled is the default again, the file leaves it out
    assert saved(game, None)


def saved(game, element: str | None, timeout: float = 10.0) -> bool:
    """Waits for the plugin's delayed save to write the element, or to drop
    <Enabled>"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = re.sub(
            "<!--.*?-->",
            "",
            game.server.plugin_cfg.read_text(encoding="utf-8"),
            flags=re.S,
        )
        if element in text if element else "<Enabled>" not in text:
            return True
        time.sleep(0.5)
    return False


def test_enable_with_a_bad_argument(game):
    reply = game.a.command("!blocklimit enable maybe")
    assert "Usage:" in reply
    assert game.b.command("!blocklimit limits") != "Plugin disabled"


def test_unknown_subcommand(game):
    assert (
        game.b.command("!blocklimit nosuch") == "Unknown command. Try !blocklimit help"
    )


def test_help_shows_only_what_the_player_may_use(game):
    help_b = game.b.command("!blocklimit help")
    help_a = game.a.command("!blocklimit help")
    for command in ("mylimit", "limits", "pairnames"):
        assert command in help_b
    assert "enable" not in help_b
    assert "update" not in help_b
    assert "enable" in help_a
