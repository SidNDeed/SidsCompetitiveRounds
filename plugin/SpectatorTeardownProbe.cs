using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Text;
using HarmonyLib;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Measurement only. Answers ONE question with a number: between the round
    /// call-in and the moment vanilla forces the bodies to stop, does a seat
    /// that is WATCHING keep integrating them when a seat that is PLAYING does
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
    /// PLAYERS END` is kept only as a late backstop, and a window that ends
    /// there is not comparable to one that ended at the stop.
    ///
    /// **What is counted, and why it is not a distance.** Three methods have
    /// been tried here and the first two were both measuring the wrong thing.
    ///
    /// Method 1 split observed displacement by the `simulated` flag. Review r10
    /// killed it: `Photon.Pun.SyncPlayerMovement.Update` writes
    /// `transform.position` on every REMOTE copy of a body, every frame it has
    /// a package, without consulting `simulated` — so a spectator, for whom
    /// every body is remote, banks the whole network lerp as "moved while
    /// simulated", and the differential appears whether or not local physics
    /// contributed anything.
    ///
    /// Method 2 bracketed `PlayerVelocity.FixedUpdate` with a Harmony
    /// prefix/postfix pair and reported the position difference across it.
    /// Review r12 killed that too, for three separate reasons: a bracket
    /// measures the NET EFFECT OF THE WHOLE METHOD, so vanilla's own
    /// z-normalization (V/PlayerVelocity.cs:50 flattens z to 0) reports a metre
    /// of "drive" for a body that started at z=1 and travelled nowhere, and any
    /// co-patch on the same method is attributed to vanilla; `PlayerCollision`
    /// ALSO writes player transforms under physics (V/PlayerCollision.cs:67
    /// clamps a body out of a wall, and :100 pushes a DIFFERENT body out of an
    /// overlap under the weaker guard `simulated || !isKinematic`), so a
    /// distance from this bracket was never the whole of local physics anyway;
    /// and the number is a float, so "did not move" and "was not measured" are
    /// the same reading.
    ///
    /// Method 3, the one here, counts instead. `PlayerVelocity.FixedUpdate` is:
    ///
    ///     if (data.isPlaying)
    ///         if (isKinematic) velocity *= 0f;
    ///         if (simulated &amp;&amp; !isKinematic)
    ///             velocity += down * fixedDeltaTime * timeScale * 20f;
    ///             transform.position += fixedDeltaTime * timeScale * velocity;
    ///             transform.position = new Vector3(x, y, 0f);
    ///
    /// A prefix reads the same three inputs vanilla is about to read and
    /// records two integers per body: `steps`, the number of times the method
    /// RAN at all, and `driveSteps`, the number of those runs that were going
    /// to take the integrating branch. Nothing between the read and the branch
    /// changes any of the three, so the second count is exact rather than
    /// approximate — and because it is a decision and not an effect, no other
    /// writer of the transform can contribute to it and no co-patch can be
    /// mistaken for vanilla. There is no postfix, so there is no bracket to
    /// straddle a window edge.
    ///
    /// This is also the right SHAPE for the question. "Is this seat still
    /// integrating the bodies" is binary per step; distance was only ever a
    /// proxy for it, and every version of the proxy has been wrong.
    ///
    /// **It does restate vanilla's guard, and that is worth saying plainly**,
    /// because a restatement going stale is exactly what r11 caught in method
    /// 1. It is a smaller restatement than that one in the two ways that
    /// matter. REACHABILITY is no longer copied at all: `isActiveAndEnabled`
    /// and the active GameObject were the term method 1 was missing, and Unity
    /// simply does not call `FixedUpdate` on a component that fails them, so
    /// the prefix does not run and there is nothing to get wrong — which is the
    /// case `HealthHandler.RPCA_Die` (V/HealthHandler.cs:374) produces, a
    /// deactivated body with `isPlaying`, `simulated` and `isKinematic`
    /// untouched. And what IS copied — the three fields, on two adjacent lines
    /// of the method being patched — is pinned by a test that reads the
    /// decompiled source and fails if vanilla's guard stops matching. `steps`
    /// is independent of the copy either way: it counts invocations, so even a
    /// stale predicate leaves the sample size honest.
    ///
    /// The expected reading follows directly from vanilla: on a FIGHTER the
    /// stop lands, so `simulated` is false and `driveSteps` falls to zero while
    /// `steps` keeps counting; on a SPECTATOR under the suspicion the stop
    /// never ran, so `driveSteps` stays equal to `steps`.
    ///
    /// **`steps` is also the proof that the instrument is running.** A count of
    /// zero from a probe that never attached looks exactly like a count of zero
    /// from a body that is not being integrated, which is the failure direction
    /// this whole file exists to avoid (#83: a Harmony patch can silently fail
    /// to attach). The patch class therefore latches a separate `Alive` flag
    /// the first time the prefix runs at all — before the window check, so it
    /// is set during ordinary play — and a window closed while `Alive` is false
    /// is reported `bracket=absent` and is NOT comparable. The probe says it
    /// was not measuring rather than reporting a zero.
    ///
    /// Observed displacement is still reported, as `moved`, with no attribution
    /// attached to it. It is context — the bodies went somewhere, by any
    /// mechanism including the network lerp, the respawn walk and
    /// `PlayerCollision`'s pushes — and it is deliberately NOT the acceptance
    /// number.
    ///
    /// **What ends a window, and what does not.** The control is only a control
    /// while its bodies STAY stopped, so a re-enable inside an open window ends
    /// it as `revived` and it is not counted. That latch reads `simulated`
    /// ALONE, not the composite: `isKinematic` is flipped true and back by
    /// `StunHandler` (V/StunHandler.cs:57,65) on every seat that sees the stun,
    /// so latching on the composite would discard a window every time a stun
    /// expired in it — throwing away precisely the windows whose bodies were
    /// live enough to collide, and leaving the acceptance number computed over
    /// what survived. `simulated` has three writers in vanilla
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
    /// one keeps what it earned, and the per-body figures on the line are
    /// labelled with that same PlayerID so they can be matched to a player.
    ///
    /// Two placement rules this file depends on, both the #376 class — a
    /// diagnostic inside the behaviour it judges is dead where it is needed:
    ///   * the window opens ABOVE `SpectatorPatchSupport.Suppress`, so a
    ///     FIGHTER seat emits the same line as a positive control, and a
    ///     suppression that fails to engage still produces a reading;
    ///   * the close runs ABOVE `OnUnityLog`'s spectator quiesce, which returns
    ///     at its fourth line on exactly the seat under test.
    ///
    /// ACCEPTANCE for the fix this informs: `driveSteps` on a spectator seat
    /// down to what the fighter control already reports, with `steps` on both
    /// seats showing the instrument was running. The totals line is made of
    /// exactly the windows that criterion names — the comparable ones — rather
    /// than of every window with a comparable COUNT beside it, so the two
    /// seats' figures can be read against each other directly. Every window
    /// that did NOT make that cut is counted under the reason it failed, so
    /// the gap between `windows` and `comparable` is always accounted for.
    ///
    /// Bounded on purpose: a broadcast seat sits in matches all day, so this
    /// logs the first MAX_REPORTS windows of a session and then a periodic
    /// aggregate. One line per round, never one per frame.
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

        /// <summary>Observed displacement below this in a single frame is float
        /// noise in two transform reads, not motion. It applies to `moved`
        /// ONLY — the acceptance counters are integers and have no arithmetic
        /// error to filter.</summary>
        private const float NOISE_FLOOR = 0.001f;

        private const int MAX_REPORTS = 20;
        private const int MAX_PLAYERS_LISTED = 8;

        /// <summary>The ONE close edge the acceptance criterion is stated over:
        /// the per-player stop itself. Every other edge produces a differently
        /// shaped interval — a backstop close covers the whole `Move`
        /// coroutine, a room-left or disconnect close covers part of a
        /// teardown, a horizon close covers eight seconds of something else —
        /// and mixing those into the totals is how a number nobody can evaluate
        /// gets produced. An ALLOWLIST rather than a list of exclusions, so an
        /// edge added later is non-comparable until somebody decides
        /// otherwise.</summary>
        private const string COMPARABLE_CLOSE = "move-start";

        private static bool open;
        private static float openedAt;
        private static string openSeat;
        private static int frames;
        private static int physFrames;
        private static int rosterAtOpen;

        /// <summary>The PlayerIDs the window opened over, not merely how many
        /// there were. Roster drift used to be "a body first seen on a frame
        /// after the first", which misses a body that joined between OpenWindow
        /// and the first Tick entirely -- it is new to the map, but so is
        /// everyone on that frame, so the rule could not tell them apart. The
        /// set can: anyone not in it arrived after the window did, whenever the
        /// sampler happened to notice (r13 LOW).</summary>
        private static readonly HashSet<int> rosterIdsAtOpen = new HashSet<int>();
        private static bool rosterChanged;
        private static bool sawStopped;
        private static bool revived;

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
            internal int playerId;       // the game's own id, printed on the line
            internal Vector3 lastPos;
            internal float moved;
            internal bool wasSimulated;  // vel.simulated ALONE - see the latch
            internal int order;          // first-seen, so the line's order is stable
            internal int velId;          // which PlayerVelocity the counts below came from
            internal int stepsSeen;      // that instance's cumulative, already folded in
            internal int driveStepsSeen;
            internal int steps;          // this body's own totals for the window
            internal int driveSteps;
        }

        private static readonly Dictionary<int, BodyState> bodies =
            new Dictionary<int, BodyState>();
        private static int bodyOrder;
        private const int MAX_BODIES_TRACKED = 32;

        /// <summary>Per PlayerVelocity instance, cumulative for the window:
        /// how many times `FixedUpdate` ran, and how many of those runs were
        /// going to integrate. Written on the physics step by the patch below
        /// and drained by Tick (and once more by CloseWindow, so a step taken
        /// after the last Tick is not lost).
        ///
        /// Keyed by instance rather than by player id ON PURPOSE: identity
        /// resolution costs a component walk, and the physics step is the one
        /// place in this file that must stay cheap. Tick already holds both
        /// halves of the mapping, so it does the attribution.</summary>
        private struct StepCount
        {
            internal int steps;
            internal int driveSteps;
        }

        private static readonly Dictionary<int, StepCount> stepCounts =
            new Dictionary<int, StepCount>();

        /// <summary>Window totals for the two counters, across every body.
        /// `physSteps` is the sample size; `driveSteps` is the answer.
        ///
        /// THE ANSWER COMES FROM HERE, not from the per-body sums (r13 MEDIUM).
        /// A body's counters are attributed through its current PlayerVelocity,
        /// and an instance that is replaced mid-window, or destroyed before the
        /// sampler has attributed it once, takes its counts out of that sum --
        /// so the number the question is settled with was the one number a
        /// component swap could quietly reduce. These two are incremented on
        /// the physics step itself and no identity change can touch them. The
        /// per-body figures remain, as attribution, and the line prints both:
        /// a gap between them is a fact about the window worth seeing.</summary>
        private static int physSteps;
        private static int driveSteps;

        /// <summary>How many prefix runs the instrument had done when this
        /// window opened. `Alive` says the patch attached SOMETIME in this
        /// process; it cannot say the patch ran during THIS window, and a
        /// window with frames, bodies and no physics step at all would
        /// otherwise be banked as a measured zero (r13 LOW).</summary>
        private static int prefixRunsAtOpen;

        /// <summary>What the co-patch census read, and whether it could be
        /// taken at all. Either one makes the window non-comparable: this probe
        /// reads the fields vanilla is about to read, and another patch that
        /// writes them after us, or rewrites the method body, or declines to
        /// run the original, makes "the branch vanilla took" a claim we are not
        /// in a position to make. Refusing loudly is the outcome this file
        /// prefers over a number with an asterisk (r13 MEDIUM).
        ///
        /// FIVE fields rather than two, because one snapshot at open answered a
        /// different question than the one being asked (r14 MEDIUM 9). A patch
        /// installed lazily -- by a mod that patches when its own feature first
        /// fires, rather than at load -- lands AFTER the open sample and before
        /// the steps being measured, and the stale zero let such a window bank
        /// as comparable. The census is now taken at open, on every frame
        /// carrying a physics step, on every Tick and at close, and the
        /// window's answer is the OR across all of them:
        ///
        ///   coPatchedAny       some sample saw a foreign body-rewriting patch;
        ///   censusFailedAny    some sample could not find out;
        ///   coPatchesAtOpen    what the OPEN sample counted, and
        ///   censusFailedAtOpen whether it counted anything at all -- kept so
        ///                      the line can say a co-patch arrived DURING the
        ///                      window, and can decline to say it when the open
        ///                      sample itself failed (#351: a claim must not
        ///                      outrun the sample it rests on);
        ///   coPatchesFirst     the count read by the first sample that saw
        ///                      any. Deliberately not a maximum: samples taken
        ///                      at different moments are different
        ///                      measurements and folding them into one number
        ///                      is what #511 is about.</summary>
        private static bool coPatchedAny;
        private static bool censusFailedAny;
        private static int coPatchesAtOpen;
        private static bool censusFailedAtOpen;
        private static int coPatchesFirst;

        /// <summary>The frame the in-window sampler last censused on.
        ///
        /// That sampler is driven from the physics prefix rather than from
        /// Tick, because the prefix is the only hook that is live inside the
        /// window on EVERY seat: `Plugin.cs`'s `modDisabled` return sits above
        /// the call that ticks this probe, so a Tick-driven census does not run
        /// on one of the seats the census exists for. Frame-gated, so the
        /// steady per-step cost is one int compare and one branch and the
        /// GetPatchInfo allocation happens at most once per frame -- the rate
        /// the design already accepted for Tick (#364's budget).</summary>
        private static int lastCensusFrame = -1;

        /// <summary>One-shot for the process. A census that cannot be taken
        /// makes every window non-comparable for as long as it keeps failing,
        /// and its only other trace is a token on a heartbeat printed once per
        /// twenty windows -- so a whole sitting can produce no data and look
        /// quiet. A refusal that costs everything has to say so once (#430).</summary>
        private static bool censusUnavailableLogged;

        private static int reports;

        /// <summary>Session totals, kept PER SEAT. One process can play a round
        /// and then watch one; a single set of counters would report the last
        /// window's seat beside both seats' numbers, which is a heartbeat that
        /// cannot be read (r10).</summary>
        private class SeatTotals
        {
            internal int windows;
            internal int frames;
            internal int physFrames;
            internal int steps;
            internal int driveSteps;
            internal float moved;
            internal int comparable;    // the windows every other field is made of
            internal int nonComparable; // and the rest; the two sum to windows

            // One tally per conjunct of the comparability predicate, each
            // named for the term it answers for.
            //
            // Until r14 LOW 3 there was a single `notMeasured`, incremented on
            // two of the seven conjuncts, so a window dropped for any of the
            // other five was counted in `windows` and nowhere else. In Sid's
            // 2026-09-06 log that was 39 of 120 windows: a third of the
            // evidence present as an unexplained gap between two numbers.
            //
            // A window can fail several conjuncts at once, so these OVERLAP and
            // sum to at least nonComparable. They explain the drops; they do
            // not partition them, and the identity that holds is
            // comparable + nonComparable == windows.
            internal int dropEarlyClose;
            internal int dropRevived;
            internal int dropNoFrames;
            internal int dropNoBodies;
            internal int dropBracketDead;
            internal int dropBracketIdle;
            internal int dropCoPatched;
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
                rosterChanged = false;
                sawStopped = false;
                revived = false;
                bodies.Clear();
                bodyOrder = 0;
                stepCounts.Clear();
                physSteps = 0;
                driveSteps = 0;
                rosterIdsAtOpen.Clear();
                rosterAtOpen = SnapshotRoster();
                prefixRunsAtOpen = PlayerVelocity_TeardownDrive_Patch.Runs;
                coPatchedAny = false;
                censusFailedAny = false;
                coPatchesFirst = 0;
                lastCensusFrame = -1;
                CensusCoPatches();
                // Held apart from the running OR so the line can distinguish
                // "it was already there" from "it arrived while we watched".
                coPatchesAtOpen = coPatchedAny ? coPatchesFirst : 0;
                censusFailedAtOpen = censusFailedAny;
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

                CensusCoPatches();

                var players = PlayerManager.instance != null ? PlayerManager.instance.players : null;
                if (players == null) return;

                bool anyDriven = false;

                for (int i = 0; i < players.Count; i++)
                {
                    var p = players[i];
                    if (p == null) continue;

                    int id;
                    int velId = 0;
                    bool simulatedNow = false;
                    try
                    {
                        id = p.PlayerID;
                        var data = p.data;
                        var vel = data != null ? data.playerVel : null;
                        if (vel != null)
                        {
                            velId = vel.GetInstanceID();
                            simulatedNow = vel.simulated;
                        }
                    }
                    catch { continue; }

                    BodyState st;
                    if (!bodies.TryGetValue(id, out st))
                    {
                        if (bodies.Count >= MAX_BODIES_TRACKED) continue;
                        // Roster drift is asked of the ROSTER, not of the frame
                        // count. "New to the accumulator map" cannot answer it:
                        // on the first sampled frame every body is new, because
                        // the map starts empty -- keying on the map being
                        // non-empty made every ordinary 1v1 print
                        // rosterChanged=1. `frames > 0` fixed that and bought a
                        // hole with it: a body that joined between OpenWindow
                        // and the first Tick arrives on frame 0 and is
                        // indistinguishable from the roster the window opened
                        // over, though the emitted line still says
                        // players=rosterAtOpen (r13 LOW). The set of ids the
                        // window opened with answers both.
                        if (!rosterIdsAtOpen.Contains(id)) rosterChanged = true;
                        st = new BodyState
                        {
                            playerId = id,
                            lastPos = SafePos(players, i),
                            wasSimulated = simulatedNow,
                            order = bodyOrder++,
                            velId = velId,
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
                    // It must NOT be latched on the composite predicate the
                    // prefix reads. isKinematic is flipped by StunHandler on
                    // every seat that sees the stun, and a stun expiring inside
                    // the window would then read as a re-enable and discard the
                    // window — losing precisely the windows whose bodies were
                    // live enough to be stunned. `simulated` is moved by
                    // SetPlayersSimulated, by the Move coroutine (whose own log
                    // lines close this window) and by StartPicking, so a
                    // false->true on it inside an open window means the control
                    // came back and nothing else.
                    if (!simulatedNow) sawStopped = true;
                    else if (sawStopped && !st.wasSimulated) revived = true;
                    st.wasSimulated = simulatedNow;

                    Vector3 now = SafePos(players, i);
                    float step = Vector3.Distance(now, st.lastPos);
                    st.lastPos = now;
                    if (step >= NOISE_FLOOR) st.moved += step;

                    // A body whose PlayerVelocity was replaced starts a fresh
                    // baseline rather than differencing against another
                    // instance's running totals -- but the OUTGOING instance is
                    // drained first (r13 MEDIUM). Resetting the seen-counters
                    // and moving on abandoned whatever that instance had banked
                    // since the last drain, which is a body's last steps before
                    // it was replaced: the steps most likely to be the ones
                    // under question.
                    if (velId != 0 && velId != st.velId)
                    {
                        DrainSteps(st);
                        st.velId = velId;
                        st.stepsSeen = 0;
                        st.driveStepsSeen = 0;
                    }
                    if (DrainSteps(st)) anyDriven = true;
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

        /// <summary>Fold whatever the physics step banked for this body's
        /// current PlayerVelocity into the body's own window totals. Returns
        /// whether any INTEGRATING step arrived since the last drain.
        ///
        /// Called from Tick and once more from CloseWindow: a fixed step taken
        /// after the last render frame but before the close is otherwise left
        /// sitting in the instance map and never reaches the line.</summary>
        private static bool DrainSteps(BodyState st)
        {
            if (st.velId == 0) return false;
            StepCount c;
            if (!stepCounts.TryGetValue(st.velId, out c)) return false;
            int freshSteps = c.steps - st.stepsSeen;
            int freshDrive = c.driveSteps - st.driveStepsSeen;
            if (freshSteps <= 0 && freshDrive <= 0) return false;
            st.stepsSeen = c.steps;
            st.driveStepsSeen = c.driveSteps;
            if (freshSteps > 0) st.steps += freshSteps;
            if (freshDrive > 0) st.driveSteps += freshDrive;
            return freshDrive > 0;
        }

        internal static bool WindowOpen() { return open; }

        /// <summary>Called from the prefix below, once per body per fixed step,
        /// with vanilla's own decision about whether this step is going to
        /// integrate the body. Costs one bool read while the window is closed,
        /// which is almost always.
        ///
        /// `willIntegrate` is read from the three fields vanilla is about to
        /// read, in the same invocation, before it acts on them — so it is the
        /// branch vanilla takes and not a re-derivation of it. Counting the
        /// decision rather than measuring the displacement is what retires the
        /// z-normalization, the co-patch attribution and the second physics
        /// writer in `PlayerCollision`, none of which can move a count of
        /// branches taken.</summary>
        internal static void NotePhysicsStep(int velId, bool willIntegrate)
        {
            if (!open) return;

            // The in-window census (r14 MEDIUM 9), driven from here because
            // this is the one hook that runs inside the window on every seat.
            // Frame-gated for cost, and stopped once the OR is raised: a window
            // already known non-comparable buys nothing from further sampling,
            // which is also what bounds the work on a seat whose window stays
            // open until the room is left.
            if (!coPatchedAny && Time.frameCount != lastCensusFrame)
            {
                lastCensusFrame = Time.frameCount;
                CensusCoPatches();
            }

            StepCount c;
            if (!stepCounts.TryGetValue(velId, out c))
            {
                if (stepCounts.Count >= MAX_BODIES_TRACKED) return;
                c = default(StepCount);
            }
            c.steps++;
            if (willIntegrate) c.driveSteps++;
            stepCounts[velId] = c;
            physSteps++;
            if (willIntegrate) driveSteps++;
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
                int totalSteps = 0, totalDrive = 0;
                float totalMoved = 0f;
                foreach (var st in bodies.Values)
                {
                    DrainSteps(st);
                    totalSteps += st.steps;
                    totalDrive += st.driveSteps;
                    totalMoved += st.moved;
                }

                string seat = openSeat ?? "?";
                SeatTotals t;
                if (!totals.TryGetValue(seat, out t)) { t = new SeatTotals(); totals[seat] = t; }

                // Comparability is decided BEFORE anything is banked. The
                // acceptance criterion in this file's header is stated over one
                // shape of window, and the totals line is the only place that
                // criterion is ever read — so the totals have to be made of
                // that shape and nothing else. Banking every window and merely
                // COUNTING the comparable ones produced a figure nobody could
                // evaluate.
                //
                // SEVEN conjuncts, and they make one point: a window whose
                // number cannot be attributed to vanilla must not be banked as
                // one that can. The sharpest case is the instrument itself -- a
                // window measured by a patch that never attached, or by one
                // that latched dead on an exception, reports zero integrating
                // steps for the same reason a properly stopped body does, which
                // is the failure direction this probe cannot have (#83).
                //
                // A window that fails any of them is banked nowhere, counted in
                // `nonComparable`, and counted again under each conjunct it
                // failed. Do not add a conjunct here without adding its tally
                // below: an unaccounted drop is invisible in the totals, and
                // the count in this sentence is part of what a gate checks.
                //
                //   bracketLive     the patch attached at some point and has
                //                   not latched dead;
                //   bracketRan      it ran during THIS window. "Ever ran" is
                //                   not "ran here", and a window that contains
                //                   no physics step at all reports zero
                //                   integrating steps for the same reason a
                //                   properly stopped body does (#83);
                //   uncoPatched     nothing foreign prefixes or rewrites the
                //                   method. This probe reads the fields vanilla
                //                   is about to read; a patch that writes them
                //                   after us, rewrites the body, or declines to
                //                   run the original makes that reading a claim
                //                   about somebody else's code.
                CensusCoPatches();
                bool bracketLive = PlayerVelocity_TeardownDrive_Patch.Alive;
                bool bracketRan = PlayerVelocity_TeardownDrive_Patch.Runs > prefixRunsAtOpen;
                bool uncoPatched = !coPatchedAny && !censusFailedAny;
                bool comparable = why == COMPARABLE_CLOSE
                                  && !revived
                                  && frames > 0
                                  && bodies.Count > 0
                                  && bracketLive
                                  && bracketRan
                                  && uncoPatched;
                t.windows++;
                if (comparable)
                {
                    t.comparable++;
                    t.frames += frames;
                    t.physFrames += physFrames;
                    // The GLOBAL counters, for the reason on their
                    // declaration: a per-body sum is what a replaced or
                    // destroyed PlayerVelocity can silently shrink.
                    t.steps += physSteps;
                    t.driveSteps += driveSteps;
                    t.moved += totalMoved;
                }
                else
                {
                    // One line per conjunct above, each naming its own term, so
                    // a conjunct added without a tally is a hole a gate can
                    // see rather than a silent gap in the totals (r14 LOW 3).
                    t.nonComparable++;
                    if (why != COMPARABLE_CLOSE) t.dropEarlyClose++;
                    if (revived) t.dropRevived++;
                    if (frames == 0) t.dropNoFrames++;
                    if (bodies.Count == 0) t.dropNoBodies++;
                    if (!bracketLive) t.dropBracketDead++;
                    if (!bracketRan) t.dropBracketIdle++;
                    if (!uncoPatched) t.dropCoPatched++;
                }

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
                  .Append(" bracket=").Append(bracketLive ? "live" : "absent")
                  .Append(bracketRan ? "" : " bracketRan=0")
                  .Append(censusFailedAny ? " coPatched=?"
                          : (coPatchedAny ? " coPatched=" + coPatchesFirst : ""))
                  // Whether it ARRIVED during the window. Only sayable when the
                  // open sample succeeded and read zero; when that sample
                  // failed, "mid" is a claim about a moment nobody observed.
                  .Append(coPatchedAny && censusFailedAtOpen ? " coPatchedMid=?"
                          : (coPatchedAny && coPatchesAtOpen == 0 ? " coPatchedMid=1" : ""))
                  .Append(" comparable=").Append(comparable ? "1" : "0")
                  .Append(revived ? " revived=1" : "")
                  .Append(" physFrames=").Append(physFrames).Append("/").Append(frames)
                  // The answer, then what could be attributed to a body. They
                  // agree unless an instance was replaced or destroyed, and the
                  // difference is the size of what attribution lost.
                  .Append(" driveSteps=").Append(driveSteps).Append("/").Append(physSteps)
                  .Append(totalDrive == driveSteps && totalSteps == physSteps ? ""
                          : " attributed=" + totalDrive + "/" + totalSteps)
                  .Append(" moved=").Append(totalMoved.ToString("F3"));
                // Listed in first-seen order so two lines from one sitting can
                // be read against each other, and labelled with the game's own
                // player id, which is what makes a figure attributable to a
                // body rather than to a position in a list.
                var ordered = new List<BodyState>(bodies.Values);
                ordered.Sort((a, b) => a.order.CompareTo(b.order));
                int listed = Math.Min(ordered.Count, MAX_PLAYERS_LISTED);
                for (int i = 0; i < listed; i++)
                    sb.Append(" p").Append(ordered[i].playerId).Append("=")
                      .Append(ordered[i].driveSteps).Append("/").Append(ordered[i].steps)
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
        /// with its own counters. The comparison between them is the whole
        /// reading, so it cannot be split across lines whose seats are only
        /// known from when they happened to be written.
        ///
        /// `windows` is every window the seat held; every other measured
        /// field is made of the `comparable` subset only. A seat whose two
        /// numbers diverge is telling you its windows are being cut short, and
        /// the `drop*` tallies say why — one per conjunct of the comparability
        /// predicate, printed only where non-zero. They overlap, since a window
        /// can fail several at once, so they sum to at least `nonComparable`
        /// rather than to exactly it; the identity that holds is
        /// `comparable + nonComparable == windows`.
        ///
        /// Before r14 LOW 3 the only account here was a `notMeasured` covering
        /// two of the seven conjuncts, and windows failing the other five were
        /// counted in `windows` and nowhere else — 39 of 120 in one afternoon's
        /// log, which is not a rounding error but a third of the reading
        /// sitting in a gap between two numbers.</summary>
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
                      .Append(" nonComparable=").Append(t.nonComparable)
                      .Append(DropReasons(t))
                      .Append(" physFrames=").Append(t.physFrames).Append("/").Append(t.frames)
                      .Append(" driveSteps=").Append(t.driveSteps).Append("/").Append(t.steps)
                      .Append(" moved=").Append(t.moved.ToString("F2"));
                }
                Plugin.Log?.LogInfo(sb.ToString());
            }
            catch { }
        }

        /// <summary>Why the dropped windows were dropped, printed only where a
        /// tally is non-zero so an ordinary heartbeat stays one readable line.
        /// A seat whose `windows` and `comparable` diverge used to give no
        /// account of the difference at all; this is that account.</summary>
        private static string DropReasons(SeatTotals t)
        {
            var sb = new StringBuilder();
            if (t.dropEarlyClose > 0) sb.Append(" dropEarlyClose=").Append(t.dropEarlyClose);
            if (t.dropRevived > 0) sb.Append(" dropRevived=").Append(t.dropRevived);
            if (t.dropNoFrames > 0) sb.Append(" dropNoFrames=").Append(t.dropNoFrames);
            if (t.dropNoBodies > 0) sb.Append(" dropNoBodies=").Append(t.dropNoBodies);
            if (t.dropBracketDead > 0) sb.Append(" dropBracketDead=").Append(t.dropBracketDead);
            if (t.dropBracketIdle > 0) sb.Append(" dropBracketIdle=").Append(t.dropBracketIdle);
            if (t.dropCoPatched > 0) sb.Append(" dropCoPatched=").Append(t.dropCoPatched);
            return sb.ToString();
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

        /// <summary>The roster the window opens over: the count for the line,
        /// and the ids in `rosterIdsAtOpen` so drift is a question about WHO
        /// rather than about when the sampler first noticed.</summary>
        private static int SnapshotRoster()
        {
            try
            {
                var players = PlayerManager.instance != null ? PlayerManager.instance.players : null;
                if (players == null) return 0;
                for (int i = 0; i < players.Count; i++)
                {
                    var p = players[i];
                    if (p == null) continue;
                    try { rosterIdsAtOpen.Add(p.PlayerID); } catch { }
                }
                return players.Count;
            }
            catch { return 0; }
        }

        /// <summary>Count the patches on PlayerVelocity.FixedUpdate that are not
        /// ours, once per window rather than once per process -- a patch can be
        /// applied by a mod that loads after us, and a census taken at startup
        /// would answer for a world that no longer exists.
        ///
        /// EVERY category that can rewrite or replace the body: prefixes,
        /// transpilers and IL MANIPULATORS. A postfix cannot change the branch
        /// vanilla took before it ran, and a finalizer wraps the call rather
        /// than rewriting it, so neither invalidates the reading; a prefix can
        /// write the three fields after us or decline to run the original, and
        /// a transpiler or an IL manipulator can replace the branch outright.
        ///
        /// ILManipulators is a HarmonyX category that plain Harmony does not
        /// have, and leaving it out let a foreign rewrite of the integrating
        /// branch pass as an uncontested window (r14 MEDIUM 8). It is a public
        /// field on `HarmonyLib.Patches` in the 0Harmony.dll this mod actually
        /// references -- read out of that assembly rather than assumed from the
        /// API surface of some other Harmony build (#123's class: a probe must
        /// be checked against the artifact it will run against).
        ///
        /// A census that THROWS is not a census: `censusFailedAny` makes the
        /// window non-comparable exactly as a positive count does, because "we
        /// could not find out" and "there is nothing there" must not be the
        /// same answer. Both are RAISED and never lowered here -- the window's
        /// answer is the OR over every sample taken during it, and only
        /// OpenWindow clears them.</summary>
        private static void CensusCoPatches()
        {
            int foreign = 0;
            bool failed = false;
            try
            {
                var target = AccessTools.Method(typeof(PlayerVelocity), "FixedUpdate");
                if (target == null) failed = true;
                else
                {
                    var info = Harmony.GetPatchInfo(target);
                    if (info != null)
                    {
                        foreign += CountForeign(info.Prefixes);
                        foreign += CountForeign(info.Transpilers);
                        foreign += CountForeign(info.ILManipulators);
                    }
                }
            }
            catch { failed = true; }

            if (failed)
            {
                censusFailedAny = true;
                if (!censusUnavailableLogged)
                {
                    censusUnavailableLogged = true;
                    // Once, and from here rather than from Tick: Tick is
                    // per-frame and carries no logging at all by design.
                    try
                    {
                        Plugin.Log?.LogWarning("[SPEC-FREEZE] co-patch census unavailable; "
                                               + "no window can be comparable this session");
                    }
                    catch { }
                }
            }
            else if (foreign > 0)
            {
                if (!coPatchedAny) coPatchesFirst = foreign;
                coPatchedAny = true;
            }
        }

        /// <summary>Foreign entries in one patch category. `owner` is the
        /// Harmony id that applied the patch; ours is not foreign. A null
        /// category is an empty one, which is what HarmonyX returns for a
        /// method nobody has patched in that way.</summary>
        private static int CountForeign(ReadOnlyCollection<Patch> list)
        {
            if (list == null) return 0;
            int n = 0;
            foreach (var p in list)
                if (!string.Equals(p.owner, Plugin.ModId, StringComparison.Ordinal)) n++;
            return n;
        }
    }

    /// <summary>Reads vanilla's own decision about whether this fixed step is
    /// going to integrate this body, immediately before vanilla makes it.
    ///
    /// A PREFIX ONLY. The three fields the decision is made from
    /// (`data.isPlaying`, `simulated`, `isKinematic`) are not written by
    /// anything between this read and the branch that consumes them, so the
    /// answer is exact; and with no postfix there is no pair of hooks that can
    /// straddle a window edge, and nothing to attribute to vanilla that vanilla
    /// did not do. The earlier version measured the position difference across
    /// the method, which also collected vanilla's z-flattening on line 50 and
    /// any co-patch's movement.
    ///
    /// Runs on every body every fixed step for the whole session, so the closed
    /// case has to be free: a static store, a bool read, and return.
    ///
    /// `Alive` is the instrument's own liveness, and it is set BEFORE the
    /// window check so ordinary play establishes it. A probe that reports zero
    /// integrating steps because it never attached must not look like a probe
    /// that reports zero because the bodies were stopped (#83); the window that
    /// reads this flag false is reported as not measured instead.
    ///
    /// A throw here would break vanilla movement, so the body swallows and the
    /// channel latches dead — the probe reporting nothing is a fine outcome, a
    /// game that cannot move bodies is not (#376 places diagnostics so they
    /// cannot damage the behaviour they observe).</summary>
    [HarmonyPatch(typeof(PlayerVelocity), "FixedUpdate")]
    internal static class PlayerVelocity_TeardownDrive_Patch
    {
        private static int runs;
        private static bool dead;

        /// <summary>TRUE once the prefix has actually executed and has not
        /// latched dead. Read by CloseWindow to decide whether the patch
        /// attached at all -- ATTACHMENT, not activity: see Runs.</summary>
        internal static bool Alive { get { return runs > 0 && !dead; } }

        /// <summary>How many times the prefix has run this process. A window
        /// compares this against the value it opened with, because "the patch
        /// attached earlier in this session" says nothing about whether a
        /// physics step happened inside the window being reported (r13 LOW).</summary>
        internal static int Runs { get { return runs; } }

        /// <summary>LAST among prefixes (r13 MEDIUM). The three fields this
        /// reads are vanilla's own inputs, and another prefix on the same
        /// method may write them; sampling before it recorded a decision
        /// vanilla was not going to make. HarmonyX orders prefixes high
        /// priority to low, so Priority.Last puts this sample after every
        /// prefix at a higher priority -- and it runs regardless of what any
        /// of them returned, since HarmonyX runs every prefix even after one
        /// returns false (bug #203, proven live on this codebase).
        ///
        /// It is an ORDERING, not a guarantee: a co-patch may sit at Last too,
        /// and the order between equals is not ours to decide. That residue is
        /// why the census below exists rather than being belt-and-braces --
        /// any foreign prefix at all makes the window non-comparable, whatever
        /// priority it holds.
        ///
        /// That covers a co-patch that WRITES the fields. A co-patch that
        /// suppresses the original cannot be detected from in here at all --
        /// this HarmonyX has no `__runOriginal` -- so it is answered where it
        /// can be: SpectatorTeardownProbe counts foreign prefixes and
        /// transpilers on this method per window and refuses to call such a
        /// window comparable.</summary>
        [HarmonyPriority(Priority.Last)]
        private static void Prefix(PlayerVelocity __instance)
        {
            if (dead) return;
            runs++;
            if (!SpectatorTeardownProbe.WindowOpen()) return;
            try
            {
                var data = __instance.data;
                bool integrating = data != null && data.isPlaying
                                   && __instance.simulated && !__instance.isKinematic;
                SpectatorTeardownProbe.NotePhysicsStep(__instance.GetInstanceID(), integrating);
            }
            catch { dead = true; }
        }
    }
}
