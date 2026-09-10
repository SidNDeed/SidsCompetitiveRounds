using System;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Room rules (Sept 10 batch, ai-collab/sept10-batch/01-room-rules.md
    /// §5): friendly fire (a host toggle on 2v2 / 1v2 lobbies) and Same Cards
    /// (every mode). The SERVER freezes the pair on the room's record when the
    /// room is issued and sends it as <c>rules_prop</c> ("ff=1;sc=0" — fixed key
    /// order, 0/1, no spaces, produced by the server only; this client never
    /// re-derives it). The creator stamps that string as the Photon room
    /// property <c>cr_rules</c>; every joiner compares the room's property with
    /// the string it was issued and LEAVES on a mismatch (§5.2), so a seat can
    /// never play under rules it was not admitted to.
    ///
    /// <para>Two pieces of state, each bound to one incarnation:</para>
    /// <list type="bullet">
    /// <item>PENDING — staged together with the pending room name
    /// (<see cref="Plugin.SetPendingRoom(string, string, string, string)"/>)
    /// and cleared exactly when the pending room is cleared, never earlier
    /// (the standing pending-room rule).</item>
    /// <item>LATCHED — read ONCE from the room's properties when the join is
    /// confirmed, reset on the left-room / disconnect edges. Never re-read per
    /// hit or per deal: a room property is eventually consistent (#321) and the
    /// value must be the same on every seat for the whole sitting.</item>
    /// </list>
    ///
    /// <para>Outside any latched room both rules read as the vanilla defaults
    /// (friendly fire ON, Same Cards OFF), which is what a private room, a
    /// tournament room and a spectated default room all play.</para></summary>
    internal static class RoomRules
    {
        public const string PropKey = "cr_rules";
        public const string DefaultProp = "ff=1;sc=0";

        // ── pending (dies with the pending room) ──────────────────────────
        public static string PendingProp { get; private set; }
        public static string PendingSrc { get; private set; }

        // ── latched (dies with the room) ──────────────────────────────────
        public static bool FriendlyFire { get; private set; } = true;
        public static bool SameCards { get; private set; } = false;
        public static bool Latched { get; private set; }
        public static string LatchedProp { get; private set; } = DefaultProp;
        public static string LatchedSrc { get; private set; }
        /// <summary>True when the latched room plays anything but the defaults.</summary>
        public static bool NonDefault => Latched && (!FriendlyFire || SameCards);

        private static bool announced;
        private static int suppressedThisGame;
        private static int unattributedThisGame;

        public enum LatchVerdict { Defaults, Latched, Mismatch }

        public static bool IsDefaultProp(string prop) => string.IsNullOrEmpty(prop) || prop == DefaultProp;

        /// <summary>Stage the rules the server issued with the pending room. An
        /// empty prop (an older server, a tournament dispatch, an FFA lobby —
        /// whose settings ride its own property) means "the defaults are
        /// expected".</summary>
        public static void StagePending(string prop, string src)
        {
            PendingProp = string.IsNullOrEmpty(prop) ? null : prop;
            PendingSrc = string.IsNullOrEmpty(src) ? null : src;
            // §6: a pending room that plays Same Cards advertises the card
            // sequence engine's level pre-join (the FFA pattern, #79); the
            // in-room advert carrying the pool hash follows at game start
            // (VanillaCardSequence.OnGameStart).
            try
            {
                if (TryParse(PendingProp, out _, out bool sc) && sc)
                    FfaCardSequence.PublishCapability();
            }
            catch { }
        }

        public static void ClearPending()
        {
            PendingProp = null;
            PendingSrc = null;
        }

        /// <summary>Strict grammar: exactly <c>ff=&lt;0|1&gt;;sc=&lt;0|1&gt;</c>.
        /// Anything else is unparseable — and an unparseable room property is a
        /// mismatch, never "close enough" (§5.2).</summary>
        public static bool TryParse(string prop, out bool ff, out bool sc)
        {
            ff = true; sc = false;
            if (prop == null || prop.Length != 9) return false;
            if (prop[0] != 'f' || prop[1] != 'f' || prop[2] != '=' || prop[4] != ';'
                || prop[5] != 's' || prop[6] != 'c' || prop[7] != '=') return false;
            char f = prop[3], s = prop[8];
            if ((f != '0' && f != '1') || (s != '0' && s != '1')) return false;
            ff = f == '1';
            sc = s == '1';
            return true;
        }

        /// <summary>The property the creator stamps at JoinOrCreate: the issued
        /// string when the server sent one. Null when nothing was issued — an
        /// FFA room carries its settings on its own property, a tournament room
        /// plays the defaults, and a joiner of such a room accepts an absent
        /// property only because it expects the defaults.</summary>
        public static string PropToStamp() => PendingProp;

        /// <summary>Compare the room we just entered with what we were issued.
        /// Called ONCE, from the join confirmation, BEFORE the pending tuple is
        /// cleared. Absent property: accepted only when the defaults were
        /// expected. Present: must parse and must equal the expectation. The
        /// caller acts on <see cref="LatchVerdict.Mismatch"/> (leave + toast);
        /// this method only records and logs.</summary>
        public static LatchVerdict LatchOnJoin(Photon.Realtime.Room room, string seat)
        {
            string expected = PendingProp ?? DefaultProp;
            // c1 H4: presence and value are tracked separately — only GENUINE
            // absence may select the defaults; a present value that is not a
            // string (or a null value) is a mismatch, never "absent".
            bool present = false;
            string actual = null;
            try
            {
                if (room != null && room.CustomProperties != null
                    && room.CustomProperties.TryGetValue(PropKey, out object v))
                {
                    present = true;
                    actual = v as string;
                }
            }
            catch { present = false; actual = null; }

            // c1 M2: no room name in these lines — a spectator room's name is
            // its join credential and these logs ride bug bundles; the seat
            // and the two rule strings are what a diagnosis needs.
            if (!present)
            {
                if (expected == DefaultProp)
                {
                    SetLatched(true, false, DefaultProp, PendingSrc);
                    Plugin.Log.LogInfo($"[ROOM-RULES] {seat}: no {PropKey} on the room — defaults (expected defaults)");
                    return LatchVerdict.Defaults;
                }
                return Mismatch(seat, expected, "(absent)");
            }
            if (actual == null)
                return Mismatch(seat, expected, "(non-string)");
            if (!TryParse(actual, out bool ff, out bool sc) || actual != expected)
                return Mismatch(seat, expected, actual);
            SetLatched(ff, sc, actual, PendingSrc);
            Plugin.Log.LogInfo($"[ROOM-RULES] {seat}: latched {actual} (src={PendingSrc ?? "-"}) ff={(ff ? 1 : 0)} sc={(sc ? 1 : 0)}");
            return LatchVerdict.Latched;
        }

        private static LatchVerdict Mismatch(string seat, string expected, string actual)
        {
            // Defaults are latched so that, for the frames before the leave
            // lands, nothing is suppressed that vanilla would not suppress.
            SetLatched(true, false, DefaultProp, null);
            Plugin.Log.LogWarning($"[ROOM-RULES] mismatch pending={expected} room={actual} ({seat}) — leaving");
            return LatchVerdict.Mismatch;
        }

        private static void SetLatched(bool ff, bool sc, string prop, string src)
        {
            FriendlyFire = ff;
            SameCards = sc;
            LatchedProp = prop;
            LatchedSrc = src;
            Latched = true;
            announced = false;
            suppressedThisGame = 0;
            unattributedThisGame = 0;
        }

        /// <summary>Left-room / disconnect edge. Idempotent.</summary>
        public static void ResetLatched()
        {
            FriendlyFire = true;
            SameCards = false;
            LatchedProp = DefaultProp;
            LatchedSrc = null;
            Latched = false;
            announced = false;
            suppressedThisGame = 0;
            unattributedThisGame = 0;
        }

        /// <summary>Game start (every seat): one toast per latched room naming
        /// the non-default rules, and the per-game diagnostic counters reset.</summary>
        public static void OnGameStart()
        {
            if (suppressedThisGame > 0 || unattributedThisGame > 0)
                Plugin.Log.LogInfo($"[ROOM-RULES] previous game: teammate hits suppressed={suppressedThisGame} unattributed hits seen={unattributedThisGame}");
            suppressedThisGame = 0;
            unattributedThisGame = 0;
            if (!NonDefault || announced) return;
            announced = true;
            string text = !FriendlyFire && SameCards
                ? I18n.Tr("Room rules: friendly fire OFF, same cards for everyone")
                : !FriendlyFire ? I18n.Tr("Room rules: friendly fire OFF")
                : I18n.Tr("Room rules: same cards for everyone");
            try { CompetitiveUI.ShowNotification(text, new Color(0.6f, 0.9f, 1f), 6f); } catch { }
        }

        /// <summary>The friendly-fire verdict for ONE hit, consumed by the
        /// combined DoDamage gate (fighter seats) and by both PoisonSync branches.
        /// True = this hit is a teammate's and the room plays friendly fire OFF,
        /// so no health moves (the hit still lands physically: knockback and
        /// sound are vanilla's — Sid, answer E). Unattributed damage
        /// (out-of-bounds, environment: attacker null) is never suppressed and
        /// is counted for the per-game diagnostic line. Never throws.</summary>
        public static bool SuppressTeammateDamage(Player attacker, Player victim)
        {
            if (FriendlyFire) return false;
            if (attacker == null)
            {
                unattributedThisGame++;
                return false;
            }
            if (victim == null || ReferenceEquals(attacker, victim)) return false;
            bool sameTeam;
            try { sameTeam = attacker.TeamID == victim.TeamID; }
            catch { return false; }
            if (!sameTeam) return false;
            suppressedThisGame++;
            if (suppressedThisGame <= 5)
                Plugin.Log.LogInfo($"[ROOM-RULES] teammate hit suppressed (#{suppressedThisGame} this game) attacker=p{attacker.PlayerID} victim=p{victim.PlayerID} team={attacker.TeamID}");
            return true;
        }

        /// <summary>One line naming the non-default rules of a history row
        /// (template: FfaSettingsSummary). Empty for defaults and for rows with
        /// no record — a game born before the record is unknown, not default,
        /// and the row says nothing rather than something false.</summary>
        public static string Summary(bool hasRules, bool ff, bool sc, bool? xp = null)
        {
            if (!hasRules) return "";
            string s = "";
            if (!ff) s = I18n.Tr("Friendly fire off");
            if (sc) s = s.Length > 0 ? s + " · " + I18n.Tr("Same cards") : I18n.Tr("Same cards");
            if (xp == true) s = s.Length > 0 ? s + " · " + I18n.Tr("Solo extra pick") : I18n.Tr("Solo extra pick");
            return s;
        }
    }
}
