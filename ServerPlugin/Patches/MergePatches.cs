using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Sandbox;
using Sandbox.Game.Entities;
using SpaceEngineers.Game.Entities.Blocks;

namespace ServerPlugin.Patches;

// Merge blocks joining two grids. Refused, the grids stay apart.
[HarmonyPatch(typeof(MyCubeGrid), nameof(MyCubeGrid.MergeGrid_MergeBlock))]
public static class MergeBlockPatch
{
    // ReSharper disable once UnusedMember.Local
    private static bool Prefix(
        MyCubeGrid __instance,
        MyCubeGrid gridToMerge,
        ref MyCubeGrid __result
    )
    {
        if (MergeGuard.CanMerge(__instance, gridToMerge, mergeBlocks: true))
            return true;

        __result = null;
        return false;
    }
}

// Two stations touching, after a block is built or a grid pasted or spawned. Refused,
// they stay two grids.
[HarmonyPatch(typeof(MyCubeGrid), "MergeGrid_Static")]
public static class StaticMergePatch
{
    // ReSharper disable once UnusedMember.Local
    private static bool Prefix(
        MyCubeGrid __instance,
        MyCubeGrid gridToMerge,
        ref MyCubeGrid __result
    )
    {
        if (MergeGuard.CanMerge(__instance, gridToMerge, mergeBlocks: false))
            return true;

        __result = null;
        return false;
    }
}

internal static class MergeGuard
{
    private static readonly TimeSpan MessageInterval = TimeSpan.FromSeconds(10);
    private static readonly Dictionary<(long, long), DateTime> lastMessage =
        new Dictionary<(long, long), DateTime>();

    public static bool CanMerge(MyCubeGrid grid, MyCubeGrid other, bool mergeBlocks)
    {
        BlockLimitService limits = Plugin.Instance?.Limits;
        if (limits == null || limits.CanMerge(grid, other, out Denial denial))
            return true;

        // Switched off, the merge blocks of the smaller grid don't try again every few
        // frames; switched on again, they do. The other side stays on: a station's merge
        // block notices a ship only as it comes close. Not right now: the merge block
        // calling us uses its other half after we return, and switching off lets go of it.
        List<MyShipMergeBlock> blocks = mergeBlocks
            ? MergeBlocksBetween(grid, other)
            : new List<MyShipMergeBlock>();
        MyCubeGrid smaller = grid.BlocksCount <= other.BlocksCount ? grid : other;
        List<MyShipMergeBlock> switchOff = blocks
            .Where(block => block.CubeGrid == smaller)
            .ToList();
        if (switchOff.Count != 0)
            MySandboxGame.Static.Invoke(
                () =>
                {
                    foreach (MyShipMergeBlock block in switchOff)
                        block.Enabled = false;
                },
                "BlockLimits"
            );

        if (FirstInAWhile(grid.EntityId, other.EntityId))
        {
            Plugin.Instance.Log.Info(
                "Refused merging {0} and {1} over limit '{2}'",
                grid.DisplayName,
                other.DisplayName,
                denial.LimitName
            );
            IEnumerable<long> players = mergeBlocks
                ? blocks.Select(block =>
                    block.OwnerId != 0 ? block.OwnerId : block.SlimBlock.BuiltBy
                )
                : grid.BigOwners.Concat(other.BigOwners);
            foreach (long player in players.Where(id => id != 0).Distinct())
                Plugin.Instance.Notify(player, denial);
        }

        return false;
    }

    private static List<MyShipMergeBlock> MergeBlocksBetween(MyCubeGrid grid, MyCubeGrid other) =>
        grid.GetFatBlocks<MyShipMergeBlock>()
            .Concat(other.GetFatBlocks<MyShipMergeBlock>())
            .Where(block =>
                block.InConstraint
                && (block.Other?.CubeGrid == grid || block.Other?.CubeGrid == other)
                && block.Other.CubeGrid != block.CubeGrid
            )
            .ToList();

    private static bool FirstInAWhile(long grid, long other)
    {
        (long, long) key = grid < other ? (grid, other) : (other, grid);
        DateTime now = DateTime.UtcNow;
        if (lastMessage.TryGetValue(key, out DateTime last) && now - last < MessageInterval)
            return false;

        foreach (
            (long, long) old in lastMessage
                .Where(item => now - item.Value >= MessageInterval)
                .Select(item => item.Key)
                .ToList()
        )
            lastMessage.Remove(old);

        lastMessage[key] = now;
        return true;
    }
}
