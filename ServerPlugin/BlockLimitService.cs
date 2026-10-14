using System;
using System.Collections.Generic;
using System.Linq;
using Sandbox.Definitions;
using Sandbox.Game.Entities;
using Sandbox.Game.Entities.Cube;
using Sandbox.Game.World;
using Shared.Config;
using VRage.Game;

namespace ServerPlugin;

public sealed class BlockLimitService
{
    private readonly object sync = new object();
    private readonly Dictionary<long, int> smallGridsByPlayer = new Dictionary<long, int>();
    private readonly Dictionary<long, int> largeGridsByPlayer = new Dictionary<long, int>();
    private readonly Dictionary<LimitRuleKey, int> counts = new Dictionary<LimitRuleKey, int>();

    public bool Enabled => Plugin.Instance?.Config?.Enabled == true;

    public void Recalculate() => RecalculateWithout(null);

    /// <summary>Counts every block in the world except one, the block just built</summary>
    public void RecalculateWithout(MySlimBlock except)
    {
        lock (sync)
        {
            smallGridsByPlayer.Clear();
            largeGridsByPlayer.Clear();
            counts.Clear();

            foreach (MyCubeGrid grid in MyEntities.GetEntities().OfType<MyCubeGrid>())
            {
                if (!IsRealGrid(grid))
                    continue;

                CountGridForPlayers(grid);
                foreach (MySlimBlock block in grid.GetBlocks())
                {
                    if (block != except)
                        CountBlock(grid, block);
                }
            }
        }
    }

    public void Add(MySlimBlock block)
    {
        lock (sync)
            CountBlock(block.CubeGrid, block);
    }

    public bool CanAdd(List<MySlimBlock> blocks, long identityId, out List<MySlimBlock> deniedBlocks)
    {
        deniedBlocks = new List<MySlimBlock>();
        if (!Enabled || blocks == null || blocks.Count == 0)
            return true;

        lock (sync)
        {
            // Each allowed block holds its place in the player's and faction's
            // counts, so the blocks asked about count toward the limits together
            Recalculate();
            foreach (MySlimBlock block in blocks)
            {
                if (block == null || block.IsDestroyed || block.CubeGrid == null)
                    continue;

                if (!CanAddBlock(block.CubeGrid, block.BlockDefinition, identityId, 1, out _))
                    deniedBlocks.Add(block);
                else
                    Count(block.CubeGrid, block.BlockDefinition, identityId, false, countGrid: false);
            }

            Recalculate();
        }

        return deniedBlocks.Count == 0;
    }

    public bool CanAddBlock(MyCubeGrid grid, MyCubeBlockDefinition definition, long identityId, int amount, out string limitName)
    {
        limitName = null;
        if (!Enabled || definition == null)
            return true;

        IPluginConfig config = Plugin.Instance.Config;

        if (grid != null && IsGridSizeViolation(grid, config))
        {
            limitName = "Grid size";
            return false;
        }

        MyFaction faction = identityId > 0 ? MySession.Static.Factions.GetPlayerFaction(identityId) : null;
        bool npc = IsNpc(identityId);
        foreach (LimitRule rule in AllRules(config))
        {
            if (!RuleMatches(rule, definition) || IsExcepted(rule, identityId) || IsExcepted(rule, grid?.EntityId ?? 0) ||
                IsExcepted(rule, faction?.FactionId ?? 0) || (rule.IgnoreNpcs && npc))
                continue;

            if (!GridMatches(rule, grid))
                continue;

            string name = string.IsNullOrWhiteSpace(rule.Name) ? string.Join(",", rule.BlockList ?? new List<string>()) : rule.Name;
            if (rule.Limit == 0 && (rule.LimitPlayers || rule.LimitFaction || rule.LimitGrids))
            {
                limitName = name;
                return false;
            }

            if (rule.LimitGrids && grid != null &&
                CountFor(rule, LimitScope.Grid, grid.EntityId) + amount > rule.Limit)
            {
                limitName = name;
                return false;
            }

            if (rule.LimitPlayers && identityId > 0 &&
                CountFor(rule, LimitScope.Player, identityId) + amount > rule.Limit)
            {
                limitName = name;
                return false;
            }

            if (rule.LimitFaction && faction != null &&
                CountFor(rule, LimitScope.Faction, faction.FactionId) + amount > rule.Limit)
            {
                limitName = name;
                return false;
            }
        }

        return true;
    }

    public string BuildLimitReport(long identityId)
    {
        IPluginConfig config = Plugin.Instance.Config;
        List<string> lines = new List<string>();

        foreach (LimitRule rule in AllRules(config))
        {
            if (rule.Limit <= 0)
                continue;

            string name = string.IsNullOrWhiteSpace(rule.Name) ? string.Join(",", rule.BlockList ?? new List<string>()) : rule.Name;
            if (rule.LimitPlayers)
                lines.Add($"{name}: player {CountFor(rule, LimitScope.Player, identityId)}/{rule.Limit}");

            MyFaction faction = MySession.Static.Factions.GetPlayerFaction(identityId);
            if (rule.LimitFaction && faction != null)
                lines.Add($"{name}: faction {CountFor(rule, LimitScope.Faction, faction.FactionId)}/{rule.Limit}");
        }

        return lines.Count == 0 ? "You have no block within set limit" : string.Join(Environment.NewLine, lines);
    }

    public string BuildLimitsList()
    {
        IPluginConfig config = Plugin.Instance.Config;
        List<string> lines = new List<string>();

        if (config.MaxBlockSizeShips > 0)
            lines.Add($"Ship Size Limit = {config.MaxBlockSizeShips} blocks");
        if (config.MaxBlockSizeStations > 0)
            lines.Add($"Station Size Limit = {config.MaxBlockSizeStations} blocks");
        if (config.MaxBlocksLargeGrid > 0)
            lines.Add($"Large Grid Size Limit = {config.MaxBlocksLargeGrid} blocks");
        if (config.MaxBlocksSmallGrid > 0)
            lines.Add($"Small Grid Size Limit = {config.MaxBlocksSmallGrid} blocks");
        if (config.MaxSmallGridsPerPlayer > 0)
            lines.Add($"Small Grids Limit = {config.MaxSmallGridsPerPlayer} per player");
        if (config.MaxLargeGridsPerPlayer > 0)
            lines.Add($"Large Grids Limit = {config.MaxLargeGridsPerPlayer} per player");

        foreach (LimitRule rule in AllRules(config).Where(rule => rule.BlockList?.Count > 0))
        {
            string name = string.IsNullOrWhiteSpace(rule.Name) ? "No Name" : rule.Name;
            lines.Add("");
            lines.Add(name);
            lines.Add("Blocks: " + string.Join(", ", rule.BlockList));
            lines.Add($"GridType: {rule.GridType}");
            lines.Add($"Limit: {rule.Limit}");
            lines.Add($"PlayerLimit: {rule.LimitPlayers}");
            lines.Add($"FactionLimit: {rule.LimitFaction}");
            lines.Add($"GridLimit: {rule.LimitGrids}");
        }

        return lines.Count == 0 ? "No block limits found" : string.Join(Environment.NewLine, lines);
    }

    private void CountGridForPlayers(MyCubeGrid grid)
    {
        HashSet<long> owners = new HashSet<long>(grid.BigOwners);
        if (owners.Count == 0)
        {
            foreach (long owner in grid.GetBlocks().Select(block => block.BuiltBy).Where(id => id != 0))
                owners.Add(owner);
        }

        foreach (long owner in owners)
        {
            Dictionary<long, int> target = grid.GridSizeEnum == MyCubeSize.Small ? smallGridsByPlayer : largeGridsByPlayer;
            target[owner] = target.TryGetValue(owner, out int count) ? count + 1 : 1;
        }
    }

    private void CountBlock(MyCubeGrid grid, MySlimBlock block)
    {
        if (block == null || block.IsDestroyed || block.BlockDefinition == null)
            return;

        Count(grid, block.BlockDefinition, block.BuiltBy, IsNpc(block.BuiltBy) || IsNpc(block.OwnerId));
    }

    private void Count(MyCubeGrid grid, MyCubeBlockDefinition definition, long builtBy, bool npc, bool countGrid = true)
    {
        MyFaction faction = builtBy != 0 ? MySession.Static.Factions.GetPlayerFaction(builtBy) : null;
        foreach (LimitRule rule in AllRules(Plugin.Instance.Config))
        {
            if (!RuleMatches(rule, definition) || !GridMatches(rule, grid) || (rule.IgnoreNpcs && npc))
                continue;

            if (countGrid)
                AddCount(rule, LimitScope.Grid, grid.EntityId, 1);

            AddCount(rule, LimitScope.Player, builtBy, 1);

            if (faction != null)
                AddCount(rule, LimitScope.Faction, faction.FactionId, 1);
        }
    }

    private static bool IsNpc(long identityId)
        => identityId != 0 && MySession.Static.Players.IdentityIsNpc(identityId);

    private static IEnumerable<LimitRule> AllRules(IPluginConfig config)
    {
        foreach (LimitRule rule in config.Limits ?? new List<LimitRule>())
            yield return Normalize(rule);

        if (!config.UseVanillaLimits || MySession.Static.BlockLimitsEnabled == MyBlockLimitsEnabledEnum.NONE)
            yield break;

        bool faction = MySession.Static.BlockLimitsEnabled == MyBlockLimitsEnabledEnum.PER_FACTION;
        bool player = MySession.Static.BlockLimitsEnabled == MyBlockLimitsEnabledEnum.PER_PLAYER;
        foreach (KeyValuePair<string, short> item in MySession.Static.BlockTypeLimits)
        {
            yield return new LimitRule
            {
                Name = "Vanilla " + item.Key,
                BlockList = new List<string> { item.Key },
                SearchType = BlockListSearchType.BlockPairName,
                Limit = item.Value,
                LimitFaction = faction,
                LimitPlayers = player,
                LimitGrids = false,
                GridType = GridType.AllGrids,
                Exceptions = new List<string>(),
            };
        }
    }

    private static LimitRule Normalize(LimitRule rule)
    {
        rule.BlockList ??= new List<string>();
        rule.Exceptions ??= new List<string>();
        return rule;
    }

    private static bool RuleMatches(LimitRule rule, MyCubeBlockDefinition definition)
    {
        if (rule.BlockList == null || rule.BlockList.Count == 0)
            return false;

        string typeId = definition.Id.TypeId.ToString().Substring(16);
        string subtype = definition.Id.SubtypeName;
        string pair = definition.BlockPairName;

        foreach (string raw in rule.BlockList)
        {
            if (string.IsNullOrWhiteSpace(raw))
                continue;

            string item = raw.Trim();
            if (rule.SearchType is BlockListSearchType.Auto or BlockListSearchType.BlockPairName)
            {
                if (string.Equals(item, pair, StringComparison.OrdinalIgnoreCase))
                    return true;
            }

            if (rule.SearchType is BlockListSearchType.Auto or BlockListSearchType.TypeId)
            {
                if (string.Equals(item, typeId, StringComparison.OrdinalIgnoreCase))
                    return true;
            }

            if (rule.SearchType is BlockListSearchType.Auto or BlockListSearchType.SubtypeId)
            {
                if (string.Equals(item, subtype, StringComparison.OrdinalIgnoreCase))
                    return true;
            }
        }

        return false;
    }

    private static bool GridMatches(LimitRule rule, MyCubeGrid grid)
    {
        if (grid == null)
            return true;

        return rule.GridType switch
        {
            GridType.AllGrids => true,
            GridType.SmallGrid => grid.GridSizeEnum == MyCubeSize.Small,
            GridType.LargeGrid => grid.GridSizeEnum == MyCubeSize.Large,
            GridType.Static => grid.IsStatic,
            GridType.Ship => !grid.IsStatic,
            _ => true,
        };
    }

    private static bool IsGridSizeViolation(MyCubeGrid grid, IPluginConfig config)
    {
        if (config.MaxBlocksSmallGrid > 0 && grid.GridSizeEnum == MyCubeSize.Small && grid.BlocksCount > config.MaxBlocksSmallGrid)
            return true;

        if (config.MaxBlocksLargeGrid > 0 && grid.GridSizeEnum == MyCubeSize.Large && grid.BlocksCount > config.MaxBlocksLargeGrid)
            return true;

        if (config.MaxBlockSizeShips > 0 && !grid.IsStatic && grid.BlocksCount > config.MaxBlockSizeShips)
            return true;

        if (config.MaxBlockSizeStations > 0 && grid.IsStatic && grid.BlocksCount > config.MaxBlockSizeStations)
            return true;

        return false;
    }

    private static bool IsExcepted(LimitRule rule, long id)
        => id != 0 && rule.Exceptions != null && rule.Exceptions.Any(item => string.Equals(item, id.ToString(), StringComparison.OrdinalIgnoreCase));

    private void AddCount(LimitRule rule, LimitScope scope, long id, int amount)
    {
        if (id == 0)
            return;

        LimitRuleKey key = new LimitRuleKey(rule.Name, string.Join("|", rule.BlockList ?? new List<string>()), scope, id);
        counts[key] = counts.TryGetValue(key, out int count) ? count + amount : amount;
    }

    private int CountFor(LimitRule rule, LimitScope scope, long id)
    {
        if (id == 0)
            return 0;

        LimitRuleKey key = new LimitRuleKey(rule.Name, string.Join("|", rule.BlockList ?? new List<string>()), scope, id);
        return counts.TryGetValue(key, out int count) ? count : 0;
    }

    private static bool IsRealGrid(MyCubeGrid grid)
        => grid != null && !grid.MarkedForClose && !grid.MarkedAsTrash && grid.Projector == null;

    private enum LimitScope
    {
        Player,
        Faction,
        Grid,
    }

    private readonly struct LimitRuleKey : IEquatable<LimitRuleKey>
    {
        private readonly string name;
        private readonly string blocks;
        private readonly LimitScope scope;
        private readonly long id;

        public LimitRuleKey(string name, string blocks, LimitScope scope, long id)
        {
            this.name = name ?? "";
            this.blocks = blocks ?? "";
            this.scope = scope;
            this.id = id;
        }

        public bool Equals(LimitRuleKey other)
            => name == other.name && blocks == other.blocks && scope == other.scope && id == other.id;

        public override bool Equals(object obj)
            => obj is LimitRuleKey other && Equals(other);

        public override int GetHashCode()
        {
            unchecked
            {
                int hashCode = name.GetHashCode();
                hashCode = (hashCode * 397) ^ blocks.GetHashCode();
                hashCode = (hashCode * 397) ^ (int)scope;
                hashCode = (hashCode * 397) ^ id.GetHashCode();
                return hashCode;
            }
        }
    }
}
