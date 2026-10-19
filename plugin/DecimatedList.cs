using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>Bounded telemetry series that COMPRESSES instead of stopping
    /// (Stan bug 181 root cause — the old hard 128-sample cap was a 6:24
    /// recording ceiling every 2v2/FFA game overran). At the cap the series
    /// drops every other sample and doubles its stride, so it always spans
    /// the whole game in at most 128 entries: 6.4 min at 3s/sample, 12.8 at
    /// 6s, 25.6 at 12s... Renderers must scale the x-axis by the real match
    /// duration rather than assuming a fixed cadence. Shared by
    /// GameStateWatcher and FfaMode.</summary>
    internal sealed class DecimatedList<T>
    {
        public readonly List<T> Items = new List<T>();
        private int stride = 1;
        private int tick;

        public int Count => Items.Count;

        public void Add(T value)
        {
            if ((tick++ % stride) != 0) return;
            Items.Add(value);
            if (Items.Count >= 128)
            {
                int half = Items.Count / 2;
                for (int i = 0; i < half; i++) Items[i] = Items[i * 2];
                Items.RemoveRange(half, Items.Count - half);
                stride *= 2;
            }
        }

        public void Clear()
        {
            Items.Clear();
            stride = 1;
            tick = 0;
        }
    }
}
