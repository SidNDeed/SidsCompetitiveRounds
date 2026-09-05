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
    /// `isActiveAndEnabled &amp;&amp; isPlaying &amp;&amp; simulated &amp;&amp;
    /// !isKinematic` holds, it adds |velocity| * deltaTime * timeScale — the
    /// distance local physics moved this body over the frame, summed over the
    /// frame's fixed steps. A position written by the network lerp, by the
    /// respawn walk or by a map rescale adds nothing to it, because none of
    /// those is that expression.
    ///
    /// The first term is the writer's REACHABILITY and r11 added it: a dead
    /// body is deactivated by `HealthHandler.RPCA_Die` (V/HealthHandler.cs:374)
    /// with `isPlaying`, `simulated` and `isKinematic` all untouched and its
    /// death velocity still on it, so the other three terms hold for a body
    /// `FixedUpdate` is not running on at all.
    /// The lerp does write `velocity`, and that is the point rather than a
    /// leak: a seat whose bodies are still simulated integrates that velocity
    /// into the transform, which is the behaviour under suspicion, and a seat
    /// whose bodies are stopped multiplies the same velocity by zero.
    ///
    /// Observed displacement is still reported, as `moved`, with no
    /// attribution attached to it. It is context — it says the bodies went
    /// somewhere — and it is deliberately NOT the acceptance number.
    ///
    /// **What ends a window, and what does not.** The control is only a control
    /// while its bodies STAY stopped, so a re-enable inside an open window ends
    /// it as `revived` and it is not counted. That latch reads `simulated`
    /// ALONE, not the four-term predicate: `isKinematic` is flipped true and
    /// back by `StunHandler` (V/StunHandler.cs:57,65) on every seat that sees
    /// the stun, so latching on the composite would discard a window every time
    /// a stun expired in it — throwing away precisely the windows whose bodies
    /// were live enough to collide, and leaving the acceptance number computed
    /// over what survived. `simulated` has three writers in vanilla
    /// (`SetPlayersSimulated`, the `Move` coroutine whose own log lines close
    /// this window, and `PopUpHandler.StartPicking`), so a false→true on it
    /// inside an open window means the control came back and nothing else.
    ///
    /// **Accumulators are keyed by `Player.PlayerID`, not by list position.**
    /// A slot whose occupant changes without changing the roster count would
    /// otherwise carry the previous body's baseline forward and bank the gap
    /// between two different bodies as movement; the count-triggered rebase
    /// that used to guard that wiped every accumulator in the window to do it.
    /// Keyed by identity, an arriving body starts its own baseline, a departing
    /// one keeps what it earned, and `rosterChanged=1` is a note on the line
    /// rather than a reason to discard numbers.
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
        private static bool rosterChanged;
        private static bool sawStopped;
        private static bool revived;
        private static float maxPhysStep;

        /// <summary>Per-body accumulators, keyed by Player.PlayerID rather than
        /// by position in PlayerManager.players. A list index is not an
        /// identity: a slot whose occupant changes without changing the count
        /// carries the previous body's position baseline forward, and the whole
        /// gap between two different bodies is banked as one frame of movement.
        /// Guarding that with a count-triggered rebase costs every accumulator
        /// in the window. Keyed by identity, a body that appears starts its own
        /// baseline and a body that leaves keeps what it earned.</summary>
        private class BodyState
        {
            internal Vector3 lastPos;
            internal float physDrive;
            internal float moved;
            internal bool wasSimulated;  // vel.simulated ALONE - see the latch
            internal int order;          // first-seen, so the line's order is stable
        }

        private static readonly Dictionary<int, BodyState> bodies =
            new Dictionary<int, BodyState>();
        private static int bodyOrder;
        private const int MAX_BODIES_TRACKED = 32;

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
                rosterChanged = false;
                sawStopped = false;
                revived = false;
                bodies.Clear();
                bodyOrder = 0;
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

                float dt = Time.deltaTime;
                float scale = SafeTimeScale();
                bool anyDriven = false;

                for (int i = 0; i < players.Count; i++)
                {
                    var p = players[i];
                    if (p == null) continue;

                    int id;
                    bool simulatedNow = false;
                    bool driven = false;
                    float speed = 0f;
                    try
                    {
                        id = p.PlayerID;
                        var data = p.data;
                        var vel = data != null ? data.playerVel : null;
                        if (vel != null)
                        {
                            simulatedNow = vel.simulated;
                            // The exact predicate PlayerVelocity.FixedUpdate
                            // applies before it touches the transform, INCLUDING
                            // the term that decides whether FixedUpdate runs at
                            // all. A dead body is deactivated by
                            // HealthHandler.RPCA_Die with isPlaying, simulated
                            // and isKinematic untouched and its death velocity
                            // still on it, so without isActiveAndEnabled the
                            // probe banks drive for a body local physics is not
                            // touching — the same defect class this sampler was
                            // written to remove, one term further in.
                            driven = vel.isActiveAndEnabled
                                     && data.isPlaying
                                     && simulatedNow
                                     && !vel.isKinematic;
                            if (driven) speed = ((Vector2)vel.velocity).magnitude;
                        }
                    }
                    catch { continue; }

                    BodyState st;
                    if (!bodies.TryGetValue(id, out st))
                    {
                        if (bodies.Count >= MAX_BODIES_TRACKED) continue;
                        if (bodies.Count != 0) rosterChanged = true;
                        st = new BodyState
                        {
                            lastPos = SafePos(players, i),
                            wasSimulated = simulatedNow,
                            order = bodyOrder++,
                        };
                        bodies[id] = st;
                    }

                    // The control's own validity, latched on `simulated` ALONE.
                    // A window is only comparable while the bodies STAY
                    // stopped: in a code room the vanilla rematch popup runs
                    // about two seconds in and revives them
                    // (PopUpHandler.StartPicking), and the spectator suppresses
                    // that popup — so a fighter window left open to the horizon
                    // would report revived bodies as if they had never been
                    // stopped.
                    //
                    // It must NOT be latched on the composite predicate above.
                    // isKinematic is flipped by StunHandler on every seat that
                    // sees the stun, and a stun expiring inside the window would
                    // then read as a re-enable and discard the window — losing
                    // precisely the windows whose bodies were live enough to be
                    // stunned. `simulated` is moved by SetPlayersSimulated, by
                    // the Move coroutine (whose own log lines close this window)
                    // and by StartPicking, so a false->true on it inside an open
                    // window means the control came back and nothing else.
                    if (!simulatedNow) sawStopped = true;
                    else if (sawStopped && !st.wasSimulated) revived = true;
                    st.wasSimulated = simulatedNow;

                    Vector3 now = SafePos(players, i);
                    float step = Vector3.Distance(now, st.lastPos);
                    st.lastPos = now;
                    if (step >= NOISE_FLOOR) st.moved += step;

                    if (!driven) continue;
                    anyDriven = true;
                    float travel = speed * dt * scale;
                    if (travel < NOISE_FLOOR) continue;
                    st.physDrive += travel;
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
                foreach (var st in bodies.Values) { totalDrive += st.physDrive; totalMoved += st.moved; }

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
                  .Append(rosterChanged ? " rosterChanged=1" : "")
                  .Append(" comparable=").Append(comparable ? "1" : "0")
                  .Append(revived ? " revived=1" : "")
                  .Append(" physFrames=").Append(physFrames).Append("/").Append(frames)
                  .Append(" physDrive=").Append(totalDrive.ToString("F3"))
                  .Append(" maxPhysStep=").Append(maxPhysStep.ToString("F4"))
                  .Append(" moved=").Append(totalMoved.ToString("F3"));
                // Listed in first-seen order so two lines from one sitting
                // can be read against each other; the key itself is the game's
                // player id, which is what makes the numbers attributable.
                var ordered = new List<BodyState>(bodies.Values);
                ordered.Sort((a, b) => a.order.CompareTo(b.order));
                int listed = Math.Min(ordered.Count, MAX_PLAYERS_LISTED);
                for (int i = 0; i < listed; i++)
                    sb.Append(" p").Append(i).Append("=").Append(ordered[i].physDrive.ToString("F3"))
                      .Append("/").Append(ordered[i].moved.ToString("F3"));
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
