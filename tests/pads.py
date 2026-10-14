"""Every pad of the test world. Each test builds on pads of its own, so the
tests don't see each other's blocks in their per-grid counts.

The pads lie in a row along -z, PAD_SPACING_M apart; each one stretches along
+x from x = 0.
"""

from __future__ import annotations

import world
from world import PLAYER_A, PLAYER_C, Pad, block

_pads: list[Pad] = []


def pad(name: str, **kwargs) -> Pad:
    p = Pad(name, 777_000_000_000 + 1000 * len(_pads), len(_pads), **kwargs)
    _pads.append(p)
    return p


# --- rules (test_rules.py) ---------------------------------------------------

PLAYER_A1 = pad("Player A1")
PLAYER_A2 = pad("Player A2")
PLAYER_B1 = pad("Player B1")
GRID_1 = pad("Grid 1")
GRID_2 = pad("Grid 2")
# Two batteries built by Charlie, a member of the test faction who never joins
FACTION = pad(
    "Faction",
    filled={
        0: ("BatteryBlock", "LargeBlockBatteryBlock", PLAYER_C),
        1: ("BatteryBlock", "LargeBlockBatteryBlock", PLAYER_C),
    },
)
FACTION_B = pad("Faction B")
SEARCH = pad("Search", sockets=12)
GROUP = pad("Group")
ZERO = pad("Zero")
SMALL_STATIC = pad("Small static", size="Small")
LARGE_STATIC = pad("Large static")
LARGE_SHIP = pad("Large ship", static=False)
SMALL_SHIP = pad("Small ship", size="Small", static=False)
EXCEPTED_GRID = pad("Excepted grid")
OTHER_GRID = pad("Other grid")
EXCEPTIONS = pad("Exceptions")
EXCEPTIONS_B = pad("Exceptions B")
REMOVAL = pad("Removal")
MESSAGE = pad("Message")
OWNERSHIP = pad("Ownership")
# Three cargo containers built by an NPC
NPC = pad(
    "NPC",
    filled={
        i: ("CargoContainer", "LargeBlockSmallContainer", world.NPC) for i in range(3)
    },
)

# --- commands (test_commands.py) ---------------------------------------------

COMMANDS = pad("Commands")

# --- cross-plugin API (test_api.py) ------------------------------------------

# Five timer blocks without a builder: what a plugin would ask CanAdd about
API_TEMPLATE = pad(
    "API template",
    filled={i: ("TimerBlock", "TimerBlockLarge", 0) for i in range(5)},
)
API_TARGET = pad("API target")

# --- grids (test_grids.py) ---------------------------------------------------

# Two decoys without a builder on a station whose merge block reaches out at
# +x, and a ship with two more decoys and a merge block touching it. The merge
# blocks face each other on their local x axes.
MERGE_STATION = pad(
    "Merge station",
    filled={0: ("Decoy", "LargeDecoy", 0), 1: ("Decoy", "LargeDecoy", 0)},
    extra=block(
        "MergeBlock",
        "LargeShipMergeBlock",
        (17, 1, 1),
        entity_id=0,
        extra="<Enabled>true</Enabled>",
    ),
)
MERGE_SHIP_ID = MERGE_STATION.entity_id + 500
MERGE_SHIP_XML = world.grid(
    "Merge ship",
    MERGE_SHIP_ID,
    block(
        "MergeBlock",
        "LargeShipMergeBlock",
        (0, 0, 0),
        entity_id=MERGE_SHIP_ID + 1,
        forward="Backward",
        extra="<Enabled>true</Enabled>",
    )
    + "".join(block("CubeBlock", "LargeBlockArmorBlock", (x, 0, 0)) for x in (1, 2, 3))
    + block("Decoy", "LargeDecoy", (2, 1, 0), entity_id=MERGE_SHIP_ID + 2)
    + block("Decoy", "LargeDecoy", (3, 1, 0), entity_id=MERGE_SHIP_ID + 3),
    tuple(a + 2.5 * b for a, b in zip(MERGE_STATION.position, (18, 1, 1))),
    static=False,
)


def _lattice(x0: int, sockets: int) -> list:
    cells = []
    for x in range(x0, x0 + 2 * sockets + 1):
        for y in range(3):
            for z in range(3):
                if (y, z) == (1, 1) and (x - x0) % 2 == 1:
                    continue
                cells.append((x, y, z))
    return cells


# Two three-socket lattices joined by one armor block at (7, 1, 1). Decoys
# without a builder fill sockets (1, 1, 1), (3, 1, 1), (9, 1, 1), (11, 1, 1);
# (5, 1, 1) and (13, 1, 1) are free.
SPLIT_BRIDGE = (7, 1, 1)
SPLIT_FREE = ((5, 1, 1), (13, 1, 1))
SPLIT = pad(
    "Split",
    bare=True,
    extra="".join(
        block("CubeBlock", "LargeBlockArmorBlock", c)
        for c in _lattice(0, 3) + [SPLIT_BRIDGE] + _lattice(8, 3)
    )
    + "".join(
        block("Decoy", "LargeDecoy", c, entity_id=777_900_000_000 + i)
        for i, c in enumerate([(1, 1, 1), (3, 1, 1), (9, 1, 1), (11, 1, 1)])
    ),
)

# A floor with a projector, a battery and a ship welder built by player A,
# switched off. The projection puts four heavy armor blocks on the floor around
# the cell in front of the welder's tip.
PROJECTION_CELLS = [(1, 1, 2), (2, 1, 2), (3, 1, 2), (2, 1, 1)]
PROJECTOR_CELL = (0, 1, 0)
WELDER_CELL = (2, 1, 3)


def _projection_xml() -> str:
    projected = block("Projector", "LargeProjector", PROJECTOR_CELL) + "".join(
        block("CubeBlock", "LargeHeavyBlockArmorBlock", c) for c in PROJECTION_CELLS
    )
    grids = (
        "<MyObjectBuilder_CubeGrid>"
        "<SubtypeName /><EntityId>0</EntityId>"
        "<PersistentFlags>CastShadows InScene</PersistentFlags>"
        '<PositionAndOrientation><Position x="0" y="0" z="0" />'
        '<Forward x="0" y="0" z="-1" /><Up x="0" y="1" z="0" /></PositionAndOrientation>'
        f"<GridSizeEnum>Large</GridSizeEnum><CubeBlocks>{projected}</CubeBlocks>"
        "<DisplayName>Projection</DisplayName></MyObjectBuilder_CubeGrid>"
    )
    return grids


PROJECTION = pad(
    "Projection",
    bare=True,
    extra="".join(
        block("CubeBlock", "LargeBlockArmorBlock", (x, 0, z))
        for x in range(6)
        for z in range(6)
    )
    + block(
        "Projector",
        "LargeProjector",
        PROJECTOR_CELL,
        built_by=PLAYER_A,
        entity_id=777_800_000_001,
        extra="<CustomName>Test Projector</CustomName><Enabled>true</Enabled>"
        f"<ProjectedGrids>{_projection_xml()}</ProjectedGrids>"
        "<KeepProjection>true</KeepProjection><ShowOnlyBuildable>false</ShowOnlyBuildable>",
    )
    + block(
        "BatteryBlock",
        "LargeBlockBatteryBlock",
        (0, 1, 5),
        entity_id=777_800_000_002,
        extra="<Enabled>true</Enabled><CurrentStoredPower>3</CurrentStoredPower>"
        "<ProducerEnabled>true</ProducerEnabled>",
    )
    + block(
        "ShipWelder",
        "LargeShipWelder",
        WELDER_CELL,
        built_by=PLAYER_A,
        entity_id=777_800_000_003,
        extra="<Enabled>false</Enabled>",
    ),
)
PROJECTOR_ID = 777_800_000_001
WELDER_ID = 777_800_000_003

# --- grid size limits (test_grid_size.py) ------------------------------------

SIZE_LARGE_STATIC = pad("Size large static", sockets=4)
SIZE_LARGE_SHIP = pad("Size large ship", sockets=4, static=False)
SIZE_SMALL_STATIC = pad("Size small static", sockets=4, size="Small")
SIZE_SMALL_SHIP = pad("Size small ship", sockets=4, size="Small", static=False)
SIZE_LARGE_STATIC_2 = pad("Size large static 2", sockets=4)

# --- vanilla limits and persistence ------------------------------------------

VANILLA = pad("Vanilla")
PERSIST = pad("Persist")
DISABLED = pad("Disabled")

ALL = list(_pads)
EXTRA_GRIDS = MERGE_SHIP_XML


# The players wait beside the row, where every pad is in streaming range
STANDING = (-20.0, 0.0, world.PAD_ROW_Z_M - 10.0 * len(ALL))
