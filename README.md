# BlockLimits

BlockLimits is a Space Engineers dedicated server plugin for Magnetar. It is a PluginSDK rewrite of the old Torch BlockLimiter plugin.

This port provides:

- Magnetar/PluginSDK server configuration
- Block limit rules by player, faction, and grid
- Optional vanilla block type limit import
- Grid size limits
- `!blocklimit` server commands
- Cross-plugin API: `BlockLimits.PluginApi.Limits.CanAdd(...)`

Nexus synchronization from the Torch plugin is intentionally not included.

## Commands

- `!blocklimit enable [true|false]`
- `!blocklimit update`
- `!blocklimit mylimit`
- `!blocklimit limits`
- `!blocklimit pairnames [blockType]`

## Build

Build with:

```bash
dotnet build BlockLimits.sln -c Release
```

The plugin version lives in `Version.Build.props`. Bump the version there.

`Directory.Build.props` auto-detects the Dedicated Server (`Dedicated64`) and the Magnetar
installation holding `PluginSdk.dll` (`Magnetar`). To override them, put your local paths into
`Directory.Build.props.user`, which is not committed. Running `setup.py` writes that file for you.

## Development

Load the working copy through a Magnetar development folder: start Magnetar with `-sources` and
add the repository with the Sources button. Magnetar then compiles the plugin from source.

Builds deploy nothing by default. To copy the build into Magnetar's `Local` plugin folder, set
`MagnetarData` to the Magnetar config folder (the one holding `Local`, `Sources` and `Profiles`)
in `Directory.Build.props.user`, or pass it to a single build:

```bash
dotnet build BlockLimits.sln -p:MagnetarData=$HOME/.config/Magnetar/Magnetar
```

## Tests

`tests/` holds an in-game test suite. It starts a Magnetar server with this working copy
of the plugin, joins it with two headless game clients and drives them through the
[Remote plugin](https://github.com/CometWorks/remote): player A is an administrator,
player B has no rights. The players place blocks the way the cube builder does, run the
chat commands and read the replies, and the tests check the results on the server.
It runs on Linux only.

What it covers:

- Rules by player, faction and grid, matched by type, subtype, pair name or any of
  them, with block groups, grid types, exceptions (player, grid, faction), NPC blocks,
  a zero limit and the denial message (`test_rules.py`)
- The grid size limits (`test_grid_size.py`)
- Grids merging, splitting, pasted and welded from a projection (`test_grids.py`)
- The `!blocklimit` commands, their permissions and bad input (`test_commands.py`)
- `BlockLimits.PluginApi.Limits.CanAdd` (`test_api.py`)
- Importing the vanilla block type limits (`test_vanilla.py`)
- The config and the counts across a server restart, and a broken config file
  (`test_restart.py`)

Things the plugin doesn't do yet are strict xfails, so a fix shows up as an unexpected
pass: limits on pasted and merged grids, and the grid count limits per player.

The test world is the game's Empty World with the test players, a faction and a row of
pads to build on, written fresh for every run. `tests/probe` is a test-only server
plugin the server loads next to Block Limits: it calls the cross-plugin API, reads the
plugin's counts and puts a new config into the running plugin, so the tests don't need
a restart for each config.

### Running

You need the Space Engineers client and Dedicated Server from Steam, Magnetar and
Pulsar installed, [uv](https://docs.astral.sh/uv/), and working copies of
[Remote](https://github.com/CometWorks/remote) and
[DirectTransport](https://github.com/CometWorks/direct-transport). The rig takes the
ports, client ids and folders from a test slot of the `se` workspace
(`notes/parallel-test-work`), and waits for free memory before each process it starts.

```bash
uv run pytest
```

The server and the clients download their hub plugins from GitHub. Where GitHub's API
rate limits you, export `PULSAR_GITHUB_TOKEN`; Pulsar and Magnetar read it.

A full run takes about 25 minutes, most of it the server and clients starting.
`tests/rig.py` lists the environment variables that point the rig at other
installations and working copies. To keep the server and clients running between
runs while you work on a test:

```bash
uv run python tests/session.py start
BL_ATTACH=1 BL_KEEP=1 uv run pytest tests/test_rules.py
uv run python tests/session.py stop
```

Functionality is inspired by and reimplements the original Torch plugin
BlockLimiter by N1Ran: https://github.com/N1Ran/BlockLimiter
