using System.Reflection;
using HarmonyLib;
using Sandbox.Definitions;
using Sandbox.Game.Entities;
using Sandbox.Game.World;
using VRage.Game;
using VRage.Network;

namespace ServerPlugin.Patches;

// The cube builder starting a new grid. Its first block reaches BlockBuilt and the block
// rules, so this checks only the grid count of the player.
[HarmonyPatch(typeof(MyCubeBuilder), "RequestGridSpawn")]
public static class GridSpawnPatch
{
    // MyCubeBuilder.SpawnGridReply(bool canSpawn, ulong senderId), the "unable" sound
    private static readonly MethodInfo SpawnGridReply = AccessTools.Method(
        typeof(MyCubeBuilder),
        "SpawnGridReply",
        new[] { typeof(bool), typeof(ulong) }
    );

    // ReSharper disable once UnusedMember.Local
    // The request is a private struct of MyCubeBuilder, read through Traverse
    private static bool Prefix(object[] __args)
    {
        BlockLimitService limits = Plugin.Instance?.Limits;
        if (limits?.Enabled != true)
            return true;

        Traverse data = Traverse.Create(__args[0]);
        long identityId = data.Field("Author").Field("IdentityId").GetValue<long>();
        MyDefinitionId id = data.Field("Definition").GetValue<DefinitionIdBlit>();
        if (
            !MyDefinitionManager.Static.TryGetCubeBlockDefinition(
                id,
                out MyCubeBlockDefinition definition
            ) || limits.CanAddGrid(identityId, definition.CubeSize, out string limitName)
        )
            return true;

        Plugin.Instance.Log.Info(
            "Refused a new grid by {0} over limit '{1}'",
            identityId,
            limitName
        );
        Plugin.Instance.Notify(
            identityId,
            new Denial(limitName, 1, new[] { BlockLimitService.BlockName(definition) })
        );

        ulong steamId = MyEventContext.Current.Sender.Value;
        if (!MyEventContext.Current.IsLocallyInvoked && steamId != 0)
            SpawnGridReply?.Invoke(null, new object[] { false, steamId });

        return false;
    }
}
