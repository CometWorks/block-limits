"""One session for the whole run: the server with the test world, player A on
client 1 (an administrator) and player B on client 2 (no rights).

Every test sets the plugin config it needs through the probe (`configure`), so
the server keeps running between tests. Only test_restart.py restarts it.

BL_ATTACH=1 reuses a running server and clients (session.py start), BL_KEEP=1
leaves them running after the run.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rig  # noqa: E402
import session  # noqa: E402
from session import CLIENTS, SERVER  # noqa: E402

ATTACH = os.environ.get("BL_ATTACH") == "1"
KEEP = os.environ.get("BL_KEEP") == "1"


class Game:
    def __init__(self):
        self.a, self.b = session.players()
        self.server = SERVER

    def configure(self, rules=(), **options) -> None:
        """Puts this config into the running plugin, and counts again"""
        SERVER.write_plugin_config(rig.plugin_config(rules, **options))
        assert self.a.probe("reload") == "Probe: config reloaded"

    def rejoin(self) -> None:
        """After a server restart"""
        session.join_all()
        self.a, self.b = session.players()


@pytest.fixture(scope="session")
def game():
    attach = ATTACH and SERVER.pid() and all(c.pid() for c in CLIENTS)
    try:
        if not attach:
            session.stop_all()
            session.prepare()
            SERVER.start()
            session.join_all()
        yield Game()
    finally:
        if not KEEP:
            session.stop_all()


def pytest_collection_modifyitems(items):
    """The restart tests go last: a failed restart would take the session
    down with it"""
    items.sort(key=lambda item: item.module.__name__ == "test_restart")


def socket(i: int):
    return session.world.Pad.socket_cell(i)
