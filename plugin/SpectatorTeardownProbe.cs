using System;
using System.Collections.Generic;
using System.Text;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Measurement only. Answers ONE question with a number: do player bodies
    /// keep simulating through the round teardown on a seat that is watching
    /// rather than playing?
    ///
    /// The suspicion is structural. Vanilla stops the bodies from INSIDE
    /// `GM_ArmsRace.RPCA_NextRound` — `PlayerManager.SetPlayersSimulated(false)`
    /// at V/GM_ArmsRace.cs:531, in the middle of a method whose other work
    /// (score writes, GameManager.GameOver, the transition coroutine) an
    /// observer seat must never run. `Spectator_ObserveNextRound_Patch` skips
    /// the WHOLE method, so the stop goes with it, and nothing else on the
    /// observer path performs it.
    ///
    /// That is an argument, not evidence, which is why no fix is written yet.
    /// Two things make this probe worth its lines:
    ///
    ///   * it opens the window from the SAME call-in on both seat kinds, so a
    ///     fighter seat is a positive control in the identical format — if a
    ///     fighter also reports movement, the reading is about teardown motion
    ///     generally and not about the suppression at all (#391);
    ///   * it does not live inside the mitigation it is meant to judge. The
    ///     window opens ABOVE the observer gate, so a suppression that fails to
    ///     engage still produces a line rather than silence (#376).
    ///
    /// The acceptance test for the eventual fix is this same line read back:
    /// `moved` and `maxStep` at the noise floor on a spectator seat, matching
    /// what the fighter control already reports.
    ///
    /// Bounded on purpose: a broadcast seat sits in matches all day, so the
    /// probe logs the first MAX_REPORTS windows of a session and then keeps
    /// only totals. One line per round, not one per frame — at ~60 fps a
    /// per-frame line would be ~200 lines per round and tens of thousands per
    /// sitting, and the per-frame maximum is carried in `maxStep` anyway.
    /// </summary>
    internal static class SpectatorTeardownProbe
    {
        /// <summary>Hard cap on a window. Teardown is ~2.5-3.5 s; anything
        /// past this means the closing marker never arrived and the reading
        /// would be measuring the next round's combat.</summary>
        private const float WINDOW_CAP_SECONDS = 8f;

        /// <summary>Movement below this in a single frame is sampling noise
        /// (a body settling on the ground, float jitter), not simulation.</summary>
        private const float NOISE_FLOOR = 0.001f;

        private const int MAX_REPORTS = 20;
        private const int MAX_PLAYERS_LISTED = 8;

        private static bool open;
        private static float openedAt;
        private static string openSeat;
        private static int frames;
        private static int framesAnySimulated;
        private static int rosterAtOpen;
        private static float maxStep;
        private static readonly List<Vector3> lastPos = new List<Vector3>();
        private static readonly List<float> moved = new List<float>();

        private static int reports;
        private static int windowsTotal;
        private static float movedTotal;

        /// <summary>Opened from the round call-in, ABOVE the observer gate.
        /// `seat` is the control axis: "spectator" is the case under
        /// suspicion, "fighter" is the seat where vanilla's own stop runs.</summary>
        internal static void OpenWindow(string seat)
        {
            try
            {
                // A duplicate/bunched broadcast must not restart the clock —
                // the first call-in is where teardown actually began.
                if (open) return;
                open = true;
                openedAt = Time.time;
                openSeat = seat;
                frames = 0;
                framesAnySimulated = 0;
                maxStep = 0f;
                lastPos.Clear();
                moved.Clear();
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
                if (Time.time - openedAt > WINDOW_CAP_SECONDS)
                {
                    CloseWindow("cap");
                    return;
                }

                var players = PlayerManager.instance != null ? PlayerManager.instance.players : null;
                if (players == null) return;

                // A roster change mid-window invalidates the position
                // baselines (indices shift), so rebase rather than report a
                // list-reshuffle as movement.
                if (players.Count != lastPos.Count)
                {
                    lastPos.Clear();
                    moved.Clear();
                    for (int i = 0; i < players.Count; i++)
                    {
                        lastPos.Add(SafePos(players, i));
                        moved.Add(0f);
                    }
                    return;
                }

                bool anySimulated = false;
                for (int i = 0; i < players.Count; i++)
                {
                    var p = players[i];
                    if (p == null) continue;
                    try
                    {
                        if (p.data != null && p.data.playerVel != null && p.data.playerVel.simulated)
                            anySimulated = true;
                    }
                    catch { }

                    Vector3 now = SafePos(players, i);
                    float step = Vector3.Distance(now, lastPos[i]);
                    lastPos[i] = now;
                    if (step < NOISE_FLOOR) continue;
                    moved[i] = moved[i] + step;
                    if (step > maxStep) maxStep = step;
                }

                frames++;
                if (anySimulated) framesAnySimulated++;
            }
            catch { CloseWindow("error"); }
        }

        /// <summary>Closed by the combat-start marker (the teardown is over by
        /// then) or by the cap. Emits the one line the question is settled
        /// with.</summary>
        internal static void CloseWindow(string why)
        {
            if (!open) return;
            open = false;
            try
            {
                float total = 0f;
                for (int i = 0; i < moved.Count; i++) total += moved[i];
                movedTotal += total;

                if (reports >= MAX_REPORTS)
                {
                    // Budget spent: keep a heartbeat so a log opened late in a
                    // long sitting still carries the answer, at 1/20th the
                    // volume.
                    if (windowsTotal % MAX_REPORTS == 0)
                        Plugin.Log?.LogInfo(
                            "[SPEC-FREEZE] totals: windows=" + windowsTotal +
                            " movedTotal=" + movedTotal.ToString("F2"));
                    return;
                }
                reports++;

                var sb = new StringBuilder();
                sb.Append("[SPEC-FREEZE] seat=").Append(openSeat ?? "?")
                  .Append(" close=").Append(why)
                  .Append(" dur=").Append((Time.time - openedAt).ToString("F2")).Append("s")
                  .Append(" frames=").Append(frames)
                  .Append(" players=").Append(rosterAtOpen)
                  .Append(" moved=").Append(total.ToString("F3"))
                  .Append(" maxStep=").Append(maxStep.ToString("F4"))
                  .Append(" simFrames=").Append(framesAnySimulated).Append("/").Append(frames);
                int listed = Math.Min(moved.Count, MAX_PLAYERS_LISTED);
                for (int i = 0; i < listed; i++)
                    sb.Append(" p").Append(i).Append("=").Append(moved[i].ToString("F3"));
                Plugin.Log?.LogInfo(sb.ToString());

                if (reports == MAX_REPORTS)
                    Plugin.Log?.LogInfo(
                        "[SPEC-FREEZE] sample budget spent after " + MAX_REPORTS +
                        " windows; totals keep accumulating (see the summary on room exit)");
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
