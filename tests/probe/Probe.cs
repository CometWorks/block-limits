using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using PluginSdk.Commands;
using PluginSdk.Config;
using Sandbox.Definitions;
using Sandbox.Game.Entities;
using Sandbox.Game.Entities.Blocks;
using Sandbox.Game.Entities.Cube;
using Sandbox.Game.EntityComponents;
using Sandbox.Game.Weapons;
using Sandbox.Game.World;
using VRage.FileSystem;
using VRage.Game;
using VRage.Game.ModAPI;
using VRage.Plugins;
using VRage.Utils;
using VRageMath;

namespace BlockLimitsProbe;

// Test hooks of the Block Limits suite: the cross-plugin API, the plugin's own
// counts, and its config swapped at runtime. Reaches Block Limits by reflection,
// so it needs no build dependency on it.
public class Probe : IPlugin
{
    public void Init(object gameInstance) =>
        ServerCommands.Register(Assembly.GetExecutingAssembly(), typeof(ProbeCommands));

    public void Update() { }

    public void Dispose() { }
}

[CommandRoot("blprobe", "BlockLimitsProbe", "Block Limits test hooks")]
public sealed class ProbeCommands : CommandModule
{
    private static Assembly BlockLimits =>
        AppDomain
            .CurrentDomain.GetAssemblies()
            .First(a => a.GetType("BlockLimits.PluginApi.Limits") != null);

    private static object Plugin =>
        BlockLimits.GetType("ServerPlugin.Plugin").GetProperty("Instance").GetValue(null);

    private static object Service => Plugin.GetType().GetProperty("Limits").GetValue(Plugin);

    [Command("reload", "Loads BlockLimits.cfg into the running plugin.")]
    [Permission(MyPromoteLevel.Admin)]
    public string Reload()
    {
        object live = Plugin.GetType().GetProperty("PluginConfig").GetValue(Plugin);
        Type type = live.GetType();
        string path = Path.Combine(MyFileSystem.UserDataPath, "BlockLimits.cfg");
        object loaded = typeof(ConfigStorage)
            .GetMethod(nameof(ConfigStorage.LoadXml))
            .MakeGenericMethod(type)
            .Invoke(null, new object[] { path });

        foreach (
            PropertyInfo property in type.GetProperties(
                BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly
            )
        )
        {
            if (property.CanRead && property.CanWrite)
                property.SetValue(live, property.GetValue(loaded));
        }

        Service.GetType().GetMethod("Recalculate").Invoke(Service, null);
        return "Probe: config reloaded";
    }

    [Command("report", "BuildLimitReport of any identity.")]
    [Permission(MyPromoteLevel.Admin)]
    public string Report(long identityId) =>
        "Probe report: "
        + Service
            .GetType()
            .GetMethod("BuildLimitReport")
            .Invoke(Service, new object[] { identityId });

    [Command("canadd", "Limits.CanAdd with the blocks of a grid, or of one subtype on it.")]
    [Permission(MyPromoteLevel.Admin)]
    public string CanAdd(long gridId, long identityId, string subtype = null)
    {
        if (!(MyEntities.GetEntityById(gridId) is MyCubeGrid grid))
            return "Probe canadd: no grid";

        List<MySlimBlock> blocks = grid.GetBlocks()
            .Where(b => subtype == null || b.BlockDefinition.Id.SubtypeName == subtype)
            .ToList();
        object[] args = { blocks, identityId, null };
        bool allowed = (bool)
            BlockLimits
                .GetType("BlockLimits.PluginApi.Limits")
                .GetMethod("CanAdd")
                .Invoke(null, args);
        int denied = ((IList)args[2]).Count;
        return $"Probe canadd: allowed={allowed} denied={denied} total={blocks.Count}";
    }

    [Command("blocks", "Block count of a grid on the server, by subtype.")]
    [Permission(MyPromoteLevel.Admin)]
    public string Blocks(long gridId)
    {
        if (!(MyEntities.GetEntityById(gridId) is MyCubeGrid grid) || grid.MarkedForClose)
            return "Probe blocks: no grid";

        IEnumerable<string> subtypes = grid.GetBlocks()
            .GroupBy(b => b.BlockDefinition.Id.SubtypeName)
            .OrderBy(g => g.Key)
            .Select(g => $"{g.Key}={g.Count()}");
        return $"Probe blocks: total={grid.BlocksCount} " + string.Join(" ", subtypes);
    }

    [Command("grids", "The plugin's small and large grid counts of an identity.")]
    [Permission(MyPromoteLevel.Admin)]
    public string Grids(long identityId)
    {
        int Count(string field)
        {
            var counts = (IDictionary)
                Service
                    .GetType()
                    .GetField(field, BindingFlags.NonPublic | BindingFlags.Instance)
                    .GetValue(Service);
            return counts.Contains(identityId) ? (int)counts[identityId] : 0;
        }

        return $"Probe grids: small={Count("smallGridsByPlayer")} large={Count("largeGridsByPlayer")}";
    }

    [Command(
        "projection",
        "The projected blocks of a projector, in its grid's cells, and whether they can be built."
    )]
    [Permission(MyPromoteLevel.Admin)]
    public string Projection(long projectorId)
    {
        if (!(MyEntities.GetEntityById(projectorId) is MyProjectorBase projector))
            return "Probe projection: no projector";

        MyCubeGrid projected = projector.ProjectedGrid;
        if (projected == null)
            return "Probe projection: none";

        IEnumerable<string> blocks = projected
            .GetBlocks()
            .Select(b =>
                $"{projector.CubeGrid.WorldToGridInteger(projected.GridIntegerToWorld(b.Position))}:{projector.CanBuild(b, true)}"
            );
        return "Probe projection: " + string.Join(" ", blocks);
    }

    [Command("tool", "The detector sphere of a ship tool, in its grid's cells.")]
    [Permission(MyPromoteLevel.Admin)]
    public string Tool(long toolId)
    {
        if (!(MyEntities.GetEntityById(toolId) is MyShipToolBase tool))
            return "Probe tool: no tool";

        var center = Vector3D.Transform(tool.DetectorSphere.Center, tool.CubeGrid.WorldMatrix);
        var cell = (center - tool.CubeGrid.PositionComp.GetPosition()) / tool.CubeGrid.GridSize;
        return $"Probe tool: center={cell.X:F2},{cell.Y:F2},{cell.Z:F2} radius={tool.DetectorSphere.Radius / tool.CubeGrid.GridSize:F2} "
            + $"enabled={tool.Enabled} functional={tool.IsFunctional} working={tool.IsWorking} "
            + $"powered={tool.ResourceSink?.IsPoweredByType(MyResourceDistributorComponent.ElectricityId)}";
    }

    [Command("enabled", "Whether a functional block is switched on, on the server.")]
    [Permission(MyPromoteLevel.Admin)]
    public string Enabled(long blockId) =>
        MyEntities.GetEntityById(blockId) is MyFunctionalBlock block
            ? $"Probe enabled: {block.Enabled}"
            : "Probe enabled: no block";

    [Command(
        "newgrid",
        "Sends the cube builder's request for a new static grid of one block, as a player."
    )]
    [Permission(MyPromoteLevel.Admin)]
    public string NewGrid(long identityId, string subtype, double x, double y, double z)
    {
        MyIdentity identity = MySession.Static.Players.TryGetIdentity(identityId);
        if (identity?.Character == null)
            return "Probe newgrid: no character";

        MyCubeBlockDefinition definition = MyDefinitionManager
            .Static.GetAllDefinitions()
            .OfType<MyCubeBlockDefinition>()
            .FirstOrDefault(d => d.Id.SubtypeName == subtype);
        if (definition == null)
            return "Probe newgrid: no block";

        // MyCubeBuilder.RequestGridSpawn(GridSpawnRequestData), private like its types
        const BindingFlags Private = BindingFlags.NonPublic | BindingFlags.Static;
        Type builder = typeof(MyCubeBuilder);
        Type requestType = builder.GetNestedType("GridSpawnRequestData", BindingFlags.NonPublic);
        object author = Activator.CreateInstance(
            builder.GetNestedType("Author", BindingFlags.NonPublic),
            identity.Character.EntityId,
            identityId
        );
        object position = Activator.CreateInstance(requestType.GetField("Position").FieldType);
        Type positionType = position.GetType();
        positionType.GetField("Position").SetValue(position, new Vector3D(x, y, z));
        positionType.GetField("Forward").SetValue(position, Vector3.Forward);
        positionType.GetField("Up").SetValue(position, Vector3.Up);
        positionType.GetField("AbsolutePosition").SetValue(position, true);
        object request = Activator.CreateInstance(
            requestType,
            author,
            (DefinitionIdBlit)definition.Id,
            position,
            false,
            true,
            new MyCubeGrid.MyBlockVisuals(0, MyStringHash.NullOrEmpty)
        );
        builder.GetMethod("RequestGridSpawn", Private).Invoke(null, new[] { request });
        return "Probe newgrid: sent";
    }
}
