"""A running test session: the server with its world, and the players on the
clients. Also usable from the command line while iterating::

    uv run python tests/session.py start     # server and both clients
    uv run python tests/session.py stop
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pads  # noqa: E402
import rig  # noqa: E402
import world  # noqa: E402
from rig import Rule  # noqa: E402

SERVER = rig.Server()
CLIENT_A = rig.Client(1, "Alpha")
CLIENT_B = rig.Client(2, "Bravo")
CLIENTS = (CLIENT_A, CLIENT_B)

# Wait after a placement before deciding the block stays: the server removes a
# block over a limit in the same frame it builds it, the client hears of the
# removal on the next replication update
SETTLE_S = 1.5
REPLY_TIMEOUT_S = 20.0
# A reply is complete once no more of it came for this long
QUIET_S = 1.0
PLACE_TIMEOUT_S = 15.0
# Replies come from the command's root, errors from its title. The plugin's
# denial messages share the title, so a command during a denial may still
# catch one.
ROOT_TITLES = {"blocklimit": "BlockLimits", "blprobe": "BlockLimitsProbe"}


# In force from the start: the merge grids merge as the world loads
DECOYS = Rule("Grid decoys", ["Decoy"], 3, grids=True)

# Vanilla block limits per player, with one block type limit
WORLD_SETTINGS = {
    "BlockLimitsEnabled": "PER_PLAYER",
    "TotalPCU": "4000000",
    "MaxBlocksPerPlayer": "0",
}
VANILLA_LIMITS = {"Collector": 3}


class Player:
    """A client's player: chat commands and block placement through Remote"""

    def __init__(self, client: rig.Client, identity_id: int):
        self.client = client
        self.identity_id = identity_id
        self.api = client.api()

    # --- chat ----------------------------------------------------------------

    def _chat(self) -> list[tuple[str, str, str]]:
        hud = self.api.get_chat_messages().get("hud") or []
        return [(m.get("sender"), m.get("text"), m.get("timestamp")) for m in hud]

    def chat_since(self, before: set) -> list[tuple[str, str]]:
        return [(s, t) for s, t, ts in self._chat() if (s, t, ts) not in before]

    def mark(self) -> set:
        return set(self._chat())

    def command(self, text: str, timeout: float = REPLY_TIMEOUT_S) -> str:
        """Sends a chat command and returns its reply. A reply of several
        messages comes back as their lines."""
        prefix = text.split()[0][1:]
        senders = {prefix, ROOT_TITLES.get(prefix)}
        before = self.mark()
        self.api.send_chat(text)
        deadline = time.monotonic() + timeout
        replies, last = [], None
        while time.monotonic() < deadline:
            new = [t for s, t in self.chat_since(before) if s in senders]
            if new != replies:
                replies, last = new, time.monotonic()
            elif replies and time.monotonic() - last > QUIET_S:
                return "\n".join(replies)
            time.sleep(0.3)
        if replies:
            return "\n".join(replies)
        raise TimeoutError(f"No reply to {text!r}")

    def probe(self, *args) -> str:
        return self.command("!blprobe " + " ".join(str(a) for a in args))

    def report(self, identity_id: int | None = None) -> str:
        """The plugin's limit report of an identity, through the probe"""
        reply = self.probe("report", identity_id or self.identity_id)
        return reply.removeprefix("Probe report: ")

    def server_blocks(self, grid_id: int) -> dict[str, int]:
        """The grid's blocks on the server, by subtype, plus 'total'"""
        reply = self.probe("blocks", grid_id).removeprefix("Probe blocks: ")
        if reply == "no grid":
            return {}
        return {k: int(v) for k, v in (p.split("=") for p in reply.split())}

    # --- building ------------------------------------------------------------

    def place(self, grid_id: int, cell, subtype: str) -> tuple[bool, list[str]]:
        """Places a block the way the cube builder does. Returns whether it
        stays once the server had its say, and the chat lines that came
        meanwhile. A block over a limit comes with the denial message, and it
        may never show up on the client at all."""
        before = self.mark()
        result = self.api.character_build_block(grid_id, tuple(cell), subtype)
        assert result.get("sent"), result
        deadline = time.monotonic() + PLACE_TIMEOUT_S
        while time.monotonic() < deadline:
            chat = [t for _, t in self.chat_since(before)]
            if chat:
                # The denial; the block goes away if it came at all
                time.sleep(SETTLE_S)
                return self.has_block(grid_id, cell), [
                    t for _, t in self.chat_since(before)
                ]
            if self.has_block(grid_id, cell):
                time.sleep(SETTLE_S)
                return self.has_block(grid_id, cell), [
                    t for _, t in self.chat_since(before)
                ]
            time.sleep(0.3)
        raise TimeoutError(f"{subtype} at {cell}: no block and no denial: {result}")

    def free_socket(self, pad: world.Pad):
        """The first socket of the pad without a block"""
        taken = {tuple(c["cellMin"]) for c in self.cubes(pad.entity_id)}
        return next(
            pad.socket_cell(i)
            for i in range(pad.sockets)
            if pad.socket_cell(i) not in taken
        )

    def grid_of(self, fat_entity_id: int) -> tuple[int, list[int]] | None:
        """The grid holding a functional block, and the block's cell"""
        for grid in self.api.list_grids():
            for cube in self.cubes(grid["entityId"]):
                if cube.get("fatEntityId") == fat_entity_id:
                    return grid["entityId"], cube["cellMin"]
        return None

    def cubes(self, grid_id: int) -> list[dict]:
        """Every block of a grid as this client sees it"""
        cubes = []
        while True:
            page = self.api.list_cubes(grid_id, offset=len(cubes), limit=500)
            cubes += page["cubes"]
            if not page["cubes"] or len(cubes) >= page["total"]:
                return cubes

    def has_block(self, grid_id: int, cell) -> bool:
        return any(c["cellMin"] == list(cell) for c in self.cubes(grid_id))

    def remove(self, grid_id: int, cell, timeout: float = 15.0) -> None:
        """The creative remove request, carried out by the server"""
        self.api.character_grid_event(grid_id, tuple(cell), "raze")
        deadline = time.monotonic() + timeout
        while self.has_block(grid_id, cell):
            assert time.monotonic() < deadline, f"{cell} was not removed"
            time.sleep(0.3)

    def stand_by(self, pad: world.Pad | None = None) -> None:
        """Moves beside the row of pads, or next to one. Building needs no
        proximity, but the server takes terminal changes only from a player
        near the block."""
        if pad is None:
            self.api.character_teleport(*pads.STANDING)
        else:
            x, y, z = pad.position
            self.api.character_teleport(x - 4.0, y + 2.0, z + 2.0)
        time.sleep(2)


# ---------------------------------------------------------------------------
# Start and stop
# ---------------------------------------------------------------------------


def prepare() -> None:
    """A fresh world with every pad, and the server's configs"""
    world.prepare(
        rig.EMPTY_WORLD,
        SERVER.world,
        {
            CLIENT_A.steam_id: (world.PLAYER_A, CLIENT_A.name),
            CLIENT_B.steam_id: (world.PLAYER_B, CLIENT_B.name),
        },
        pads.ALL,
        pads.EXTRA_GRIDS,
        WORLD_SETTINGS,
        VANILLA_LIMITS,
    )
    SERVER.prepare([CLIENT_A.steam_id])
    SERVER.write_plugin_config(rig.plugin_config([DECOYS]))


def join(client: rig.Client) -> rig.RemoteAPI:
    """Launches a client, which connects on its own, and waits for its
    character"""
    client.launch(SERVER.port)
    api = client.wait_api()
    rig.wait_world(api)
    rig.ensure_character(api)
    rig.focus_gameplay(api)
    api.character_teleport(*pads.STANDING)
    return api


def join_all(clients=CLIENTS) -> None:
    """Joins the clients in parallel"""
    errors = []

    def run(client):
        try:
            join(client)
        except Exception as error:  # noqa: BLE001 -- reported below
            errors.append((client.name, error))

    threads = [threading.Thread(target=run, args=(c,)) for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise RuntimeError(f"Joining failed: {errors}")


def stop_all() -> None:
    for client in CLIENTS:
        client.stop()
    SERVER.stop()


def players() -> tuple[Player, Player]:
    return Player(CLIENT_A, world.PLAYER_A), Player(CLIENT_B, world.PLAYER_B)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "start":
        stop_all()
        prepare()
        SERVER.start()
        join_all()
        print(
            f"Joined. Remote ports {CLIENT_A.port}, {CLIENT_B.port}; server log {SERVER.log}"
        )
    elif command == "stop":
        stop_all()
    else:
        sys.exit(__doc__)
