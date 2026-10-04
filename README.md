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

Functionality is inspired by and reimplements the original Torch plugin
BlockLimiter by N1Ran: https://github.com/N1Ran/BlockLimiter
