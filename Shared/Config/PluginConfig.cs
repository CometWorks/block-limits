using System.Collections.Generic;
using PluginSdk.Config;

namespace Shared.Config;

[Tab("main", caption: "Main")]
[Tab("limits", caption: "Limits")]
[Section("main-core", "main", "Core")]
[Section("main-grid", "main", "Grid Counts")]
[Section("limit-rules", "limits", "Rules")]
public class PluginConfig : PluginSdk.Config.PluginConfig, IPluginConfig
{
    [BoolOption("Enable BlockLimits enforcement and API.", Parent = "main-core")]
    public bool Enabled { get; set => SetField(ref field, value); } = true;

    [BoolOption("Import vanilla block type limits into BlockLimits checks.", Parent = "main-core")]
    public bool UseVanillaLimits { get; set => SetField(ref field, value); }

    [StringOption(description: "Message returned when a block limit is reached. {BL}=block names, {BC}=count, {LIMIT}=limit name.", Parent = "main-core")]
    public string DenyMessage { get; set => SetField(ref field, value); } = "Limit reached: {BC} blocks denied. BlockNames: {BL}";

    [IntOption(0, int.MaxValue, "Maximum blocks on small grids. 0 disables this check.", Parent = "main-grid")]
    public int MaxBlocksSmallGrid { get; set => SetField(ref field, value); }

    [IntOption(0, int.MaxValue, "Maximum blocks on large grids. 0 disables this check.", Parent = "main-grid")]
    public int MaxBlocksLargeGrid { get; set => SetField(ref field, value); }

    [IntOption(0, int.MaxValue, "Maximum blocks on dynamic grids. 0 disables this check.", Parent = "main-grid")]
    public int MaxBlockSizeShips { get; set => SetField(ref field, value); }

    [IntOption(0, int.MaxValue, "Maximum blocks on static grids. 0 disables this check.", Parent = "main-grid")]
    public int MaxBlockSizeStations { get; set => SetField(ref field, value); }

    [IntOption(0, int.MaxValue, "Maximum small grids per player, checked when the player starts or pastes a grid. A grid counts for its owners, or for its main builders while it has no owner; subgrids don't count. 0 disables this check.", Parent = "main-grid")]
    public int MaxSmallGridsPerPlayer { get; set => SetField(ref field, value); }

    [IntOption(0, int.MaxValue, "Maximum large grids per player, checked when the player starts or pastes a grid. A grid counts for its owners, or for its main builders while it has no owner; subgrids don't count. 0 disables this check.", Parent = "main-grid")]
    public int MaxLargeGridsPerPlayer { get; set => SetField(ref field, value); }

    [ListOption(description: "Per-block limit rules.", Parent = "limit-rules")]
    public List<LimitRule> Limits { get; set => SetField(ref field, value); } = new List<LimitRule>();
}

public struct LimitRule
{
    [StructMember("Friendly name shown in reports.")]
    [StructCaption]
    public string Name { get; set; }

    [StructMember("Block type id, subtype id, or block pair name. Empty matches nothing.")]
    public List<string> BlockList { get; set; }

    [StructMember("How block names are matched.")]
    public BlockListSearchType SearchType { get; set; }

    [StructMember("Allowed count.")]
    public int Limit { get; set; }

    [StructMember("Apply this rule to player built-by counts.")]
    public bool LimitPlayers { get; set; }

    [StructMember("Apply this rule to faction counts.")]
    public bool LimitFaction { get; set; }

    [StructMember("Apply this rule to individual grids.")]
    public bool LimitGrids { get; set; }

    [StructMember("Grid type filter.")]
    public GridType GridType { get; set; }

    [StructMember("Player, faction, or grid identity/entity ids ignored by this rule.")]
    public List<string> Exceptions { get; set; }

    [StructMember("Leave blocks built or owned by NPCs out of the counts, and NPCs out of the limit.")]
    public bool IgnoreNpcs { get; set; }
}

public enum BlockListSearchType
{
    Auto,
    TypeId,
    SubtypeId,
    BlockPairName,
}

public enum GridType
{
    AllGrids,
    SmallGrid,
    LargeGrid,
    Static,
    Ship,
}
