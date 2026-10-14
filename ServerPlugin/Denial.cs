using System.Collections.Generic;
using System.Linq;

namespace ServerPlugin;

/// <summary>What a limit refused, for the deny message</summary>
public sealed class Denial
{
    public string LimitName { get; }
    public int Count { get; }
    public List<string> Blocks { get; }

    public Denial(string limitName, int count, IEnumerable<string> blocks)
    {
        LimitName = limitName;
        Count = count;
        Blocks = blocks.ToList();
    }
}
