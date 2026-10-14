"""Limit rules: player, faction and grid scopes, how block names match, grid
types, exceptions, a zero limit, the denial message, and counts following
removals and ownership changes.

Players build with the cube builder's build request (Remote's build-block),
so the server's BlockBuilt event decides, as for a player in the game. The
server removes a block over a limit at once and sends the player the denial
message; the client may never see the block.

Each test uses block types of its own, so player and faction counts of one
test never reach into another. The tests of one scope build on each other and
run in file order.
"""

from __future__ import annotations

import time

import pads
import world
from conftest import socket
from rig import Rule

DEFAULT_DENIAL = "Limit reached: 1 blocks denied. BlockNames: {}"


def place(player, pad, i, subtype) -> bool:
    return player.place(pad.entity_id, socket(i), subtype)[0]


# --- player scope --------------------------------------------------------------

LIGHTS = Rule("Player lights", ["InteriorLight"], 2, players=True)


def test_player_limit_denies_the_block_over_it(game):
    game.configure([LIGHTS])
    a = game.a
    assert place(a, pads.PLAYER_A1, 0, "SmallLight")
    assert place(a, pads.PLAYER_A1, 1, "SmallLight")
    kept, chat = a.place(pads.PLAYER_A1.entity_id, socket(2), "SmallLight")
    assert not kept
    assert DEFAULT_DENIAL.format("InteriorLight") in chat
    assert a.server_blocks(pads.PLAYER_A1.entity_id).get("SmallLight") == 2
    assert "Player lights: player 2/2" in a.report()


def test_player_limit_counts_all_grids_of_the_player(game):
    game.configure([LIGHTS])
    assert not place(game.a, pads.PLAYER_A2, 0, "SmallLight")


def test_type_rule_covers_every_subtype_of_the_type(game):
    game.configure([LIGHTS])
    assert not place(game.a, pads.PLAYER_A2, 1, "LargeBlockLight_1corner")


def test_players_have_counts_of_their_own(game):
    game.configure([LIGHTS])
    b = game.b
    assert place(b, pads.PLAYER_B1, 0, "SmallLight")
    assert place(b, pads.PLAYER_B1, 1, "LargeBlockLight_1corner")
    assert not place(b, pads.PLAYER_B1, 2, "SmallLight")
    assert "Player lights: player 2/2" in game.a.report(world.PLAYER_B)


def test_mylimit_reports_the_callers_counts(game):
    game.configure([LIGHTS])
    assert game.b.command("!blocklimit mylimit") == "Player lights: player 2/2"


# --- grid scope ----------------------------------------------------------------

BUTTONS = Rule("Grid buttons", ["ButtonPanel"], 1, grids=True)


def test_grid_limit_counts_each_grid_on_its_own(game):
    game.configure([BUTTONS])
    a, b = game.a, game.b
    assert place(a, pads.GRID_1, 0, "ButtonPanelLarge")
    # Another player's block counts toward the same grid
    assert not place(b, pads.GRID_1, 1, "ButtonPanelLarge")
    assert place(b, pads.GRID_2, 0, "ButtonPanelLarge")
    assert not place(a, pads.GRID_2, 1, "ButtonPanelLarge")


def test_grid_limit_is_not_in_the_players_report(game):
    game.configure([BUTTONS])
    assert game.a.report() == "You have no block within set limit"


# --- faction scope -------------------------------------------------------------

BATTERIES = Rule("Faction batteries", ["BatteryBlock"], 3, faction=True)


def test_faction_limit_counts_every_member(game):
    """Charlie, a member who never joins, built two batteries: player A, a
    member too, may add one"""
    game.configure([BATTERIES])
    a = game.a
    assert "Faction batteries: faction 2/3" in a.report()
    assert place(a, pads.FACTION_B, 0, "LargeBlockBatteryBlock")
    assert not place(a, pads.FACTION_B, 1, "LargeBlockBatteryBlock")
    assert "Faction batteries: faction 3/3" in a.report()


def test_faction_limit_leaves_players_without_faction_alone(game):
    game.configure([BATTERIES])
    b = game.b
    assert place(b, pads.FACTION_B, 2, "LargeBlockBatteryBlock")
    assert place(b, pads.FACTION_B, 3, "LargeBlockBatteryBlock")
    assert place(b, pads.FACTION_B, 4, "LargeBlockBatteryBlock")
    assert "faction" not in game.a.report(world.PLAYER_B)


def test_joining_a_faction_brings_the_players_blocks_along(game):
    game.configure([BATTERIES])
    b = game.b
    b.api.join_faction(world.FACTION_TAG)
    deadline = time.monotonic() + 30
    while b.api.get_faction().get("tag") != world.FACTION_TAG:
        assert time.monotonic() < deadline, "Player B did not get into the faction"
        time.sleep(1)
    assert game.a.command("!blocklimit update") == "Limits updated"
    assert "Faction batteries: faction 6/3" in game.a.report()
    assert not place(b, pads.FACTION_B, 5, "LargeBlockBatteryBlock")


# --- block names ---------------------------------------------------------------


def test_subtype_rule_matches_the_subtype(game):
    game.configure(
        [
            Rule(
                "Corners",
                ["LargeBlockArmorCorner"],
                1,
                players=True,
                search="SubtypeId",
            )
        ]
    )
    assert place(game.a, pads.SEARCH, 0, "LargeBlockArmorCorner")
    assert not place(game.a, pads.SEARCH, 1, "LargeBlockArmorCorner")


def test_pair_name_rule_matches_the_pair_name(game):
    game.configure(
        [Rule("Slopes", ["LightArmorSlope"], 1, players=True, search="BlockPairName")]
    )
    assert place(game.a, pads.SEARCH, 2, "LargeBlockArmorSlope")
    assert not place(game.a, pads.SEARCH, 3, "LargeBlockArmorSlope")


def test_type_rule_matches_the_type(game):
    game.configure([Rule("Conveyors", ["Conveyor"], 1, players=True, search="TypeId")])
    assert place(game.a, pads.SEARCH, 4, "LargeBlockConveyor")
    assert not place(game.a, pads.SEARCH, 5, "LargeBlockConveyor")


def test_type_rule_does_not_match_a_subtype(game):
    game.configure(
        [Rule("Armor", ["LargeBlockArmorBlock"], 0, players=True, search="TypeId")]
    )
    assert place(game.a, pads.SEARCH, 6, "LargeBlockArmorBlock")


def test_auto_rule_ignores_case_and_spaces(game):
    game.configure([Rule("Pillars", ["  largeinteriorpillar "], 1, players=True)])
    assert place(game.a, pads.SEARCH, 7, "LargeInteriorPillar")
    assert not place(game.a, pads.SEARCH, 8, "LargeInteriorPillar")


def test_blocks_of_one_rule_share_its_limit(game):
    game.configure(
        [
            Rule(
                "Sound and text",
                ["LargeBlockSoundBlock", "LargeTextPanel"],
                2,
                players=True,
            )
        ]
    )
    a = game.a
    assert place(a, pads.GROUP, 0, "LargeBlockSoundBlock")
    assert place(a, pads.GROUP, 1, "LargeTextPanel")
    assert not place(a, pads.GROUP, 2, "LargeBlockSoundBlock")
    assert not place(a, pads.GROUP, 3, "LargeTextPanel")


# --- grid types ----------------------------------------------------------------


def test_small_grid_rule(game):
    game.configure(
        [
            Rule(
                "Small cargo",
                ["CargoContainer"],
                1,
                players=True,
                grid_type="SmallGrid",
            )
        ]
    )
    a = game.a
    assert place(a, pads.SMALL_STATIC, 0, "SmallBlockSmallContainer")
    assert not place(a, pads.SMALL_STATIC, 1, "SmallBlockSmallContainer")
    assert place(a, pads.LARGE_STATIC, 0, "LargeBlockSmallContainer")
    assert place(a, pads.LARGE_STATIC, 1, "LargeBlockSmallContainer")


def test_large_grid_rule(game):
    game.configure(
        [
            Rule(
                "Large spotlights",
                ["ReflectorLight"],
                1,
                players=True,
                grid_type="LargeGrid",
            )
        ]
    )
    a = game.a
    assert place(a, pads.LARGE_STATIC, 2, "LargeBlockFrontLight")
    assert not place(a, pads.LARGE_STATIC, 3, "LargeBlockFrontLight")
    assert place(a, pads.SMALL_STATIC, 2, "SmallBlockFrontLight")
    assert place(a, pads.SMALL_STATIC, 3, "SmallBlockFrontLight")


def test_static_grid_rule(game):
    game.configure(
        [Rule("Station gyros", ["Gyro"], 1, players=True, grid_type="Static")]
    )
    a = game.a
    assert place(a, pads.LARGE_STATIC, 4, "LargeBlockGyro")
    assert not place(a, pads.LARGE_STATIC, 5, "LargeBlockGyro")
    assert place(a, pads.LARGE_SHIP, 0, "LargeBlockGyro")
    assert place(a, pads.LARGE_SHIP, 1, "LargeBlockGyro")


def test_ship_rule(game):
    game.configure(
        [Rule("Ship sensors", ["SensorBlock"], 1, players=True, grid_type="Ship")]
    )
    a = game.a
    assert place(a, pads.LARGE_SHIP, 2, "LargeBlockSensor")
    assert not place(a, pads.LARGE_SHIP, 3, "LargeBlockSensor")
    assert place(a, pads.LARGE_STATIC, 6, "LargeBlockSensor")
    assert place(a, pads.LARGE_STATIC, 7, "LargeBlockSensor")


# --- zero limits ---------------------------------------------------------------


def test_zero_limit_denies_every_block(game):
    game.configure([Rule("Banned vents", ["AirVent"], 0, players=True)])
    assert not place(game.a, pads.ZERO, 0, "AirVentFull")


def test_zero_limit_without_a_scope_denies_nothing(game):
    game.configure([Rule("Unscoped vents", ["AirVent"], 0)])
    assert place(game.a, pads.ZERO, 1, "AirVentFull")


# --- exceptions ----------------------------------------------------------------


def test_excepted_player_is_not_limited(game):
    game.configure(
        [
            Rule(
                "Connectors",
                ["ShipConnector"],
                1,
                players=True,
                exceptions=[world.PLAYER_A],
            )
        ]
    )
    assert place(game.a, pads.EXCEPTIONS, 0, "Connector")
    assert place(game.a, pads.EXCEPTIONS, 1, "Connector")
    assert place(game.b, pads.EXCEPTIONS_B, 0, "Connector")
    assert not place(game.b, pads.EXCEPTIONS_B, 1, "Connector")


def test_excepted_grid_is_not_limited(game):
    rule = Rule(
        "Cryo",
        ["LargeBlockCryoChamber"],
        1,
        players=True,
        exceptions=[pads.EXCEPTED_GRID.entity_id],
    )
    game.configure([rule])
    a = game.a
    assert place(a, pads.OTHER_GRID, 0, "LargeBlockCryoChamber")
    assert not place(a, pads.OTHER_GRID, 1, "LargeBlockCryoChamber")
    assert place(a, pads.EXCEPTED_GRID, 0, "LargeBlockCryoChamber")
    assert place(a, pads.EXCEPTED_GRID, 1, "LargeBlockCryoChamber")


def test_excepted_faction_is_not_limited(game):
    """The option's description names faction ids among the exceptions"""
    game.configure(
        [Rule("Plates", ["LandingGear"], 1, faction=True, exceptions=[world.FACTION])]
    )
    assert place(game.a, pads.EXCEPTIONS, 2, "LargeBlockSmallMagneticPlate")
    assert place(game.a, pads.EXCEPTIONS, 3, "LargeBlockSmallMagneticPlate")


def test_npc_blocks_count_toward_a_grid_limit(game):
    game.configure([Rule("NPC cargo", ["CargoContainer"], 3, grids=True)])
    assert not place(game.a, pads.NPC, 3, "LargeBlockSmallContainer")


def test_ignore_npcs_leaves_npc_blocks_out(game):
    game.configure(
        [Rule("NPC cargo", ["CargoContainer"], 3, grids=True, ignore_npcs=True)]
    )
    assert place(game.a, pads.NPC, 3, "LargeBlockSmallContainer")


# --- counts following the world ------------------------------------------------

ASSEMBLERS = Rule("Assemblers", ["BasicAssembler"], 1, players=True)


def test_removed_block_frees_its_place_at_once(game):
    game.configure([ASSEMBLERS])
    a = game.a
    assert place(a, pads.REMOVAL, 0, "BasicAssembler")
    assert not place(a, pads.REMOVAL, 1, "BasicAssembler")
    a.remove(pads.REMOVAL.entity_id, socket(0))
    assert place(a, pads.REMOVAL, 2, "BasicAssembler")


def test_ownership_change_keeps_the_builders_count(game):
    """The counts go by who built a block, not who owns it"""
    game.configure([Rule("Panels", ["LargeLCDPanel"], 1, players=True)])
    a = game.a
    assert place(a, pads.OWNERSHIP, 0, "LargeLCDPanel")
    a.api.set_owner(pads.OWNERSHIP.entity_id, socket(0), identity_id=world.PLAYER_B)
    deadline = time.monotonic() + 20
    while (
        a.api.get_block(pads.OWNERSHIP.entity_id, socket(0)).get("ownerId")
        != world.PLAYER_B
    ):
        assert time.monotonic() < deadline, "The owner did not change"
        time.sleep(1)
    assert a.command("!blocklimit update") == "Limits updated"
    assert "Panels: player 1/1" in a.report()
    assert "Panels: player 0/1" in a.report(world.PLAYER_B)
    assert not place(a, pads.OWNERSHIP, 1, "LargeLCDPanel")


# --- denial message ------------------------------------------------------------


def test_custom_denial_message(game):
    game.configure(
        [Rule("", ["ConveyorTube"], 0, players=True)],
        DenyMessage="Denied {BL} by {LIMIT} ({BC})",
    )
    kept, chat = game.a.place(pads.MESSAGE.entity_id, socket(0), "ConveyorTube")
    assert not kept
    # A rule without a name goes by its block list
    assert "Denied ConveyorTube by ConveyorTube (1)" in chat


def test_disabled_plugin_denies_nothing(game):
    game.configure([Rule("Masses", ["VirtualMass"], 0, players=True)], Enabled=False)
    assert place(game.a, pads.DISABLED, 0, "VirtualMassLarge")
    game.configure([Rule("Masses", ["VirtualMass"], 0, players=True)])
    assert not place(game.a, pads.DISABLED, 1, "VirtualMassLarge")
