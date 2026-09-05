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
    /// inside the window on BOTH seat kinds, so the stated acceptance test was
    /// unreachable by construction. The window now closes on the FIRST `MOVE
    /// PLAYERS START` (V/PlayerManager.cs:384), logged immediately before that
    /// per-player stop — exactly the interval the hypothesis is about. `MOVE
    /// PLAYERS END` is kept only as a late backstop.
    ///
    /// **What is measured, and why it is not displacement.** Review r10 showed
    /// that splitting observed displacement by the `simulated` flag measures
    /// the wrong thing. `Photon.Pun.SyncPlayerMovement.Update` writes
    /// `transform.position` on every REMOTE copy of a body, every frame it has
    /// a package, without consulting `simulated` — so a spectator, for whom
    /// every body is remote, banks the whole network lerp as "moved while
    /// simulated", while the fighter banks vanilla's scripted respawn walk as
    /// "moved while stopped". That produces the differential the acceptance
    /// test looks for whether or not local physics contributed anything.
    ///
    /// So the number is taken from the writer instead of from the result.
    /// V/PlayerVelocity.cs:38-51 is the ONLY thing on this seat that local
    /// physics moves a body with:
    ///
    ///     if (data.isPlaying)
    ///         if (isKinematic) velocity *= 0f;
    ///         if (simulated &amp;&amp; !isKinematic)
    ///             velocity += down * fixedDeltaTime * timeScale * 20f;
    ///             transform.position += fixedDeltaTime * timeScale * velocity;
    ///
    /// `physDrive` accumulates that step and nothing else: while
    /// `isPlaying &amp;&amp; simulated &amp;&amp; !isKinematic` holds, it adds
    /// |velocity| * deltaTime * timeScale — the distance local physics moved
    /// this body over the frame, summed over the frame's fixed steps. A
    /// position written by the network lerp, by the respawn walk or by a map
    /// rescale adds nothing to it, because none of those is that expression.
    /// The lerp does write `velocity`, and that is the point rather than a
    /// leak: a seat whose bodies are still simulated integrates that velocity
    /// into the transform, which is the behaviour under suspicion, and a seat
    /// whose bodies are stopped multiplies the same velocity by zero.
    ///
    /// Observed displacement is still reported, as `moved`, with no
    /// attribution attached to it. It is context — it says the bodies went
    /// somewhere — and it is deliberately NOT the acceptance number.
    ///
    /// Two placement rules this file depends on, both the #376 class — a
    /// diagnostic inside the behaviour it judges is dead where it is needed:
    ///   * the window opens ABOVE `SpectatorPatchSupport.Suppress`, so a
    ///     FIGHTER seat emits the same line as a positive control, and a
    ///     suppression that fails to engage still produces a reading;
    ///   * the close runs ABOVE `OnUnityLog`'s spectator quiesce, which returns
    ///     at its fourth line on exactly the seat under test.
    ///
    /// ACCEPTANCE for the fix this informs: `physDrive` and `maxPhysStep` on a
    /// spectator seat down to what the fighter control already reports, over
    /// windows that are neither `revived` nor closed by the horizon.
    ///
    /// Bounded on purpose: a broadcast seat sits in matches all day, so this
    /// logs the first MAX_REPORTS windows of a session and then a periodic
    /// aggregate. One line per round, never one per frame — at ~60 fps that
    /// would be hundreds of lines a round and the per-frame maximum is carried
    /// as `maxPhysStep` anyway.
    /// </summary>
    internal static class SpectatorTeardownProbe
    {
        /// <summary>Fixed observation horizon, NOT a "the marker never
        /// arrived" signal. With the close on `MOVE PLAYERS START` the real
        /// interval is short, but a window can still be abandoned by a seat
        /// that leaves or by a transition that never calls players in, and a
        /// window left open would fold the next round into its numbers.
        ///
        /// A window that ends here is reported with `close=horizon` and is NOT
        /// comparable to one that ended at the stop: eight seconds is long
        /// enough for the seat to have started doing something else.</summary>
        private const float WINDOW_HORIZON_SECONDS = 8f;

        /// <summary>Physics travel below this in a single frame is arithmetic
        /// noise, not motion.</summary>
        private const float NOISE_FLOOR = 0.001f;

        private const int MAX_REPORTS = 20;
        private const int MAX_PLAYERS_LISTED = 8;

        private static bool open;
        private static float openedAt;
        private static string openSeat;
        private static int frames;
        private static int physFrames;
        private static int rosterAtOpen;
        private static bool rebased;
        private static bool sawStopped;
        private static bool revived;
        private static float maxPhysStep;
        private static readonly List<Vector3> lastPos = new List<Vector3>();
        private static readonly List<float> physDrive = new List<float>();
        private static readonly List<float> moved = new List<float>();
        private static readonly List<bool> wasSimulated = new List<bool>();

        private static int reports;

        /// <summary>Session totals, kept PER SEAT. One process can play a round
        /// and then watch one; a single set of counters would report the last
        /// window's seat beside both seats' numbers, which is a heartbeat that
        /// cannot be read (r10). Each seat carries its own maximum too, for the
        /// same reason.</summary>
        private class SeatTotals
        {
            internal int windows;
            internal int frames;
            internal int physFrames;
            internal float physDrive;
            internal float moved;
            internal float maxPhysStep;
            internal int comparable;   // neither revived nor horizon-closed
        }

        private static readonly Dictionary<string, SeatTotals> totals =
            new Dictionary<string, SeatTotals>();
        private static int windowsTotal;

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
                physFrames = 0;
                maxPhysStep = 0f;
                rebased = false;
                sawStopped = false;
                revived = false;
                lastPos.Clear();
                physDrive.Clear();
                moved.Clear();
                wasSimulated.Clear();
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
                    physDrive.Clear();
                    moved.Clear();
                    wasSimulated.Clear();
                    for (int i = 0; i < players.Count; i++)
                    {
                        lastPos.Add(SafePos(players, i));
                        physDrive.Add(0f);
                        moved.Add(0f);
                        wasSimulated.Add(false);
                    }
                    return;
                }

                float dt = Time.deltaTime;
                float scale = SafeTimeScale();
                bool anyDriven = false;

                for (int i = 0; i < players.Count; i++)
                {
                    var p = players[i];
                    if (p == null) continue;

                    // The exact predicate PlayerVelocity.FixedUpdate applies
                    // before it touches the transform, and the exact quantity
                    // it adds. Anything that writes a position WITHOUT going
                    // through that expression — the network lerp above all —
                    // contributes nothing here by construction.
                    bool driven = false;
                    float speed = 0f;
                    try
                    {
                        var data = p.data;
                        var vel = data != null ? data.playerVel : null;
                        if (vel != null)
                        {
                            driven = data.isPlaying && vel.simulated && !vel.isKinematic;
                            if (driven) speed = ((Vector2)vel.velocity).magnitude;
                        }
                    }
                    catch { }

                    // The control's own validity. A window is only comparable
                    // while the bodies STAY stopped: in a code room the vanilla
                    // rematch popup runs about two seconds in and revives them
                    // (PopUpHandler.StartPicking), and the spectator suppresses
                    // that popup — so a fighter window left open to the horizon
                    // would report the revived bodies as if they had never been
                    // stopped. The first re-enable after a stop ends the window.
                    if (!driven) sawStopped = true;
                    else if (sawStopped && i < wasSimulated.Count && !wasSimulated[i]) revived = true;
                    if (i < wasSimulated.Count) wasSimulated[i] = driven;

                    Vector3 now = SafePos(players, i);
                    float step = Vector3.Distance(now, lastPos[i]);
                    lastPos[i] = now;
                    if (step >= NOISE_FLOOR) moved[i] = moved[i] + step;

                    if (!driven) continue;
                    anyDriven = true;
                    float travel = speed * dt * scale;
                    if (travel < NOISE_FLOOR) continue;
                    physDrive[i] = physDrive[i] + travel;
                    if (travel > maxPhysStep) maxPhysStep = travel;
                }

                frames++;
                if (anyDriven) physFrames++;
                if (revived)
                {
                    CloseWindow("revived");
                    return;
                }
            }
            catch { CloseWindow("error"); }
        }

        /// <summary>Closed by the first `MOVE PLAYERS START` (the per-player
        /// stop, i.e. the end of the interval in question), by `MOVE PLAYERS
        /// END` as a late backstop, by the reliable room-exit edges, by a
        /// re-enable that ends the control, or by the horizon. Emits the one
        /// line the question is settled with.</summary>
        internal static void CloseWindow(string why)
        {
            if (!open) return;
            open = false;
            try
            {
                float totalDrive = 0f, totalMoved = 0f;
                for (int i = 0; i < physDrive.Count; i++) totalDrive += physDrive[i];
                for (int i = 0; i < moved.Count; i++) totalMoved += moved[i];

                string seat = openSeat ?? "?";
                SeatTotals t;
                if (!totals.TryGetValue(seat, out t)) { t = new SeatTotals(); totals[seat] = t; }
                t.windows++;
                t.frames += frames;
                t.physFrames += physFrames;
                t.physDrive += totalDrive;
                t.moved += totalMoved;
                if (maxPhysStep > t.maxPhysStep) t.maxPhysStep = maxPhysStep;
                bool comparable = !revived && why != "horizon" && why != "error";
                if (comparable) t.comparable++;

                if (reports >= MAX_REPORTS)
                {
                    // Budget spent. The heartbeat carries the ANSWER, not just
                    // a volume count, so a log opened late in a long sitting is
                    // still worth reading — and it carries every seat, because
                    // the answer IS the comparison between them.
                    if (windowsTotal % MAX_REPORTS == 0) LogTotals();
                    return;
                }
                reports++;

                var sb = new StringBuilder();
                sb.Append("[SPEC-FREEZE] seat=").Append(seat)
                  .Append(" close=").Append(why)
                  .Append(" dur=").Append((Time.time - openedAt).ToString("F2")).Append("s")
                  .Append(" frames=").Append(frames)
                  .Append(" players=").Append(rosterAtOpen)
                  .Append(rebased ? " rebased=1" : "")
                  .Append(" comparable=").Append(comparable ? "1" : "0")
                  .Append(revived ? " revived=1" : "")
                  .Append(" physFrames=").Append(physFrames).Append("/").Append(frames)
                  .Append(" physDrive=").Append(totalDrive.ToString("F3"))
                  .Append(" maxPhysStep=").Append(maxPhysStep.ToString("F4"))
                  .Append(" moved=").Append(totalMoved.ToString("F3"));
                int listed = Math.Min(physDrive.Count, MAX_PLAYERS_LISTED);
                for (int i = 0; i < listed; i++)
                    sb.Append(" p").Append(i).Append("=").Append(physDrive[i].ToString("F3"))
                      .Append("/").Append(moved[i].ToString("F3"));
                Plugin.Log?.LogInfo(sb.ToString());

                if (reports == MAX_REPORTS)
                    Plugin.Log?.LogInfo(
                        "[SPEC-FREEZE] sample budget spent after " + MAX_REPORTS +
                        " windows; a totals line follows every " + MAX_REPORTS + " windows");
            }
            catch { }
        }

        /// <summary>One line carrying every seat this process has held, each
        /// with its own counters and its own maximum. The comparison between
        /// them is the whole reading, so it cannot be split across lines whose
        /// seats are only known from when they happened to be written.</summary>
        private static void LogTotals()
        {
            try
            {
                var sb = new StringBuilder("[SPEC-FREEZE] totals");
                foreach (var kv in totals)
                {
                    var t = kv.Value;
                    sb.Append(" | ").Append(kv.Key)
                      .Append(": windows=").Append(t.windows)
                      .Append(" comparable=").Append(t.comparable)
                      .Append(" physFrames=").Append(t.physFrames).Append("/").Append(t.frames)
                      .Append(" physDrive=").Append(t.physDrive.ToString("F2"))
                      .Append(" maxPhysStep=").Append(t.maxPhysStep.ToString("F4"))
                      .Append(" moved=").Append(t.moved.ToString("F2"));
                }
                Plugin.Log?.LogInfo(sb.ToString());
            }
            catch { }
        }

        /// <summary>Vanilla scales physics by this; the probe integrates the
        /// same expression, so it has to read the same number.</summary>
        private static float SafeTimeScale()
        {
            try { return TimeHandler.timeScale; }
            catch { return 1f; }
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
