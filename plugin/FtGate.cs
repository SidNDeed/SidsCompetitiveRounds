#if SCR_FRAMETIME
namespace CompetitiveRounds
{
    /// <summary>FrameTime M3 (METHOD-V4.md 3.1): the one switch for all seven components
    /// (the six evidence collectors and PeerBuild). Set at an OFF point's first live frame,
    /// cleared when live combat ends; outside live combat it is always clear. Every gated
    /// entry reads it first. The schedule that drives it is part 2 of the build brief;
    /// M6's dispatch calibration times the read itself.</summary>
    internal static class FtGate
    {
        internal static bool Off;
    }
}
#endif
