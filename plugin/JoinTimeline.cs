using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using Photon.Pun;

namespace CompetitiveRounds
{
    /// <summary>I1, the client connect timeline (connect-failure design V11,
    /// sec4 I1). One line per named step of a gated FFA lock's join, from the
    /// poll that first sees the lock to the game start:
    ///
    ///   [JOIN-TL] +{ms}ms {utc:HH:mm:ss.fff}Z step={step} lobby={id8}
    ///             room={nonce} att={attempt} st={ClientState} rg={live}/{want} {detail}
    ///
    /// `ms` is a Stopwatch (monotonic, blind to Unity's time scale) started by
    /// Seen, or by Arm when Seen did not run for that lobby. `utc` only lines
    /// the client up with the server's I2 timestamps; no duration reads it.
    /// The tag exists for nothing else (#306): every existing log line stays
    /// as it was.
    ///
    /// While disarmed, Step prints only the allowlist: the in-game lines that
    /// fire after a seat's timeline disarmed at game_start (the kept epoch,
    /// the quarantine, the fence, LAG_OUT, the release), the poll and POST
    /// failure lines, and the I1 rows marked "printed armed or not".</summary>
    internal static class JoinTimeline
    {
        internal const string Banner = "[JOIN-TL] armed v11 clock=stopwatch";

        private static readonly Stopwatch _sw = new Stopwatch();
        private static bool _armed;
        private static string _lobby = "";
        private static string _room = "";
        private static string _want = "";
        private static string _seenLobby;
        private static readonly Dictionary<string, float> _throttle = new Dictionary<string, float>(StringComparer.Ordinal);

        /// <summary>The joiner's attempt ordinal source (joinAttempts + 1),
        /// wired by QueueRoomJoiner.Awake; 1 before it exists.</summary>
        internal static Func<int> AttemptOrdinal;

        private static readonly HashSet<string> Always = new HashSet<string>(StringComparer.Ordinal)
        {
            "poll_fail", "poll_drop", "post_fail",
            "kept", "quarantine", "quarantine_refused", "late_digest",
            "epoch_rx", "epoch_bad", "epoch_ready_tx", "epoch_ready", "epoch_raise", "epoch_refused",
            "master_fence",
            "epoch_ack_tx", "epoch_ack", "epoch_unacked", "callin_stamp", "stamp_rx", "stamp_refused",
            "master_ack",
            "stamp_late", "stamp_superseded", "lag_out", "lag_out_end", "release", "release_handoff",
            "ledger_skip", "scale_refused", "seq_mismatch", "gate", "cfg_apply",
            // The master's boundary telemetry (item 5): it runs after the
            // master's own timeline disarmed at game_start, so it would
            // otherwise never print.
            "late_wait", "seed_pub",
        };

        internal static bool Armed => _armed;
        internal static string Lobby => _lobby;

        /// <summary>The boot banner, printed once from Plugin.Awake.</summary>
        internal static void PrintBanner()
        {
            try { Plugin.Log.LogInfo(Banner); } catch { }
        }

        /// <summary>The pre-arm emitter: the first statement inside the poll's
        /// ready_join branch, once per lobby id. It arms the timeline and
        /// prints lock_seen.</summary>
        internal static void Seen(string lobbyId, string detail)
        {
            try
            {
                if (string.IsNullOrEmpty(lobbyId)) return;
                if (string.Equals(_seenLobby, lobbyId, StringComparison.Ordinal)) return;
                if (_armed && !string.Equals(_lobby, lobbyId, StringComparison.Ordinal))
                    Emit("rearm", "to=" + Id8(lobbyId));
                _seenLobby = lobbyId;
                _lobby = lobbyId;
                _room = "";
                _want = "";
                _sw.Reset();
                _sw.Start();
                _armed = true;
                Emit("lock_seen", detail);
            }
            catch { }
        }

        /// <summary>At the lock (ApiClient's "[FFA] Lobby locked!" line): adds
        /// the room and the wanted region and prints lock_rx. When Seen did not
        /// run for this lobby it starts the Stopwatch itself (seen=0).</summary>
        internal static void Arm(string lobbyId, string room, string wantRegion, string detail, int adm)
        {
            try
            {
                if (string.IsNullOrEmpty(lobbyId)) return;
                bool seen = string.Equals(_seenLobby, lobbyId, StringComparison.Ordinal) && _armed;
                if (!seen)
                {
                    if (_armed && !string.Equals(_lobby, lobbyId, StringComparison.Ordinal))
                        Emit("rearm", "to=" + Id8(lobbyId));
                    _sw.Reset();
                    _sw.Start();
                    _seenLobby = lobbyId;
                }
                _lobby = lobbyId;
                _room = room ?? "";
                _want = wantRegion ?? "";
                _armed = true;
                Emit("lock_rx", (detail ?? "") + " seen=" + (seen ? "1" : "0") + " adm=" + (adm != 0 ? "1" : "0"));
            }
            catch { }
        }

        /// <summary>One named step. Printed while armed, and while disarmed
        /// only for the allowlist.</summary>
        internal static void Step(string step, string detail = "")
        {
            try
            {
                if (!_armed && !Always.Contains(step)) return;
                Emit(step, detail);
            }
            catch { }
        }

        /// <summary>Ends the timeline for this lobby. Later steps print only
        /// when allowlisted.</summary>
        internal static void Disarm(string why)
        {
            _armed = false;
        }

        /// <summary>At most one pass per key per window: post_fail (per kind)
        /// and poll_fail print at most once per 10 s, poll_drop once per lobby
        /// id (a window that never ends).</summary>
        internal static bool Throttle(string key, float seconds)
        {
            try
            {
                float now = UnityEngine.Time.realtimeSinceStartup;
                float last;
                if (_throttle.TryGetValue(key, out last) && (seconds < 0f || now - last < seconds))
                    return false;
                _throttle[key] = now;
                return true;
            }
            catch { return true; }
        }

        /// <summary>Milliseconds since Seen or Arm, clamped for the POST
        /// bodies' client_ms (0-600000).</summary>
        internal static int ClientMs()
        {
            long ms = _sw.ElapsedMilliseconds;
            if (ms < 0) ms = 0;
            if (ms > 600000) ms = 600000;
            return (int)ms;
        }

        internal static string Id8(string id)
        {
            if (string.IsNullOrEmpty(id)) return "-";
            return id.Length <= 8 ? id : id.Substring(0, 8);
        }

        internal static string Nonce(string room)
        {
            try
            {
                if (BroadcastMode.IsBroadcastIdentity) return "-";
            }
            catch { }
            if (string.IsNullOrEmpty(room)) return "-";
            int u = room.IndexOf('_');
            return u >= 0 && u + 1 < room.Length ? room.Substring(u + 1) : room;
        }

        private static void Emit(string step, string detail)
        {
            string st = "?";
            try { st = PhotonNetwork.NetworkClientState.ToString(); } catch { }
            string live = "";
            try { live = ApiClient.LiveOnlineRegion(); } catch { }
            if (string.IsNullOrEmpty(live)) live = "-";
            int att = 1;
            try { if (AttemptOrdinal != null) att = AttemptOrdinal(); } catch { }
            string room = _room;
            if (string.IsNullOrEmpty(room))
            {
                try { room = PhotonNetwork.CurrentRoom?.Name ?? ""; } catch { }
            }
            string line = "[JOIN-TL] +" + _sw.ElapsedMilliseconds.ToString(CultureInfo.InvariantCulture) + "ms "
                          + DateTime.UtcNow.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture) + "Z"
                          + " step=" + step
                          + " lobby=" + Id8(_lobby)
                          + " room=" + Nonce(room)
                          + " att=" + att.ToString(CultureInfo.InvariantCulture)
                          + " st=" + st
                          + " rg=" + live + "/" + (string.IsNullOrEmpty(_want) ? "-" : _want)
                          + (string.IsNullOrEmpty(detail) ? "" : " " + detail);
            try { Plugin.Log.LogInfo(line); } catch { }
        }
    }
}
