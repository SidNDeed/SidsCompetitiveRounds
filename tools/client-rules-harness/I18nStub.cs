namespace CompetitiveRounds
{
    /// <summary>
    /// The harness's stand-in for plugin/I18n.cs, which needs Unity and the
    /// plugin's config. The generated descriptor table
    /// (plugin/SettingsDescriptors.g.cs) passes its display strings through
    /// I18n.Tr; the settings suite reads only the table's keys, homes and
    /// reset flags, so an identity translation is all it needs.
    /// </summary>
    internal static class I18n
    {
        internal static string Tr(string english) => english;
    }
}
