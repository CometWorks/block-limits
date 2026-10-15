using System.Collections.Generic;
using HarmonyLib;
using Sandbox.Engine.Multiplayer;
using Sandbox.Game.Entities;
using Sandbox.Game.World;
using VRage.Game;
using VRage.Network;

namespace ServerPlugin.Patches;

// A player pasting new grids: the clipboard (copy-paste or creative rights), admin
// paste and Remote's blueprints/paste all come to the server as this event. Pastes the
// server or a plugin makes itself are locally invoked and pass.
[HarmonyPatch(typeof(MyCubeGrid), nameof(MyCubeGrid.TryPasteGrid_Implementation))]
public static class PasteGridPatch
{
    // ReSharper disable once UnusedMember.Local
    private static bool Prefix(MyCubeGrid.MyPasteGridParameters parameters)
    {
        if (
            !PasteGuard.ShouldCheck(out ulong steamId)
            || !MySession.Static.IsCopyPastingEnabledForUser(steamId)
        )
            return true;

        if (Plugin.Instance.Limits.CanPaste(parameters.Entities, null, out Denial denial))
            return true;

        PasteGuard.Refuse(steamId, denial);

        // The client waits for this to hide its paste spinner
        MyMultiplayer.RaiseStaticEvent(
            _ => MyCubeGrid.SendHudNotificationAfterPaste,
            new EndpointId(steamId)
        );
        return false;
    }
}

// Clipboard contents snapped onto an existing grid
[HarmonyPatch(typeof(MyCubeGrid), "PasteBlocksToGridServer_Implementation")]
public static class PasteBlocksToGridPatch
{
    // ReSharper disable once UnusedMember.Local
    private static bool Prefix(MyCubeGrid __instance, List<MyObjectBuilder_CubeGrid> gridsToMerge)
    {
        if (
            !PasteGuard.ShouldCheck(out ulong steamId)
            || !MySession.Static.HasPlayerCreativeRights(steamId)
        )
            return true;

        if (Plugin.Instance.Limits.CanPaste(gridsToMerge, __instance, out Denial denial))
            return true;

        PasteGuard.Refuse(steamId, denial);
        return false;
    }
}

internal static class PasteGuard
{
    /// <summary>Whether to check this event: from a player, with the limits on</summary>
    public static bool ShouldCheck(out ulong steamId)
    {
        steamId = MyEventContext.Current.Sender.Value;
        return Plugin.Instance?.Limits?.Enabled == true
            && !MyEventContext.Current.IsLocallyInvoked
            && steamId != 0;
    }

    public static void Refuse(ulong steamId, Denial denial)
    {
        long identityId = MySession.Static.Players.TryGetIdentityId(steamId);
        Plugin.Instance.Log.Info(
            "Refused a paste by {0} over limit '{1}': {2} blocks",
            identityId,
            denial.LimitName,
            denial.Count
        );
        Plugin.Instance.Notify(identityId, denial);
        MyMultiplayer.RaiseStaticEvent(
            _ => MyCubeGrid.ShowPasteFailedOperation,
            new EndpointId(steamId)
        );
    }
}
