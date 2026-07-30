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
        public const int RoundsToWin = 5;
        public const int PointsToWinRound = 2;
        public const int CardCap = 5;
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
        public static int PointsTotalFor(int teamId) { return pointsTotal.TryGetValue(teamId, out var v) ? v : 0; }
        public static int KillsFor(int teamId) { return kills.TryGetValue(teamId, out var v) ? v : 0; }

        /// <summary>Placement order (Sid's item 3): points (rounds) desc, then
        /// ALL half points earned incl. spent ones (pointsTotal) desc, then
        /// total kills desc, then slot for stability. 0 = tied placement
        /// (shares a place, competition ranking). Used by the game-over
        /// placement, the report payload ordering and the score HUD.</summary>
        public static int ComparePlacement(int teamA, int teamB)
        {
            int c = RoundsFor(teamB).CompareTo(RoundsFor(teamA));
            if (c != 0) return c;
            c = PointsTotalFor(teamB).CompareTo(PointsTotalFor(teamA));
            if (c != 0) return c;
            return KillsFor(teamB).CompareTo(KillsFor(teamA));
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

        /// <summary>Current overall leader (rounds, then points) or null on a
        /// tie/no score. Used by the crown patch.</summary>
        public static Player CurrentLeader()
        {
            try
            {
                if (PlayerManager.instance == null) return null;
                Player best = null;
                int bestR = -1, bestP = -1;
                bool tie = false;
                foreach (var p in PlayerManager.instance.players)
                {
                    if (p == null || p.gameObject == null || p.data == null) continue;
                    int r = RoundsFor(p.TeamID), pt = PointsFor(p.TeamID);
                    if (r > bestR || (r == bestR && pt > bestP))
                    {
                        best = p; bestR = r; bestP = pt; tie = false;
                    }
                    else if (r == bestR && pt == bestP) tie = true;
                }
                if (tie || (bestR == 0 && bestP == 0)) return null;
                return best;
            }
            catch { return null; }
        }

        /// <summary>Compact score line for the IMGUI strip: one entry per live
        /// player, sorted by (rounds, points) desc. ASCII only (#47).</summary>
        public static string ScoreLine()
        {
            try
            {
                if (PlayerManager.instance == null) return "";
                var entries = new List<(string name, int r, int p, bool dead)>();
                foreach (var pl in PlayerManager.instance.players)
                {
                    if (pl == null || pl.gameObject == null || pl.data == null) continue;
                    string nm = "P" + pl.PlayerID;
                    try { nm = pl.data.view?.Owner?.NickName ?? nm; } catch { }
                    if (nm.Length > 12) nm = nm.Substring(0, 12);
                    entries.Add((nm, RoundsFor(pl.TeamID), PointsFor(pl.TeamID), pl.data.dead));
                }
                entries.Sort((a, b) => b.r != a.r ? b.r.CompareTo(a.r) : b.p.CompareTo(a.p));
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

        // ── Lifecycle ──

        /// <summary>New game in the room (game 1 AND rematches — invoked from
        /// the DoStartGame replacement, which vanilla runs on both paths).</summary>
        public static void OnGameStart()
        {
            gameNumber++;
            cycleNumber = 0;
            points.Clear(); rounds.Clear(); pointsTotal.Clear(); kills.Clear();
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
            try { remaining = PhotonNetwork.CurrentRoom?.PlayerCount ?? 0; } catch { }

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
                        "FFA cancelled - not enough players for a fresh game.");
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
                try { remaining = PhotonNetwork.CurrentRoom?.PlayerCount ?? 0; } catch { }
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
                int winnerTeam = alive.Count == 1 ? alive[0].TeamID : -1;
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
                        int remaining = PhotonNetwork.CurrentRoom?.PlayerCount ?? 0;
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
        }

        /// <summary>Vanilla WaitForSyncUp waits for any one peer's reply with
        /// NO timeout — alone in the room (everyone else left mid-transition)
        /// it waits forever. Same handshake, bounded, skipped with no peers.</summary>
        private static IEnumerator BoundedSyncUp(GM_ArmsRace gm, float maxSeconds)
        {
            if (PhotonNetwork.OfflineMode) yield break;
            int others = 0;
            try { others = (PhotonNetwork.CurrentRoom?.PlayerCount ?? 1) - 1; } catch { }
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
            try { return PhotonNetwork.CurrentRoom?.PlayerCount ?? 0; } catch { return 0; }
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
            try { ApiClient.FfaLeaveQueue(); } catch { }
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
            try { ApiClient.FfaLeaveQueue(); } catch { }
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
        public static IEnumerator FfaDoStartGame(GM_ArmsRace gm)
        {
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
                    try { ApiClient.FfaLeaveQueue(); } catch { }
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
                // Initial draw: EVERYONE picks one card, simultaneously.
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
            CompetitiveUI.ShowNotification($"FFA - {Diag2v2.PlayersNeeded()} players - first to {RoundsToWin} points!",
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

            if (PhotonNetwork.IsMasterClient)
                SetRoomProp(PropCycle, $"{game}:{cycle}:{string.Join(",", pickerIds)}");

            // Wait for the manifest (all clients, incl. master reading its own write).
            List<int> manifest = null;
            while (Time.realtimeSinceStartup - phaseStart < ManifestWaitSeconds)
            {
                manifest = ReadCycleManifest(game, cycle);
                if (manifest != null) break;
                // Master migration: if the original master died before
                // publishing, the new master publishes.
                if (PhotonNetwork.IsMasterClient && Time.realtimeSinceStartup - phaseStart > 2f)
                    SetRoomProp(PropCycle, $"{game}:{cycle}:{string.Join(",", pickerIds)}");
                yield return null;
            }
            if (manifest == null)
            {
                Plugin.Log.LogWarning($"[FFA] pick cycle {cycle}: no manifest after {ManifestWaitSeconds}s — using local picker set");
                manifest = pickerIds;
            }

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
            while (true)
            {
                result = ReadCycleResult(game, cycle);
                if (result != null) break;
                float now = Time.realtimeSinceStartup;
                if (now - lastCollect > 0.25f)   // prop-table reads throttled
                {
                    lastCollect = now;
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
                    CompetitiveUI.ShowNotification("Pick window closed - no card this round.",
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

        // ── Local pick UI ──

        private static readonly List<GameObject> localCardObjects = new List<GameObject>();

        private static IEnumerator FfaLocalPickUI(GM_ArmsRace gm, Player localPlayer, int game, int cycle)
        {
            var choice = CardChoice.instance;
            if (choice == null) yield break;
            // Card slot anchors: vanilla CardChoice's own children transforms.
            var slots = new List<Transform>();
            for (int i = 0; i < choice.transform.childCount && i < 5; i++)
                slots.Add(choice.transform.GetChild(i));
            if (slots.Count == 0) yield break;

            try { ArtHandler.instance.SetSpecificArt(choice.cardPickArt); } catch { }

            // Local candidates (own RNG — candidates are per-picker private).
            var candidates = new List<CardInfo>();
            var candidateObjs = new List<GameObject>();
            int guard = 0;
            while (candidates.Count < slots.Count && guard++ < 200)
            {
                var c = PickRandomCard(choice);
                if (c == null) break;
                if (!IsCardAllowedFor(localPlayer, c, candidates)) continue;
                candidates.Add(c);
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
                var actions = localPlayer?.data?.playerActions;
                if (actions != null)
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
                    CompetitiveUI.ShowNotification($"Time's up - {display} picked automatically.",
                        new Color(1f, 0.85f, 0.5f), 5f);
                }
                catch { }
            }
            try { GameStateWatcher.RecordFfaLocalPick(cardName, RoundsTotalAll()); } catch { }

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
                int remaining = PhotonNetwork.CurrentRoom?.PlayerCount ?? 0;
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
        /// (the positional self-exclusion the vanilla call sites need).</summary>
        public static Player NearestOpponent(PlayerManager pm, Vector3 position,
                                             int excludeTeam, bool needVision = false)
        {
            Player best = null;
            float bestDist = float.PositiveInfinity;
            if (pm?.players == null) return null;
            foreach (var p in pm.players)
            {
                if (p == null || p.gameObject == null || p.data == null) continue;
                if (p.data.dead) continue;
                if (excludeTeam >= 0 && p.TeamID == excludeTeam) continue;
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

}
