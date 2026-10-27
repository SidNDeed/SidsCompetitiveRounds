using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>The two roster decisions an FFA room makes at every game
    /// boundary: which seats a roster WIDENING may take in, and which
    /// rejection latches the resulting roster now covers.
    ///
    /// They live here, away from Photon, for the same reason FfaReportRules
    /// does: both are rules with a stated property that has to hold for every
    /// input, and a rule whose only gate is a source-shape test is asserted
    /// ABOUT and never RUN (#391). tools/client-rules-harness compiles this
    /// file and EXECUTES <see cref="SelfTest"/>. RoomActors keeps everything
    /// genuinely contextual — reading Photon's player list, the role property
    /// and the u_id — and hands the result in as plain values.
    ///
    /// ── THE DEFECT THESE CLOSE (Codex client r2 HIGH, GameStateWatcher.cs
    /// :6452) ───────────────────────────────────────────────────────────────
    /// The per-game widening used to take its census from
    /// RoomActors.ActiveFighters(). That census applies IsUnauthorized, which
    /// tests the rejection latch FIRST — so a latched actor is removed from
    /// the census before its Steam ID can reach the union, the roster never
    /// widens to cover it, and the release predicate (which asks whether the
    /// roster covers the actor) can therefore never fire. The latch hid the
    /// only evidence that would have released it.
    ///
    /// Worse, and the same fact from the other side: once the roster is
    /// frozen, ActiveFighters() is a SUBSET of the roster by construction, so
    /// a union taken over it could not widen the roster at all under any
    /// input. The widening was vacuous, not merely blind to one case.
    ///
    /// So the census here is the RAW one — every actor the room holds — and
    /// it does not consult the latch at any point.
    ///
    /// ── WHY THE RAW CENSUS IS STILL NARROWED, AND BY WHAT ──────────────────
    /// "Take every actor in the room" would hand the roster to any actor that
    /// obtained the room name after the freeze, which is the one thing the
    /// freeze exists to refuse. The discriminator is not the latch and not the
    /// roster — both are downstream of the defect — it is WHEN THE ACTOR WAS
    /// IN THE ROOM:
    ///
    ///   * the roster is the set of seats the assembly snapshot could RESOLVE;
    ///   * the assembly set is the set of actors that were THERE when that
    ///     snapshot was taken.
    ///
    /// A seat in the second and not the first is a fighter whose identity the
    /// snapshot could not read yet — mid-load, u_id not yet delivered, a slow
    /// rejoin — and it belongs to the assembly. A seat in neither was not in
    /// the room when the roster was taken, which is exactly what "late
    /// entrant" means. Photon never reuses an ActorNumber inside a room, so
    /// the assembly set cannot alias a later joiner onto an earlier seat.
    ///
    /// ── WHAT THE DISCRIMINATOR DOES NOT ASK, AND WHY THAT IS THE WHOLE
    /// RESIDUAL ────────────────────────────────────────────────────────────
    /// It does not ask WHY an actor was off the roster. Presence at the
    /// assembly instant is the entire test, so every reason lands in the same
    /// bucket. That is sound and not a shortcut, because it is the same
    /// authority the FREEZE itself has: the roster is built from
    /// RawActorCensus, so an actor in the room at that instant with a readable
    /// u_id is ON the roster whatever the lobby thinks of it. The widening
    /// therefore admits exactly what the freeze would have admitted had the
    /// u_id arrived a moment earlier — it removes a TIMING artifact and adds
    /// no authority. Enumerated, because "the benign case" is not the only
    /// case and a comment that names only it is the class this file exists to
    /// stop being:
    ///
    ///   * spectator at the instant — refused by IsSpectator, in both rules;
    ///   * impostor — refused by IsImpostor, in both rules;
    ///   * u_id unreadable at the instant, readable later — ADMITTED. This is
    ///     the intended case AND the one an actor that never belonged to the
    ///     lobby is indistinguishable from, because nothing the client holds
    ///     can tell them apart;
    ///   * latched as unauthorized — not consulted at all. The latch is
    ///     downstream of the two above, so it adds no evidence; consulting it
    ///     is the circularity the r2 HIGH was.
    ///
    /// RESIDUALS, stated rather than left to be discovered:
    ///
    ///  1. A seat that joins the Photon room AFTER the assembly window is
    ///     never admitted, even if the lobby believes it belongs. That is the
    ///     freeze's own definition of a late entrant, and the window is taken
    ///     ONCE per room (RoomActors.CaptureAssemblyActors) so a later freeze
    ///     cannot move it forward.
    ///  2. An actor that was in the room at the assembly instant WITHOUT being
    ///     a lobby member — it had the room name and joined in time — is
    ///     admitted on the game after its u_id arrives, exactly as it would
    ///     have been by the freeze itself. LOBBY MEMBERSHIP IS NOT A FACT THIS
    ///     CENSUS HAS. The server holds it: the FFA report endpoint refuses a
    ///     report whose player set is not exactly the lobby's frozen roster,
    ///     terminally, and the client's own key/eligibility rules cannot
    ///     recover that game. So the cost of this residual is a refused
    ///     report, not a settled wrong one — the fail-closed direction — and
    ///     the input that would close it is the server-authoritative lobby
    ///     roster, not this census, which is assembled entirely from
    ///     client-published properties.
    /// </summary>
    internal static class RosterCensusRules
    {
        /// <summary>One actor, reduced to the four facts these rules use.
        /// Deliberately not a Photon type: the harness has no Photon.</summary>
        internal struct Actor
        {
            internal readonly int ActorNumber;
            /// <summary>The u_id this actor advertises, or null/empty when it
            /// is not readable yet. Empty is the case the whole fix is about,
            /// so it is a first-class value here rather than a filter the
            /// caller applies.</summary>
            internal readonly string SteamId;
            internal readonly bool IsSpectator;
            /// <summary>An actor duplicating a live roster fighter's u_id. It
            /// keeps its latch, in both rules, for the reason RecordRejected
            /// keeps it: the latch is what survives its property teardown at
            /// departure and proves its leave was not a fighter's.</summary>
            internal readonly bool IsImpostor;

            internal Actor(int actorNumber, string steamId, bool isSpectator, bool isImpostor)
            {
                ActorNumber = actorNumber;
                SteamId = steamId;
                IsSpectator = isSpectator;
                IsImpostor = isImpostor;
            }
        }

        /// <summary>The Steam IDs a roster write may take, from the RAW actor
        /// census. Never consults a rejection latch — that is the whole point.
        ///
        /// Before the roster is frozen this is "every resolvable, non-spectator,
        /// non-impostor actor present", which is the snapshot the first freeze
        /// is meant to be. After it is frozen the result is additionally
        /// restricted to actors that are already on the roster or were in the
        /// room when it was taken.
        ///
        /// Order is by ActorNumber, and duplicates are collapsed: two actors
        /// can only carry one u_id if one of them is an impostor, and an
        /// impostor is excluded above.
        ///
        /// THE FROZEN-ROSTER NARROWING IS NOT BELT-AND-BRACES. onRoster and
        /// wasAtAssembly are the only thing standing between a frozen roster
        /// and every actor holding the room name; deleting them as redundant
        /// (the roster and latch tests upstream were REMOVED on purpose —
        /// RawActorCensus applies neither) re-opens the late-entrant hole in
        /// full. Case 2 of the self-test is that deletion's alarm.</summary>
        internal static List<string> UnionCensus(IList<Actor> raw,
                                                 ICollection<string> roster,
                                                 ICollection<int> assembly,
                                                 bool rosterFrozen)
        {
            var ids = new List<string>();
            if (raw == null) return ids;
            var seen = new HashSet<string>(StringComparer.Ordinal);
            var ordered = new List<Actor>(raw);
            ordered.Sort((a, b) => a.ActorNumber.CompareTo(b.ActorNumber));
            foreach (var a in ordered)
            {
                if (a.IsSpectator || a.IsImpostor) continue;
                if (string.IsNullOrEmpty(a.SteamId)) continue;
                if (rosterFrozen)
                {
                    bool onRoster = roster != null && roster.Contains(a.SteamId);
                    bool wasAtAssembly = assembly != null && assembly.Contains(a.ActorNumber);
                    if (!onRoster && !wasAtAssembly) continue;
                }
                if (seen.Add(a.SteamId)) ids.Add(a.SteamId);
            }
            return ids;
        }

        /// <summary>The ActorNumbers whose rejection latch the roster NOW
        /// covers. RecordRejected's own predicate, re-read against the roster
        /// as it now stands: on the roster, by a readable identity, and not an
        /// impostor.
        ///
        /// Only actors STILL IN THE ROOM take part — <paramref name="raw"/> is
        /// the room's census, so a departed actor is simply absent. Its latch
        /// is what proves its leave was not a fighter's, and its identity is
        /// no longer resolvable to test anyway.
        ///
        /// An unreadable identity is NOT released: once the roster is frozen
        /// the live rule reads an unreadable identity as unauthorized, so a
        /// release there would contradict it and nothing is lost by refusing.
        /// A spectator is not released either — it was never a fighter, so a
        /// latch on it is not the conclusion this rule invalidates.</summary>
        internal static List<int> LatchesToRelease(IList<Actor> raw,
                                                   ICollection<int> latched,
                                                   ICollection<string> roster)
        {
            var release = new List<int>();
            if (raw == null || latched == null || latched.Count == 0) return release;
            foreach (var a in raw)
            {
                if (!latched.Contains(a.ActorNumber)) continue;
                if (a.IsImpostor) continue;
                if (a.IsSpectator) continue;
                if (string.IsNullOrEmpty(a.SteamId)) continue;
                if (roster == null || !roster.Contains(a.SteamId)) continue;
                release.Add(a.ActorNumber);
            }
            return release;
        }

        /// <summary>Whether a freeze may take the assembly window, given
        /// whether this room has already had one taken.
        ///
        /// A rule rather than an `if` at the call site, for the same reason
        /// the other two are: the widening's discriminator is "was this actor
        /// in the room when the roster was taken", so WHICH INSTANT that names
        /// is part of the rule, not plumbing around it. Re-taking the window
        /// at a later freeze moves the instant forward and makes every actor
        /// that joined in between admissible at the next game boundary — the
        /// fail-OPEN direction, and precisely the late entrant the freeze
        /// exists to refuse. First window wins; the cost is residual 1 above.
        ///
        /// It takes the FLAG and not the set: a window taken in a room whose
        /// census read nothing is an EMPTY window that has still been taken,
        /// and "empty" must not invite a re-take.</summary>
        internal static bool ShouldCaptureAssembly(bool alreadyCaptured)
        {
            return !alreadyCaptured;
        }

        // ── self-test (EXECUTED by tools/client-rules-harness) ──────────────

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private static HashSet<string> Roster(params string[] ids)
        {
            return new HashSet<string>(ids, StringComparer.Ordinal);
        }

        private static string Join(IEnumerable<string> ids)
        {
            var sb = new StringBuilder("{");
            bool first = true;
            foreach (string s in ids) { if (!first) sb.Append(','); sb.Append(s); first = false; }
            return sb.Append('}').ToString();
        }

        private static string JoinInts(IEnumerable<int> ns)
        {
            var sb = new StringBuilder("{");
            bool first = true;
            foreach (int n in ns) { if (!first) sb.Append(','); sb.Append(n); first = false; }
            return sb.Append('}').ToString();
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();

            // The three seats the whole defect is about. A and B were resolved
            // at assembly and are on the roster; C was IN THE ROOM at assembly
            // but its u_id had not arrived, so the snapshot could not read it,
            // IsUnauthorized read it as unauthorized (fail-closed) and it was
            // latched. Its u_id has since arrived.
            var A = new Actor(1, "76561190000000001", false, false);
            var B = new Actor(2, "76561190000000002", false, false);
            var C = new Actor(3, "76561190000000003", false, false);

            // 1. THE FIX, end to end and in the order production runs it:
            //    frozen {A,B}, raw {A,B,C}, C latched -> the census admits C,
            //    the roster widens, and the latch is released.
            {
                var raw = new List<Actor> { A, B, C };
                var roster = Roster(A.SteamId, B.SteamId);
                var assembly = new HashSet<int> { 1, 2, 3 };
                var latched = new HashSet<int> { C.ActorNumber };

                var census = UnionCensus(raw, roster, assembly, true);
                foreach (string s in census) roster.Add(s);
                var released = LatchesToRelease(raw, latched, roster);

                Check(r, "a widening census discovers a latched fighter and releases it",
                      census.Contains(C.SteamId) && roster.Contains(C.SteamId)
                      && released.Count == 1 && released[0] == C.ActorNumber,
                      "census=" + Join(census) + " released=" + JoinInts(released));
            }

            // 1b. NEGATIVE CONTROL for the same case. The old census was
            //     ActiveFighters(), i.e. the raw census with the latched actor
            //     already removed. Feed the rules exactly that and the release
            //     must NOT happen — if this case passes, case 1 proves nothing
            //     about the census being raw.
            {
                var prefiltered = new List<Actor> { A, B };          // C removed by the latch
                var roster = Roster(A.SteamId, B.SteamId);
                var assembly = new HashSet<int> { 1, 2, 3 };
                var latched = new HashSet<int> { C.ActorNumber };

                var census = UnionCensus(prefiltered, roster, assembly, true);
                foreach (string s in census) roster.Add(s);
                var released = LatchesToRelease(prefiltered, latched, roster);

                Check(r, "a census that pre-excludes the latched actor cannot release it",
                      !census.Contains(C.SteamId) && released.Count == 0,
                      "census=" + Join(census) + " released=" + JoinInts(released));
            }

            // 2. THE HOLE THE NARROWING EXISTS FOR. D obtained the room name
            //    and joined after the freeze: not on the roster, not in the
            //    assembly set. The census must refuse it, and its latch must
            //    stay.
            {
                var D = new Actor(9, "76561190000000009", false, false);
                var raw = new List<Actor> { A, B, D };
                var roster = Roster(A.SteamId, B.SteamId);
                var assembly = new HashSet<int> { 1, 2, 3 };
                var latched = new HashSet<int> { D.ActorNumber };

                var census = UnionCensus(raw, roster, assembly, true);
                foreach (string s in census) roster.Add(s);
                var released = LatchesToRelease(raw, latched, roster);

                Check(r, "a late entrant is not admitted by the widening",
                      !census.Contains(D.SteamId) && !roster.Contains(D.SteamId)
                      && released.Count == 0,
                      "census=" + Join(census) + " released=" + JoinInts(released));
            }

            // 3. An UNRESOLVED seat contributes nothing and is not released —
            //    it is the state C was in at assembly, and the live rule reads
            //    it as unauthorized, so the two must agree.
            {
                var unresolved = new Actor(3, "", false, false);
                var raw = new List<Actor> { A, B, unresolved };
                var roster = Roster(A.SteamId, B.SteamId);
                var assembly = new HashSet<int> { 1, 2, 3 };
                var latched = new HashSet<int> { 3 };

                var census = UnionCensus(raw, roster, assembly, true);
                var released = LatchesToRelease(raw, latched, roster);

                Check(r, "an unreadable identity is neither admitted nor released",
                      census.Count == 2 && released.Count == 0,
                      "census=" + Join(census) + " released=" + JoinInts(released));
            }

            // 4. An IMPOSTOR is in the room, in the assembly window, and its
            //    u_id is a roster fighter's. It must be refused by BOTH rules:
            //    the latch on it is precisely what survives its departure.
            {
                var impostor = new Actor(4, A.SteamId, false, true);
                var raw = new List<Actor> { A, B, impostor };
                var roster = Roster(A.SteamId, B.SteamId);
                var assembly = new HashSet<int> { 1, 2, 3, 4 };
                var latched = new HashSet<int> { impostor.ActorNumber };

                var census = UnionCensus(raw, roster, assembly, true);
                var released = LatchesToRelease(raw, latched, roster);

                Check(r, "an impostor keeps its latch and adds nothing",
                      census.Count == 2 && released.Count == 0,
                      "census=" + Join(census) + " released=" + JoinInts(released));
            }

            // 5. A SPECTATOR takes no part in either rule, in the assembly
            //    window or out of it.
            {
                var spec = new Actor(5, "76561190000000005", true, false);
                var raw = new List<Actor> { A, B, spec };
                var roster = Roster(A.SteamId, B.SteamId);
                var assembly = new HashSet<int> { 1, 2, 5 };
                var latched = new HashSet<int> { spec.ActorNumber };

                var census = UnionCensus(raw, roster, assembly, true);
                var released = LatchesToRelease(raw, latched, roster);

                Check(r, "a spectator is not a fighter in either rule",
                      !census.Contains(spec.SteamId) && released.Count == 0,
                      "census=" + Join(census) + " released=" + JoinInts(released));
            }

            // 6. BEFORE the first freeze the census is the plain snapshot: no
            //    roster and no assembly set exist yet, and requiring either
            //    would make the first freeze empty and the whole mechanism
            //    inert.
            {
                var raw = new List<Actor> { A, B, C };
                var census = UnionCensus(raw, Roster(), new HashSet<int>(), false);
                Check(r, "an unfrozen room takes the whole resolvable snapshot",
                      census.Count == 3, "census=" + Join(census));
            }

            // 7. The census never NARROWS the roster: a roster member that is
            //    momentarily absent from the room is simply not re-listed, and
            //    the caller unions rather than replaces. Proved here as the
            //    property the caller depends on — the census of a room B has
            //    left still contains A, and contains nothing that would remove
            //    B.
            {
                var raw = new List<Actor> { A };
                var roster = Roster(A.SteamId, B.SteamId);
                var census = UnionCensus(raw, roster, new HashSet<int> { 1, 2 }, true);
                Check(r, "an absent roster member is not evicted by the census",
                      census.Count == 1 && census[0] == A.SteamId
                      && roster.Contains(B.SteamId),
                      "census=" + Join(census));
            }

            // 8. Order is by ActorNumber whatever order the room enumerated
            //    in, so two seats reading the same room build the same census.
            {
                var one = new List<Actor> { C, A, B };
                var two = new List<Actor> { B, C, A };
                var assembly = new HashSet<int> { 1, 2, 3 };
                var a = UnionCensus(one, Roster(), assembly, false);
                var b = UnionCensus(two, Roster(), assembly, false);
                Check(r, "the census is order-independent",
                      Join(a) == Join(b) && a.Count == 3 && a[0] == A.SteamId,
                      "a=" + Join(a) + " b=" + Join(b));
            }

            // 9. Degenerate inputs: no actors, no latches, nulls. None of them
            //    throw, and none of them release anything.
            {
                var census = UnionCensus(null, null, null, true);
                var released = LatchesToRelease(null, null, null);
                var released2 = LatchesToRelease(new List<Actor> { A }, new HashSet<int>(), Roster(A.SteamId));
                Check(r, "degenerate inputs are empty, not exceptions",
                      census.Count == 0 && released.Count == 0 && released2.Count == 0,
                      "census=" + census.Count + " released=" + released.Count);
            }

            // 10. THE ASSEMBLY WINDOW IS TAKEN ONCE PER ROOM, driven exactly as
            //     RoomActors.CaptureAssemblyActors drives it. The first freeze
            //     asks and takes {1,2}; D then obtains the room name and joins;
            //     a second freeze (a replace-freeze from a room-scoped path, or
            //     a re-entry) asks again with the flag set, is refused, and the
            //     window still describes the assembly — so the widening refuses
            //     D. Without this rule the second freeze would move the instant
            //     forward and D would be admitted at the next game boundary,
            //     which is the late entrant the freeze exists to refuse.
            {
                var D = new Actor(9, "76561190000000009", false, false);
                var window = new HashSet<int>();
                bool captured = false;

                if (ShouldCaptureAssembly(captured))          // first freeze: A and B are the room
                {
                    captured = true;
                    window.Clear(); window.Add(1); window.Add(2);
                }
                if (ShouldCaptureAssembly(captured))          // D has joined by now
                {
                    captured = true;
                    window.Clear(); window.Add(1); window.Add(2); window.Add(D.ActorNumber);
                }

                var raw = new List<Actor> { A, B, D };
                var roster = Roster(A.SteamId, B.SteamId);
                var census = UnionCensus(raw, roster, window, true);
                Check(r, "a second freeze does not re-open the assembly window",
                      !window.Contains(D.ActorNumber) && !census.Contains(D.SteamId),
                      "window=" + JoinInts(window) + " census=" + Join(census));
            }

            // 10b. NEGATIVE CONTROL for case 10. Hand the widening a window
            //      that WAS re-taken after D joined and D is admitted — so
            //      case 10 measures the refusal to re-take, and not something
            //      about D that would have excluded it anyway.
            {
                var D = new Actor(9, "76561190000000009", false, false);
                var retaken = new HashSet<int> { 1, 2, 9 };
                var raw = new List<Actor> { A, B, D };
                var roster = Roster(A.SteamId, B.SteamId);
                var census = UnionCensus(raw, roster, retaken, true);
                Check(r, "a re-taken window would admit the actor case 10 refuses",
                      census.Contains(D.SteamId),
                      "census=" + Join(census));
            }

            return r;
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
