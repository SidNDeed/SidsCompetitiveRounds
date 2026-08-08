using HarmonyLib;
using Photon.Pun;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// FFA (free-for-all, 3-10 players) game engine. Vanilla GM_ArmsRace is
    /// hard 2-team (TeamsAlive() checks teams 0/1 only; RPCA_NextRound's
    /// switch handles winningTeamID 0/1 only), so in ffa_ rooms this class
    /// fully replaces death handling, round accounting, transitions and the
    /// pick phase. Everything is gated on EngineActive(): ffa_ room name AND
    /// a mod-issued signal (queue lobby id or the creator-stamped cr_ffa_n
    /// room prop) — a hand-crafted ffa_-named room without the prop never
    /// activates the engine (Codex design find 24), and quickplay/vanilla
    /// rooms are untouched.
    ///
    /// Scoring: every player is their own team (TeamID = slot). Last player
    /// alive wins a HALF POINT; 2 half points = a point (halves reset); first
    /// to 5 points wins the game. (Player-facing language is half point /
    /// point; the internal names stay points/rounds to match vanilla's.)
    /// After each point, everyone but the point winner picks a card — ALL AT
    /// THE SAME TIME (see the pick-phase section) — with a hard 5-card cap:
    /// picking a 6th erases the oldest ("Rolling Card Bar", reset+replay).
    /// </summary>
    internal static class FfaMode
    {
        // ── Per-lobby config (v1.36 configurable lobbies) ──
        // Was `const` — a const is INLINED into the shipped DLL, which is how
        // the July-30 destroyed-reports class happened (an old client silently
        // plays to 5 while the server expects the row's value). Now static,
        // stamped from the server's ready_join poll payload (the authoritative
        // frozen row — identical for every member), re-asserted as a room prop
        // by the master, and reset to defaults on room leave. The server
        // validates reports against ITS row regardless of what we hold.
        public static int RoundsToWin = 5;
        public const int PointsToWinRound = 2;   // not configurable
        public static int CardCap = 5;
        public static int InitialPicks = 1;      // TOTAL opening draws (base 1 + knob)
        public static int CardCandidates = 5;    // host knob 1-5 (unlocked Aug 7; was pinned 5 through v1.37)
        public static bool SameCardRule = false;
        public static bool LobbyRanked = true;
        /// <summary>Aug 6 item 10 — sudden death. While at least one LIVE player is
        /// at match point, damage between two players who are NOT at match point is
        /// suppressed, so the lobby has to deal with the leader.
        ///
        /// Whether the option is even offered is a SERVER decision: the lobby row
        /// carries `sudden_death` and the server collapses it to false unless the
        /// whole locked roster advertised a build that implements it. A pre-item-10
        /// client cannot turn it on either — see the parse in LatchConfigFromRoom.
        /// Default false, which is the inert direction on every unknown path.</summary>
        public static bool SuddenDeath = false;
        // Room prop: master re-asserts the frozen config in-room so a client
        // whose poll payload predates a late settings write still pins the
        // same rule set. Format "target:cand:picks:cap:sameCard:ranked[:suddenDeath]".
        private const string PropConfig = "cr_ffa_cfg";

        public static void SetPendingConfig(int scoreTarget, int candidates, int initialPicks,
                                            int cardCap, bool sameCard, bool ranked,
                                            bool suddenDeath = false)
        {
            RoundsToWin = Mathf.Clamp(scoreTarget, 3, 10);
            CardCandidates = Mathf.Clamp(candidates, 1, 5);
            InitialPicks = Mathf.Clamp(initialPicks, 1, 6);
            CardCap = Mathf.Clamp(cardCap, 3, 6);
            SameCardRule = sameCard;
            LobbyRanked = ranked;
            // Optional with a false default ON PURPOSE: any caller that predates
            // item 10 (or any config source that does not carry the field) turns
            // sudden death OFF rather than leaving a stale true behind.
            SuddenDeath = suddenDeath;
            Plugin.Log.LogInfo($"[FFA-CFG] pending config: target={RoundsToWin} cand={CardCandidates} picks={InitialPicks} cap={CardCap} same={SameCardRule} ranked={LobbyRanked} sudden={SuddenDeath}");
        }

        public static void ResetConfigToDefaults()
        {
            RoundsToWin = 5; CardCandidates = 5; InitialPicks = 1;
            CardCap = 5; SameCardRule = false; LobbyRanked = true;
            SuddenDeath = false;
        }

        private static void MasterPublishConfig()
        {
            try
            {
                if (!PhotonNetwork.IsMasterClient || PhotonNetwork.CurrentRoom == null) return;
                var h = new ExitGames.Client.Photon.Hashtable();
                // 7th segment appended: an old client's parser takes p[0..5] and
                // ignores the tail, so the string stays readable both ways.
                h[PropConfig] = $"{RoundsToWin}:{CardCandidates}:{InitialPicks}:{CardCap}:{(SameCardRule ? 1 : 0)}:{(LobbyRanked ? 1 : 0)}:{(SuddenDeath ? 1 : 0)}";
                PhotonNetwork.CurrentRoom.SetCustomProperties(h);
            }
            catch { }
        }

        private static void LatchConfigFromRoom()
        {
            // Latched once per game entry, idempotent (config is frozen per
            // lobby). Prefer the room prop when present; the pending statics
            // (server poll) are the fallback AND normally identical, because
            // both trace to the same frozen row.
            try
            {
                var room = PhotonNetwork.CurrentRoom;
                var raw = room?.CustomProperties != null && room.CustomProperties.ContainsKey(PropConfig)
                    ? room.CustomProperties[PropConfig] as string : null;
                if (string.IsNullOrEmpty(raw)) return;
                var p = raw.Split(':');
                if (p.Length < 6) return;
                int st, cc, ip, cap, sc, rk;
                // Aug 6 item 10: the sudden-death segment is OPTIONAL and defaults
                // to FALSE when absent. That is load-bearing, not tidiness — a
                // 6-segment string means the MASTER is on a pre-item-10 build,
                // i.e. a mixed room, and a mixed room must not run a rule half the
                // clients would ignore (they would then disagree about health).
                // Turning it off on the new clients is the only direction that
                // keeps every replica in step.
                bool sd = false;
                if (p.Length >= 7)
                {
                    int sdv;
                    if (int.TryParse(p[6], out sdv)) sd = sdv != 0;
                }
                if (int.TryParse(p[0], out st) && int.TryParse(p[1], out cc) && int.TryParse(p[2], out ip)
                    && int.TryParse(p[3], out cap) && int.TryParse(p[4], out sc) && int.TryParse(p[5], out rk))
                    SetPendingConfig(st, cc, ip, cap, sc != 0, rk != 0, sd);
            }
            catch { }
        }
        // Pick window. Two design passes, both deliberate:
        // - Bug #92-#98 killed the old 25s SILENT auto-pick (invisible timer;
        //   with one human testing three seats it fired seconds after his own
        //   pick+key-spam and read as "spamming space forces everyone's first
        //   card").
        // - Sid's July 29 correction: a player must NEVER be able to skip a
        //   pick — "miss the window, get no card" let anyone protect a
        //   finished build by ignoring the timer, defeating the rolling
        //   5-card bar. So the pick is FORCED, but legibly: the countdown is
        //   on the HUD the whole time, and when it hits zero the client
        //   confirms the card the player has HIGHLIGHTED (card 0 if never
        //   moved) and announces it in a toast. The master still closes the
        //   window without a client that never published (crashed/stalled
        //   seat) — that residual path keeps the "no card" toast.
        // Master close rule: at least PickBase, extended by PickGrace after
        // each received pick, hard-capped at PickCap.
        private const float PickBaseSeconds = 45f;
        private const float PickGraceSeconds = 20f;
        private const float PickCapSeconds = 90f;
        private const float ManifestWaitSeconds = 8f;
        // The auto-confirm fires this many seconds BEFORE the deadline so the
        // pick prop lands before the MASTER's copy of the rule closes the
        // window. Two leads (Codex round-2 find 3a): tracking a
        // master-published shared deadline the only slack needed is prop
        // latency (5s is generous); under an OLD-version master we only have
        // our LOCAL mirror, which inherits BoundedSyncUp's ~10s phase-entry
        // skew — 12s covers skew + latency there. The HUD countdown is
        // shifted by the same amount (PickSecondsLeft), so "0 on screen" and
        // "card confirmed" are the same moment either way. Constants stay
        // 45/90 for mixed-version lobbies.
        private const float AutoPickLeadSeconds = 5f;
        private const float AutoPickLeadFallbackSeconds = 12f;

        // Photon property keys (FFA pick-sync protocol; all values ASCII).
        private const string PropCycle = "cr_ffa_cyc";   // room: "{game}:{cycle}:{pid,pid,...}"
        private const string PropResult = "cr_ffa_res";  // room: "{game}:{cycle}:{pid=Card|pid=Card}"
        // Master-published authoritative deadline in PHOTON SERVER TIME
        // (Codex Jul-29 finds 3/6): per-client deadline mirrors inherit the
        // full phase-entry skew (BoundedSyncUp tolerates ~10s), which could
        // put a slow-entering client's auto-confirm AFTER the master's close.
        // Sharing the deadline through the server clock collapses the skew to
        // prop latency, which the 5s auto-pick lead covers many times over.
        // A NEW prop key: old clients ignore it and keep their local mirror
        // (their behaviour is unchanged either way — they have no auto-pick).
        private const string PropDeadline = "cr_ffa_dl"; // room: "{game}:{cycle}:{photonTime}"
        // Player prop: "{roomNonce}:{game}:{cycle}:{CardName}". Review find 4:
        // Photon PLAYER properties survive room changes and every new FFA room
        // restarts at game 1/cycle 1 — without the room nonce, a stale "1:1:"
        // pick from a previous FFA would be collected as this room's pick and
        // the wrong card applied. The nonce is the room name (server-issued,
        // unique per lobby).
        private const string PropPick = "cr_ffa_pk";

        // ── Per-game state (reset in OnGameStart) ──
        private static readonly Dictionary<int, int> points = new Dictionary<int, int>();       // live points, by TeamID
        private static readonly Dictionary<int, int> rounds = new Dictionary<int, int>();       // round wins
        private static readonly Dictionary<int, int> pointsTotal = new Dictionary<int, int>();  // cumulative point wins
        private static readonly Dictionary<int, int> kills = new Dictionary<int, int>();        // kill credits (placement tiebreak)
        private static readonly List<string> timelineEvents = new List<string>();               // "slot[R][G]" per half point

        public static string TimelineString => string.Join(",", timelineEvents.ToArray());
        private static readonly Dictionary<int, List<CardInfo>> decks = new Dictionary<int, List<CardInfo>>();  // live rolling deck
        private static readonly Dictionary<int, List<MatchTracker.CardPickData>> pickHistory =
            new Dictionary<int, List<MatchTracker.CardPickData>>();  // ALL picks incl. rolled-off
        private static readonly Dictionary<int, FfaBaseline> baselines = new Dictionary<int, FfaBaseline>();
        // Leavers mid-game: steam -> (name, slot, rounds, points) at leave time.
        public static readonly Dictionary<string, FfaLeaver> Leavers = new Dictionary<string, FfaLeaver>();

        private static int gameNumber = 0;
        private static int cycleNumber = 0;
        private static bool isTransitioning = false;
        private static bool pointLatched = false;      // master's point-resolution latch (find 17)
        private static bool gameOverFired = false;
        private static bool freshGameCancelFired = false;
        private static float matchStartRealtime = 0f;
        // A rolling rebuild applies card stats silently, then publishes one
        // authoritative card-bar/currentCards snapshot at the end. Suppress
        // the incremental AddCard calls while that snapshot is being built.
        private static readonly HashSet<int> deckViewRebuilds = new HashSet<int>();
        // Pick-window state for the HUD countdown (CompetitiveUI reads these).
        private static bool pickPhaseActive = false;
        private static float pickDeadlineRealtime = 0f;
        // True while pickDeadlineRealtime tracks the master-published shared
        // deadline (drives which auto-pick lead applies).
        private static bool pickDeadlineShared = false;
        private static bool localPickOpen = false;     // local player's own pick UI is up

        public static bool PickPhaseActive => pickPhaseActive;
        public static bool LocalPickOpen => localPickOpen;
        /// <summary>Seconds until the local pick auto-confirms — the real
        /// deadline minus AutoPickLeadSeconds, so the HUD's "0" is exactly the
        /// moment the highlighted card locks in. (The master's own unshifted
        /// copy of the rule is what actually closes the window.)</summary>
        private static float CurrentAutoPickLead =>
            pickDeadlineShared ? AutoPickLeadSeconds : AutoPickLeadFallbackSeconds;
        public static float PickSecondsLeft =>
            pickPhaseActive ? Mathf.Max(0f, pickDeadlineRealtime - CurrentAutoPickLead - Time.realtimeSinceStartup) : 0f;
        /// <summary>Unshifted seconds until the window actually closes — for
        /// surfaces that describe the WINDOW (the non-picker banner), not the
        /// auto-confirm moment (Codex Jul-29 find 11).</summary>
        public static float PickWindowSecondsLeft =>
            pickPhaseActive ? Mathf.Max(0f, pickDeadlineRealtime - Time.realtimeSinceStartup) : 0f;

        /// <summary>Local player's offered candidates this GAME (§10 offer
        /// baseline — cleared in OnGameStart/OnRoomLeft, sent on the report's
        /// own entry only; other seats' offers are unknowable here when the
        /// same-card rule is off).</summary>
        public class OfferRecord { public string CardName; public int Round; public bool Picked; }
        public static readonly List<OfferRecord> LocalOffers = new List<OfferRecord>();

        public class FfaLeaver
        {
            public string displayName;
            public int slot, roundsWon, pointsTotal, kills;
            // Which game they left DURING — distinguishes "played part of
            // this game" (rated, even at zero score) from "absent ghost
            // carried for the roster check" (never rated).
            public int leftGameNumber;
        }

        private class FfaBaseline
        {
            public bool captured;
            public float gravityForce, regeneration;
            public int jumps;
            public float ammoReg;
            public GameObject projectile;
        }

        // ── Gates ──

        /// <summary>The FFA engine only runs in a server-issued ffa_ room: the
        /// room name matches AND (we hold a queue lobby id OR the creator
        /// stamped cr_ffa_n). Room name alone is spoofable; the prop/lobby
        /// requirement keeps hand-made rooms on (broken) vanilla behavior
        /// rather than activating gameplay patches.</summary>
        public static bool EngineActive()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return false;
                if (!(PhotonNetwork.CurrentRoom.Name ?? "").StartsWith("ffa_")) return false;
                if (!string.IsNullOrEmpty(ApiClient.ActiveFfaLobbyId)) return true;
                var p = PhotonNetwork.CurrentRoom.CustomProperties;
                return p != null && p.ContainsKey("cr_ffa_n");
            }
            catch { return false; }
        }

        public static int GameNumber => gameNumber;
        public static bool InFfaMatch => EngineActive() && matchStartRealtime > 0f;
        public static float MatchStartRealtime => matchStartRealtime;

        // ── Score access ──

        public static int RoundsFor(int teamId) { return rounds.TryGetValue(teamId, out var v) ? v : 0; }
        public static int PointsFor(int teamId) { return points.TryGetValue(teamId, out var v) ? v : 0; }

        /// <summary>Spectator-only (SpectatorSync boundary apply): overwrite
        /// the score tables with the master's snapshot values. FFA accounting
        /// is INCREMENTAL per client (HandleNextRound applies deltas from the
        /// winner broadcast), so a late joiner starts at zero and would be
        /// wrong forever without this seed; after it, the normal broadcasts
        /// keep the tables current. Never called on a fighter.</summary>
        internal static void SpectatorSeedScores(int[] roundsByTeam, int[] pointsByTeam)
        {
            try
            {
                if (!RoomActors.LocalIsSpectator) return;
                rounds.Clear();
                points.Clear();
                if (roundsByTeam != null)
                    for (int t = 0; t < roundsByTeam.Length; t++) rounds[t] = roundsByTeam[t];
                if (pointsByTeam != null)
                    for (int t = 0; t < pointsByTeam.Length; t++) points[t] = pointsByTeam[t];
                // Codex r2 find 17: the multi-player FFA score strip gates on
                // InFfaMatch (= EngineActive && matchStartRealtime > 0), and
                // no participant path ever stamps it on a spectator — the
                // 10-player HUD silently fell back to a 2-team line. UI-only:
                // duration/report consumers of this value are all
                // spectator-guarded.
                if (matchStartRealtime <= 0f) matchStartRealtime = Time.realtimeSinceStartup;
            }
            catch { }
        }
        public static int PointsTotalFor(int teamId) { return pointsTotal.TryGetValue(teamId, out var v) ? v : 0; }
        public static int KillsFor(int teamId) { return kills.TryGetValue(teamId, out var v) ? v : 0; }

        // ── Match point + sudden death (Aug 6 item 10) ─────────────────────────

        /// <summary>True when this team is HALF A POINT from winning the game:
        /// one point short of the target, and holding the first of the two half
        /// points that convert into it. Reads only the score dictionaries, which
        /// HandleNextRound advances from the master's single RpcTarget.All
        /// broadcast — so the answer is identical on every client.</summary>
        public static bool IsAtMatchPoint(int teamId)
        {
            return RoundsFor(teamId) == RoundsToWin - 1
                && PointsFor(teamId) == PointsToWinRound - 1;
        }

        /// <summary>Fill <paramref name="into"/> with the team ids currently at
        /// match point, in ascending slot order (deterministic for display).
        /// Caller-owned buffer — no per-frame allocation (#162).</summary>
        public static void CollectMatchPointTeams(List<int> into)
        {
            if (into == null) return;
            into.Clear();
            try
            {
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return;
                foreach (var p in pm.players)
                {
                    if (p == null || p.gameObject == null || p.data == null) continue;
                    int t = p.TeamID;
                    if (!IsAtMatchPoint(t)) continue;
                    if (!into.Contains(t)) into.Add(t);
                }
                into.Sort();
            }
            catch { }
        }

        /// <summary>Sudden-death damage gate. True = this damage event must be
        /// SUPPRESSED entirely.
        ///
        /// Rule: while at least one LIVE player is at match point, two players who
        /// are BOTH not at match point cannot damage each other. Damage to or from
        /// a match-point player is always allowed, as is out-of-bounds damage
        /// (vanilla passes a null dealer there) and self damage.
        ///
        /// CROSS-CLIENT DETERMINISM. Every input is replicated:
        ///  * <c>SuddenDeath</c> — the frozen lobby config, from the server row and
        ///    re-asserted by the master as one room property.
        ///  * rounds / points — advanced only inside <c>HandleNextRound</c>, which
        ///    runs from the master's <c>RPCA_NextRound</c> RpcTarget.All broadcast.
        ///  * <c>TeamID</c> — vanilla's networked player assignment.
        ///  * <c>data.dead</c> — set by <c>RPCA_Die</c>, also RpcTarget.All.
        /// And the gated method itself is reached identically everywhere:
        /// <c>CallTakeDamage</c> RPCs <c>RPCA_SendTakeDamage</c> to All
        /// (HealthHandler.cs:208-236), so every client runs <c>DoDamage</c> for the
        /// same hit with the same dealer/victim — the same property FFA kill credit
        /// and damage telemetry already rely on.
        ///
        /// Residual: <c>data.dead</c> lands at RPC-delivery time, so a hit inside
        /// that ~one-ping window after the last match-point player dies can be
        /// suppressed on one replica and applied on another. That window is the
        /// same one vanilla block/DOT already lives with, it needs the last
        /// match-point player to die in the same instant as an unrelated hit, and
        /// closing it would need a round trip per bullet.</summary>
        public static bool SuddenDeathSuppresses(Player dealer, Player victim)
        {
            try
            {
                if (!SuddenDeath) return false;
                if (!EngineActive()) return false;
                if (dealer == null || victim == null) return false;
                if (dealer.data == null || victim.data == null) return false;
                if (dealer.TeamID == victim.TeamID) return false;          // self / own-team
                if (IsAtMatchPoint(dealer.TeamID)) return false;
                if (IsAtMatchPoint(victim.TeamID)) return false;

                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return false;
                foreach (var p in pm.players)
                {
                    if (p == null || p.gameObject == null || p.data == null) continue;
                    if (p.data.dead) continue;
                    if (IsAtMatchPoint(p.TeamID)) return true;   // a live leader → FF off
                }
                return false;                                     // all leaders dead → normal
            }
            catch { return false; }
        }

        /// <summary>Kills as used for ORDERING, saturated at the report bound.
        /// Full-wipe battles advance no point, so raw kills are structurally
        /// unbounded — any transport cap below the ceiling would let the
        /// client order 2001-vs-2000 while the signed report carries a tie
        /// (Codex Aug-3 r2 find 3). Making saturation part of the RULE keeps
        /// client and server placement identical by definition: above the
        /// bound, kills compare equal everywhere. Display keeps raw counts.</summary>
        public const int KillsCompareCap = 2000;
        public static int KillsRankFor(int teamId)
        {
            int k = KillsFor(teamId);
            return k > KillsCompareCap ? KillsCompareCap : k;
        }

        /// <summary>Placement order: points (rounds) desc, then ALL half
        /// points earned incl. spent ones (pointsTotal) desc, then KILLS desc
        /// (the second tie-break — Sid approved 2026-08-03). 0 = tied
        /// placement (shares a place, competition ranking). Used by the
        /// game-over placement and the pairwise session records. Kills may
        /// rank here because this build SIGNS them in the v2 ffa: canonical —
        /// "signed" means the value is attributable to the reporting build
        /// (same trust class as rounds/points, which the reporter equally
        /// attests), NOT proof of gameplay truth. Server honors the kills
        /// tie-break only when the WHOLE roster advertised a v2-signing build
        /// at lobby lock, so in a mixed-version lobby this local mirror can
        /// split a tie the server shares. That divergence PERSISTS locally
        /// (the "placed #N" toast, session placements CSV and pairwise W/L
        /// are written before the report and only the elected reporter ever
        /// sees the server response — Codex Aug-3 r2 find 5): session-scoped
        /// display and local tallies only, never ratings/gold, and the window
        /// closes at the MIN_MOD_VERSION raise.</summary>
        public static int ComparePlacement(int teamA, int teamB)
        {
            int c = RoundsFor(teamB).CompareTo(RoundsFor(teamA));
            if (c != 0) return c;
            c = PointsTotalFor(teamB).CompareTo(PointsTotalFor(teamA));
            if (c != 0) return c;
            return KillsRankFor(teamB).CompareTo(KillsRankFor(teamA));
        }

        // ── Damage dealt + per-player timelines (bug #127 / #130) ────────
        // Damage DEALT was tracked nowhere: the client only ever accumulated
        // damage TAKEN (GameStateWatcher.LocalDamageTakenThisMatch), and the
        // whole database had no damage column at all. It is attributable
        // though: vanilla's HealthHandler.DoDamage receives the dealing
        // `Player`, and because CallTakeDamage RPCs to All, EVERY client sees
        // every attributed hit — the same property that lets kill credit be
        // computed locally. So the reporter alone can produce a full
        // damage-dealt table for all N players with no new peer heartbeat.
        private static readonly Dictionary<int, float> damageDealt = new Dictionary<int, float>();
        // Cumulative CSV samples per team id, taken on GameStateWatcher's
        // existing 3s telemetry cadence so the x-axis matches hit/block.
        private static readonly Dictionary<int, List<int>> killTimeline = new Dictionary<int, List<int>>();
        private static readonly Dictionary<int, List<int>> damageTimeline = new Dictionary<int, List<int>>();
        private const int FFA_TIMELINE_CAP = 128;   // 6.4 min at 3s, matches hit/block

        public static int DamageDealtFor(int teamId)
        {
            float v;
            return damageDealt.TryGetValue(teamId, out v) ? (int)v : 0;
        }

        /// <summary>Credits damage to the dealer. Called from the
        /// HealthHandler.DoDamage patch on every client. Self-damage is
        /// excluded (vanilla passes the victim as the dealer for recoil/DOT
        /// self-hits) and so is anything after game over, so the number always
        /// matches the score snapshot the report carries.</summary>
        public static void RecordDamageDealt(Player dealer, Player victim, float amount)
        {
            try
            {
                if (gameOverFired) return;
                if (dealer == null || victim == null) return;
                if (dealer.TeamID == victim.TeamID) return;
                if (!(amount > 0f) || amount > 10000f) return;   // same sanity bound as damage-taken
                float cur;
                damageDealt.TryGetValue(dealer.TeamID, out cur);
                damageDealt[dealer.TeamID] = cur + amount;
            }
            catch { }
        }

        /// <summary>One cumulative sample per player, on the 3s cadence.
        /// Driven from GameStateWatcher's existing telemetry tick so all FFA
        /// series share one x-axis.</summary>
        public static void SampleTimelines()
        {
            try
            {
                if (!EngineActive()) return;
                var pm = PlayerManager.instance;
                if (pm?.players == null) return;
                for (int i = 0; i < pm.players.Count; i++)
                {
                    var p = pm.players[i];
                    if (p == null) continue;
                    int tid = p.TeamID;
                    List<int> kl;
                    if (!killTimeline.TryGetValue(tid, out kl)) { kl = new List<int>(32); killTimeline[tid] = kl; }
                    if (kl.Count < FFA_TIMELINE_CAP) kl.Add(KillsFor(tid));
                    List<int> dl;
                    if (!damageTimeline.TryGetValue(tid, out dl)) { dl = new List<int>(32); damageTimeline[tid] = dl; }
                    if (dl.Count < FFA_TIMELINE_CAP) dl.Add(DamageDealtFor(tid));
                }
            }
            catch { }
        }

        public static string KillTimelineFor(int teamId)
        {
            List<int> l;
            if (!killTimeline.TryGetValue(teamId, out l) || l.Count == 0) return null;
            return string.Join(",", l.ConvertAll(v => v.ToString()).ToArray());
        }

        public static string DamageTimelineFor(int teamId)
        {
            List<int> l;
            if (!damageTimeline.TryGetValue(teamId, out l) || l.Count == 0) return null;
            return string.Join(",", l.ConvertAll(v => v.ToString()).ToArray());
        }

        /// <summary>Kill credit at death time: the victim's
        /// lastSourceOfDamage (vanilla sets it in HealthHandler.TakeDamage on
        /// every client) unless it's the victim themselves or already gone.
        /// Suicides with no prior damager credit nobody.</summary>
        public static void RecordKillFor(Player killed)
        {
            try
            {
                // End-screen kills don't count (the report snapshot was
                // already taken at game over).
                if (gameOverFired) return;
                if (killed == null || killed.data == null) return;
                var src = killed.data.lastSourceOfDamage;
                if (src == null || src.gameObject == null || src.data == null) return;
                if (src.TeamID == killed.TeamID) return;
                kills[src.TeamID] = KillsFor(src.TeamID) + 1;
            }
            catch { }
        }

        /// <summary>lastSourceOfDamage persists across rounds (nothing vanilla
        /// clears it), so an untouched fall in round N would credit round
        /// N-1's damager. Cleared at every round/battle start.</summary>
        private static void ClearLastDamageSources()
        {
            try
            {
                var pm = PlayerManager.instance;
                if (pm?.players == null) return;
                foreach (var p in pm.players)
                {
                    if (p == null || p.gameObject == null || p.data == null) continue;
                    p.data.lastSourceOfDamage = null;
                }
            }
            catch { }
        }
        public static List<MatchTracker.CardPickData> PickHistoryFor(int teamId)
        {
            return pickHistory.TryGetValue(teamId, out var v) ? v : new List<MatchTracker.CardPickData>();
        }

        /// <summary>Current overall leader (rounds, then LIVE points, then
        /// kills) or null on a full tie/no score. Used by the crown patch.
        /// DELIBERATE divergence from ComparePlacement (Codex Aug-3 find 5):
        /// the crown tracks the CURRENT round standing via PointsFor (live,
        /// spendable), not the placement-authoritative PointsTotalFor — the
        /// mid-game crown answers "who is winning right now", not "who would
        /// place first if the game ended". The zero-score guard also means a
        /// kills-only leader (0 rounds, 0 live points) shows no crown; both
        /// are display-only and never feed the report.</summary>
        public static Player CurrentLeader()
        {
            try
            {
                if (PlayerManager.instance == null) return null;
                Player best = null;
                int bestR = -1, bestP = -1, bestK = -1;
                bool tie = false;
                foreach (var p in PlayerManager.instance.players)
                {
                    if (p == null || p.gameObject == null || p.data == null) continue;
                    int r = RoundsFor(p.TeamID), pt = PointsFor(p.TeamID), k = KillsRankFor(p.TeamID);
                    if (r > bestR || (r == bestR && pt > bestP)
                        || (r == bestR && pt == bestP && k > bestK))
                    {
                        best = p; bestR = r; bestP = pt; bestK = k; tie = false;
                    }
                    else if (r == bestR && pt == bestP && k == bestK) tie = true;
                }
                if (tie || (bestR == 0 && bestP == 0)) return null;
                return best;
            }
            catch { return null; }
        }

        /// <summary>Compact score line for the IMGUI strip: one entry per live
        /// player, sorted by (rounds, LIVE points, kills) desc — the crown's
        /// current-standing order, deliberately NOT ComparePlacement's
        /// (which uses cumulative pointsTotal). Log/diagnostic display only.
        /// ASCII only (#47).</summary>
        public static string ScoreLine()
        {
            try
            {
                if (PlayerManager.instance == null) return "";
                var entries = new List<(string name, int r, int p, int k, bool dead)>();
                foreach (var pl in PlayerManager.instance.players)
                {
                    if (pl == null || pl.gameObject == null || pl.data == null) continue;
                    string nm = "P" + pl.PlayerID;
                    try { nm = pl.data.view?.Owner?.NickName ?? nm; } catch { }
                    if (nm.Length > 12) nm = nm.Substring(0, 12);
                    entries.Add((nm, RoundsFor(pl.TeamID), PointsFor(pl.TeamID),
                                 KillsRankFor(pl.TeamID), pl.data.dead));
                }
                entries.Sort((a, b) => b.r != a.r ? b.r.CompareTo(a.r)
                    : b.p != a.p ? b.p.CompareTo(a.p) : b.k.CompareTo(a.k));
                var sb = new System.Text.StringBuilder();
                foreach (var e in entries)
                {
                    if (sb.Length > 0) sb.Append("   ");
                    sb.Append(e.name).Append(' ').Append(e.r).Append('R');
                    if (e.p > 0) sb.Append('+').Append(e.p);
                }
                return sb.ToString();
            }
            catch { return ""; }
        }

        // ── Spawn grace (bug #119) ─────────────────────────────────────────
        // "Some people don't get to spawn and react before being shot in FFA,
        // can we give a 1 second moment when you spawn in where you can't
        // shoot (just for FFA)."
        //
        // NO-FIRE, not invulnerability. Every client gates its own player, and
        // Gun.FireBurst only spawns a projectile under CheckIsMine() — so a
        // blocked shot never exists on ANY client and there is no desync
        // surface. Invulnerability would have to be suppressed identically in
        // HealthHandler.TakeDamage on every client AND still wouldn't stop
        // knockback, so an "invulnerable" player could still be launched out
        // of bounds.
        //
        // Armed at the rising edge of the LOCAL player's isPlaying+simulated,
        // which is the instant vanilla hands control back at the END of
        // PlayerManager.Move (~0.93s, measured). Deliberately NOT armed at
        // `battleOngoing = true`: this engine sets that 0.6-0.9s EARLIER,
        // while players are still being flown to their spawn points and
        // physically cannot fire, so a window anchored there would deliver
        // ~0.37s of protection per round and ~0.07s on game 1.
        public const float SpawnGraceSeconds = 1.0f;
        private static float spawnGraceUntil = 0f;
        private static bool lastLocalPlaying = false;

        /// <summary>True while the FFA post-spawn no-fire window is open.</summary>
        public static bool SpawnGraceActive =>
            spawnGraceUntil > 0f && Time.realtimeSinceStartup < spawnGraceUntil && EngineActive();

        public static float SpawnGraceLeft =>
            SpawnGraceActive ? Mathf.Max(0f, spawnGraceUntil - Time.realtimeSinceStartup) : 0f;

        /// <summary>Per-frame edge detector. realtimeSinceStartup is monotonic
        /// and timescale-independent, so the window expires even in slow motion
        /// (#221), even if the transition coroutine is killed by a leaver
        /// (#222), and even if the round ends inside it — there is no state to
        /// tear down and no way to strand a player unable to shoot.</summary>
        public static void TickSpawnGrace()
        {
            try
            {
                if (!EngineActive()) { lastLocalPlaying = false; return; }
                bool playing = false;
                var pm = PlayerManager.instance;
                if (pm?.players != null)
                {
                    foreach (var po in pm.players)
                    {
                        if (po == null || po.gameObject == null) continue;
                        if (po.data?.view == null || !po.data.view.IsMine) continue;
                        playing = po.data.isPlaying && po.data.playerVel != null
                                  && po.data.playerVel.simulated;
                        break;
                    }
                }
                if (playing && !lastLocalPlaying)
                    spawnGraceUntil = Time.realtimeSinceStartup + SpawnGraceSeconds;
                lastLocalPlaying = playing;
            }
            catch { }
        }

        private static void ClearSpawnGrace()
        {
            spawnGraceUntil = 0f;
            lastLocalPlaying = false;
        }

        // NOTE on the arming-order race (Codex round-3 residual 12, ACCEPTED):
        // on the exact frame the edge detector arms the window, a component
        // Update that ran earlier in that frame can still act. The obvious
        // "arm earlier" fixes are all worse: Revive and battleOngoing both
        // fire during the fly-in, and anchoring there burns the window to
        // ~0.37s of real protection (the original #119 measurement). The slop
        // is one frame, defensive-input only, and the identical slop has
        // existed for FIRE suppression since #119 with zero field reports.

        // ── Lifecycle ──

        /// <summary>New game in the room (game 1 AND rematches — invoked from
        /// the DoStartGame replacement, which vanilla runs on both paths).</summary>
        public static void OnGameStart()
        {
            gameNumber++;
            cycleNumber = 0;
            points.Clear(); rounds.Clear(); pointsTotal.Clear(); kills.Clear();
            // Per-game, same lifetime as kills (bug #127/#130 telemetry).
            damageDealt.Clear(); killTimeline.Clear(); damageTimeline.Clear();
            timelineEvents.Clear();
            decks.Clear(); pickHistory.Clear(); baselines.Clear();
            // Leavers PERSIST across rematches in the same room (Codex review
            // find 3): the server froze the roster at lock, so every game's
            // report must still cover the departed member or it 403s. Their
            // tallies zero out per game — the server "ghosts" all-zero
            // left_early entries (no rating/XP), they just hold their roster
            // slot. Cleared only in OnRoomLeft.
            foreach (var kv in Leavers)
            {
                kv.Value.roundsWon = 0;
                kv.Value.pointsTotal = 0;
                kv.Value.kills = 0;
            }
            isTransitioning = false;
            pointLatched = false;
            gameOverFired = false;
            ClearSpawnGrace();
            freshGameCancelFired = false;
            deckViewRebuilds.Clear();
            matchStartRealtime = Time.realtimeSinceStartup;
            // v1.36 config + same-card sequence lifecycle. Config latch is
            // idempotent (frozen per lobby); the seed publish is derived so a
            // master-migration republish can never fork it.
            LatchConfigFromRoom();
            try { MasterPublishConfig(); } catch { }
            try { FfaCardSequence.OnGameStart(); } catch { }
            // In-room capability republish WITH the pool hash (find 3): the
            // pre-join advert can only carry the level; the hash needs the
            // loaded card pool. Every client does this, so a mixed-pool room
            // fails the gate on every seat uniformly.
            try { FfaCardSequence.PublishCapabilityWithHash(); } catch { }
            try { FfaCardSequence.MasterPublishSeed(gameNumber); } catch { }
            LocalOffers.Clear();
            // §8 settings banner during load-in — reads the statics the
            // engine itself runs on, AFTER the latch, so it cannot disagree
            // with the rules in force.
            try
            {
                string cfgLine = (InitialPicks == 1
                        ? I18n.TrF("FIRST TO {0}   -   {1} OPENING DRAW   -   {2}-CARD HAND", RoundsToWin, InitialPicks, CardCap)
                        : I18n.TrF("FIRST TO {0}   -   {1} OPENING DRAWS   -   {2}-CARD HAND", RoundsToWin, InitialPicks, CardCap))
                    // Aug 7 item 5: only surfaced when non-default, like the
                    // history tail — the banner stays short for stock lobbies.
                    + (CardCandidates != 5 ? I18n.TrF("   -   {0}-CARD DRAW", CardCandidates) : "")
                    + (SameCardRule ? I18n.Tr("   -   SAME CARDS FOR EVERYONE") : "")
                    + (LobbyRanked ? "" : I18n.Tr("   -   CASUAL (UNRATED)"));
                CompetitiveUI.ShowFfaSettingsBanner(cfgLine, 9f);
            }
            catch { }
            // Review find 1 (critical): FFA can't ride the vanilla match-start
            // path (it keys on a log marker + the vanilla p1/p2 fields, which
            // never move here), so arm the watcher's per-game state explicitly
            // — on EVERY game, rematches included.
            try { GameStateWatcher.OnFfaMatchStarted(); }
            catch (Exception ex) { Plugin.Log.LogError($"[FFA] match-start hook: {ex.Message}"); }
            Plugin.Log.LogInfo($"[FFA] Game {gameNumber} starting (players needed: {Diag2v2.PlayersNeeded()})");
        }

        public static void OnRoomLeft()
        {
            // Defense in depth for review find 4: drop our pick prop so it can
            // never be read in a later room (the room-nonce prefix is the real
            // guard; this keeps the property table clean).
            try
            {
                var h = new ExitGames.Client.Photon.Hashtable();
                h[PropPick] = "";
                PhotonNetwork.LocalPlayer?.SetCustomProperties(h);
            }
            catch { }
            matchStartRealtime = 0f;
            gameNumber = 0;
            points.Clear(); rounds.Clear(); pointsTotal.Clear(); kills.Clear();
            // Per-game, same lifetime as kills (bug #127/#130 telemetry).
            damageDealt.Clear(); killTimeline.Clear(); damageTimeline.Clear();
            timelineEvents.Clear();
            decks.Clear(); pickHistory.Clear(); baselines.Clear();
            Leavers.Clear();
            isTransitioning = false;
            gameOverFired = false;
            freshGameCancelFired = false;
            deckViewRebuilds.Clear();
            pickPhaseActive = false;
            pickDeadlineRealtime = 0f;
            pickDeadlineShared = false;
            localPickOpen = false;
            try { FfaMapScale.Reset(); } catch { }
            try { FfaSpawnPoints.Clear(); } catch { }
            ClearSpawnGrace();
            try { FfaCardSequence.OnRoomLeft(); } catch { }
            ResetConfigToDefaults();
            LocalOffers.Clear();
            GameStartedInRoom = false;
        }

        /// <summary>Capture a leaver's tallies before Photon destroys their
        /// player object. Called from GameStateWatcher's OnPlayerLeftRoom.</summary>
        public static void RecordLeaver(string steamId, string displayName, int teamId)
        {
            if (string.IsNullOrEmpty(steamId)) return;
            // Overwrite, never early-return (review find 11): a player who
            // left, rejoined and left AGAIN must snapshot their CURRENT
            // tallies — the stale first record would misplace them. A
            // duplicate callback for the same leave writes identical data.
            Leavers[steamId] = new FfaLeaver
            {
                displayName = displayName ?? "Player",
                slot = teamId,
                roundsWon = RoundsFor(teamId),
                pointsTotal = PointsTotalFor(teamId),
                kills = KillsFor(teamId),
                leftGameNumber = gameNumber,
            };
            Plugin.Log.LogInfo($"[FFA] leaver recorded: {steamId} slot={teamId} r={RoundsFor(teamId)}");
        }

        // ── Death handling / round accounting ──

        /// <summary>Bug #99: vanilla keeps a departed player's DESTROYED
        /// Player in PlayerManager.players — vanilla never needed cleanup
        /// because any leave tears the whole room down, which FFA suppresses.
        /// Every later vanilla pass over the list (MovePlayers, Move,
        /// RevivePlayers) then NREs; the RevivePlayers throw landed inside
        /// FfaTransition and killed the coroutine before DoSpeedUp — stuck
        /// slow motion, nobody respawning. Purge fake-null entries instead.
        /// Every client runs the same purge, so the positional
        /// spawnPoints[i]-players[i] pairing stays identical everywhere.</summary>
        public static void PurgeDepartedPlayers(string reason)
        {
            try
            {
                var pm = PlayerManager.instance;
                if (pm?.players == null) return;
                int removed = pm.players.RemoveAll(p => p == null || p.gameObject == null || p.data == null);
                try { PlayerAssigner.instance?.players?.RemoveAll(cd => cd == null || cd.gameObject == null); } catch { }
                if (removed > 0)
                    Plugin.Log.LogInfo($"[FFA] purged {removed} departed player entry(ies) ({reason})");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] purge failed: {ex.Message}"); }
        }

        /// <summary>Alive = not dead, object alive, owner still connected.</summary>
        private static List<Player> AlivePlayers()
        {
            var alive = new List<Player>();
            if (PlayerManager.instance == null) return alive;
            foreach (var p in PlayerManager.instance.players)
            {
                if (p == null || p.gameObject == null || p.data == null) continue;   // Unity fake-null = destroyed/left
                if (p.data.dead) continue;
                alive.Add(p);
            }
            return alive;
        }

        /// <summary>A peer left mid-battle. Photon destroys their player
        /// objects moments after the callback, so the alive-count is checked
        /// on a short delay: if the leaver was one of the last two standing,
        /// the survivor must win the point (no death event ever fires for a
        /// leaver — without this the round would hang).</summary>
        public static IEnumerator CheckRoundAfterLeave()
        {
            yield return new WaitForSecondsRealtime(0.7f);
            if (!EngineActive()) yield break;
            PurgeDepartedPlayers("after leave");
            int remaining = 0;
            try { remaining = RoomActors.ActiveFighterCount(); } catch { }   // spectators are not fighters (census)

            bool battle = false;
            try { battle = GameManager.instance != null && GameManager.instance.battleOngoing; } catch { }

            // Bug #114 item 2: a fresh game that loses quorum before two
            // half-points have been scored has no meaningful placement yet.
            // Cancel before HandlePlayerDied can award the survivor a point.
            // battleOngoing keeps this out of the game-over/rematch flow,
            // whose own below-minimum checks already own the sitting.
            int scored = TotalPointsScored();
            if (!gameOverFired && battle && remaining > 0 && remaining < 3 && scored < 2)
            {
                if (!freshGameCancelFired)
                {
                    freshGameCancelFired = true;
                    LeaveBelowMinimum(
                        $"[FFA] fresh game cancelled - {remaining} player(s), {scored} half-point(s) scored",
                        I18n.Tr("FFA cancelled - not enough players for a fresh game."));
                }
                yield break;
            }

            if (!gameOverFired)
            {
                // Last player standing: nobody else can die, so no PlayerDied
                // ever fires — resolve the round from the alive count.
                if (battle)
                {
                    var gm = GM_ArmsRace.instance;
                    if (gm != null) HandlePlayerDied(gm);   // internally exception-safe
                }
            }

            // Review find 6: we suppressed vanilla's teardown, so when we are
            // the only client left the game can't continue — end it here (the
            // report already went out if a game-over resolved above) and go
            // back to the menu ourselves rather than sitting in a dead room.
            if (remaining <= 1)
            {
                yield return new WaitForSecondsRealtime(2.5f);   // let a resolving point finish
                if (!EngineActive()) yield break;
                try { remaining = RoomActors.ActiveFighterCount(); } catch { }   // census: a spectator must not keep the FFA "alive"
                if (remaining > 1) yield break;
                Plugin.Log.LogInfo("[FFA] last player in the room — ending the FFA and returning to menu");
                try
                {
                    CompetitiveUI.ShowNotification("Everyone else left the FFA — returning to menu.",
                        new Color(1f, 0.8f, 0.4f), 7f);
                }
                catch { }
                try { NetworkConnectionHandler.instance.NetworkRestart(); }
                catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] NetworkRestart failed: {ex.Message}"); }
            }
        }

        /// <summary>PlayerDied replacement. When <=1 players remain alive the
        /// MASTER (with a one-shot latch — two deaths in one physics step must
        /// not fire two RPCs, Codex design find 17) broadcasts the round
        /// result through vanilla's own RPCA_NextRound RPC; winningTeamID
        /// carries the surviving team (or -1 for a full wipe = replay point).</summary>
        public static void HandlePlayerDied(GM_ArmsRace gm)
        {
            try
            {
                // End-screen / post-game-over kills must never latch another
                // round (the EndScreenKill vanilla-fix class of bug — a stray
                // kill after the decisive point would re-fire the round RPC).
                if (gameOverFired || !GameManager.instance.battleOngoing) return;
                var alive = AlivePlayers();
                if (alive.Count > 1) return;
                // Spectator gate BEFORE any state mutation (Codex r2 find 9:
                // DoSlowDown ran first, and with the participant transition
                // suppressed nothing ever restored timescale on the
                // spectator). Also keeps a transiently-master spectator from
                // latching/broadcasting a round result.
                if (RoomActors.LocalIsSpectator) return;
                TimeHandler.instance.DoSlowDown();
                if (!PhotonNetwork.IsMasterClient || pointLatched || isTransitioning) return;
                // Review find 5: vanilla invokes PlayerDied per victim, so a
                // double-KO (same explosion) reaches here on the FIRST death
                // with the second victim still counted alive — latching them
                // as winner. Latch the SLOT now (so no second callback can
                // race in), but decide the winner at end of frame, after every
                // death in this physics step has landed.
                pointLatched = true;
                if (Plugin.Instance != null) Plugin.Instance.StartCoroutine(ResolvePointEndOfFrame(gm));
                else ResolvePointNow(gm);
            }
            catch (Exception ex) { Plugin.Log.LogError($"[FFA] HandlePlayerDied: {ex.Message}"); }
        }

        /// <summary>Winner id meaning "nobody survived, because the last
        /// players alive killed each other". Distinct from -1, which is the
        /// generic no-winner value every other path uses (a leaver ending the
        /// round, an unresolved state). Both are < 0, so every award gate keeps
        /// treating them identically — only the announcement differs.</summary>
        private const int WINNER_DOUBLE_KO = -2;

        private static IEnumerator ResolvePointEndOfFrame(GM_ArmsRace gm)
        {
            yield return new WaitForEndOfFrame();
            ResolvePointNow(gm);
        }

        private static void ResolvePointNow(GM_ArmsRace gm)
        {
            try
            {
                if (gameOverFired || isTransitioning) { pointLatched = false; return; }
                var alive = AlivePlayers();
                if (alive.Count > 1)
                {
                    // A revive (Phoenix / respawns) landed in the same frame —
                    // the round is still live. Release the latch.
                    pointLatched = false;
                    return;
                }
                /* The winner id doubles as the REASON there is no winner
                  * (r4 finds 8+9). This method is only reached from the death
                  * path, so zero survivors here really is a mutual kill —
                  * whereas CheckRoundAfterLeave also resolves from the alive
                  * count and can legitimately reach zero because the last
                  * living player quit.
                  *
                  * Putting that on the wire rather than in a local static fixes
                  * both halves at once: a leaver-ended round can no longer
                  * inherit the flag, and every client (not just the master)
                  * learns the reason, because they all read the same RPC.
                  * WINNER_DOUBLE_KO is safe in a mixed lobby — an older
                  * client's `winnerTeam >= 0` award gate rejects it exactly as
                  * it rejects -1, so it awards nothing either way. */
                int winnerTeam = alive.Count == 1 ? alive[0].TeamID : WINNER_DOUBLE_KO;
                // Map-scale count rides ahead of the round RPC: Photon orders
                // a sender's operations, so every client holds the fresh count
                // before its transition loads the next map (FfaMapScale).
                try { FfaMapScale.MasterPublishCount(); } catch { }
                gm.view.RPC("RPCA_NextRound", RpcTarget.All, winnerTeam, winnerTeam, 0, 0, 0, 0);
            }
            catch (Exception ex)
            {
                pointLatched = false;
                Plugin.Log.LogError($"[FFA] ResolvePointNow: {ex.Message}");
            }
        }

        /// <summary>SPECTATOR-ONLY score observation (Codex spectator r1 find
        /// 8): the full HandleNextRound runs the participant transition
        /// engine (visibility, revives, pick phase, sync-up, reports), none
        /// of which a spectator may execute. This applies EXACTLY the score
        /// accounting from the master's broadcast — the same deltas every
        /// fighter applies — on top of the boundary-snapshot seed. Map load,
        /// call-in and body moves reach the spectator through the master's
        /// own MapManager RPCs; nothing else is needed.</summary>
        internal static void SpectatorObserveRound(int winnerTeam)
        {
            try
            {
                if (!RoomActors.LocalIsSpectator) return;
                if (winnerTeam >= 0)
                {
                    points[winnerTeam] = PointsFor(winnerTeam) + 1;
                    pointsTotal[winnerTeam] = PointsTotalFor(winnerTeam) + 1;
                    if (points[winnerTeam] >= PointsToWinRound)
                    {
                        rounds[winnerTeam] = RoundsFor(winnerTeam) + 1;
                        points.Clear();
                    }
                }
                else if (winnerTeam == WINNER_DOUBLE_KO)
                {
                    try
                    {
                        CompetitiveUI.ShowNotification(
                            I18n.Tr("Double KO - nobody scored this round."),
                            new Color(1f, 0.85f, 0.5f), 4f);
                    }
                    catch { }
                }
            }
            catch { }
        }

        /// <summary>RPCA_NextRound replacement — deterministic accounting on
        /// every client from the winner id alone.</summary>
        public static void HandleNextRound(GM_ArmsRace gm, int winnerTeam)
        {
            if (isTransitioning || gameOverFired) return;
            isTransitioning = true;
            pointLatched = false;
            GameManager.instance.battleOngoing = false;
            // A leave in the same physics step as the decisive death would
            // otherwise reach GetPlayersInTeam below with a corpse entry
            // still in the list (the CheckRoundAfterLeave purge is 0.7s out).
            PurgeDepartedPlayers("next round");
            try { PlayerManager.instance.SetPlayersSimulated(false); } catch { }

            bool roundOver = false, gameOver = false;
            if (winnerTeam >= 0)
            {
                points[winnerTeam] = PointsFor(winnerTeam) + 1;
                pointsTotal[winnerTeam] = PointsTotalFor(winnerTeam) + 1;
                if (points[winnerTeam] >= PointsToWinRound)
                {
                    rounds[winnerTeam] = RoundsFor(winnerTeam) + 1;
                    points.Clear();
                    roundOver = true;
                    gameOver = rounds[winnerTeam] >= RoundsToWin;
                }
                // Score timeline for the Recent panel's hover graph: one
                // token per half point, "slot[R][G]" (R = converted a point,
                // G = won the game). Deterministic on every client; only the
                // reporter's copy ships.
                if (timelineEvents.Count < 400)
                    timelineEvents.Add($"{winnerTeam}{(roundOver ? "R" : "")}{(gameOver ? "G" : "")}");
            }
            else
            {
                /* Nobody survived the round — the last players alive killed each
                 * other inside one resolve window, so there is no winner to
                 * award (ResolvePointNow yields -1 when AlivePlayers() is
                 * empty). That is not a bug in the accounting, but it WAS
                 * completely silent: the round simply ended, no score moved,
                 * and the next map loaded. Sid hit it at 2 rounds + 1 point
                 * against NotNic and could not tell what had happened, or
                 * whether the other client had seen the same thing.
                 *
                 * It does see the same thing: the master decides the winner
                 * once in ResolvePointNow and broadcasts it with
                 * RpcTarget.All, so every client applies the identical value.
                 * There is no desync here — only a missing explanation.
                 *
                 * Announce it. Whether a double knockout SHOULD award nothing,
                 * award both, or replay the round is a game-design call that
                 * is Sid's, not mine; this only makes the current rule
                 * legible (learning #250: the axis is visible-and-announced
                 * versus silent). */
                if (winnerTeam == WINNER_DOUBLE_KO)
                {
                    try
                    {
                        CompetitiveUI.ShowNotification(
                            I18n.Tr("Double KO - nobody scored this round."),
                            new Color(1f, 0.85f, 0.5f), 4f);
                    }
                    catch { }
                }
            }
            Plugin.Log.LogInfo($"[FFA] point over: winner team={winnerTeam} " +
                               $"roundOver={roundOver} gameOver={gameOver} scores=[{ScoreLine()}]");

            if (gameOver)
            {
                if (!gameOverFired)
                {
                    gameOverFired = true;
                    try { GameStateWatcher.OnFfaGameOver(winnerTeam); }
                    catch (Exception ex) { Plugin.Log.LogError($"[FFA] game-over report hook: {ex.Message}"); }
                    // Bug #104: with fewer than 3 members left the sitting
                    // ends after this game — a 2-player "FFA" rematch is
                    // below the mode minimum (server FFA_MIN_PLAYERS).
                    try
                    {
                        // Census: spectators must not prevent the below-minimum
                        // shutdown (design §4.2 — FFA survivor/quorum).
                        int remaining = RoomActors.ActiveFighterCount();
                        if (remaining < 3 && Plugin.Instance != null)
                            Plugin.Instance.StartCoroutine(EndSittingBelowMinimum());
                    }
                    catch { }
                }
                // Vanilla victory text + rematch popup (the competitive
                // auto-confirm patch answers Yes for everyone). Skips vanilla
                // GameOver()'s Steam-achievement block, whose m_localTeam flag
                // math is 2-team-shaped. Edge guard: GameOverTransition and
                // GameOverRematch both index GetPlayersInTeam(winner)[0] — if
                // the winner left the instant they clinched, anchor the visual
                // flow on a team that still has a live player (the report
                // above already carried the true winner).
                int anchorTeam = winnerTeam;
                if (PlayerManager.instance.GetPlayersInTeam(winnerTeam).Length == 0)
                {
                    var anyAlive = AlivePlayers();
                    if (anyAlive.Count > 0) anchorTeam = anyAlive[0].TeamID;
                    else
                    {
                        foreach (var pAny in PlayerManager.instance.players)
                            if (pAny != null && pAny.gameObject != null) { anchorTeam = pAny.TeamID; break; }
                    }
                }
                gm.currentWinningTeamID = anchorTeam;
                gm.StartCoroutine(gm.GameOverTransition(anchorTeam));
                isTransitioning = false;  // rematch flow owns state from here
                return;
            }
            gm.StartCoroutine(FfaTransition(gm, winnerTeam, roundOver));
        }

        // ── Transitions (replaces vanilla Point/RoundTransition) ──

        private static IEnumerator FfaTransition(GM_ArmsRace gm, int winnerTeam, bool roundOver)
        {
            PurgeDepartedPlayers("transition start");
            yield return new WaitForSecondsRealtime(1f);
            try { MapManager.instance.LoadNextLevel(); }
            catch (Exception ex) { Plugin.Log.LogError($"[FFA] LoadNextLevel: {ex.Message}"); }
            yield return new WaitForSecondsRealtime(roundOver ? 1.3f : 0.5f);
            yield return BoundedSyncUp(gm, 10f);

            if (roundOver && gm.pickPhase)
            {
                try { PlayerManager.instance.SetPlayersVisible(false); } catch { }
                yield return FfaPickPhase(gm, winnerTeam);
                try { PlayerManager.instance.SetPlayersVisible(true); } catch { }
            }

            yield return BoundedSyncUp(gm, 10f);
            PurgeDepartedPlayers("pre-move");
            // Bug #99: any vanilla throw from here on used to kill this
            // coroutine, so DoSpeedUp/battleOngoing never ran and the whole
            // lobby sat in permanent slow motion. The recovery lines below
            // must run no matter what the vanilla calls do.
            try { MapManager.instance.CallInNewMapAndMovePlayers(MapManager.instance.currentLevelID); }
            catch (Exception ex) { Plugin.Log.LogError($"[FFA] CallInNewMap: {ex.Message}"); }
            try { PlayerManager.instance.RevivePlayers(); }
            catch (Exception ex) { Plugin.Log.LogError($"[FFA] RevivePlayers: {ex.Message}"); }
            ClearLastDamageSources();
            yield return new WaitForSecondsRealtime(0.3f);
            try { TimeHandler.instance.DoSpeedUp(); } catch { }
            isTransitioning = false;
            GameManager.instance.battleOngoing = true;
            // Sid, Aug 3: with up to 10 identical-looking bodies on screen,
            // finding yourself at spawn is genuinely hard. Flash the local
            // player bright and dim everyone else for the grace second.
            try { Plugin.Instance.StartCoroutine(SpawnSpotlight()); } catch { }
        }

        /// <summary>"Which one am I?" — starts the spawn spotlight overlay.
        ///
        /// REWRITTEN after review: the first version recoloured every player's
        /// SpriteRenderers. That was wrong twice over — the ROUNDS body is
        /// largely PARTICLE-rendered (so the most visible layer never dimmed),
        /// and the cosmetics system rewrites those colours at 30 Hz for
        /// prismatic/chrome skins, so the effect was overwritten within a
        /// frame AND risked leaving a player permanently mis-coloured if the
        /// restore was ever interrupted.
        ///
        /// The overlay approach touches NO game state at all: CompetitiveUI
        /// draws a darkened frame around the local player's screen position
        /// for the grace second, so the background dims and you are the only
        /// thing in the clear. Nothing to restore, nothing to fight, and a
        /// crash mid-effect leaves the game exactly as it was.</summary>
        private static IEnumerator SpawnSpotlight()
        {
            // One frame of settle so MovePlayers has placed everyone before
            // the overlay reads a screen position.
            yield return null;
            Player mine = null;
            try
            {
                foreach (var pl in PlayerManager.instance.players)
                {
                    if (pl == null) continue;
                    bool isMine = false;
                    try { isMine = pl.data != null && pl.data.view != null && pl.data.view.IsMine; } catch { }
                    if (isMine) { mine = pl; break; }
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] spotlight: {ex.Message}"); }
            if (mine == null) yield break;
            CompetitiveUI.BeginSpawnSpotlight(mine.transform);
        }

        /// <summary>Vanilla WaitForSyncUp waits for any one peer's reply with
        /// NO timeout — alone in the room (everyone else left mid-transition)
        /// it waits forever. Same handshake, bounded, skipped with no peers.</summary>
        private static IEnumerator BoundedSyncUp(GM_ArmsRace gm, float maxSeconds)
        {
            if (PhotonNetwork.OfflineMode) yield break;
            // SPECTATOR: never SEND a sync request. Vanilla RPCO_RequestSyncUp
            // makes each receiver broadcast RPCM_ReturnSyncUp, and a waiting
            // FIGHTER can be released early by a return triggered from OUR
            // request — a player-visible timing change, the one thing the
            // spectator design forbids (design §2). The spectator's own
            // transitions are driven by observation, not by this handshake.
            if (RoomActors.LocalIsSpectator) yield break;
            // Census (design §2, FFA row): sync PEERS are other FIGHTERS.
            // Spectators never reply (their RPCO_RequestSyncUp handler is
            // suppressed), so counting one here would guarantee the timeout
            // path every round once all real fighters have left.
            int others = 0;
            try { others = RoomActors.OtherActiveFighterCount(); } catch { }
            if (others <= 0) yield break;
            float start = Time.realtimeSinceStartup;
            gm.isWaiting = true;
            try { gm.view.RPC("RPCO_RequestSyncUp", RpcTarget.Others); }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[FFA] sync-up RPC failed: {ex.Message}");
                gm.isWaiting = false;
                yield break;
            }
            while (gm.isWaiting && Time.realtimeSinceStartup - start < maxSeconds)
                yield return null;
            if (gm.isWaiting)
            {
                gm.isWaiting = false;
                Plugin.Log.LogWarning($"[FFA] sync-up timed out after {maxSeconds:0}s — continuing");
            }
        }

        /// <summary>Bug #104: after the game-over screen, if leavers took the
        /// room below the 3-player mode minimum, everyone returns to the
        /// menu instead of rematching as a 2-player "FFA". The report for
        /// the finished game already went out.</summary>
        private static int RoomCount()
        {
            // FIGHTER count, not actor count: every caller is a below-minimum
            // quorum check, and a spectator must not satisfy any of them
            // (census, design §4.2). Inert when no spectator is in the room.
            try { return RoomActors.ActiveFighterCount(); } catch { return 0; }
        }

        private static int TotalPointsScored()
        {
            int total = 0;
            try
            {
                foreach (var value in pointsTotal.Values) total += value;
            }
            catch { }
            return total;
        }

        private static void LeaveBelowMinimum(string logMessage, string notification)
        {
            Plugin.Log.LogInfo(logMessage);
            try
            {
                CompetitiveUI.ShowNotification(notification,
                    new Color(1f, 0.8f, 0.4f), 7f);
            }
            catch { }
            // NO cause tag (round-11 find 4): this is the FRESH-game
            // no-quorum cancel — nothing was or will be reported, and the
            // zero-game dissolution is the DESIRED outcome. The round-10
            // in_room_exit tag landed here by an old_string shape collision
            // (learning #220's bulk-edit trap, again) and would have left a
            // dead active parent awaiting a report that cannot exist.
            // GameStartedInRoom resets FIRST so the generic room-exit hook
            // (firing after NetworkRestart) cannot re-tag this leave, and
            // the durable-cause store is cleared of any earlier upgrade.
            GameStartedInRoom = false;
            try { ApiClient.FfaLeaveQueue("fresh_cancel"); } catch { }
            try { NetworkConnectionHandler.instance.NetworkRestart(); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] end-sitting NetworkRestart: {ex.Message}"); }
        }

        private static IEnumerator EndSittingBelowMinimum()
        {
            yield return new WaitForSecondsRealtime(4f);   // let the victory screen play
            if (!EngineActive()) yield break;
            int remaining = RoomCount();
            // Someone reconnected: stand down — the rematch's DoStartGame
            // runs its own inline below-minimum check (review find 12), so
            // nothing is stranded by this early exit.
            if (remaining >= 3) yield break;
            Plugin.Log.LogInfo($"[FFA] {remaining} player(s) left in the room (<3) — ending the sitting");
            try
            {
                CompetitiveUI.ShowNotification("Not enough players to continue the FFA - returning to menu.",
                    new Color(1f, 0.8f, 0.4f), 7f);
            }
            catch { }
            // in_room_exit (round-10 find 3): this teardown runs AFTER a
            // recorded game with the reporter's POST possibly still in
            // flight — the pre-room dissolution must never eat that report.
            try { ApiClient.FfaLeaveQueue("in_room_exit"); } catch { }
            try { NetworkConnectionHandler.instance.NetworkRestart(); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] end-sitting NetworkRestart: {ex.Message}"); }
        }

        /// <summary>Bug #102: re-send the local player's face (vanilla RPC,
        /// custom cosmetic ids included — they resolve through the GetItem
        /// prefix on every client) once everyone is definitely in the room.
        /// Idempotent: EquipFace just re-equips.</summary>
        private static IEnumerator ResyncLocalFace()
        {
            yield return new WaitForSecondsRealtime(2.5f);
            if (!EngineActive()) yield break;
            try
            {
                var lp = LocalPlayer();
                if (lp == null || lp.data == null || lp.data.view == null) yield break;
                var face = CharacterCreatorHandler.instance.selectedPlayerFaces[0];
                // Review find 13: an account that never opened the character
                // creator has an all-zero face — re-sending that WIPES the
                // stock face on every other screen (the cr_face publisher
                // rejects this exact payload; mirror it).
                if (face.eyeID == 0 && face.mouthID == 0 && face.detailID == 0 && face.detail2ID == 0)
                {
                    Plugin.Log.LogInfo("[FFA] face resync skipped — all-zero default face");
                    yield break;
                }
                lp.data.view.RPC("RPCA_SetFace", RpcTarget.Others,
                    face.eyeID, face.eyeOffset, face.mouthID, face.mouthOffset,
                    face.detailID, face.detailOffset, face.detail2ID, face.detail2Offset);
                Plugin.Log.LogInfo("[FFA] face resync sent (bug #102)");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] face resync: {ex.Message}"); }
        }

        /// <summary>DoStartGame replacement body — game 1 and every rematch.</summary>
        /// <summary>True once a game ACTUALLY STARTED in the current ffa_
        /// room (round-10 find 4): the room-exit hook attests in_room_exit
        /// from THIS, not from mere room occupancy — a pre-start exit from a
        /// never-filled room must stay eligible for assembly dissolution.</summary>
        public static bool GameStartedInRoom { get; private set; }

        public static IEnumerator FfaDoStartGame(GM_ArmsRace gm)
        {
            GameStartedInRoom = true;
            OnGameStart();
            PurgeDepartedPlayers("game start");
            // Bug #104 + review find 12: below the 3-player minimum, wait
            // briefly IN PLACE (a reconnect can restore the count), then
            // either proceed or end the sitting right here. The old shape —
            // abort the start and hand the decision to a separate coroutine —
            // stranded the room when a third player reconnected inside the
            // window: the decider saw >=3 and stood down, but nothing
            // restarted the aborted game.
            if (gameNumber > 1)
            {
                float waitUntil = Time.realtimeSinceStartup + 4f;
                int remaining0 = RoomCount();
                while (remaining0 > 0 && remaining0 < 3 && Time.realtimeSinceStartup < waitUntil)
                {
                    yield return new WaitForSecondsRealtime(0.5f);
                    remaining0 = RoomCount();
                }
                if (remaining0 > 0 && remaining0 < 3)
                {
                    Plugin.Log.LogInfo($"[FFA] rematch aborted — {remaining0} player(s) (<3) — ending the sitting");
                    try
                    {
                        CompetitiveUI.ShowNotification("Not enough players to continue the FFA - returning to menu.",
                            new Color(1f, 0.8f, 0.4f), 7f);
                    }
                    catch { }
                    // in_room_exit (round-11 find 3): the rematch abort
                    // runs AFTER game 1 recorded, with the reporter's POST
                    // possibly still in flight — same report-preserving rule
                    // as EndSittingBelowMinimum.
                    try { ApiClient.FfaLeaveQueue("in_room_exit"); } catch { }
                    try { NetworkConnectionHandler.instance.NetworkRestart(); }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] end-sitting NetworkRestart: {ex.Message}"); }
                    yield break;
                }
            }
            GameManager.instance.battleOngoing = false;
            yield return new WaitForSeconds(0.25f);
            try { UIHandler.instance.HideJoinGameText(); } catch { }
            PlayerManager.instance.SetPlayersSimulated(false);
            PlayerManager.instance.SetPlayersVisible(false);
            // Publish the live count BEFORE the load RPC so every client's
            // SetStartPos sees it (FfaMapScale; prop-before-RPC ordering).
            if (PhotonNetwork.IsMasterClient)
                try { FfaMapScale.MasterPublishCount(); } catch { }
            MapManager.instance.LoadNextLevel();
            TimeHandler.instance.DoSpeedUp();
            yield return new WaitForSecondsRealtime(1f);
            if (gm.pickPhase)
            {
                // Initial draw: EVERYONE picks, simultaneously. InitialPicks
                // (config: base 1 + host knob, floored server-side at
                // clamp(C+1-N,1,C) — §7d) runs as K SEQUENTIAL cycles, never
                // one cycle with K picks: sequential gets clean protocol
                // namespaces (each cycle its own PropCycle/PropResult) and
                // correct duplicate filtering for free, and avoids the #225
                // same-frame double-apply class entirely (§4d).
                int openingDraws = Mathf.Clamp(InitialPicks, 1, 6);
                for (int od = 0; od < openingDraws; od++)
                    yield return FfaPickPhase(gm, -1);
            }
            // Same leave-race fencing as FfaTransition (Codex review find 5):
            // a picker leaving as the opening draw resolves would otherwise
            // NRE the move/visibility passes and strand the game start.
            PurgeDepartedPlayers("pre-move start");
            try { MapManager.instance.CallInNewMapAndMovePlayers(MapManager.instance.currentLevelID); }
            catch (Exception ex) { Plugin.Log.LogError($"[FFA] CallInNewMap(start): {ex.Message}"); }
            ClearLastDamageSources();
            TimeHandler.instance.DoSpeedUp();
            TimeHandler.instance.StartGame();
            GameManager.instance.battleOngoing = true;
            try { PlayerManager.instance.SetPlayersVisible(true); }
            catch (Exception ex) { Plugin.Log.LogError($"[FFA] SetPlayersVisible(start): {ex.Message}"); }
            CompetitiveUI.ShowNotification(I18n.TrF("FFA - {0} players - first to {1} points!", Diag2v2.PlayersNeeded(), RoundsToWin),
                new Color(0.7f, 1f, 0.7f), 5f);
            // Bug #102: vanilla sends each player's face via an UNBUFFERED
            // RpcTarget.All at AssignPlayerID time — clients still joining
            // drop it forever, so late joiners saw default faces/cosmetics on
            // early spawners (the room creator, in longest, saw everyone).
            // Everyone re-sends their own face once the game is actually on.
            try { if (Plugin.Instance != null) Plugin.Instance.StartCoroutine(ResyncLocalFace()); } catch { }
        }

        // ── Simultaneous pick phase ──
        //
        // Vanilla CardChoice is ONE shared networked state machine (single
        // pickrID, Photon-instantiated cards) — unusable for parallel picks.
        // Protocol (single-reducer, master-authoritative — Codex design finds
        // 5/18/19):
        //   1. Master publishes the cycle MANIFEST (room prop): who picks.
        //   2. Each picker runs a LOCAL pick UI (locally instantiated card
        //      visuals, own input) and publishes its choice as a player prop.
        //      NOTHING is applied yet — not even locally.
        //   3. Master collects picks; when all are in (or 30s), publishes the
        //      RESULT manifest (room prop) echoing the accepted picks.
        //   4. Every client applies EXACTLY the result manifest, in manifest
        //      order, via the silent-apply path. Late picks are ignored by
        //      construction — they're not in the manifest.

        private static IEnumerator FfaPickPhase(GM_ArmsRace gm, int roundWinnerTeam)
        {
            cycleNumber++;
            int cycle = cycleNumber;
            int game = gameNumber;
            float phaseStart = Time.realtimeSinceStartup;
            // Vanilla logs "PICK PHASE" from RoundTransition; GameStateWatcher's
            // log intercept keys inPickPhase (input/achievement gating) on that
            // exact marker. Emit it for parity or pick-phase keystrokes count
            // as combat input (#28 class).
            UnityEngine.Debug.Log("PICK PHASE");
            PurgeDepartedPlayers("pick phase");

            // Local picker computation (master publishes; others use as fallback).
            var pickerIds = new List<int>();
            foreach (var p in PlayerManager.instance.players)
            {
                if (p == null || p.gameObject == null || p.data == null) continue;
                if (roundWinnerTeam >= 0 && p.TeamID == roundWinnerTeam) continue;
                pickerIds.Add(p.PlayerID);
            }
            pickerIds.Sort();

            // §8c drift recovery — FINAL SHAPE after three review rounds
            // (wave-2 round-3 find N6 closed the book on cache adoption).
            // Adoption acts on FRESH EVIDENCE ONLY, ahead-only:
            //  (b) mid-wait, the cycle prop CHANGES to an ahead identity
            //      (a fresh publish is current by construction);
            //  (d) the master's pick-evidence detector (quorum of the other
            //      pickers) + the non-master fresh-prop watch in the result
            //      loop.
            // There is deliberately NO adoption from a STABLE cached prop
            // (the round-2/round-3 draft): a cached value can be the
            // PREVIOUS cycle whose manifest, picks, AND result all still
            // exist, and every hold/grace scheme Codex reviewed still let
            // the master collect stale picks and finalize the old namespace.
            // The population that needed cache adoption — a mid-game
            // rejoiner with reset counters — does not exist: FFA rooms never
            // readmit mid-game (roster frozen at start, leavers purged and
            // reported departed), so every present client's local counters
            // are continuous. A successor master that LAGGED (missed a
            // cycle) is corrected by (d) the moment peers publish picks.
            System.Func<int, int, bool> aheadOfLocal =
                (g, c) => g > game || (g == game && c > cycle);
            string rawCycleAtEntry = ReadRawRoomProp(PropCycle);

            if (PhotonNetwork.IsMasterClient)
                SetRoomProp(PropCycle, $"{game}:{cycle}:{string.Join(",", pickerIds)}");

            // Wait for the manifest (all clients, incl. master reading its own write).
            List<int> manifest = null;
            while (Time.realtimeSinceStartup - phaseStart < ManifestWaitSeconds)
            {
                manifest = ReadCycleManifest(game, cycle);
                if (manifest != null) break;
                string rawNow = ReadRawRoomProp(PropCycle);
                if (rawNow != null && rawNow != rawCycleAtEntry)
                {
                    var adopted = ParseCycleProp(rawNow);
                    if (adopted != null && aheadOfLocal(adopted.Item1, adopted.Item2))
                    {
                        Plugin.Log.LogWarning($"[FFA] cycle identity drift: local {game}:{cycle} vs master {adopted.Item1}:{adopted.Item2} — adopting");
                        game = adopted.Item1;
                        cycle = adopted.Item2;
                        gameNumber = game;
                        cycleNumber = cycle;
                        manifest = adopted.Item3;
                        break;
                    }
                }
                // Master migration: if the original master died before
                // publishing, the new master publishes.
                if (PhotonNetwork.IsMasterClient && Time.realtimeSinceStartup - phaseStart > 2f)
                    SetRoomProp(PropCycle, $"{game}:{cycle}:{string.Join(",", pickerIds)}");
                yield return null;
            }
            // No timeout adoption from the (possibly stale) cached prop —
            // see the §8c decision comment above (round-3 find N6).
            if (manifest == null)
            {
                Plugin.Log.LogWarning($"[FFA] pick cycle {cycle}: no manifest after {ManifestWaitSeconds}s — using local picker set");
                manifest = pickerIds;
            }

            // Same-card sequence: latch once per game at the FIRST pick phase
            // (the seed prop has had the whole first round to propagate), then
            // consume one draw index for EVERY manifest picker — the manifest
            // is the agreed offer event, so a crashed seat's index advances
            // too (§4c.3: consume-on-offer). The residual: a client that hit
            // the manifest TIMEOUT above consumed from its LOCAL picker set,
            // which can skew ITS OWN indexes only — candidates are private,
            // picks travel by name, so nothing desyncs beyond that screen's
            // fairness for this game.
            try { FfaCardSequence.MasterPublishSeed(game); } catch { }
            // Poll the latch to ITS OWN verdict (round-4 find F2: a 3s caller
            // ceiling truncated the latch's 8s pending budget — a property
            // arriving at 3.2s still split shared/private). LatchForGame owns
            // the deadline (it latches fallback at 8s of pending); the 12s
            // caller ceiling is only a belt against a throwing latch, above
            // the 8s budget by construction. Normal case resolves <1s; the
            // pick window is ~25s.
            {
                float latchWait = Time.realtimeSinceStartup;
                while (true)
                {
                    bool latched = true;
                    try
                    {
                        FfaCardSequence.LatchForGame(game);
                        latched = FfaCardSequence.IsLatchedFor(game);
                    }
                    catch { }
                    if (latched || Time.realtimeSinceStartup - latchWait > 12f) break;
                    yield return null;
                }
            }
            try { FfaCardSequence.ConsumeOffers(manifest); } catch { }

            // Local player picks?
            var localPlayer = LocalPlayer();
            bool iPick = localPlayer != null && manifest.Contains(localPlayer.PlayerID);
            Coroutine localUi = null;
            if (iPick)
                localUi = gm.StartCoroutine(FfaLocalPickUI(gm, localPlayer, game, cycle));

            // Master: collect picks and close the window adaptively — at
            // least PickBase, extended by PickGrace whenever a pick arrives
            // (someone is clearly still at the keyboard), capped at PickCap.
            // Every client mirrors the rule so the HUD countdown matches.
            // Connected pickers self-confirm their highlighted card
            // AutoPickLead seconds before this deadline (see the constants
            // comment), so only a crashed/stalled seat is ever finalized
            // without a card.
            float deadline = phaseStart + PickBaseSeconds;
            int lastGotCount = 0;
            float lastCollect = -999f;
            bool wasMaster = PhotonNetwork.IsMasterClient;
            pickPhaseActive = true;
            pickDeadlineRealtime = deadline;
            // The master's own deadline IS the authority; everyone else runs
            // on the local mirror (long auto-pick lead) until the shared prop
            // is first read.
            pickDeadlineShared = wasMaster;
            double lastPublishedPhotonDeadline = -1.0;
            if (wasMaster) PublishSharedDeadline(game, cycle, deadline, ref lastPublishedPhotonDeadline);
            Dictionary<int, string> result = null;
            // Round-2 find 2: the cached-result short-circuit must not bypass
            // the drift detector — a drifted master could otherwise consume a
            // stale result for its old identity before ever observing peers'
            // ahead picks. One detector pass BEFORE the first result read.
            if (PhotonNetwork.IsMasterClient)
            {
                var pre = DetectAheadPickIdentity(manifest, game, cycle);
                if (pre != null)
                {
                    Plugin.Log.LogWarning($"[FFA] master identity {game}:{cycle} behind peers' {pre.Item1}:{pre.Item2} at result entry — adopting");
                    game = pre.Item1; cycle = pre.Item2;
                    gameNumber = game; cycleNumber = cycle;
                    SetRoomProp(PropCycle, $"{game}:{cycle}:{string.Join(",", pickerIds)}");
                }
            }
            // Snapshot for the non-master watch below (round-4 find F1: a
            // STABLE cached prop is not evidence — only a CHANGE observed
            // during this loop is a fresh publish).
            string rawCycleAtResultEntry = ReadRawRoomProp(PropCycle);
            while (true)
            {
                result = ReadCycleResult(game, cycle);
                if (result != null) break;
                float now = Time.realtimeSinceStartup;
                if (now - lastCollect > 0.25f)   // prop-table reads throttled
                {
                    lastCollect = now;
                    // Master drift self-heal (find 2): if two+ peers publish
                    // picks under an identity strictly AHEAD of ours, we are
                    // the drifted one — adopt it and republish the manifest
                    // so the phase converges instead of running one behind.
                    if (PhotonNetwork.IsMasterClient)
                    {
                        var ahead = DetectAheadPickIdentity(manifest, game, cycle);
                        if (ahead != null)
                        {
                            Plugin.Log.LogWarning($"[FFA] master identity {game}:{cycle} is behind peers' {ahead.Item1}:{ahead.Item2} — adopting and republishing");
                            game = ahead.Item1;
                            cycle = ahead.Item2;
                            gameNumber = game;
                            cycleNumber = cycle;
                            SetRoomProp(PropCycle, $"{game}:{cycle}:{string.Join(",", pickerIds)}");
                        }
                    }
                    else
                    {
                        // Non-master drift watch — CHANGE-TRIGGERED (round-4
                        // find F1: a stable cached value is not evidence; a
                        // publish observed DURING this loop is fresh by
                        // construction). Catches a lagged continuous client
                        // the master-only detector can't help.
                        string rawNow = ReadRawRoomProp(PropCycle);
                        var np = rawNow != rawCycleAtResultEntry ? ParseCycleProp(rawNow) : null;
                        if (np != null && (np.Item1 > game || (np.Item1 == game && np.Item2 > cycle)))
                        {
                            Plugin.Log.LogWarning($"[FFA] non-master identity {game}:{cycle} behind authoritative {np.Item1}:{np.Item2} — adopting");
                            game = np.Item1;
                            cycle = np.Item2;
                            gameNumber = game;
                            cycleNumber = cycle;
                            if (np.Item3 != null) manifest = np.Item3;
                            lastGotCount = 0;
                        }
                    }
                    var got = CollectPicks(manifest, game, cycle);
                    if (got.Count > lastGotCount)
                    {
                        lastGotCount = got.Count;
                        // Extension may only ever move the deadline FORWARD
                        // (round-3 find 3a): after a migration/adoption the
                        // deadline can legitimately sit past OUR local
                        // phaseStart+Cap, and the old Min-outside form would
                        // clamp it backward — potentially behind `now`,
                        // closing the window on the spot. The cap bounds the
                        // EXTENSION TARGET, never the standing deadline.
                        deadline = Mathf.Max(deadline,
                                             Mathf.Min(phaseStart + PickCapSeconds,
                                                       now + PickGraceSeconds));
                    }
                    // Master migration mid-cycle (Codex review find 4): the
                    // new master's local deadline can already be past (its
                    // phase clock started later/earlier than the old
                    // master's). Grant one grace window before finalizing so
                    // an in-flight pick isn't discarded on the handover.
                    // Deliberately NOT clamped to the local phaseStart+Cap
                    // (round-2 find 3b): an adopted shared deadline can sit
                    // past OUR cap, and clamping would yank it backward —
                    // potentially behind `now` — closing the window in the
                    // handover instant.
                    if (PhotonNetwork.IsMasterClient && !wasMaster)
                    {
                        wasMaster = true;
                        pickDeadlineShared = true;   // we are the authority now
                        deadline = Mathf.Max(deadline, now + PickGraceSeconds);
                        Plugin.Log.LogInfo($"[FFA] pick cycle {cycle}: became master mid-cycle — extending window");
                    }
                    if (PhotonNetwork.IsMasterClient)
                    {
                        // Authoritative deadline: republished on every change
                        // (initial, grace extensions, migration handover), so
                        // every current client's countdown AND auto-confirm
                        // track the clock that actually closes the window.
                        // (An auto-pick arriving extends grace like a human
                        // pick would — indistinguishable by design, since the
                        // pick prop format is frozen for old masters. Bounded:
                        // the moment every present picker is in, allIn closes
                        // the window regardless of the extension.)
                        PublishSharedDeadline(game, cycle, deadline, ref lastPublishedPhotonDeadline);
                    }
                    else
                    {
                        // Non-master: adopt the master's published deadline
                        // when present; the local grace mirror above stays as
                        // the fallback for an old-version master that never
                        // publishes one (auto-pick then uses the LONG lead —
                        // see AutoPickLeadFallbackSeconds).
                        float shared = ReadSharedDeadline(game, cycle);
                        if (shared > 0f) { deadline = shared; pickDeadlineShared = true; }
                    }
                    pickDeadlineRealtime = deadline;
                    if (PhotonNetwork.IsMasterClient)
                    {
                        bool allIn = got.Count >= CountStillPresent(manifest);
                        if (allIn || now > deadline)
                        {
                            var sb = new System.Text.StringBuilder();
                            sb.Append(game).Append(':').Append(cycle).Append(':');
                            bool first = true;
                            foreach (var kv in got.OrderBy(k => k.Key))
                            {
                                if (!first) sb.Append('|');
                                sb.Append(kv.Key).Append('=').Append(kv.Value);
                                first = false;
                            }
                            SetRoomProp(PropResult, sb.ToString());
                            if (!allIn)
                                Plugin.Log.LogWarning($"[FFA] pick cycle {cycle} closed with {got.Count}/{manifest.Count} picks (window ended)");
                            // Adopt what we just published as OUR result and
                            // exit now (round-3 new-defect find): a master
                            // that stalled past deadline+15 used to publish
                            // here and then hit the bail watchdog in the SAME
                            // iteration, replacing its own result with an
                            // empty set — peers applied the picks, the master
                            // applied none, and the decks diverged for the
                            // rest of the game.
                            result = got;
                            break;
                        }
                    }
                }
                // Bail watchdog keys off the DEADLINE, not the local phase
                // clock (round-2 find 3c): an early-entering client's local
                // phaseStart+Cap can lapse while a later-entering master is
                // still legitimately open — the deadline (shared when
                // available) is the clock that tracks the actual close. The
                // 20s phase-age floor keeps a very late entrant from bailing
                // before it has even had a chance to read the result prop.
                if (now > deadline + 15f && now - phaseStart > 20f)
                {
                    // Belt-and-suspenders: master gone AND no result — proceed cardless.
                    Plugin.Log.LogWarning($"[FFA] pick cycle {cycle}: no result manifest — proceeding without picks");
                    result = new Dictionary<int, string>();
                    break;
                }
                yield return null;
            }
            pickPhaseActive = false;
            pickDeadlineRealtime = 0f;
            pickDeadlineShared = false;

            if (localUi != null) { try { gm.StopCoroutine(localUi); } catch { } }
            CleanupLocalPickUI();

            // The result is ground truth: a manifest picker missing from it
            // missed the window (their UI just got torn down above). With the
            // auto-confirm this should only happen when our publish lost the
            // race to a master whose phase clock ran well ahead of ours —
            // log it loudly so repeat sightings surface the skew.
            if (iPick && localPlayer != null && !result.ContainsKey(localPlayer.PlayerID))
            {
                Plugin.Log.LogWarning($"[FFA] cycle {cycle}: local pick missed the window — no card this cycle (auto-confirm lost the close race?)");
                try
                {
                    CompetitiveUI.ShowNotification("Your pick missed the cutoff - no card this round.",
                        new Color(1f, 0.75f, 0.4f), 5f);
                }
                catch { }
            }

            // Apply the result — the ONLY apply site, identical on all clients.
            foreach (var kv in result.OrderBy(k => k.Key))
            {
                yield return ApplyManifestPick(kv.Key, kv.Value, cycle);
            }
            Plugin.Log.LogInfo($"[FFA] pick cycle {cycle} applied ({result.Count} picks)");
        }

        private static Player LocalPlayer()
        {
            try
            {
                foreach (var p in PlayerManager.instance.players)
                    if (p != null && p.gameObject != null && p.data != null && p.data.view != null && p.data.view.IsMine)
                        return p;
            }
            catch { }
            return null;
        }

        private static int CountStillPresent(List<int> manifest)
        {
            int n = 0;
            foreach (var pid in manifest)
            {
                var p = PlayerManager.instance?.GetPlayerWithID(pid);
                if (p != null && p.gameObject != null && p.data?.view?.Owner != null) n++;
            }
            return Math.Max(1, n);
        }

        private static void SetRoomProp(string key, string value)
        {
            try
            {
                var h = new ExitGames.Client.Photon.Hashtable();
                h[key] = value;
                PhotonNetwork.CurrentRoom.SetCustomProperties(h);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] SetRoomProp {key}: {ex.Message}"); }
        }

        private static string ReadRawRoomProp(string key)
        {
            try
            {
                var props = PhotonNetwork.CurrentRoom?.CustomProperties;
                if (props == null || !props.ContainsKey(key)) return null;
                return props[key] as string;
            }
            catch { return null; }
        }

        /// <summary>Parse a PropCycle value into (game, cycle, pickerIds), or
        /// null. Used by the §8c drift-adoption path, which needs the fields
        /// WITHOUT the local-identity equality check.</summary>
        private static Tuple<int, int, List<int>> ParseCycleProp(string raw)
        {
            try
            {
                var parts = (raw ?? "").Split(new[] { ':' }, 3);
                if (parts.Length != 3) return null;
                int g, c;
                if (!int.TryParse(parts[0], out g) || !int.TryParse(parts[1], out c)) return null;
                var ids = new List<int>();
                foreach (var s in parts[2].Split(','))
                    if (int.TryParse(s, out var v)) ids.Add(v);
                return Tuple.Create(g, c, ids);
            }
            catch { return null; }
        }

        private static List<int> ReadCycleManifest(int game, int cycle)
        {
            try
            {
                var props = PhotonNetwork.CurrentRoom?.CustomProperties;
                if (props == null || !props.ContainsKey(PropCycle)) return null;
                var parts = (props[PropCycle] as string ?? "").Split(new[] { ':' }, 3);
                if (parts.Length != 3) return null;
                if (int.Parse(parts[0]) != game || int.Parse(parts[1]) != cycle) return null;
                var ids = new List<int>();
                foreach (var s in parts[2].Split(','))
                    if (int.TryParse(s, out var v)) ids.Add(v);
                return ids;
            }
            catch { return null; }
        }

        private static Dictionary<int, string> ReadCycleResult(int game, int cycle)
        {
            try
            {
                var props = PhotonNetwork.CurrentRoom?.CustomProperties;
                if (props == null || !props.ContainsKey(PropResult)) return null;
                var parts = (props[PropResult] as string ?? "").Split(new[] { ':' }, 3);
                if (parts.Length != 3) return null;
                if (int.Parse(parts[0]) != game || int.Parse(parts[1]) != cycle) return null;
                var dict = new Dictionary<int, string>();
                if (parts[2].Length > 0)
                {
                    foreach (var pair in parts[2].Split('|'))
                    {
                        int eq = pair.IndexOf('=');
                        if (eq <= 0) continue;
                        if (int.TryParse(pair.Substring(0, eq), out var pid))
                            dict[pid] = pair.Substring(eq + 1);
                    }
                }
                return dict;
            }
            catch { return null; }
        }

        /// <summary>Master: publish the window deadline in Photon server time
        /// (shared, monotone-enough clock). Republished only when it moved by
        /// more than half a second so the prop table isn't spammed at 4 Hz.</summary>
        private static void PublishSharedDeadline(int game, int cycle, float localDeadline, ref double lastPublished)
        {
            try
            {
                double photonDl = PhotonNetwork.Time + (localDeadline - Time.realtimeSinceStartup);
                if (Math.Abs(photonDl - lastPublished) < 0.5) return;
                lastPublished = photonDl;
                SetRoomProp(PropDeadline, $"{game}:{cycle}:" +
                    photonDl.ToString("F2", System.Globalization.CultureInfo.InvariantCulture));
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] deadline publish: {ex.Message}"); }
        }

        /// <summary>Any client: the master's published deadline converted to
        /// local realtime, or -1 when absent/stale (old-version master).</summary>
        private static float ReadSharedDeadline(int game, int cycle)
        {
            try
            {
                var props = PhotonNetwork.CurrentRoom?.CustomProperties;
                if (props == null || !props.ContainsKey(PropDeadline)) return -1f;
                var parts = (props[PropDeadline] as string ?? "").Split(new[] { ':' }, 3);
                if (parts.Length != 3) return -1f;
                if (int.Parse(parts[0]) != game || int.Parse(parts[1]) != cycle) return -1f;
                double photonDl = double.Parse(parts[2], System.Globalization.CultureInfo.InvariantCulture);
                return Time.realtimeSinceStartup + (float)(photonDl - PhotonNetwork.Time);
            }
            catch { return -1f; }
        }

        /// <summary>Master-side: read each manifest picker's pick prop for this cycle.</summary>
        private static string RoomNonce()
        {
            try { return PhotonNetwork.CurrentRoom?.Name ?? ""; } catch { return ""; }
        }

        private static Dictionary<int, string> CollectPicks(List<int> manifest, int game, int cycle)
        {
            var got = new Dictionary<int, string>();
            try
            {
                string prefix = $"{RoomNonce()}:{game}:{cycle}:";
                foreach (var pid in manifest)
                {
                    var pl = PlayerManager.instance?.GetPlayerWithID(pid);
                    var owner = pl?.data?.view?.Owner;
                    var props = owner?.CustomProperties;
                    if (props == null || !props.ContainsKey(PropPick)) continue;
                    string v = props[PropPick] as string ?? "";
                    if (v.StartsWith(prefix) && v.Length > prefix.Length)
                        got[pid] = v.Substring(prefix.Length);
                }
            }
            catch { }
            return got;
        }

        /// <summary>Master self-heal for the drifted-successor case (Codex
        /// client review find 2): a master whose own identity is BEHIND sees
        /// its collect find nothing, while peers' pick props carry the true
        /// (game, cycle). When two or more manifest peers publish picks under
        /// one identity strictly ahead of ours, that identity wins. Returns
        /// the majority (game, cycle) or null.</summary>
        private static Tuple<int, int> DetectAheadPickIdentity(List<int> manifest, int game, int cycle)
        {
            try
            {
                string noncePrefix = RoomNonce() + ":";
                var counts = new Dictionary<string, int>();
                foreach (var pid in manifest)
                {
                    var pl = PlayerManager.instance?.GetPlayerWithID(pid);
                    var props = pl?.data?.view?.Owner?.CustomProperties;
                    if (props == null || !props.ContainsKey(PropPick)) continue;
                    string v = props[PropPick] as string ?? "";
                    if (!v.StartsWith(noncePrefix)) continue;
                    var parts = v.Substring(noncePrefix.Length).Split(new[] { ':' }, 3);
                    if (parts.Length != 3) continue;
                    int g, c;
                    if (!int.TryParse(parts[0], out g) || !int.TryParse(parts[1], out c)) continue;
                    if (g > game || (g == game && c > cycle))
                    {
                        string key = g + ":" + c;
                        counts[key] = (counts.TryGetValue(key, out var n) ? n : 0) + 1;
                    }
                }
                // Quorum (round-2 find 2): with a 2-picker cycle only ONE
                // other picker exists, so a flat >=2 is unreachable there —
                // require agreement from every OTHER manifest peer, capped
                // at 2 (a lone forged prop can then only sway a 2-picker
                // cycle, where it is also the only evidence available).
                int quorum = Math.Min(2, Math.Max(1, manifest.Count - 1));
                foreach (var kv in counts)
                {
                    if (kv.Value >= quorum)
                    {
                        var p = kv.Key.Split(':');
                        return Tuple.Create(int.Parse(p[0]), int.Parse(p[1]));
                    }
                }
            }
            catch { }
            return null;
        }

        // ── Local pick UI ──

        private static readonly List<GameObject> localCardObjects = new List<GameObject>();

        private static IEnumerator FfaLocalPickUI(GM_ArmsRace gm, Player localPlayer, int game, int cycle)
        {
            var choice = CardChoice.instance;
            if (choice == null) yield break;
            // Card slot anchors: vanilla CardChoice's own children transforms.
            // The 5 anchors are a fanned arc; taking the FIRST k would leave a
            // left-shifted, tilted half-hand, so sub-5 counts use a SYMMETRIC
            // index table (§4a). The candidates knob is server-locked at 5
            // for v1.36 (§9c), so today idx always yields all five — the
            // table is the reviewed-and-ready half of the future knob.
            var allSlots = new List<Transform>();
            for (int i = 0; i < choice.transform.childCount && i < 5; i++)
                allSlots.Add(choice.transform.GetChild(i));
            if (allSlots.Count == 0) yield break;
            var slots = allSlots;
            int wantCount = Mathf.Clamp(CardCandidates, 1, allSlots.Count);
            if (wantCount < allSlots.Count && allSlots.Count == 5)
            {
                int[][] symmetric = {
                    new[] { 2 },            // 1 candidate: centre
                    new[] { 1, 3 },         // 2: inner pair
                    new[] { 1, 2, 3 },      // 3: inner trio
                    new[] { 0, 1, 3, 4 },   // 4: skip centre
                };
                slots = new List<Transform>();
                foreach (var si in symmetric[wantCount - 1]) slots.Add(allSlots[si]);
            }

            try { ArtHandler.instance.SetSpecificArt(choice.cardPickArt); } catch { }

            // Candidates: TWO STREAMS (§7e ⚠ box). Same-card rule active →
            // the deterministic shared sequence (every client computes an
            // identical Sk for draw k). Otherwise → the private per-client
            // roll below, exactly as shipped — reproducibility must never
            // leak into this path or the rule could not be switched off.
            var candidates = new List<CardInfo>();
            var candidateObjs = new List<GameObject>();
            bool sharedDraw = false;
            try { sharedDraw = FfaCardSequence.TryGetCandidates(localPlayer, slots.Count, candidates); }
            catch (Exception sqx) { Plugin.Log.LogWarning($"[FFA-SEQ] shared draw failed: {sqx.Message}"); candidates.Clear(); }
            if (!sharedDraw)
            {
                int guard = 0;
                while (candidates.Count < slots.Count && guard++ < 200)
                {
                    var c = PickRandomCard(choice);
                    if (c == null) break;
                    if (!IsCardAllowedFor(localPlayer, c, candidates)) continue;
                    candidates.Add(c);
                }
            }
            // `shown` stays index-aligned with candidateObjs: a candidate
            // whose visual failed to spawn is DROPPED, not silently kept —
            // otherwise `selected` (an index into the visuals) would publish
            // a different card than the one highlighted (Codex Jul-29
            // adjacent find; matters double now that timeout confirms the
            // highlighted card).
            var shown = new List<CardInfo>();
            for (int i = 0; i < candidates.Count; i++)
            {
                GameObject vis = null;
                try
                {
                    vis = choice.AddCardVisual(candidates[i], slots[i].position);
                    vis.transform.rotation = slots[i].rotation;
                    // Vanilla disables the card's DamagableEvent Collider2D so
                    // bullets can't "shoot-to-pick" it. Referencing Collider2D
                    // at compile time would drag in Physics2DModule (csproj is
                    // deliberately untouched) — string-typed GetComponent gets
                    // the same component; Collider2D derives from Behaviour so
                    // .enabled is reachable through that cast.
                    var dmg = vis.GetComponentInChildren<DamagableEvent>();
                    var col = dmg != null ? dmg.GetComponent("Collider2D") as Behaviour : null;
                    if (col != null) col.enabled = false;
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] card visual spawn: {ex.Message}"); }
                if (vis != null) { candidateObjs.Add(vis); localCardObjects.Add(vis); shown.Add(candidates[i]); }
            }
            if (candidateObjs.Count == 0) yield break;

            CompetitiveUI.ShowNotification("Pick a card! (left/right + jump)", new Color(0.8f, 0.9f, 1f), 4f);

            int selected = 0;
            int lastDir = 0;
            float started = Time.realtimeSinceStartup;
            int chosen = -1;
            bool autoPicked = false;
            localPickOpen = true;
            // The 0.35s arm delay keeps a jump pressed during the transition
            // (or any queued press on the very first frame) from
            // insta-confirming card 0.
            const float armDelay = 0.35f;
            while (chosen < 0)
            {
                // Countdown expiry confirms the HIGHLIGHTED card (see the
                // constants comment: a pick can never be skipped, but the
                // timer is on the HUD and the confirm is announced — nothing
                // silent, unlike the #92-#98 auto-pick this replaces). Guarded
                // on armDelay so a degenerate short window can't insta-pick.
                if (pickPhaseActive && PickSecondsLeft <= 0f
                    && Time.realtimeSinceStartup - started > armDelay)
                {
                    chosen = selected;
                    autoPicked = true;
                    break;
                }
                // Bug #128: playerActions are read DIRECTLY here, so
                // GameManager.lockInput (which only gates GeneralInput) does not
                // cover the pick phase — a SPACE typed into the chat box would
                // confirm a card. Freeze the highlight and ignore Jump while
                // either chat owns the keyboard. lastDir is zeroed rather than
                // frozen so the first real nudge after closing chat registers.
                var actions = localPlayer?.data?.playerActions;
                if (CompetitiveUI.AnyChatTyping) { lastDir = 0; }
                else if (actions != null)
                {
                    int dir = 0;
                    try
                    {
                        if (actions.Right.Value > 0.7f) dir = 1;
                        else if (actions.Left.Value > 0.7f) dir = -1;
                    }
                    catch { }
                    if (dir != lastDir && dir != 0)
                        selected = Mathf.Clamp(selected + dir, 0, candidateObjs.Count - 1);
                    lastDir = dir;
                    try
                    {
                        if (Time.realtimeSinceStartup - started > armDelay && actions.Jump.WasPressed)
                            chosen = selected;
                    }
                    catch { }
                }
                for (int i = 0; i < candidateObjs.Count; i++)
                {
                    try
                    {
                        var cv = candidateObjs[i] != null ? candidateObjs[i].GetComponentInChildren<CardVisuals>() : null;
                        if (cv != null) cv.ChangeSelected(i == selected);
                    }
                    catch { }
                }
                yield return null;
            }

            localPickOpen = false;
            string cardName = shown[chosen].gameObject.name.Replace("(Clone)", "");
            // Publish BEFORE any local application — application happens only
            // from the result manifest, identically on every client.
            try
            {
                var h = new ExitGames.Client.Photon.Hashtable();
                h[PropPick] = $"{RoomNonce()}:{game}:{cycle}:{cardName}";
                PhotonNetwork.LocalPlayer.SetCustomProperties(h);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] pick publish: {ex.Message}"); }
            Plugin.Log.LogInfo(autoPicked
                ? $"[FFA] local pick AUTO-CONFIRMED at window expiry: {cardName} (cycle {cycle})"
                : $"[FFA] local pick published: {cardName} (cycle {cycle})");
            if (autoPicked)
            {
                try
                {
                    string display = shown[chosen].cardName;
                    if (string.IsNullOrEmpty(display)) display = cardName;
                    CompetitiveUI.ShowNotification(I18n.TrF("Time's up - {0} picked automatically.", display),
                        new Color(1f, 0.85f, 0.5f), 5f);
                }
                catch { }
            }
            try { GameStateWatcher.RecordFfaLocalPick(cardName, RoundsTotalAll()); } catch { }
            // §10 offer baseline: log what THIS client was offered this draw
            // (own offers only — the report attaches them for the local entry;
            // candidate counts were previously invisible to the server).
            try
            {
                int offerRound = Math.Max(1, RoundsTotalAll() + 1);
                for (int i = 0; i < shown.Count && i < candidateObjs.Count; i++)
                {
                    LocalOffers.Add(new OfferRecord
                    {
                        CardName = CardRarityLookup.GetCanonicalName(shown[i].gameObject.name),
                        Round = offerRound,
                        Picked = (i == chosen),
                    });
                }
            }
            catch { }

            // Visual feedback: chosen card pops, others leave.
            for (int i = 0; i < candidateObjs.Count; i++)
            {
                try
                {
                    var cv = candidateObjs[i] != null ? candidateObjs[i].GetComponentInChildren<CardVisuals>() : null;
                    if (cv == null) continue;
                    if (i == chosen) cv.Pick(); else cv.Leave();
                }
                catch { }
            }
            yield return new WaitForSecondsRealtime(0.8f);
            CleanupLocalPickUI();
        }

        private static void CleanupLocalPickUI()
        {
            localPickOpen = false;
            foreach (var go in localCardObjects)
            {
                try { if (go != null) UnityEngine.Object.Destroy(go); } catch { }
            }
            localCardObjects.Clear();
        }

        private static int RoundsTotalAll()
        {
            int t = 0;
            foreach (var kv in rounds) t += kv.Value;
            return t;
        }

        private static CardInfo PickRandomCard(CardChoice choice)
        {
            try
            {
                var cards = choice.cards;
                if (cards == null || cards.Length == 0) return null;
                float total = 0f;
                foreach (var c in cards)
                    total += RarityWeight(c.rarity);
                float roll = UnityEngine.Random.Range(0f, total);
                foreach (var c in cards)
                {
                    roll -= RarityWeight(c.rarity);
                    if (roll <= 0f) return c;
                }
                return cards[cards.Length - 1];
            }
            catch { return null; }
        }

        private static float RarityWeight(CardInfo.Rarity r)
        {
            switch (r)
            {
                case CardInfo.Rarity.Common: return 10f;
                case CardInfo.Rarity.Uncommon: return 4f;
                case CardInfo.Rarity.Rare: return 1f;
                default: return 4f;
            }
        }

        /// <summary>Vanilla SpawnUniqueCard's exclusion rules, applied to a
        /// local candidate: no duplicate offers, respect allowMultiple and
        /// blacklisted categories vs the player's current cards, and the
        /// lockGunToDefault clash.</summary>
        private static bool IsCardAllowedFor(Player player, CardInfo candidate, List<CardInfo> alreadyOffered)
        {
            try
            {
                foreach (var offered in alreadyOffered)
                    if (offered == candidate) return false;
                if (player?.data == null) return true;
                var holding = player.data.GetComponent<Holding>();
                var holdable = holding != null ? holding.holdable : null;
                if (holdable != null)
                {
                    var heldGun = holdable.GetComponent<Gun>();
                    var cardGun = candidate.GetComponent<Gun>();
                    if (cardGun != null && heldGun != null && cardGun.lockGunToDefault && heldGun.lockGunToDefault)
                        return false;
                }
                var current = player.data.currentCards;
                if (current != null)
                {
                    foreach (var have in current)
                    {
                        if (have == null) continue;
                        if (!have.allowMultiple && have.name == candidate.name) return false;
                        if (have.blacklistedCategories != null && candidate.categories != null)
                        {
                            foreach (var black in have.blacklistedCategories)
                                foreach (var cat in candidate.categories)
                                    if (cat == black) return false;
                        }
                    }
                }
                return true;
            }
            catch { return true; }
        }

        // ── Applying picks (the single reducer) ──

        private static IEnumerator ApplyManifestPick(int pid, string cardName, int cycle)
        {
            // Self-heal a stale bar-suppression flag (Claude review of the
            // rebuild change): if a prior cycle's replay coroutine died
            // between Add and Remove, this pid's card-bar adds would stay
            // suppressed for the rest of the game — clear on every new apply.
            deckViewRebuilds.Remove(pid);
            var player = PlayerManager.instance?.GetPlayerWithID(pid);
            if (player == null || player.gameObject == null || player.data == null)
            {
                Plugin.Log.LogWarning($"[FFA] apply skipped — player {pid} gone (card {cardName})");
                yield break;
            }
            var prefab = ResolveCard(cardName);
            if (prefab == null)
            {
                Plugin.Log.LogWarning($"[FFA] apply skipped — unknown card '{cardName}' for pid {pid}");
                yield break;
            }
            if (!decks.TryGetValue(pid, out var deck))
            {
                deck = new List<CardInfo>();
                decks[pid] = deck;
            }
            CaptureBaselineIfNeeded(player);

            bool rebuiltDeck = false;
            if (deck.Count >= CardCap)
            {
                // Rolling Card Bar: the oldest card rolls off. No inverse-stats
                // path exists in ROUNDS — reset to the cached baseline and
                // replay the survivors, then apply the new card.
                var survivors = deck.Skip(deck.Count - (CardCap - 1)).ToList();
                Plugin.Log.LogInfo($"[FFA] rolling removal for pid {pid}: dropping '{deck[0].gameObject.name}'");
                // Mark the earliest un-rolled history entry for this card so
                // the Recent panel can paint it red (Sid round-2 item 2).
                try
                {
                    string droppedCanon = CardRarityLookup.GetCanonicalName(
                        deck[0].gameObject.name.Replace("(Clone)", ""));
                    if (pickHistory.TryGetValue(pid, out var hist0))
                        foreach (var h in hist0)
                            if (!h.Rolled && h.CardName == droppedCanon) { h.Rolled = true; break; }
                }
                catch { }
                deckViewRebuilds.Add(pid);
                rebuiltDeck = true;
                yield return RollingResetAndReplay(player, survivors);
                deck.Clear();
                deck.AddRange(survivors);
            }

            ApplyCardTo(player, prefab);
            deck.Add(prefab);

            if (rebuiltDeck)
            {
                // Let the final card's player-hosted components and the old
                // card-bar button destroys finish, then publish the exact
                // five-card deck to both display sources in one operation.
                yield return null;
                RebuildDeckViews(player, deck);
                deckViewRebuilds.Remove(pid);
            }

            if (!pickHistory.TryGetValue(pid, out var hist))
            {
                hist = new List<MatchTracker.CardPickData>();
                pickHistory[pid] = hist;
            }
            string rarity = "";
            try { rarity = prefab.rarity.ToString(); } catch { }
            hist.Add(new MatchTracker.CardPickData
            {
                CardName = CardRarityLookup.GetCanonicalName(cardName),
                CardRarity = rarity,
                PickOrder = hist.Count + 1,
                RoundNumber = Math.Max(1, RoundsTotalAll() + 1),
            });
        }

        private static CardInfo ResolveCard(string cardName)
        {
            try
            {
                var cards = CardChoice.instance?.cards;
                if (cards == null) return null;
                foreach (var c in cards)
                    if (c != null && c.gameObject.name == cardName) return c;
            }
            catch { }
            return null;
        }

        // ── spectator accessors (SpectatorSync) ──────────────────────────
        // The spectator snapshot needs (a) the silent apply primitive and
        // (b) FFA's authoritative rolling deck by pid. Exposed as narrow
        // wrappers rather than widening the members themselves — the
        // internals stay owned by this file.

        /// <summary>Silent single-card apply for spectator deck replay.
        /// Same primitive the rolling replay uses (scrub + Start() +
        /// sourceCard + OFFLINE_Pick). Caller owns frame-spacing (#225).</summary>
        internal static void SpectatorApplyCard(Player player, CardInfo prefab)
        {
            ApplyCardTo(player, prefab);
        }

        /// <summary>GameObject names of the live rolling deck for a pid, or
        /// null when FFA holds no deck for it (non-FFA rooms, unknown pid).
        /// Snapshot-only: returns a copy, never the live list.</summary>
        internal static List<string> SpectatorDeckNames(int pid)
        {
            try
            {
                if (!decks.TryGetValue(pid, out var deck) || deck == null) return null;
                var names = new List<string>(deck.Count);
                foreach (var c in deck)
                    if (c != null) names.Add(c.gameObject.name);
                return names;
            }
            catch { return null; }
        }

        /// <summary>Silent apply: local clone -> ApplyCardStats component init
        /// -> OFFLINE_Pick (applies stats + card bar, no networking, no
        /// "Picking Card:" log, no Steam achievements) -> destroy clone.
        /// sourceCard is set explicitly so ApplyStats appends the real prefab
        /// to currentCards (Codex design find 20).</summary>
        private static void ApplyCardTo(Player player, CardInfo prefab)
        {
            GameObject clone = null;
            try
            {
                // bug113.txt:5529 shows the rematch sweep firing BEFORE the
                // old ShieldCharge.OnDestroy failure at :5539. Its stale
                // ShieldChargeCollide key therefore survived until the next
                // ShieldCharge.Start hit Dictionary.Add at :5851 and aborted
                // before SuperFirstBlockAction registration. ShieldCharge's
                // Unity Start runs after OFFLINE_Pick, outside this method's
                // catch, which is why no ApplyCardTo error named it. Scrub the
                // target player immediately before every FFA apply; rolling
                // replay and fresh/rematch picks now share the safe boundary.
                int stale = BlockReflect.ScrubPlayerDelegates(player);
                if (stale > 0)
                    Plugin.Log.LogWarning($"[FFA] pre-apply scrub removed {stale} stale handler(s) for pid {player.PlayerID}");

                clone = UnityEngine.Object.Instantiate(prefab.gameObject,
                    new Vector3(2000f, 2000f, 0f), Quaternion.identity);
                var info = clone.GetComponent<CardInfo>();
                if (info != null) info.sourceCard = prefab;
                var acs = clone.GetComponentInChildren<ApplyCardStats>();
                if (acs == null)
                {
                    Plugin.Log.LogWarning($"[FFA] no ApplyCardStats on '{prefab.gameObject.name}'");
                    return;
                }
                acs.Start();   // populates myGunStats/myPlayerStats/myBlock (publicized private)
                acs.OFFLINE_Pick(new[] { player });
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[FFA] ApplyCardTo({prefab?.gameObject?.name}): {ex.Message}");
            }
            finally
            {
                try { if (clone != null) UnityEngine.Object.Destroy(clone); } catch { }
            }
        }

        /// <summary>After a rolling reset, make the authoritative deck visible
        /// all at once. bug114.txt:8480/8486/8502 proves the sixth pick removed
        /// Quick Reload in the SAME cycle; :8886 then removed Wind up, proving
        /// the reducer had already advanced. The lag was display-only: the bar
        /// and currentCards were rebuilt incrementally during replay. deck[0]
        /// is the oldest card; CardBar.AddCard inserts at visual index zero, so
        /// chronological replay leaves the oldest card at the visual tail and
        /// drops that tail, never the newest slot.</summary>
        private static void RebuildDeckViews(Player player, List<CardInfo> deck)
        {
            try
            {
                var current = player?.data?.currentCards;
                if (current != null)
                {
                    current.Clear();
                    // TabStatsOverlay interprets this count as "pre-game
                    // cards to skip". Record zero before restoring the live
                    // FFA deck so the hold-Tab source shows all five now.
                    TabStatsOverlay.RecordCardBaseline(player);
                    foreach (var card in deck)
                        if (card != null) current.Add(card);
                }

                if (player?.data?.view != null && player.data.view.IsMine)
                {
                    var bars = CardBarHandler.instance != null ? CardBarHandler.instance.cardBars : null;
                    if (bars != null && bars.Length > 0)
                    {
                        bars[0].ClearBar();
                        foreach (var card in deck)
                            if (card != null) bars[0].AddCard(card);
                    }
                }
                Plugin.Log.LogInfo($"[FFA] deck views rebuilt for pid {player.PlayerID}: {deck.Count} card(s)");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] deck-view rebuild: {ex.Message}"); }
        }

        internal static bool SuppressCardBarAdd(int playerId)
        {
            return deckViewRebuilds.Contains(playerId);
        }

        /// <summary>Deterministic per-half-point seed for spawn assignment.
        /// FNV-1a mixes the server-issued room name, game number, and the
        /// fixed 0..9 score vector. pointsTotal is monotonic within a game, so
        /// every awarded half point changes the seed; gameNumber separates
        /// rematches. Fixed slot order avoids dictionary iteration variance.</summary>
        internal static uint SpawnShuffleSeed()
        {
            unchecked
            {
                uint hash = 2166136261u;
                string room = "";
                try { room = PhotonNetwork.CurrentRoom?.Name ?? ""; } catch { }
                foreach (char ch in room)
                {
                    hash = (hash ^ (byte)(ch & 0xFF)) * 16777619u;
                    hash = (hash ^ (byte)(ch >> 8)) * 16777619u;
                }
                MixSeedInt(ref hash, gameNumber);
                for (int slot = 0; slot < 10; slot++)
                {
                    MixSeedInt(ref hash, RoundsFor(slot));
                    MixSeedInt(ref hash, PointsFor(slot));
                    MixSeedInt(ref hash, PointsTotalFor(slot));
                }
                return hash == 0u ? 0x9E3779B9u : hash;
            }
        }

        private static void MixSeedInt(ref uint hash, int value)
        {
            unchecked
            {
                uint v = (uint)value;
                for (int i = 0; i < 4; i++)
                {
                    hash = (hash ^ (byte)(v & 0xFF)) * 16777619u;
                    v >>= 8;
                }
            }
        }

        private static void CaptureBaselineIfNeeded(Player player)
        {
            int pid = player.PlayerID;
            if (baselines.TryGetValue(pid, out var b) && b.captured) return;
            var nb = new FfaBaseline { captured = true };
            try
            {
                var grav = player.GetComponent<Gravity>();
                nb.gravityForce = grav != null ? grav.gravityForce : 0f;
                var hh = player.GetComponent<HealthHandler>();
                nb.regeneration = hh != null ? hh.regeneration : 0f;
                var cd = player.GetComponent<CharacterData>();
                nb.jumps = cd != null ? cd.jumps : 1;
                var holding = player.data.GetComponent<Holding>();
                var gun = holding != null && holding.holdable != null ? holding.holdable.GetComponent<Gun>() : null;
                var ammo = gun != null ? gun.GetComponentInChildren<GunAmmo>() : null;
                nb.ammoReg = ammo != null ? ammo.ammoReg : 0f;
                nb.projectile = gun != null && gun.projectiles != null && gun.projectiles.Length > 0
                    ? gun.projectiles[0].objectToSpawn : null;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] baseline capture: {ex.Message}"); }
            baselines[pid] = nb;
        }

        /// <summary>The Rolling Card Bar core: FullReset + the residue fields
        /// vanilla's reset trio misses (verified against the 1.1.2 decompile:
        /// GunAmmo.ammoReg, CharacterData.jumps, Gravity.gravityForce,
        /// HealthHandler.regeneration, gun.projectiles[0].objectToSpawn,
        /// Gun.dontAllowAutoFire), one frame for card-object teardown, the
        /// zombie-delegate/ChildRPC scrub (#92/#103), then a silent replay of
        /// the surviving cards in original order.</summary>
        private static IEnumerator RollingResetAndReplay(Player player, List<CardInfo> survivors)
        {
            int pid = player.PlayerID;
            try
            {
                player.FullReset();
                if (baselines.TryGetValue(pid, out var b) && b.captured)
                {
                    try { var g = player.GetComponent<Gravity>(); if (g != null) g.gravityForce = b.gravityForce; } catch { }
                    try { var hh = player.GetComponent<HealthHandler>(); if (hh != null) hh.regeneration = b.regeneration; } catch { }
                    try { var cd = player.GetComponent<CharacterData>(); if (cd != null) cd.jumps = b.jumps; } catch { }
                    try
                    {
                        var holding = player.data.GetComponent<Holding>();
                        var gun = holding != null && holding.holdable != null ? holding.holdable.GetComponent<Gun>() : null;
                        if (gun != null)
                        {
                            var ammo = gun.GetComponentInChildren<GunAmmo>();
                            if (ammo != null) ammo.ammoReg = b.ammoReg;
                            // Review find 9: restore UNCONDITIONALLY, including a
                            // null baseline — the old `!= null` guard meant a
                            // player whose vanilla objectToSpawn was null kept a
                            // rolled-off card's projectile forever (and stacked
                            // the next one on top).
                            if (gun.projectiles != null && gun.projectiles.Length > 0)
                                gun.projectiles[0].objectToSpawn = b.projectile;
                            gun.dontAllowAutoFire = false;
                        }
                    }
                    catch { }
                }
                player.data.currentCards.Clear();
                // Codex audit find 2: ApplyCardStats stacks CardAudioModifiers
                // (Cold bullets' ColdStack) onto PlayerAudioModifyers and the
                // reset trio never removes them — replaying a surviving Cold
                // bullets would then increment the stack a second time.
                // Cleared here, BEFORE the replay rebuilds the real stacks.
                try
                {
                    var pam = player.GetComponent<PlayerAudioModifyers>();
                    if (pam != null && pam.modifyers != null)
                    {
                        foreach (var m in pam.modifyers)
                        {
                            // The static list holds the wrapper's .modifier.
                            try { if (m != null) PlayerAudioModifyers.activeModifyer?.Remove(m.modifier); } catch { }
                        }
                        pam.modifyers.Clear();
                    }
                }
                catch { }
                TabStatsOverlay.RecordCardBaseline(player);   // baseline = 0 for the rebuilt list
                // Local player's own card bar rebuilds below via OFFLINE_Pick.
                if (player.data.view != null && player.data.view.IsMine)
                {
                    try
                    {
                        var bars = CardBarHandler.instance != null ? CardBarHandler.instance.cardBars : null;
                        if (bars != null && bars.Length > 0) bars[0].ClearBar();
                    }
                    catch { }
                }
            }
            catch (Exception ex) { Plugin.Log.LogError($"[FFA] rolling reset({pid}): {ex.Message}"); }

            // One frame: ResetStats' Object.Destroy of the card-script hosts
            // runs its OnDestroy chain at end of frame; the scrub then clears
            // whatever an aborted teardown left subscribed (#92) or keyed
            // (#103) before the replay re-registers.
            yield return null;
            try { GMArmsRaceStartGameBlockResetPatch.RunSweep("FFA rolling removal"); } catch { }

            foreach (var card in survivors)
            {
                ApplyCardTo(player, card);
                // Codex audit find 1 (HIGH): two copies of the same
                // AttackLevel-stacking card applied in ONE frame each see the
                // OTHER unstarted copy, and both hosts get destroyed — the
                // bar shows the cards but the behavior is gone (16 cards:
                // Shield Charge, Supernova, Frost slam...). One frame between
                // applies lets the first host finish Start(), so a duplicate
                // levels it up exactly like a normal round-by-round pick.
                // This also puts a frame between the last survivor and the
                // caller's new-card apply.
                yield return null;
            }
        }
    }

    // ═════════════════════════════ Patches ═════════════════════════════

    /// <summary>Death handling: vanilla TeamsAlive() is hardcoded to teams 0/1
    /// and would never end an FFA round. Full replacement in FFA rooms.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "PlayerDied")]
    class GMArmsRace_PlayerDied_Ffa_Patch
    {
        static bool Prefix(GM_ArmsRace __instance, Player killedPlayer, int playersAlive)
        {
            if (!FfaMode.EngineActive()) return true;
            // Every death funnels through here (vanilla invokes PlayerDied
            // per victim), so this is the kill-credit tally point.
            FfaMode.RecordKillFor(killedPlayer);
            FfaMode.HandlePlayerDied(__instance);
            return false;
        }
    }

    /// <summary>Alive-count relay: vanilla PlayerManager.PlayerDied does
    /// players[i].data.dead with NO null guard, so a death landing in the
    /// short window between a leave and the 0.7s purge would NRE and swallow
    /// the death event entirely (GM_ArmsRace.PlayerDied never invoked).
    /// FFA-gated fake-null-safe replacement of the same 4 lines.</summary>
    [HarmonyPatch(typeof(PlayerManager), "PlayerDied")]
    class PlayerManager_PlayerDied_Ffa_Patch
    {
        static bool Prefix(PlayerManager __instance, Player player)
        {
            if (!FfaMode.EngineActive()) return true;
            try
            {
                int num = 0;
                foreach (var p in __instance.players)
                {
                    if (p == null || p.gameObject == null || p.data == null) continue;
                    if (!p.data.dead) num++;
                }
                __instance.PlayerDiedAction?.Invoke(player, num);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] PlayerDied relay: {ex.Message}"); }
            return false;
        }
    }

    /// <summary>Round accounting: vanilla's switch handles winningTeamID 0/1
    /// only — a team-2+ win would silently do NOTHING (hang). Full replacement.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "RPCA_NextRound")]
    class GMArmsRace_NextRound_Ffa_Patch
    {
        static bool Prefix(GM_ArmsRace __instance, int losingTeamID, int winningTeamID,
                           int p1PointsSet, int p2PointsSet, int p1RoundsSet, int p2RoundsSet)
        {
            if (!FfaMode.EngineActive()) return true;
            FfaMode.HandleNextRound(__instance, winningTeamID);
            return false;
        }
    }

    /// <summary>Game start (game 1 AND same-room rematches — IDoRematch calls
    /// DoStartGame directly, learning #138): replace the whole flow so the
    /// pick phase is simultaneous and 2-team UI pieces are skipped.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "DoStartGame")]
    class GMArmsRace_DoStartGame_Ffa_Patch
    {
        static bool Prefix(GM_ArmsRace __instance, ref IEnumerator __result)
        {
            if (!FfaMode.EngineActive()) return true;
            __result = FfaMode.FfaDoStartGame(__instance);
            return false;
        }
    }

    /// <summary>Card bar guard: OFFLINE_Pick calls CardBarHandler.AddCard with
    /// the player's PlayerID (0..9) — vanilla has TWO bars, so anything >= 2
    /// would IndexOutOfRange. In FFA only the LOCAL player's own cards render
    /// (bar 0); everyone else's live builds are on the hold-Tab board.</summary>
    [HarmonyPatch(typeof(CardBarHandler), "AddCard")]
    class CardBarHandler_AddCard_Ffa_Patch
    {
        static bool Prefix(CardBarHandler __instance, int teamId, CardInfo card)
        {
            if (!FfaMode.EngineActive()) return true;
            try
            {
                if (FfaMode.SuppressCardBarAdd(teamId)) return false;
                var local = PlayerManager.instance?.players?.FirstOrDefault(
                    p => p != null && p.gameObject != null && p.data?.view != null && p.data.view.IsMine);
                if (local == null || teamId != local.PlayerID) return false;  // skip others silently
                var bars = __instance.cardBars;
                if (bars == null || bars.Length == 0) return false;
                bars[0].AddCard(card);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] card bar add: {ex.Message}"); }
            return false;
        }
    }

    /// <summary>FFA spawn variety without mutating PlayerManager.players.
    /// Plugin.cs first sorts/pads MapManager.GetSpawnPoints at default Harmony
    /// priority. Priority.Last runs this postfix second over that final array.
    /// HarmonyX orders priorities high-to-low; the length guard also fails
    /// visibly if that ordering ever changes. A fixed xorshift32 Fisher-Yates
    /// avoids UnityEngine.Random and runtime-dependent Random state.</summary>
    [HarmonyPatch(typeof(MapManager), "GetSpawnPoints")]
    class MapManager_GetSpawnPoints_FfaShuffle_Patch
    {
        [HarmonyPriority(Priority.Last)]
        static void Postfix(ref SpawnPoint[] __result)
        {
            try
            {
                if (!FfaMode.EngineActive() || __result == null || __result.Length < 2) return;
                int needed = Diag2v2.PlayersNeeded();
                if (__result.Length < needed)
                {
                    Plugin.Log.LogWarning(
                        $"[FFA] spawn shuffle saw {__result.Length}/{needed} points - sort/pad postfix did not run first");
                    return;
                }

                var shuffled = (SpawnPoint[])__result.Clone();
                uint state = FfaMode.SpawnShuffleSeed();
                for (int i = shuffled.Length - 1; i > 0; i--)
                {
                    state ^= state << 13;
                    state ^= state >> 17;
                    state ^= state << 5;
                    int j = (int)(state % (uint)(i + 1));
                    var tmp = shuffled[i];
                    shuffled[i] = shuffled[j];
                    shuffled[j] = tmp;
                }
                __result = shuffled;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] spawn shuffle: {ex.Message}"); }
        }
    }

    /// <summary>Leaver tolerance: vanilla NetworkConnectionHandler ends the
    /// match FOR EVERYONE the moment any player leaves (OnPlayerLeftRoom →
    /// DoDisconnect → NetworkRestart). Correct for 1v1/2v2/1v2 — but a
    /// 10-player FFA must survive a single rage-quit. While 2+ players
    /// remain, suppress the cascade and instead check whether the leaver was
    /// one of the last two standing (the survivor then takes the point). When
    /// only one player remains, vanilla's cascade runs and cleans up.</summary>
    [HarmonyPatch(typeof(NetworkConnectionHandler), "OnPlayerLeftRoom")]
    class NCH_OnPlayerLeftRoom_Ffa_Patch
    {
        static bool Prefix(Photon.Realtime.Player otherPlayer)
        {
            if (!FfaMode.EngineActive()) return true;
            try
            {
                // Log-only, but fighter count — an actor count here over-reports
                // by the spectator count and misleads triage (census recon).
                int remaining = RoomActors.ActiveFighterCount();
                // Review find 6: ALWAYS suppress the cascade in a live FFA —
                // the old `remaining >= 2` form handed the last departure back
                // to vanilla, which tore the room down before the survivor
                // could be awarded the point/game or the result reported.
                // CheckRoundAfterLeave resolves the round (awarding the last
                // player standing) and, when only one client is left, ends the
                // game and reports before leaving the room itself.
                Plugin.Log.LogInfo($"[FFA] player left, {remaining} remain — match continues (vanilla end-cascade suppressed)");
                if (Plugin.Instance != null)
                    Plugin.Instance.StartCoroutine(FfaMode.CheckRoundAfterLeave());
                return false;
            }
            catch { }
            return true;
        }
    }

    /// <summary>Card targeting: vanilla GetOtherPlayer resolves "the other
    /// team" as GetOtherTeam(asker) which returns 0 for every team except 0 —
    /// in FFA, slots 2+ would always target slot 0's player (Codex design
    /// find 16). Replace with nearest living non-self player.</summary>
    [HarmonyPatch(typeof(PlayerManager), "GetOtherPlayer")]
    class PlayerManager_GetOtherPlayer_Ffa_Patch
    {
        static bool Prefix(PlayerManager __instance, Player asker, ref Player __result)
        {
            if (!FfaMode.EngineActive()) return true;
            try
            {
                __result = FfaTargeting.NearestOpponent(__instance, asker.transform.position, asker.TeamID);
                return false;
            }
            catch { return true; }
        }
    }

    /// <summary>Review find 7: several vanilla card effects (Chase,
    /// LineOfSightTrigger, LineRangeEffect, RadarShot...) never call
    /// GetOtherPlayer — they call
    /// `GetClosestPlayerInTeam(pos, GetOtherTeam(myTeam))` directly. An int
    /// team id cannot express "every other player" in FFA, so those effects
    /// only ever saw slot 0 (and nothing at all once slot 0 died). In FFA the
    /// team argument is meaningless: return the nearest LIVING player that
    /// isn't the caller. The caller is identified positionally (vanilla always
    /// passes its own transform position), so a self-hit is excluded by an
    /// exact-position match rather than by team.</summary>
    [HarmonyPatch(typeof(PlayerManager), "GetClosestPlayerInTeam")]
    class PlayerManager_GetClosestPlayerInTeam_Ffa_Patch
    {
        static bool Prefix(PlayerManager __instance, Vector3 position, int team,
                           bool needVision, ref Player __result)
        {
            if (!FfaMode.EngineActive()) return true;
            try
            {
                __result = FfaTargeting.NearestOpponent(__instance, position, -1, needVision);
                return false;
            }
            catch { return true; }
        }
    }

    internal static class FfaTargeting
    {
        /// <summary>Nearest living player to `position` that is neither the
        /// asker (excludeTeam, when known) nor standing exactly at `position`
        /// (the positional self-exclusion the vanilla call sites need).
        /// Bug #165: the positional exclusion is only sound when the call site
        /// queries from the ASKER'S OWN transform — a detached attack (a
        /// Radiance wave parked where it was emitted) must pass excludePlayer
        /// so its owner is excluded by IDENTITY, or the owner becomes the
        /// wave's nearest target the moment they move.</summary>
        public static Player NearestOpponent(PlayerManager pm, Vector3 position,
                                             int excludeTeam, bool needVision = false,
                                             Player excludePlayer = null)
        {
            Player best = null;
            float bestDist = float.PositiveInfinity;
            if (pm?.players == null) return null;
            foreach (var p in pm.players)
            {
                if (p == null || p.gameObject == null || p.data == null) continue;
                if (p.data.dead) continue;
                if (excludeTeam >= 0 && p.TeamID == excludeTeam) continue;
                if (excludePlayer != null && p == excludePlayer) continue;   // identity exclusion (bug #165)
                float d = Vector2.Distance(position, p.transform.position);
                if (d < 0.01f) continue;                 // that's the asker
                if (d >= bestDist) continue;
                if (needVision)
                {
                    try { if (!pm.CanSeePlayer(position, p).canSee) continue; }
                    catch { }
                }
                bestDist = d; best = p;
            }
            return best;
        }
    }

    /// <summary>Bug #165 (Radiance self-damage in FFA, first field report of
    /// the class). The shared GetClosestPlayerInTeam patch above excludes the
    /// asker POSITIONALLY (d &lt; 0.01) on the premise that vanilla call sites
    /// query from their own transform — but LineRangeEffect (Radiance's
    /// expanding sun wave) is spawned UNPARENTED at the owner's feet and
    /// queries from the wave's center. The moment the owner moves, they are
    /// the wave's nearest valid target: one guaranteed self-hit per wave, the
    /// `done` latch then means that wave can never hit anyone else, and
    /// lifesteal never fires on self-damage (vanilla DealtDamage gates on
    /// !selfDamage) — which is why the report blamed Parasite too. Fix:
    /// replicate vanilla's tiny Update with an IDENTITY exclusion of the
    /// owner. Runs on the wave owner's client only (spawned.IsMine()) and the
    /// hit travels the normal damage RPC, so no shared simulation is touched
    /// and no capability gate is needed (#269 does not apply). On exception
    /// return FALSE (skip this frame's targeting — under-application, #288);
    /// returning true would re-enter vanilla + the shared patch, i.e. the bug.</summary>
    [HarmonyPatch(typeof(LineRangeEffect), "Update")]
    class LineRangeEffect_FfaOwnerExclusion_Patch
    {
        static bool Prefix(LineRangeEffect __instance)
        {
            if (!FfaMode.EngineActive()) return true;
            try
            {
                if (__instance.done || __instance.spawned == null || !__instance.spawned.IsMine())
                    return false;
                var owner = __instance.owner;
                var target = FfaTargeting.NearestOpponent(PlayerManager.instance,
                    __instance.transform.position, -1, needVision: true, excludePlayer: owner);
                if (target != null)
                {
                    const float slack = 2f;
                    float radius = __instance.lineEffect != null ? __instance.lineEffect.GetRadius() : 0f;
                    float d = Vector2.Distance(__instance.transform.position, target.transform.position);
                    if (d < radius + slack && d > radius - slack)
                    {
                        __instance.done = true;
                        Vector3 dir = (target.transform.position - __instance.transform.position).normalized;
                        target.data.healthHandler.CallTakeDamage(
                            __instance.dmg * __instance.transform.localScale.x * dir,
                            target.transform.position, null, owner);
                        target.data.healthHandler.CallTakeForce(
                            __instance.knockback * __instance.transform.localScale.x * dir);
                    }
                }
                return false;
            }
            catch { return false; }
        }
    }

    /// <summary>
    /// Bug #119: enforce the FFA post-spawn no-fire window.
    ///
    /// WeaponHandler is on the PLAYER root (WeaponHandler.Awake does
    /// data = GetComponent&lt;CharacterData&gt;()), so ownership resolves cleanly
    /// here. Do NOT copy the idiom from the F5 gun block in Plugin.cs: that
    /// one calls Gun.GetComponentInParent&lt;PhotonView&gt;(), which is ALWAYS null
    /// because Holding.Awake instantiates the holdable unparented - that patch
    /// has never fired in any mode.
    ///
    /// Owner-only is both sufficient and complete: Gun.FireBurst only spawns a
    /// projectile under CheckIsMine(), so a blocked owner shot never exists
    /// anywhere. Card-driven forceAttack calls bypass WeaponHandler.Attack
    /// entirely and are deliberately left alone - they need a trigger (a block,
    /// a hit) that cannot occur inside a no-fire window anyway.
    /// </summary>
    [HarmonyPatch(typeof(WeaponHandler), "Attack")]
    internal class WeaponHandler_FfaSpawnGrace_Patch
    {
        private static float lastDenyLog = -999f;

        static bool Prefix(WeaponHandler __instance)
        {
            try
            {
                if (!FfaMode.SpawnGraceActive) return true;
                var data = __instance != null ? __instance.GetComponent<CharacterData>() : null;
                if (data == null || data.view == null || !data.view.IsMine) return true;
                if (Time.realtimeSinceStartup - lastDenyLog > 1f)
                {
                    lastDenyLog = Time.realtimeSinceStartup;
                    Plugin.Log.LogInfo($"[FFA-GRACE] fire suppressed ({FfaMode.SpawnGraceLeft:F2}s left)");
                }
                return false;
            }
            catch { return true; }   // fail OPEN - never strand a player unable to shoot
        }
    }

    /// <summary>
    /// Bug #136: extend the spawn grace to BLOCK, at the input layer.
    ///
    /// How a block actually replicates (SyncPlayerMovement decompile —
    /// logs-snapshot/decompiled/full/Photon.Pun/SyncPlayerMovement.cs): the
    /// OWNER's Block.Update reads input.shieldWasPressed -> TryBlock ->
    /// RPCA_DoBlock locally; that invokes Block.BlockAction, which the
    /// owner's SyncPlayerMovement subscribed with SendBlock -> RPC
    /// "RPCAO_DoBlock" to Others. Remote replicas NEVER read input for
    /// blocks (controlledElseWhere gates GeneralInput.Update, and the
    /// movement sync stream carries direction/aim/jump only). So clearing
    /// shieldWasPressed on the owner is complete and consistent: no local
    /// block, therefore no BlockAction, therefore no RPC, therefore no
    /// replica block anywhere. (Refines #92's "replicas simulate blocks from
    /// replicated input" — the trigger is an owner-event RPC; only the block
    /// EXECUTION is per-replica.) Same input layer vanilla's own lockInput
    /// suppression uses (#254). shieldWasPressed is a per-frame edge flag,
    /// so there is no state to strand: the first press after the window
    /// works untouched.
    /// </summary>
    [HarmonyPatch(typeof(GeneralInput), "Update")]
    internal class GeneralInput_FfaSpawnGrace_Patch
    {
        private static float lastDenyLog = -999f;

        static void Postfix(GeneralInput __instance)
        {
            try
            {
                if (!FfaMode.SpawnGraceActive) return;
                if (__instance == null || !__instance.shieldWasPressed) return;
                var data = __instance.data;   // vanilla's own wiring (publicized)
                if (data == null || data.view == null || !data.view.IsMine) return;
                __instance.shieldWasPressed = false;
                if (Time.realtimeSinceStartup - lastDenyLog > 1f)
                {
                    lastDenyLog = Time.realtimeSinceStartup;
                    Plugin.Log.LogInfo($"[FFA-GRACE] block suppressed ({FfaMode.SpawnGraceLeft:F2}s left)");
                }
            }
            catch { }   // fail OPEN - never strand a player unable to block
        }
    }

    /// <summary>
    /// Second gate for the block grace (Codex batch find 12): Unity gives no
    /// ordering guarantee between GeneralInput.Update, the mod's grace-arming
    /// Update and Block.Update, so on the exact arming frame a press could
    /// slip past the input Postfix. TryBlock is safe to gate owner-side: a
    /// skipped TryBlock never runs RPCA_DoBlock, so BlockAction never fires
    /// and SyncPlayerMovement never relays the block RPC — no replica ever
    /// disagrees (#268). Remote replicas never reach TryBlock at all (their
    /// shieldWasPressed is never set online).
    /// </summary>
    [HarmonyPatch(typeof(Block), "TryBlock")]
    internal class Block_FfaSpawnGrace_Patch
    {
        static bool Prefix(Block __instance)
        {
            try
            {
                if (!FfaMode.SpawnGraceActive) return true;
                var data = __instance != null ? __instance.data : null;
                if (data == null || data.view == null || !data.view.IsMine) return true;
                return false;
            }
            catch { return true; }   // fail OPEN
        }
    }


}
