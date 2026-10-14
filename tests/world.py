"""The test world: the game's Empty World with the test players, a faction and
the pads the tests build on.

A pad is a grid of armor with sockets: empty cells walled in by armor on all
six sides. A block placed into a socket touches armor on every face, so it
connects whatever its mount points are. The pads float in empty space in a row,
far enough apart that they never touch. Their armor has no builder and no
owner, so it counts toward no player or faction, only toward its grid.

The players exist before the clients join, so their identity ids are known and
the plugin config can name them.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# The test players. A and B are the clients, C never joins: blocks built by C
# are in the world from the start.
PLAYER_A = 144115188075870001
PLAYER_B = 144115188075870002
PLAYER_C = 144115188075870003
# The Space Pirates of the Empty World, an NPC
NPC = 144115188075855896
FACTION = 268000000000000001
FACTION_TAG = "BLT"

PAD_SPACING_M = 20.0
PAD_ROW_Z_M = -150.0
GRID_SIZE_M = {"Large": 2.5, "Small": 0.5}
ARMOR = {"Large": "LargeBlockArmorBlock", "Small": "SmallBlockArmorBlock"}


def vec(tag: str, v) -> str:
    return f'<{tag} x="{v[0]}" y="{v[1]}" z="{v[2]}" />'


def block(
    xsi_type: str,
    subtype: str,
    cell,
    *,
    built_by: int = 0,
    entity_id: int = 0,
    forward: str = "Forward",
    up: str = "Up",
    extra: str = "",
) -> str:
    """A cube block. Functional blocks get an entity id and their builder as
    owner."""
    entity = f"<EntityId>{entity_id}</EntityId>" if entity_id else ""
    owner = f"<Owner>{built_by}</Owner>" if entity_id and built_by else ""
    builder = f"<BuiltBy>{built_by}</BuiltBy>" if built_by else ""
    return (
        f'<MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_{xsi_type}">'
        f"<SubtypeName>{subtype}</SubtypeName>{entity}{vec('Min', cell)}"
        f'<BlockOrientation Forward="{forward}" Up="{up}" />'
        f'<ColorMaskHSV x="0" y="-0.8" z="0.55" />{owner}{builder}{extra}'
        "</MyObjectBuilder_CubeBlock>"
    )


def grid(
    name: str,
    entity_id: int,
    blocks: str,
    position,
    static: bool,
    size: str = "Large",
) -> str:
    return (
        '<MyObjectBuilder_EntityBase xsi:type="MyObjectBuilder_CubeGrid">'
        f"<SubtypeName /><EntityId>{entity_id}</EntityId>"
        "<PersistentFlags>CastShadows InScene</PersistentFlags>"
        "<PositionAndOrientation>"
        + vec("Position", position)
        + vec("Forward", (0, 0, -1))
        + vec("Up", (0, 1, 0))
        + "</PositionAndOrientation>"
        f"<GridSizeEnum>{size}</GridSizeEnum>"
        f"<CubeBlocks>{blocks}</CubeBlocks>"
        f"<IsStatic>{'true' if static else 'false'}</IsStatic>"
        f"<IsUnsupportedStation>{'true' if static else 'false'}</IsUnsupportedStation>"
        f"<DisplayName>{name}</DisplayName>"
        "<DestructibleBlocks>true</DestructibleBlocks>"
        "</MyObjectBuilder_EntityBase>"
    )


@dataclass
class Pad:
    """A grid with sockets along its x axis: socket i is cell (2i + 1, 1, 1)"""

    name: str
    entity_id: int
    index: int
    sockets: int = 8
    size: str = "Large"
    static: bool = True
    # Blocks in the sockets from the start: socket -> (xsi type, subtype, builder)
    filled: dict = field(default_factory=dict)
    # More blocks of the grid, as object builder XML
    extra: str = ""
    # Leaves the armor out, the extra blocks are the whole grid
    bare: bool = False

    @property
    def position(self):
        return (0.0, 0.0, PAD_ROW_Z_M - self.index * PAD_SPACING_M)

    @staticmethod
    def socket_cell(i: int):
        return (2 * i + 1, 1, 1)

    def armor_cells(self):
        for x in range(2 * self.sockets + 1):
            for y in range(3):
                for z in range(3):
                    if (y, z) == (1, 1) and x % 2 == 1:
                        continue
                    yield (x, y, z)

    @property
    def armor_count(self) -> int:
        return 0 if self.bare else (2 * self.sockets + 1) * 9 - self.sockets

    def xml(self) -> str:
        blocks = ""
        if not self.bare:
            blocks = "".join(
                block("CubeBlock", ARMOR[self.size], cell)
                for cell in self.armor_cells()
            )
        for i, (xsi_type, subtype, built_by) in self.filled.items():
            blocks += block(
                xsi_type,
                subtype,
                self.socket_cell(i),
                built_by=built_by,
                entity_id=self.entity_id + 100 + i,
            )
        blocks += self.extra
        return grid(
            self.name,
            self.entity_id,
            blocks,
            self.position,
            self.static,
            self.size,
        )


# ---------------------------------------------------------------------------
# Session data: the players and the factions
# ---------------------------------------------------------------------------


def _identity(identity_id: int, name: str) -> str:
    return (
        "<MyObjectBuilder_Identity>"
        f"<IdentityId>{identity_id}</IdentityId><DisplayName>{name}</DisplayName>"
        "<CharacterEntityId>0</CharacterEntityId>"
        "<BlockLimitModifier>0</BlockLimitModifier>"
        "</MyObjectBuilder_Identity>"
    )


def _player(steam_id: int, identity_id: int, name: str) -> str:
    return (
        '<item><Key xsi:type="PlayerId">'
        f"<ClientId>{steam_id}</ClientId><SerialId>0</SerialId></Key>"
        '<Value xsi:type="MyObjectBuilder_Player">'
        f"<DisplayName>{name}</DisplayName><IdentityId>{identity_id}</IdentityId>"
        "<Connected>false</Connected></Value></item>"
    )


def _faction(faction_id: int, tag: str, name: str, members) -> str:
    rows = "".join(
        "<MyObjectBuilder_FactionMember>"
        f"<PlayerId>{m}</PlayerId><IsLeader>{str(i == 0).lower()}</IsLeader>"
        f"<IsFounder>{str(i == 0).lower()}</IsFounder>"
        "</MyObjectBuilder_FactionMember>"
        for i, m in enumerate(members)
    )
    return (
        "<MyObjectBuilder_Faction>"
        f"<FactionId>{faction_id}</FactionId><Tag>{tag}</Tag><Name>{name}</Name>"
        "<Description /><PrivateInfo />"
        f"<Members>{rows}</Members><JoinRequests />"
        "<AutoAcceptMember>true</AutoAcceptMember><AutoAcceptPeace>false</AutoAcceptPeace>"
        "<AcceptHumans>true</AcceptHumans><EnableFriendlyFire>false</EnableFriendlyFire>"
        "</MyObjectBuilder_Faction>"
    )


def _insert(text: str, tag: str, content: str) -> str:
    """Puts content at the start of the first <tag> element, opening an empty
    <tag /> if need be"""
    if f"<{tag}>" in text:
        return text.replace(f"<{tag}>", f"<{tag}>{content}", 1)
    new, count = re.subn(rf"<{tag}\s*/>", f"<{tag}>{content}</{tag}>", text, count=1)
    assert count == 1, tag
    return new


def _set(text: str, name: str, value: str) -> str:
    new, count = re.subn(
        rf"<{name}>[^<]*</{name}>|<{name}\s*/>", f"<{name}>{value}</{name}>", text
    )
    if count:
        return new
    # Settings the template leaves at their default
    return text.replace("</Settings>", f"<{name}>{value}</{name}></Settings>", 1)


BASE_SETTINGS = {
    "GameMode": "Creative",
    "OnlineMode": "PUBLIC",
    "MaxPlayers": "8",
    "EnableRespawnShips": "false",
    "EnableSpaceSuitRespawn": "true",
    "TrashRemovalEnabled": "false",
    "EnableCopyPaste": "true",
    "BlockLimitsEnabled": "NONE",
    "EnableResearch": "false",
    "AutoSaveInMinutes": "0",
    "ExperimentalMode": "true",
    "EnableSunRotation": "false",
}


def prepare(
    template: Path,
    world: Path,
    players: dict[int, tuple[int, str]],
    pads: list[Pad],
    extra_grids: str = "",
    settings: dict | None = None,
    block_type_limits: dict | None = None,
) -> None:
    """A fresh copy of the template world (the game's Empty World) with the
    players (steam id -> (identity id, name)), the faction, the pads and more
    grids as sector object XML.
    block_type_limits fills the world's vanilla block type limits."""
    if world.exists():
        shutil.rmtree(world)
    shutil.copytree(template, world)
    (world / "SANDBOX_0_0_0_.sbsB5").unlink(missing_ok=True)
    (world / "Sandbox.sbcB5").unlink(missing_ok=True)

    sector = world / "SANDBOX_0_0_0_.sbs"
    text = sector.read_text(encoding="utf-8")
    text = _insert(text, "SectorObjects", "".join(p.xml() for p in pads) + extra_grids)
    sector.write_text(text, encoding="utf-8")

    values = {**BASE_SETTINGS, **(settings or {})}
    limits = ""
    if block_type_limits:
        limits = (
            "<dictionary>"
            + "".join(
                f"<item><Key>{k}</Key><Value>{v}</Value></item>"
                for k, v in block_type_limits.items()
            )
            + "</dictionary>"
        )
    for name in ("Sandbox.sbc", "Sandbox_config.sbc"):
        path = world / name
        text = path.read_text(encoding="utf-8")
        for key, value in values.items():
            text = _set(text, key, value)
        text = re.sub(
            r"<BlockTypeLimits>.*?</BlockTypeLimits>|<BlockTypeLimits\s*/>",
            f"<BlockTypeLimits>{limits}</BlockTypeLimits>",
            text,
            flags=re.S,
        )
        if name == "Sandbox.sbc":
            identities = "".join(_identity(i, n) for i, n in players.values())
            identities += _identity(PLAYER_C, "Charlie")
            text = _insert(text, "Identities", identities)
            text, count = re.subn(
                r"<AllPlayersData>(\s*)<dictionary>",
                lambda m: "<AllPlayersData><dictionary>"
                + "".join(_player(s, i, n) for s, (i, n) in players.items()),
                text,
                count=1,
            )
            assert count == 1, "AllPlayersData"
            faction = _faction(
                FACTION, FACTION_TAG, "Block Limit Testers", [PLAYER_C, PLAYER_A]
            )
            text, count = re.subn(
                r"<Factions>(\s*)<Factions>",
                lambda m: "<Factions><Factions>" + faction,
                text,
                count=1,
            )
            assert count == 1, "Factions"
            members = "".join(
                f'<item><Key xsi:type="xsd:long">{m}</Key>'
                f'<Value xsi:type="xsd:long">{FACTION}</Value></item>'
                for m in (PLAYER_C, PLAYER_A)
            )
            text, count = re.subn(
                r"<Players>(\s*)<dictionary>",
                lambda m: "<Players><dictionary>" + members,
                text,
                count=1,
            )
            assert count == 1, "Faction players"
        path.write_text(text, encoding="utf-8")


def blueprint(name: str, blocks: str, size: str = "Large") -> str:
    """A bp.sbc document of one grid"""
    grid_xml = (
        "<CubeGrid><SubtypeName /><EntityId>0</EntityId>"
        "<PersistentFlags>CastShadows InScene</PersistentFlags>"
        '<PositionAndOrientation><Position x="0" y="0" z="0" />'
        '<Forward x="0" y="0" z="-1" /><Up x="0" y="1" z="0" /></PositionAndOrientation>'
        f"<GridSizeEnum>{size}</GridSizeEnum><CubeBlocks>{blocks}</CubeBlocks>"
        f"<DisplayName>{name}</DisplayName></CubeGrid>"
    )
    return (
        '<?xml version="1.0"?>'
        '<Definitions xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><ShipBlueprints>'
        '<ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">'
        f'<Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="{name}" />'
        f"<CubeGrids>{grid_xml}</CubeGrids>"
        "</ShipBlueprint></ShipBlueprints></Definitions>"
    )
