using System;
using System.Collections.Generic;
using System.Text;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Measurement only. Answers ONE question with a number: between the round
    /// call-in and the moment vanilla forces the bodies to stop, does a seat
    /// that is WATCHING keep simulating them when a seat that is PLAYING does
    /// not?
    ///
    /// The suspicion is structural. Vanilla stops the bodies from INSIDE
    /// `GM_ArmsRace.RPCA_NextRound` — `PlayerManager.SetPlayersSimulated(false)`
    /// at V/GM_ArmsRace.cs:531, in the middle of a method whose other work
    /// (score writes, GameManager.GameOver, the transition coroutine) an
    /// observer seat must never run. `Spectator_ObserveNextRound_Patch` skips
    /// the WHOLE method, so the stop goes with it, and nothing else on the
    /// observer path performs it.
    ///
    /// **The window edges are the whole design, and the first version got the
    /// closing edge wrong.** It closed on `MOVE PLAYERS END`, which review r9
    /// showed is emitted at V/PlayerManager.cs:409 — the END of `Move`, a
    /// coroutine that first sets `simulated = false` and `isKinematic = true`
    /// and then drives `transform.position` frame by frame from the death
    /// position to the spawn point. Every one of those scripted frames landed
    /// inside the window on BOTH seat kinds, so `moved` could never reach the
    /// noise floor and the stated acceptance test was unreachable by
    /// construction. The window now closes on the FIRST `MOVE PLAYERS START`
    /// (V/PlayerManager.cs:384), logged immediately before that per-player
    /// stop — which is exactly the interval the hypothesis is about. `MOVE
    /// PLAYERS END` is kept only as a late backstop.
    ///
    /// Displacement alone still cannot answer the question, so it is split by
    /// the flag: `movedSim` accumulates only while that player's
    /// `playerVel.simulated` is true, `movedStop` only while it is false.
    /// A body pushed by something other than simulation lands in `movedStop`
    /// and cannot be read as evidence.
    ///
    /// Two placement rules this file depends on, both the #376 class — a
    /// diagnostic inside the behaviour it judges is dead where it is needed:
    ///   * the window opens ABOVE `SpectatorPatchSupport.Suppress`, so a
    ///     FIGHTER seat emits the same line as a positive control, and a
    ///     suppression that fails to engage still produces a reading;
    ///   * the close runs ABOVE `OnUnityLog`'s spectator quiesce, which returns
    ///     at its fourth line on exactly the seat under test.
    ///
    /// ACCEPTANCE for the fix this informs: `movedSim` and `maxStepSim` on a
    /// spectator seat down to what the fighter control already reports.
    ///
    /// Bounded on purpose: a broadcast seat sits in matches all day, so this
    /// logs the first MAX_REPORTS windows of a session and then a periodic
    /// aggregate. One line per round, never one per frame — at ~60 fps that
    /// would be hundreds of lines a round and the per-frame maximum is carried
    /// as `maxStepSim` anyway.
    /// </summary>
    internal static class SpectatorTeardownProbe
    {
        /// <summary>Fixed observation horizon, NOT a "the marker never
        /// arrived" signal. With the close on `MOVE PLAYERS START` the real
        /// interval is short, but a window can still be abandoned by a seat
        /// that leaves or by a transition that never calls players in, and a
        /// window left open would fold the next round into its numbers.</summary>
        private const float WINDOW_HORIZON_SECONDS = 8f;

        /// <summary>Movement below this in a single frame is sampling noise
        /// (a body settling, float jitter), not simulation.</summary>
        private const float NOISE_FLOOR = 0.001f;

        private const int MAX_REPORTS = 20;
        private const int MAX_PLAYERS_LISTED = 8;

        private static bool open;
        private static float openedAt;
        private static string openSeat;
        private static int frames;
        private static int framesAnySimulated;
        private static int rosterAtOpen;
        private static bool rebased;
        private static float maxStepSim;
        private static readonly List<Vector3> lastPos = new List<Vector3>();
        private static readonly List<float> movedSim = new List<float>();
        private static readonly List<float> movedStop = new List<float>();

        private static int reports;
        private static int windowsTotal;
        private static float movedSimTotal;
        private static float movedStopTotal;
        private static int simFramesTotal;
        private static int framesTotal;

        /// <summary>Opened from the round call-in, ABOVE the observer gate.
        /// `seat` is the control axis: "spectator" is the case under
        /// suspicion, "fighter" is the seat where vanilla's own stop runs
        /// microseconds later.</summary>
        internal static void OpenWindow(string seat)
        {
            try
            {
                // A duplicate/bunched broadcast must not restart the clock —
                // the first call-in is where the teardown actually began.
                if (open) return;
                open = true;
                openedAt = Time.time;
                openSeat = seat;
                frames = 0;
                framesAnySimulated = 0;
                maxStepSim = 0f;
                rebased = false;
                lastPos.Clear();
                movedSim.Clear();
                movedStop.Clear();
                rosterAtOpen = RosterCount();
                windowsTotal++;
            }
            catch { open = false; }
        }

        /// <summary>Per-frame sampler. Costs one bool read while closed.</summary>
        internal static void Tick()
        {
            if (!open) return;
            try
            {
                if (Time.time - openedAt > WINDOW_HORIZON_SECONDS)
                {
                    CloseWindow("horizon");
                    return;
                }

                var players = PlayerManager.instance != null ? PlayerManager.instance.players : null;
                if (players == null) return;

                // A roster change mid-window invalidates the position
                // baselines (indices shift), so rebase rather than report a
                // list-reshuffle as movement — and say so in the line, or a
                // truncated window reads as a window with no movement.
                if (players.Count != lastPos.Count)
                {
                    if (lastPos.Count != 0) rebased = true;
                    lastPos.Clear();
                    movedSim.Clear();
                    movedStop.Clear();
                    for (int i = 0; i < players.Count; i++)
                    {
                        lastPos.Add(SafePos(players, i));
                        movedSim.Add(0f);
                        movedStop.Add(0f);
                    }
                    return;
                }

                bool anySimulated = false;
                for (int i = 0; i < players.Count; i++)
                {
                    var p = players[i];
                    if (p == null) continue;

                    bool sim = false;
                    try
                    {
                        sim = p.data != null && p.data.playerVel != null && p.data.playerVel.simulated;
                    }
                    catch { }
                    if (sim) anySimulated = true;

                    Vector3 now = SafePos(players, i);
                    float step = Vector3.Distance(now, lastPos[i]);
                    lastPos[i] = now;
                    if (step < NOISE_FLOOR) continue;
                    // Split by the flag. Displacement while the body is NOT
                    // simulated was applied by something else (vanilla's
                    // scripted respawn traversal, a revive, a map rescale) and
                    // is not evidence for or against the hypothesis.
                    if (sim)
                    {
                        movedSim[i] = movedSim[i] + step;
                        if (step > maxStepSim) maxStepSim = step;
                    }
                    else
                    {
                        movedStop[i] = movedStop[i] + step;
                    }
                }

                frames++;
                if (anySimulated) framesAnySimulated++;
            }
            catch { CloseWindow("error"); }
        }

        /// <summary>Closed by the first `MOVE PLAYERS START` (the per-player
        /// stop, i.e. the end of the interval in question), by `MOVE PLAYERS
        /// END` as a late backstop, by the reliable room-exit edge, or by the
        /// horizon. Emits the one line the question is settled with.</summary>
        internal static void CloseWindow(string why)
        {
            if (!open) return;
            open = false;
            try
            {
                float totalSim = 0f, totalStop = 0f;
                for (int i = 0; i < movedSim.Count; i++) totalSim += movedSim[i];
                for (int i = 0; i < movedStop.Count; i++) totalStop += movedStop[i];
                movedSimTotal += totalSim;
                movedStopTotal += totalStop;
                simFramesTotal += framesAnySimulated;
                framesTotal += frames;

                if (reports >= MAX_REPORTS)
                {
                    // Budget spent. The heartbeat carries the ANSWER, not just
                    // a volume count, so a log opened late in a long sitting is
                    // still worth reading.
                    if (windowsTotal % MAX_REPORTS == 0)
                        Plugin.Log?.LogInfo(
                            "[SPEC-FREEZE] totals seat=" + (openSeat ?? "?") +
                            " windows=" + windowsTotal +
                            " simFrames=" + simFramesTotal + "/" + framesTotal +
                            " movedSim=" + movedSimTotal.ToString("F2") +
                            " movedStop=" + movedStopTotal.ToString("F2") +
                            " maxStepSim=" + maxStepSim.ToString("F4"));
                    return;
                }
                reports++;

                var sb = new StringBuilder();
                sb.Append("[SPEC-FREEZE] seat=").Append(openSeat ?? "?")
                  .Append(" close=").Append(why)
                  .Append(" dur=").Append((Time.time - openedAt).ToString("F2")).Append("s")
                  .Append(" frames=").Append(frames)
                  .Append(" players=").Append(rosterAtOpen)
                  .Append(rebased ? " rebased=1" : "")
                  .Append(" simFrames=").Append(framesAnySimulated).Append("/").Append(frames)
                  .Append(" movedSim=").Append(totalSim.ToString("F3"))
                  .Append(" movedStop=").Append(totalStop.ToString("F3"))
                  .Append(" maxStepSim=").Append(maxStepSim.ToString("F4"));
                int listed = Math.Min(movedSim.Count, MAX_PLAYERS_LISTED);
                for (int i = 0; i < listed; i++)
                    sb.Append(" p").Append(i).Append("=").Append(movedSim[i].ToString("F3"))
                      .Append("/").Append(movedStop[i].ToString("F3"));
                Plugin.Log?.LogInfo(sb.ToString());

                if (reports == MAX_REPORTS)
                    Plugin.Log?.LogInfo(
                        "[SPEC-FREEZE] sample budget spent after " + MAX_REPORTS +
                        " windows; a totals line follows every " + MAX_REPORTS + " windows");
            }
            catch { }
        }

        private static Vector3 SafePos(List<Player> players, int i)
        {
            try
            {
                var p = players[i];
                return p != null ? p.transform.position : Vector3.zero;
            }
            catch { return Vector3.zero; }
        }

        private static int RosterCount()
        {
            try
            {
                var players = PlayerManager.instance != null ? PlayerManager.instance.players : null;
                return players != null ? players.Count : 0;
            }
            catch { return 0; }
        }
    }
}
