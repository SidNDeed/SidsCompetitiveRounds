#if SCR_FRAMETIME
using System;
using System.Diagnostics;
using Photon.Pun;

namespace CompetitiveRounds
{
    /// <summary>FrameTime part c, the rematch [F04]. In an ft_ room the Continue prompt (PopUpHandler.StartPicking)
    /// is held, not answered: this seat publishes the player property ft_rm = the next game's number and answers
    /// Yes only once Photon's cache shows that number on both this seat's own player and the other fighter, so
    /// the two Yes answers land within one Photon round trip, inside vanilla's 10 s one-seat restart
    /// (GM_ArmsRace.IDoRematch). If both do not show it within 60 s of Stopwatch time, it answers nothing, logs
    /// "rematch timeout" and the self-drive disarms, so a missed rematch stops the sitting instead of splitting
    /// it. Requiring this seat's own published value (not its local intent) keeps a failed publish on either seat
    /// from letting the other side answer alone (Plugin.cs's bug-228 note, r4). The sentinel key
    /// rematch_mutant=1 is the build round's control: it answers Yes at once, which shows the one-seat restart the
    /// hold prevents. Polled at every frame boundary.</summary>
    internal static class FtRematch
    {
        internal const string PROP = "ft_rm";
        internal const double TIMEOUT_S = 60.0;

        internal static bool TimedOut;
        private static Action<PopUpHandler.YesNo> _answer;
        private static int _want;
        private static readonly Stopwatch _since = new Stopwatch();

        internal static void Hold(Action<PopUpHandler.YesNo> answer)
        {
            if (FtConfig.Get("rematch_mutant", "0") == "1")
            {
                Plugin.Log.LogInfo("[FRAME-TIME] rematch mutant: answered Yes at once");
                answer?.Invoke(PopUpHandler.YesNo.Yes);
                return;
            }
            if (FtDrive.Complete || TimedOut) { Plugin.Log.LogInfo("[FRAME-TIME] rematch not answered (sitting over)"); return; }
            _answer = answer;
            _want = FtSchedule.Game + 1;
            _since.Reset();
            _since.Start();
            try
            {
                PhotonNetwork.LocalPlayer.SetCustomProperties(new ExitGames.Client.Photon.Hashtable { { PROP, _want } });
                Plugin.Log.LogInfo("[FRAME-TIME] rematch held: published " + PROP + "=" + _want);
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] rematch publish failed: " + ex.Message); }
        }

        private static int Read(Photon.Realtime.Player p)
        {
            try
            {
                object v;
                if (p != null && p.CustomProperties != null && p.CustomProperties.TryGetValue(PROP, out v) && v is int) return (int)v;
            }
            catch { }
            return -1;
        }

        internal static void Poll()
        {
            if (_answer == null) return;
            var others = RoomActors.OtherActiveFighters();
            bool mine = Read(PhotonNetwork.LocalPlayer) == _want;
            bool theirs = others.Length == 1 && Read(others[0]) == _want;
            if (mine && theirs)
            {
                var a = _answer;
                _answer = null;
                Plugin.Log.LogInfo("[FRAME-TIME] rematch yes g=" + _want + " after " + _since.ElapsedMilliseconds + " ms");
                try { a(PopUpHandler.YesNo.Yes); }
                catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] rematch answer failed: " + ex.Message); }
                return;
            }
            if (_since.Elapsed.TotalSeconds >= TIMEOUT_S)
            {
                _answer = null;
                TimedOut = true;
                Plugin.Log.LogWarning("[FRAME-TIME] rematch timeout g=" + _want + " own=" + mine + " peer=" + theirs);
            }
        }
    }
}
#endif
