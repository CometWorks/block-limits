using System;
using System.Collections.Generic;
using System.Linq;
using Sandbox.Definitions;
using Sandbox.Game.Entities;
using Sandbox.Game.Entities.Cube;
using Sandbox.Game.World;
using Shared.Config;
using VRage.Game;
using VRage.ObjectBuilders;

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

                if (IsMainGridOfGroup(grid))
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

                GridInfo grid = GridInfo.Of(block.CubeGrid);
                if (!CanAddBlock(grid, block.BlockDefinition, identityId, 1, out _))
                    deniedBlocks.Add(block);
                else
                    Count(grid, block.BlockDefinition, identityId, false, countGrid: false);
            }

            Recalculate();
        }

        return deniedBlocks.Count == 0;
    }

    /// <summary>
    /// Whether the blocks of a paste may come into the world: new grids, or blocks pasted
    /// onto the target grid. The whole paste counts toward the limits together, the way
    /// the blocks will be counted once pasted.
    /// </summary>
    public bool CanPaste(List<MyObjectBuilder_CubeGrid> grids, MyCubeGrid target, out Denial denial)
    {
        denial = null;
        if (!Enabled || grids == null || grids.Count == 0)
            return true;

        IPluginConfig config = Plugin.Instance.Config;
        lock (sync)
        {
            Recalculate();
            try
            {
                if (target == null && !CanAddPastedGrid(grids, config, out denial))
                    return false;

                int pasted = grids.Sum(g => g.CubeBlocks?.Count ?? 0);
                string limitName = null;
                List<string> denied = new List<string>();
                for (int i = 0; i < grids.Count; i++)
                {
                    // A new grid has no entity id yet, it counts under a made up one
                    GridInfo grid = target != null
                        ? new GridInfo(target.EntityId, target.GridSizeEnum, target.IsStatic, target.BlocksCount + pasted)
                        : new GridInfo(-1 - i, grids[i].GridSizeEnum, grids[i].IsStatic, grids[i].CubeBlocks?.Count ?? 0);

                    foreach (MyObjectBuilder_CubeBlock block in grids[i].CubeBlocks ?? new List<MyObjectBuilder_CubeBlock>())
                    {
                        if (!MyDefinitionManager.Static.TryGetCubeBlockDefinition(new MyDefinitionId(block.TypeId, block.SubtypeId), out MyCubeBlockDefinition definition))
                            continue;

                        long identityId = block.BuiltBy != 0 ? block.BuiltBy : block.Owner;
                        if (CanAddBlock(grid, definition, identityId, 1, out string name))
                        {
                            Count(grid, definition, identityId, IsNpc(block.BuiltBy) || IsNpc(block.Owner));
                            continue;
                        }

                        limitName ??= name;
                        denied.Add(BlockName(definition));
                    }
                }

                if (denied.Count == 0)
                    return true;

                denial = new Denial(limitName, denied.Count, denied.Distinct());
                return false;
            }
            finally
            {
                // Drops what the pasted blocks added
                Recalculate();
            }
        }
    }

    /// <summary>
    /// Whether two grids may merge. A merge is refused when it adds blocks to a grid that
    /// ends up over a grid limit; player and faction counts don't change on a merge.
    /// </summary>
    public bool CanMerge(MyCubeGrid grid, MyCubeGrid other, out Denial denial)
    {
        denial = null;
        if (!Enabled || grid == null || other == null)
            return true;

        IPluginConfig config = Plugin.Instance.Config;
        GridInfo merged = new GridInfo(grid.EntityId, grid.GridSizeEnum, grid.IsStatic || other.IsStatic, grid.BlocksCount + other.BlocksCount);
        if (IsGridSizeViolation(merged, config))
        {
            MyCubeGrid smaller = grid.BlocksCount < other.BlocksCount ? grid : other;
            denial = new Denial("Grid size", smaller.BlocksCount, new[] { smaller.DisplayName });
            return false;
        }

        foreach (LimitRule rule in AllRules(config))
        {
            if (!rule.LimitGrids || IsExcepted(rule, grid.EntityId) || IsExcepted(rule, other.EntityId) || !GridMatches(rule, merged))
                continue;

            List<MySlimBlock> mine = MatchingBlocks(rule, grid);
            List<MySlimBlock> theirs = MatchingBlocks(rule, other);
            int total = mine.Count + theirs.Count;
            if (mine.Count == 0 || theirs.Count == 0 || total <= rule.Limit)
                continue;

            IEnumerable<string> names = mine.Concat(theirs).Select(block => BlockName(block.BlockDefinition)).Distinct();
            denial = new Denial(RuleName(rule), total - rule.Limit, names);
            return false;
        }

        return true;
    }

    /// <summary>Whether the player may start one more grid of this size</summary>
    public bool CanAddGrid(long identityId, MyCubeSize size, out string limitName)
    {
        limitName = null;
        if (!Enabled || identityId == 0)
            return true;

        lock (sync)
        {
            Recalculate();
            return !IsOverGridCount(identityId, size, Plugin.Instance.Config, out limitName);
        }
    }

    public bool CanAddBlock(MyCubeGrid grid, MyCubeBlockDefinition definition, long identityId, int amount, out string limitName)
        => CanAddBlock(grid == null ? (GridInfo?)null : GridInfo.Of(grid), definition, identityId, amount, out limitName);

    private bool CanAddBlock(GridInfo? grid, MyCubeBlockDefinition definition, long identityId, int amount, out string limitName)
    {
        limitName = null;
        if (!Enabled || definition == null)
            return true;

        IPluginConfig config = Plugin.Instance.Config;

        if (grid != null && IsGridSizeViolation(grid.Value, config))
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

            string name = RuleName(rule);
            if (rule.Limit == 0 && (rule.LimitPlayers || rule.LimitFaction || rule.LimitGrids))
            {
                limitName = name;
                return false;
            }

            if (rule.LimitGrids && grid != null &&
                CountFor(rule, LimitScope.Grid, grid.Value.EntityId) + amount > rule.Limit)
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

            string name = RuleName(rule);
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
        Dictionary<long, int> target = grid.GridSizeEnum == MyCubeSize.Small ? smallGridsByPlayer : largeGridsByPlayer;
        foreach (long owner in GridPlayers(grid.BigOwners, grid.GetBlocks().Select(block => block.BuiltBy)))
            target[owner] = target.TryGetValue(owner, out int count) ? count + 1 : 1;
    }

    /// <summary>
    /// The players a grid counts for: its big owners, or the players who built the most of
    /// its blocks when it has no owner
    /// </summary>
    private static IEnumerable<long> GridPlayers(IEnumerable<long> bigOwners, IEnumerable<long> builders)
    {
        List<long> owners = bigOwners.Where(id => id != 0).Distinct().ToList();
        if (owners.Count != 0)
            return owners;

        return Biggest(builders);
    }

    /// <summary>The ids that occur the most often, zero left out</summary>
    private static List<long> Biggest(IEnumerable<long> ids)
    {
        List<IGrouping<long, long>> groups = ids.Where(id => id != 0).GroupBy(id => id).ToList();
        if (groups.Count == 0)
            return new List<long>();

        int most = groups.Max(g => g.Count());
        return groups.Where(g => g.Count() == most).Select(g => g.Key).ToList();
    }

    /// <summary>
    /// A grid and its rotor, hinge and piston subgrids count as one grid: the one with the
    /// most blocks
    /// </summary>
    private static bool IsMainGridOfGroup(MyCubeGrid grid)
    {
        List<MyCubeGrid> group = MyCubeGridGroups.Static?.Mechanical.GetGroupNodes(grid);
        if (group == null)
            return true;

        MyCubeGrid main = grid;
        foreach (MyCubeGrid other in group)
        {
            if (IsRealGrid(other) && (other.BlocksCount > main.BlocksCount || (other.BlocksCount == main.BlocksCount && other.EntityId < main.EntityId)))
                main = other;
        }

        return main == grid;
    }

    /// <summary>
    /// A paste adds one grid, sized as its biggest grid (the others are usually its
    /// subgrids), for each player it counts for
    /// </summary>
    private bool CanAddPastedGrid(List<MyObjectBuilder_CubeGrid> grids, IPluginConfig config, out Denial denial)
    {
        denial = null;
        MyObjectBuilder_CubeGrid main = grids.OrderByDescending(g => g.CubeBlocks?.Count ?? 0).First();
        List<MyObjectBuilder_CubeBlock> blocks = main.CubeBlocks ?? new List<MyObjectBuilder_CubeBlock>();
        IEnumerable<long> players = GridPlayers(Biggest(blocks.Select(block => block.Owner)), blocks.Select(block => block.BuiltBy));
        foreach (long player in players)
        {
            if (IsNpc(player) || !IsOverGridCount(player, main.GridSizeEnum, config, out string limitName))
                continue;

            int count = grids.Sum(g => g.CubeBlocks?.Count ?? 0);
            denial = new Denial(limitName, count, new[] { string.IsNullOrWhiteSpace(main.DisplayName) ? "Grid" : main.DisplayName });
            return false;
        }

        return true;
    }

    private bool IsOverGridCount(long identityId, MyCubeSize size, IPluginConfig config, out string limitName)
    {
        bool small = size == MyCubeSize.Small;
        int limit = small ? config.MaxSmallGridsPerPlayer : config.MaxLargeGridsPerPlayer;
        Dictionary<long, int> counts = small ? smallGridsByPlayer : largeGridsByPlayer;
        limitName = small ? "Small grids per player" : "Large grids per player";
        return limit > 0 && (counts.TryGetValue(identityId, out int count) ? count : 0) + 1 > limit;
    }

    private static List<MySlimBlock> MatchingBlocks(LimitRule rule, MyCubeGrid grid)
        => grid.GetBlocks()
            .Where(block => block?.BlockDefinition != null && !block.IsDestroyed && RuleMatches(rule, block.BlockDefinition) &&
                            !(rule.IgnoreNpcs && (IsNpc(block.BuiltBy) || IsNpc(block.OwnerId))))
            .ToList();

    private static string RuleName(LimitRule rule)
        => string.IsNullOrWhiteSpace(rule.Name) ? string.Join(",", rule.BlockList ?? new List<string>()) : rule.Name;

    public static string BlockName(MyCubeBlockDefinition definition)
        => string.IsNullOrWhiteSpace(definition.BlockPairName) ? definition.Id.SubtypeName : definition.BlockPairName;

    private void CountBlock(MyCubeGrid grid, MySlimBlock block)
    {
        if (block == null || block.IsDestroyed || block.BlockDefinition == null)
            return;

        Count(GridInfo.Of(grid), block.BlockDefinition, block.BuiltBy, IsNpc(block.BuiltBy) || IsNpc(block.OwnerId));
    }

    private void Count(GridInfo grid, MyCubeBlockDefinition definition, long builtBy, bool npc, bool countGrid = true)
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

    private static bool GridMatches(LimitRule rule, GridInfo? grid)
        => grid == null || GridMatches(rule, grid.Value);

    private static bool GridMatches(LimitRule rule, GridInfo grid)
    {
        return rule.GridType switch
        {
            GridType.AllGrids => true,
            GridType.SmallGrid => grid.Size == MyCubeSize.Small,
            GridType.LargeGrid => grid.Size == MyCubeSize.Large,
            GridType.Static => grid.IsStatic,
            GridType.Ship => !grid.IsStatic,
            _ => true,
        };
    }

    private static bool IsGridSizeViolation(GridInfo grid, IPluginConfig config)
    {
        if (config.MaxBlocksSmallGrid > 0 && grid.Size == MyCubeSize.Small && grid.BlocksCount > config.MaxBlocksSmallGrid)
            return true;

        if (config.MaxBlocksLargeGrid > 0 && grid.Size == MyCubeSize.Large && grid.BlocksCount > config.MaxBlocksLargeGrid)
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

    /// <summary>A grid as the limits see it: one in the world, or one about to be pasted or merged</summary>
    private readonly struct GridInfo
    {
        public readonly long EntityId;
        public readonly MyCubeSize Size;
        public readonly bool IsStatic;
        public readonly int BlocksCount;

        public GridInfo(long entityId, MyCubeSize size, bool isStatic, int blocksCount)
        {
            EntityId = entityId;
            Size = size;
            IsStatic = isStatic;
            BlocksCount = blocksCount;
        }

        public static GridInfo Of(MyCubeGrid grid)
            => new GridInfo(grid.EntityId, grid.GridSizeEnum, grid.IsStatic, grid.BlocksCount);
    }

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
