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
        // Pick window (bug #92-#98): the old 25s CLIENT auto-pick silently
        // confirmed card 0 for anyone who hadn't picked yet — with one human
        // testing three seats it fired seconds after his own pick+key-spam,
        // which read as "spamming space forces everyone's first card". Picks
        // are NEVER made for a player now. The master closes the window
        // adaptively instead: at least PickBase, extended by PickGrace after
        // each received pick, hard-capped at PickCap; whoever hasn't picked
        // by then simply gets no card that cycle.
        private const float PickBaseSeconds = 45f;
        private const float PickGraceSeconds = 20f;
        private const float PickCapSeconds = 90f;
        private const float ManifestWaitSeconds = 8f;

        // Photon property keys (FFA pick-sync protocol; all values ASCII).
        private const string PropCycle = "cr_ffa_cyc";   // room: "{game}:{cycle}:{pid,pid,...}"
        private const string PropResult = "cr_ffa_res";  // room: "{game}:{cycle}:{pid=Card|pid=Card}"
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
        private static float matchStartRealtime = 0f;
        // Pick-window state for the HUD countdown (CompetitiveUI reads these).
        private static bool pickPhaseActive = false;
        private static float pickDeadlineRealtime = 0f;
        private static bool localPickOpen = false;     // local player's own pick UI is up

        public static bool PickPhaseActive => pickPhaseActive;
        public static bool LocalPickOpen => localPickOpen;
        /// <summary>Seconds until the pick window closes (display only — the
        /// master's own copy of the same rule is what actually closes it).</summary>
        public static float PickSecondsLeft =>
            pickPhaseActive ? Mathf.Max(0f, pickDeadlineRealtime - Time.realtimeSinceStartup) : 0f;

        public class FfaLeaver
        {
            public string displayName;
            public int slot, roundsWon, pointsTotal, kills;
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

        // ── Lifecycle ──

        /// <summary>New game in the room (game 1 AND rematches — invoked from
        /// the DoStartGame replacement, which vanilla runs on both paths).</summary>
        public static void OnGameStart()
        {
            gameNumber++;
            cycleNumber = 0;
            points.Clear(); rounds.Clear(); pointsTotal.Clear(); kills.Clear();
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
            decks.Clear(); pickHistory.Clear(); baselines.Clear();
            Leavers.Clear();
            isTransitioning = false;
            gameOverFired = false;
            pickPhaseActive = false;
            pickDeadlineRealtime = 0f;
            localPickOpen = false;
        }

        /// <summary>Capture a leaver's tallies before Photon destroys their
        /// player object. Called from GameStateWatcher's OnPlayerLeftRoom.</summary>
        public static void RecordLeaver(string steamId, string displayName, int teamId)
        {
            if (string.IsNullOrEmpty(steamId) || Leavers.ContainsKey(steamId)) return;
            Leavers[steamId] = new FfaLeaver
            {
                displayName = displayName ?? "Player",
                slot = teamId,
                roundsWon = RoundsFor(teamId),
                pointsTotal = PointsTotalFor(teamId),
                kills = KillsFor(teamId),
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

            if (!gameOverFired)
            {
                bool battle = false;
                try { battle = GameManager.instance != null && GameManager.instance.battleOngoing; } catch { }
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

        /// <summary>DoStartGame replacement body — game 1 and every rematch.</summary>
        public static IEnumerator FfaDoStartGame(GM_ArmsRace gm)
        {
            OnGameStart();
            PurgeDepartedPlayers("game start");
            GameManager.instance.battleOngoing = false;
            yield return new WaitForSeconds(0.25f);
            try { UIHandler.instance.HideJoinGameText(); } catch { }
            PlayerManager.instance.SetPlayersSimulated(false);
            PlayerManager.instance.SetPlayersVisible(false);
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
            // Nobody is ever picked FOR (bug #92-#98) — a picker who misses
            // the window gets no card this cycle.
            float deadline = phaseStart + PickBaseSeconds;
            int lastGotCount = 0;
            float lastCollect = -999f;
            bool wasMaster = PhotonNetwork.IsMasterClient;
            pickPhaseActive = true;
            pickDeadlineRealtime = deadline;
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
                        deadline = Mathf.Min(phaseStart + PickCapSeconds,
                                             Mathf.Max(deadline, now + PickGraceSeconds));
                    }
                    // Master migration mid-cycle (Codex review find 4): the
                    // new master's local deadline can already be past (its
                    // phase clock started later/earlier than the old
                    // master's). Grant one grace window before finalizing so
                    // an in-flight pick isn't discarded on the handover.
                    if (PhotonNetwork.IsMasterClient && !wasMaster)
                    {
                        wasMaster = true;
                        deadline = Mathf.Min(phaseStart + PickCapSeconds,
                                             Mathf.Max(deadline, now + PickGraceSeconds));
                        Plugin.Log.LogInfo($"[FFA] pick cycle {cycle}: became master mid-cycle — extending window");
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
                        }
                    }
                }
                if (now - phaseStart > PickCapSeconds + 15f)
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

            if (localUi != null) { try { gm.StopCoroutine(localUi); } catch { } }
            CleanupLocalPickUI();

            // The result is ground truth: a manifest picker missing from it
            // missed the window (their UI just got torn down above).
            if (iPick && localPlayer != null && !result.ContainsKey(localPlayer.PlayerID))
            {
                Plugin.Log.LogInfo($"[FFA] cycle {cycle}: local pick missed the window — no card this cycle");
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
                if (vis != null) { candidateObjs.Add(vis); localCardObjects.Add(vis); }
            }
            if (candidateObjs.Count == 0) yield break;

            CompetitiveUI.ShowNotification("Pick a card! (left/right + jump)", new Color(0.8f, 0.9f, 1f), 4f);

            int selected = 0;
            int lastDir = 0;
            float started = Time.realtimeSinceStartup;
            int chosen = -1;
            localPickOpen = true;
            // No auto-pick, ever (bug #92-#98: the old 25s auto-confirm of
            // card 0 was every "forced first card" report). If the window
            // closes first, the outer phase stops this coroutine and the
            // player simply gets no card this cycle. The 0.35s arm delay
            // keeps a jump pressed during the transition (or any queued
            // press on the very first frame) from insta-confirming card 0.
            const float armDelay = 0.35f;
            while (chosen < 0)
            {
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
            string cardName = candidates[chosen].gameObject.name.Replace("(Clone)", "");
            // Publish BEFORE any local application — application happens only
            // from the result manifest, identically on every client.
            try
            {
                var h = new ExitGames.Client.Photon.Hashtable();
                h[PropPick] = $"{RoomNonce()}:{game}:{cycle}:{cardName}";
                PhotonNetwork.LocalPlayer.SetCustomProperties(h);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] pick publish: {ex.Message}"); }
            Plugin.Log.LogInfo($"[FFA] local pick published: {cardName} (cycle {cycle})");
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

            if (deck.Count >= CardCap)
            {
                // Rolling Card Bar: the oldest card rolls off. No inverse-stats
                // path exists in ROUNDS — reset to the cached baseline and
                // replay the survivors, then apply the new card.
                var survivors = deck.Skip(deck.Count - (CardCap - 1)).ToList();
                Plugin.Log.LogInfo($"[FFA] rolling removal for pid {pid}: dropping '{deck[0].gameObject.name}'");
                yield return RollingResetAndReplay(player, survivors);
                deck.Clear();
                deck.AddRange(survivors);
            }

            ApplyCardTo(player, prefab);
            deck.Add(prefab);

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
                ApplyCardTo(player, card);
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

}
