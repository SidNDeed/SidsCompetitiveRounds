using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// v1.41.0 item 21: the Unity-free half of the damage and heal numbers.
    /// No UnityEngine, Photon or BepInEx reference, so tools/client-rules-harness
    /// compiles this file and EXECUTES its rules (suite "dmgnumbers", #391).
    ///
    /// What lives here: the coalescer (two accumulators per subject, keyed by
    /// subject AND kind), the expiring re-entrancy fence the two hooks use, the
    /// fixed live-label ring and its oldest-first eviction, the subject bound
    /// derived from the FFA lobby size, the threshold derived from the HP
    /// readout's format, the mode predicate, and the label text. Time arrives
    /// as a parameter, so the harness drives it.
    ///
    /// What does not: anchors, colours and drawing (DamageNumbers.cs), which
    /// need UnityEngine. Formatting happens HERE and only here; the Unity-side
    /// Tick stamps what this file returns and formats nothing.
    /// </summary>
    internal static class DamageNumberRules
    {
        internal enum Kind { Damage = 0, Heal = 1 }

        internal enum Mode { Off = 0, Me = 1, Everyone = 2 }

        /// <summary>A volley or burst is one event to the player.</summary>
        internal const float WindowDamage = 0.25f;
        /// <summary>Regeneration heals every frame; a shorter window stutters.</summary>
        internal const float WindowHeal = 0.75f;
        /// <summary>How stale a carried sub-threshold remainder may get.</summary>
        internal const float CarryMax = 3.0f;
        /// <summary>A fence entry older than this is a leak (a nested chain
        /// finishes inside one frame), so it reads as depth zero.</summary>
        internal const float FenceLife = 0.5f;
        /// <summary>Hard ceiling on tracked subjects, whatever the server says.</summary>
        internal const int SubjectCeiling = 16;
        /// <summary>Live labels; the ring is allocated once and never grows.</summary>
        internal const int MaxLive = 24;
        /// <summary>A label's whole life on screen.</summary>
        internal const float Life = 0.9f;
        /// <summary>The local view id of a seat with no fighter of its own.</summary>
        internal const int SpectatorSentinel = -1;

        /// <summary>One flushed number: who, which kind, the signed amount, the
        /// finished label text and the ring slot it was placed in.</summary>
        internal struct Emission
        {
            internal int Subject;
            internal Kind Kind;
            internal float Signed;
            internal string Text;
            internal int Slot;
        }

        internal struct FenceResult
        {
            internal bool Outermost;
            internal bool Expired;
        }

        internal static readonly Emission[] None = new Emission[0];

        // ------------------------------------------------------------ the coalescer

        internal sealed class Acc
        {
            internal float Mag;
            internal float OpenedAt = -1f;
            internal bool Open { get { return OpenedAt >= 0f; } }
            internal void Clear() { Mag = 0f; OpenedAt = -1f; }
        }

        internal sealed class Subj
        {
            internal int Id;
            internal readonly Acc Dmg = new Acc();
            internal readonly Acc Hl = new Acc();
        }

        /// <summary>The coalescer. Instance-shaped (one shared instance in the
        /// plugin) so the harness can run a fresh one per case; the virtual
        /// members are the seams the SelfTest mutants override.</summary>
        internal class Engine
        {
            internal readonly List<Subj> Subjects = new List<Subj>();
            internal readonly Ring Ring;
            private readonly List<Emission> _out = new List<Emission>();
            internal int Refusals;

            internal Engine() : this(new Ring()) { }
            internal Engine(Ring ring) { Ring = ring ?? new Ring(); }

            /// <summary>Accrue one observed delta. A zero, negative or
            /// non-finite magnitude notes nothing (the hooks already emit only
            /// a strictly positive change). False only when a NEW subject is
            /// refused at the cap; the caller reports that refusal.</summary>
            internal bool Note(int subject, Kind kind, float magnitude, float now, int subjectCap)
            {
                if (!(magnitude > 0f) || float.IsInfinity(magnitude)) return true;
                Subj s = Find(subject);
                if (s == null)
                {
                    if (Subjects.Count >= subjectCap) return Refuse();
                    s = new Subj { Id = subject };
                    Subjects.Add(s);
                }
                Acc a = Slot(s, kind);
                a.Mag += kind == Kind.Heal ? magnitude : -magnitude;
                if (!a.Open) a.OpenedAt = now;
                return true;
            }

            internal virtual Subj Find(int subject)
            {
                for (int i = 0; i < Subjects.Count; i++)
                    if (Subjects[i].Id == subject) return Subjects[i];
                return null;
            }

            internal virtual Acc Slot(Subj s, Kind kind) { return kind == Kind.Heal ? s.Hl : s.Dmg; }
            internal virtual bool Refuse() { Refusals++; return false; }
            internal virtual float Window(Kind kind) { return kind == Kind.Heal ? WindowHeal : WindowDamage; }
            internal virtual bool CarryExpired(float age) { return age >= CarryMax; }
            internal virtual void OnSuppressed(Acc a) { }
            internal virtual bool MayEmit() { return true; }
            internal virtual bool HealFirst(Subj s) { return false; }
            internal virtual string Text(Kind kind, float magnitude, string fmt) { return Compose(kind, magnitude, fmt); }

            /// <summary>Flush every due accumulator and return what became a
            /// label, damage before heal for each subject, subjects in the
            /// order they were first noted. A subject with nothing open is
            /// forgotten, so the cap counts live subjects only.</summary>
            internal Emission[] Tick(float now, string fmt)
            {
                if (Subjects.Count == 0) return None;
                double minShow = MinShowFromFormat(fmt);
                _out.Clear();
                for (int i = 0; i < Subjects.Count; i++)
                {
                    Subj s = Subjects[i];
                    if (HealFirst(s))
                    {
                        FlushOne(s, s.Hl, Kind.Heal, now, minShow, fmt);
                        FlushOne(s, s.Dmg, Kind.Damage, now, minShow, fmt);
                    }
                    else
                    {
                        FlushOne(s, s.Dmg, Kind.Damage, now, minShow, fmt);
                        FlushOne(s, s.Hl, Kind.Heal, now, minShow, fmt);
                    }
                }
                for (int i = Subjects.Count - 1; i >= 0; i--)
                    if (!Subjects[i].Dmg.Open && !Subjects[i].Hl.Open) Subjects.RemoveAt(i);
                return _out.Count == 0 ? None : _out.ToArray();
            }

            private void FlushOne(Subj s, Acc a, Kind slotKind, float now, double minShow, string fmt)
            {
                if (!a.Open) return;
                float age = now - a.OpenedAt;
                if (age < Window(slotKind)) return;
                float mag = Math.Abs(a.Mag);
                if (mag + 1e-6 >= minShow && MayEmit())
                {
                    Kind k = a.Mag < 0f ? Kind.Damage : Kind.Heal;
                    _out.Add(new Emission
                    {
                        Subject = s.Id,
                        Kind = k,
                        Signed = a.Mag,
                        Text = Text(k, mag, fmt),
                        Slot = Ring.Place(now),
                    });
                    a.Clear();
                }
                else if (CarryExpired(age)) a.Clear();
                else OnSuppressed(a);
            }
        }

        // ------------------------------------------------------------ the fence

        /// <summary>Per-subject (depth, stampedAt), EXPIRING. Harmony runs no
        /// Postfix when the patched method aborts and DoDamage carries no
        /// finalizer, so a plain counter would strand one victim at depth 1 and
        /// that player would silently never get another number. An entry older
        /// than FenceLife reads as depth zero, so the unhandled case self-heals
        /// on the next hit and is counted, not hidden.</summary>
        internal class Fence
        {
            private struct F { internal int Depth; internal float StampedAt; }
            private readonly Dictionary<int, F> _m = new Dictionary<int, F>();
            internal int Expirations;

            internal FenceResult Enter(int subject, float now)
            {
                F f;
                bool expired = false;
                if (_m.TryGetValue(subject, out f) && f.Depth != 0 && Stale(now - f.StampedAt))
                {
                    f.Depth = 0;
                    expired = true;
                    Expirations++;
                }
                int before = f.Depth;
                f.Depth = Increment(before);
                f.StampedAt = now;
                _m[subject] = f;
                if (_m.Count > 64) Prune(now);
                return new FenceResult { Outermost = before == 0, Expired = expired };
            }

            /// <summary>Called from the Postfix's finally, only when the Prefix
            /// armed. The entry is kept at depth zero (pruned once stale), so
            /// the floor is what stops an unmatched Exit making the next real
            /// nesting look outermost.</summary>
            internal void Exit(int subject)
            {
                F f;
                if (!_m.TryGetValue(subject, out f)) return;
                f.Depth = Decrement(f.Depth);
                _m[subject] = f;
            }

            internal int Depth(int subject)
            {
                F f;
                return _m.TryGetValue(subject, out f) ? f.Depth : 0;
            }

            internal int Count { get { return _m.Count; } }

            internal virtual int Increment(int d) { return d + 1; }
            internal virtual int Decrement(int d) { return d > 0 ? d - 1 : 0; }
            internal virtual bool Stale(float age) { return age > FenceLife; }

            private void Prune(float now)
            {
                var dead = new List<int>();
                foreach (var kv in _m) if (Stale(now - kv.Value.StampedAt)) dead.Add(kv.Key);
                foreach (int k in dead) _m.Remove(k);
            }
        }

        // ------------------------------------------------------------ the ring

        /// <summary>The live-label slots, fixed at MaxLive. A slot is free
        /// when unused or past its Life; when none is free the OLDEST is
        /// retired, never the newest, because the newest is the one being
        /// read.</summary>
        internal class Ring
        {
            internal readonly float[] Born = new float[MaxLive];
            internal readonly bool[] Used = new bool[MaxLive];
            internal int Evictions;

            internal bool IsLive(int i, float now) { return Used[i] && now - Born[i] < Life; }

            internal int Place(float now)
            {
                for (int i = 0; i < MaxLive; i++)
                    if (!IsLive(i, now)) { Used[i] = true; Born[i] = now; return i; }
                int v = Victim();
                Evictions++;
                Used[v] = true;
                Born[v] = now;
                return v;
            }

            internal virtual int Victim()
            {
                int v = 0;
                for (int i = 1; i < MaxLive; i++) if (Born[i] < Born[v]) v = i;
                return v;
            }

            internal int LiveCount(float now)
            {
                int n = 0;
                for (int i = 0; i < MaxLive; i++) if (IsLive(i, now)) n++;
                return n;
            }
        }

        // ------------------------------------------------------------ derived values

        /// <summary>The subject bound follows the room: the FFA lobby size
        /// (a mutable static the server's max_players overwrites) plus two,
        /// never above SubjectCeiling. A server value may only move this client
        /// toward the conservative outcome (#283), so the ceiling holds.</summary>
        internal static int SubjectCapFor(int ffaLobbyMaxPlayers)
        {
            int n = ffaLobbyMaxPlayers < 1 ? 1 : ffaLobbyMaxPlayers;
            return Math.Min(n + 2, SubjectCeiling);
        }

        /// <summary>The precision digit of the HP readout's format: the
        /// character after the leading F, clamped to 0..2. Any other shape
        /// reads as 0 digits, the coarsest label, never a flood.</summary>
        internal static int FormatDigits(string fmt)
        {
            if (fmt == null || fmt.Length != 2) return 0;
            if (fmt[0] != 'F' && fmt[0] != 'f') return 0;
            int d = fmt[1] - '0';
            if (d < 0 || d > 9) return 0;
            return d > 2 ? 2 : d;
        }

        /// <summary>One unit in the last displayed place: 1, 0.1 or 0.01.
        /// Derived from the format by digit arithmetic, so no format literal is
        /// written anywhere in this file outside its SelfTest.</summary>
        internal static double MinShowFromFormat(string fmt)
        {
            return Math.Pow(10, -FormatDigits(fmt));
        }

        /// <summary>The label: a sign and the number, in the HP readout's own
        /// format and the board's culture. No word, no unit - a label with two
        /// letters in it would look harvestable and ship English in four
        /// locales.</summary>
        internal static string Compose(Kind kind, float magnitude, string fmt)
        {
            int d = FormatDigits(fmt);
            string f = fmt != null && fmt.Length == 2 && fmt[1] - '0' == d
                ? fmt
                : new string(new[] { 'F', (char)('0' + d) });
            return (kind == Kind.Damage ? "-" : "+") + magnitude.ToString(f, CultureInfo.CurrentCulture);
        }

        /// <summary>Off shows nothing; Me shows the local fighter only, and
        /// degrades to everyone on a seat with no fighter (a spectator who picked
        /// Me asked for less noise, not for silence); Everyone shows all.</summary>
        internal static bool ShouldShow(Mode mode, int subjectViewId, int localViewId)
        {
            if (mode == Mode.Off) return false;
            if (mode == Mode.Me) return localViewId == SpectatorSentinel || subjectViewId == localViewId;
            return true;
        }

        // ------------------------------------------------------------ shared state

        internal static readonly Engine Shared = new Engine();
        internal static readonly Fence DamageFence = new Fence();
        internal static readonly Fence HealFence = new Fence();
        private static string _fmt;

        /// <summary>The HP readout's format, handed in by the Unity side each
        /// frame; resolved at emit, so a flying label keeps the format it was
        /// born with.</summary>
        internal static void SetFormat(string fmt) { _fmt = fmt; }

        /// <summary>The rules-side tick: flush and format. Called from
        /// DamageNumbers.Tick, which stamps anchors and colours.</summary>
        internal static Emission[] Tick(float now)
        {
            return Shared.Tick(now, _fmt);
        }

        // ------------------------------------------------------------ self-test

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private struct Ev
        {
            internal float T;
            internal int S;
            internal Kind K;
            internal float M;
            internal Ev(float t, int s, Kind k, float m) { T = t; S = s; K = k; M = m; }
        }

        // The mutants. Each overrides exactly one seam of the production
        // classes above; a check whose mutant line stays green is a check that
        // cannot fail (#342/#391).
        private sealed class ZeroWindowMutant : Engine { internal override float Window(Kind kind) { return 0f; } }
        private sealed class ResetOnSuppressMutant : Engine { internal override void OnSuppressed(Acc a) { a.Clear(); } }
        private sealed class NoCarryMaxMutant : Engine { internal override bool CarryExpired(float age) { return false; } }
        private sealed class SignedOneAccMutant : Engine { internal override Acc Slot(Subj s, Kind kind) { return s.Dmg; } }
        private sealed class KindOnlyKeyMutant : Engine
        {
            internal override Subj Find(int subject) { return Subjects.Count > 0 ? Subjects[0] : null; }
        }
        private sealed class SilentRefusalMutant : Engine { internal override bool Refuse() { return true; } }
        private sealed class NewestFirstRing : Ring
        {
            internal override int Victim()
            {
                int v = 0;
                for (int i = 1; i < MaxLive; i++) if (Born[i] > Born[v]) v = i;
                return v;
            }
        }
        private sealed class NoIncrementFence : Fence { internal override int Increment(int d) { return d; } }
        private sealed class NeverStaleFence : Fence { internal override bool Stale(float age) { return false; } }
        private sealed class NoFloorFence : Fence { internal override int Decrement(int d) { return d - 1; } }
        // Emission made conditional on a draw having happened; the harness
        // never draws, which is exactly the state a gated overlay is in.
        private sealed class DrawGatedMutant : Engine { internal override bool MayEmit() { return false; } }
        private sealed class NullTextMutant : Engine { internal override string Text(Kind kind, float magnitude, string fmt) { return null; } }
        private sealed class HealFirstMutant : Engine { internal override bool HealFirst(Subj s) { return true; } }

        /// <summary>Drive an engine at 20 frames a second: each frame applies
        /// the notes due by then (stamped at their own time), then ticks.</summary>
        private static List<Emission> Sim(Engine e, Ev[] evs, float until, string fmt, int cap)
        {
            var got = new List<Emission>();
            int next = 0;
            for (int f = 0; ; f++)
            {
                float t = f * 0.05f;
                if (t > until + 1e-4f) break;
                while (next < evs.Length && evs[next].T <= t + 1e-4f)
                {
                    e.Note(evs[next].S, evs[next].K, evs[next].M, evs[next].T, cap);
                    next++;
                }
                got.AddRange(e.Tick(t, fmt));
            }
            return got;
        }

        private static string Show(List<Emission> em)
        {
            var sb = new StringBuilder("[");
            for (int i = 0; i < em.Count; i++)
            {
                if (i > 0) sb.Append(' ');
                sb.Append(em[i].Subject.ToString(CultureInfo.InvariantCulture)).Append(':')
                  .Append(em[i].Signed.ToString("0.##", CultureInfo.InvariantCulture));
            }
            return sb.Append(']').ToString();
        }

        private static bool Near(float a, float b) { return Math.Abs(a - b) < 1e-3f; }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            const string F0 = "F0";

            // A1: three 11s inside WindowDamage are one entry of 33.
            {
                var evs = new[] { new Ev(0f, 1, Kind.Damage, 11f), new Ev(0.1f, 1, Kind.Damage, 11f), new Ev(0.2f, 1, Kind.Damage, 11f) };
                Func<Engine, List<Emission>> run = e => Sim(e, evs, 1f, F0, 12);
                var p = run(new Engine());
                var m = run(new ZeroWindowMutant());
                var c = Sim(new Engine(), new[] { new Ev(0f, 1, Kind.Damage, 11f), new Ev(0.4f, 1, Kind.Damage, 11f), new Ev(0.8f, 1, Kind.Damage, 11f) }, 1.5f, F0, 12);
                Check(r, "A1", "three damages inside WindowDamage are one entry of 33",
                    p.Count == 1 && Near(p[0].Signed, -33f), !(m.Count == 1 && Near(m[0].Signed, -33f)), c.Count == 3,
                    "prod=" + Show(p) + " mutant(window 0)=" + Show(m) + " control(0.4 s apart)=" + Show(c));
            }

            // A2: sub-threshold ticks carry until they cross MinShow.
            {
                var evs = new[] { new Ev(0f, 1, Kind.Damage, 0.4f), new Ev(0.5f, 1, Kind.Damage, 0.4f), new Ev(0.7f, 1, Kind.Damage, 0.4f) };
                var p = Sim(new Engine(), evs, 1.5f, F0, 12);
                var m = Sim(new ResetOnSuppressMutant(), evs, 1.5f, F0, 12);
                var ce = new Engine();
                ce.Note(1, Kind.Damage, 0.4f, 0f, 12);
                var c = new List<Emission>(ce.Tick(0.3f, "F2"));
                Check(r, "A2", "sub-threshold ticks carry until they cross MinShow",
                    p.Count == 1 && Near(p[0].Signed, -1.2f), m.Count == 0, c.Count == 1 && Near(c[0].Signed, -0.4f),
                    "prod=" + Show(p) + " mutant(reset on suppress)=" + Show(m) + " control(F2, first window)=" + Show(c));
            }

            // A3: a lone 0.4 is dropped at CarryMax, never emitted late.
            {
                var evs = new[] { new Ev(0f, 1, Kind.Damage, 0.4f), new Ev(3.3f, 1, Kind.Damage, 0.7f) };
                var pe = new Engine();
                var p = Sim(pe, evs, 3.7f, F0, 12);
                var m = Sim(new NoCarryMaxMutant(), evs, 3.7f, F0, 12);
                var c = Sim(new Engine(), new[] { new Ev(0f, 1, Kind.Damage, 0.4f), new Ev(CarryMax - 0.1f, 1, Kind.Damage, 0.7f) }, 3.5f, F0, 12);
                Check(r, "A3", "a lone 0.4 is dropped at CarryMax and never emitted late",
                    p.Count == 0, m.Count != 0, c.Count == 1 && Near(c[0].Signed, -1.1f),
                    "prod=" + Show(p) + " mutant(no CarryMax)=" + Show(m) + " control(0.7 at CarryMax-0.1)=" + Show(c));
            }

            // A4: damage and heal never cancel into silence.
            {
                var evs = new[] { new Ev(0f, 1, Kind.Damage, 20f), new Ev(0.05f, 1, Kind.Heal, 20f) };
                var p = Sim(new Engine(), evs, 1f, F0, 12);
                var m = Sim(new SignedOneAccMutant(), evs, 1f, F0, 12);
                var c = Sim(new Engine(), new[] { new Ev(0f, 1, Kind.Damage, 20f) }, 1f, F0, 12);
                Check(r, "A4", "-20 and +20 in one window emit two entries",
                    p.Count == 2 && Near(p[0].Signed, -20f) && Near(p[1].Signed, 20f), m.Count != 2, c.Count == 1,
                    "prod=" + Show(p) + " mutant(one signed accumulator)=" + Show(m) + " control(damage only)=" + Show(c));
            }

            // A5: the key is (subject, kind) - one dimension varied at a time,
            // each with the mutant that drops exactly that dimension.
            {
                var subjEvs = new[] { new Ev(0f, 1, Kind.Damage, 11f), new Ev(0.05f, 2, Kind.Damage, 7f) };
                var kindEvs = new[] { new Ev(0f, 1, Kind.Damage, 11f), new Ev(0.05f, 1, Kind.Heal, 7f) };
                var ps = Sim(new Engine(), subjEvs, 1f, F0, 12);
                var pk = Sim(new Engine(), kindEvs, 1f, F0, 12);
                var ms = Sim(new KindOnlyKeyMutant(), subjEvs, 1f, F0, 12);
                var mk = Sim(new SignedOneAccMutant(), kindEvs, 1f, F0, 12);
                bool subjOk = ps.Count == 2 && ps[0].Subject == 1 && Near(ps[0].Signed, -11f) && ps[1].Subject == 2 && Near(ps[1].Signed, -7f);
                bool kindOk = pk.Count == 2 && Near(pk[0].Signed, -11f) && Near(pk[1].Signed, 7f);
                bool msRed = !(ms.Count == 2 && Near(ms[0].Signed, -11f) && Near(ms[1].Signed, -7f));
                bool mkRed = !(mk.Count == 2 && Near(mk[0].Signed, -11f) && Near(mk[1].Signed, 7f));
                var c = Sim(new Engine(), new[] { new Ev(0f, 1, Kind.Damage, 11f), new Ev(0.05f, 1, Kind.Damage, 7f) }, 1f, F0, 12);
                Check(r, "A5", "the accumulators are keyed by (subject, kind), each dimension separately",
                    subjOk && kindOk, msRed && mkRed, c.Count == 1 && Near(c[0].Signed, -18f),
                    "subject: prod=" + Show(ps) + " mutant(key on kind alone)=" + Show(ms)
                    + "; kind: prod=" + Show(pk) + " mutant(key on subject alone)=" + Show(mk)
                    + "; control(two damages, one subject)=" + Show(c));
            }

            // A6: a subject past the cap is refused AND reported.
            {
                Func<Engine, string> probe = e =>
                {
                    bool all12 = true;
                    for (int s = 1; s <= 12; s++) all12 &= e.Note(s, Kind.Damage, 5f, 0f, 12);
                    int before = e.Refusals;
                    bool thirteenth = e.Note(13, Kind.Damage, 5f, 0f, 12);
                    bool again = e.Note(1, Kind.Damage, 5f, 0.01f, 12);
                    return (all12 ? "12in" : "12out") + "|" + before + "|" + (thirteenth ? "13in" : "13out") + "|" + e.Refusals + "|" + (again ? "1on" : "1off");
                };
                string p = probe(new Engine());
                string m = probe(new SilentRefusalMutant());
                var ce = new Engine();
                for (int s = 1; s <= 11; s++) ce.Note(s, Kind.Damage, 5f, 0f, 12);
                bool twelfth = ce.Note(12, Kind.Damage, 5f, 0f, 12);
                string want = "12in|0|13out|1|1on";
                Check(r, "A6", "a subject past SubjectCap is refused and counted; the first 12 keep accumulating",
                    p == want, m != want, twelfth && ce.Refusals == 0,
                    "prod=" + p + " mutant(silent refusal)=" + m + " control(12th admitted)=" + twelfth + "/refusals " + ce.Refusals);
            }

            // A7: SubjectCap follows FfaLobbyMaxPlayers + 2 under a ceiling of 16.
            {
                Func<int, int> mut = n => n + 2;
                int p40 = SubjectCapFor(40), m40 = mut(40), p10 = SubjectCapFor(10);
                Check(r, "A7", "SubjectCap is FfaLobbyMaxPlayers+2, ceilinged at 16",
                    p40 == 16, m40 != 16, p10 == 12,
                    "prod(40)=" + p40 + " mutant(no ceiling)(40)=" + m40 + " control(10)=" + p10);
            }

            // A8: at MaxLive a new entry retires the OLDEST.
            {
                Func<Ring, string> fill = ring =>
                {
                    for (int i = 0; i < MaxLive; i++) ring.Place(i * 0.001f);
                    float tNew = MaxLive * 0.001f;
                    int slot = ring.Place(tNew);
                    bool newestLive = ring.IsLive(MaxLive - 1, tNew) && Near(ring.Born[MaxLive - 1], (MaxLive - 1) * 0.001f);
                    return slot + "|" + (newestLive ? "newest-live" : "newest-gone");
                };
                string p = fill(new Ring());
                string m = fill(new NewestFirstRing());
                var cr = new Ring();
                for (int i = 0; i < MaxLive - 1; i++) cr.Place(i * 0.001f);
                int cs = cr.Place(0.5f);
                Check(r, "A8", "at MaxLive a new entry retires the oldest, never the newest",
                    p == "0|newest-live", m != "0|newest-live", cs == MaxLive - 1 && cr.Evictions == 0 && cr.LiveCount(0.5f) == MaxLive,
                    "prod=" + p + " mutant(newest first)=" + m + " control(one free slot)=slot " + cs + " evictions " + cr.Evictions);
            }

            // A9: a nested Enter on one subject is not the outermost.
            {
                Func<Fence, bool> nested = fe => { fe.Enter(7, 0f); return fe.Enter(7, 0.001f).Outermost; };
                bool p = nested(new Fence());
                bool m = nested(new NoIncrementFence());
                bool c = new Fence().Enter(8, 0f).Outermost;
                Check(r, "A9", "a nested Enter returns Outermost=false",
                    !p, m, c, "prod inner outermost=" + p + " mutant(no increment)=" + m + " control(first Enter)=" + c);
            }

            // A10: the fence expires.
            {
                Func<Fence, FenceResult> leak = fe =>
                {
                    fe.Enter(7, 0f);
                    fe.Enter(7, 0.001f);
                    return fe.Enter(7, 0.001f + FenceLife + 0.01f);
                };
                var p = leak(new Fence());
                var m = leak(new NeverStaleFence());
                var cf = new Fence();
                cf.Enter(7, 0f);
                bool cInner = cf.Enter(7, 0.01f).Outermost;
                cf.Exit(7); cf.Exit(7);
                Check(r, "A10", "a stranded fence entry expires: Outermost=true and Expired=true",
                    p.Outermost && p.Expired, !(m.Outermost && m.Expired), !cInner && cf.Depth(7) == 0,
                    "prod=" + p.Outermost + "/" + p.Expired + " mutant(never stale)=" + m.Outermost + "/" + m.Expired
                    + " control(paired inner)=" + cInner + " depth " + cf.Depth(7));
            }

            // A11: Exit floors at zero.
            {
                Func<Fence, string> probe = fe =>
                {
                    fe.Enter(7, 0f);   // a real pair leaves the entry at depth 0
                    fe.Exit(7);
                    fe.Exit(7);        // unmatched
                    bool a = fe.Enter(7, 0.01f).Outermost;
                    bool b = fe.Enter(7, 0.02f).Outermost;
                    return a + "|" + b;
                };
                string p = probe(new Fence());
                string m = probe(new NoFloorFence());
                var cf = new Fence();
                cf.Enter(9, 0f); cf.Exit(9);
                Check(r, "A11", "an unmatched Exit cannot drive depth negative",
                    p == "True|False", m != "True|False", cf.Depth(9) == 0,
                    "prod=" + p + " mutant(no floor)=" + m + " control(matched pair) depth " + cf.Depth(9));
            }

            // A12: MinShowFromFormat("F0") is 1.
            {
                Func<string, double> mut = s => 1.0;
                double p0 = MinShowFromFormat("F0"), p1 = MinShowFromFormat("F1"), p2 = MinShowFromFormat("F2");
                bool claim = Math.Abs(p0 - 1.0) < 1e-9 && Math.Abs(p1 - 0.1) < 1e-9 && Math.Abs(p2 - 0.01) < 1e-9;
                bool mRed = !(Math.Abs(mut("F0") - 1.0) < 1e-9 && Math.Abs(mut("F1") - 0.1) < 1e-9 && Math.Abs(mut("F2") - 0.01) < 1e-9);
                Check(r, "A12", "MinShowFromFormat derives 1 / 0.1 / 0.01 from F0 / F1 / F2",
                    claim, mRed, Math.Abs(p1 - 0.1) < 1e-9 && Math.Abs(p2 - 0.01) < 1e-9,
                    "prod=" + p0 + "/" + p1 + "/" + p2 + " mutant(constant)=" + mut("F0") + "/" + mut("F1") + "/" + mut("F2"));
            }

            // A13: a junk format yields 1 - the coarsest label, never a flood.
            {
                Func<string, double> mut = s => (s == "F1") ? 0.1 : (s == "F2") ? 0.01 : (s == "F0") ? 1.0 : 0.01;
                double pj = MinShowFromFormat("junk"), pn = MinShowFromFormat(null), pe = MinShowFromFormat("");
                double mj = mut("junk");
                Check(r, "A13", "a junk format string yields MinShow 1",
                    Math.Abs(pj - 1.0) < 1e-9 && Math.Abs(pn - 1.0) < 1e-9 && Math.Abs(pe - 1.0) < 1e-9,
                    !(Math.Abs(mj - 1.0) < 1e-9), Math.Abs(MinShowFromFormat("F2") - 0.01) < 1e-9,
                    "prod(junk/null/empty)=" + pj + "/" + pn + "/" + pe + " mutant(fallback 0.01)=" + mj + " control(F2)=" + MinShowFromFormat("F2"));
            }

            // A14: Tick emits a LONE hit once the window passes, with no draw.
            {
                var evs = new[] { new Ev(0f, 1, Kind.Damage, 12f) };
                var p = Sim(new Engine(), evs, 1f, F0, 12);
                var m = Sim(new DrawGatedMutant(), evs, 1f, F0, 12);
                var ce = new Engine();
                ce.Note(1, Kind.Damage, 12f, 0f, 12);
                int early = ce.Tick(0.1f, F0).Length;
                Check(r, "A14", "a lone damage with nothing after it is emitted once WindowDamage passes",
                    p.Count == 1 && Near(p[0].Signed, -12f), m.Count == 0, early == 0,
                    "prod=" + Show(p) + " mutant(emit only after a draw)=" + Show(m) + " control(inside the window)=" + early + " emitted");
            }

            // A15: the emission is PREFORMATTED in the rules layer.
            {
                var evs = new[] { new Ev(0f, 1, Kind.Damage, 12f), new Ev(0f, 2, Kind.Heal, 8f) };
                var p = Sim(new Engine(), evs, 1f, F0, 12);
                var m = Sim(new NullTextMutant(), evs, 1f, F0, 12);
                Func<List<Emission>, bool> ready = l => l.Count == 2 && l[0].Text == "-12" && l[1].Text == "+8";
                var ce = new Engine();
                ce.Note(1, Kind.Damage, 12f, 0f, 12);
                var early = ce.Tick(0.05f, F0);
                Check(r, "A15", "Tick returns render-ready text: -12 and +8",
                    ready(p), !ready(m), early.Length == 0,
                    "prod=" + (p.Count > 0 ? p[0].Text : "none") + "," + (p.Count > 1 ? p[1].Text : "none")
                    + " mutant(text left for Draw)=" + (m.Count > 0 ? (m[0].Text ?? "null") : "none")
                    + " control(unflushed)=" + early.Length + " entries");
            }

            // A16: damage before heal for one subject, whatever the input order.
            {
                // Both noted at t=0 and ticked once at t=1, so both are due in
                // the SAME tick and only the ordering rule decides.
                Func<Engine, bool, string> run = (e, healNotedFirst) =>
                {
                    if (healNotedFirst) { e.Note(1, Kind.Heal, 5f, 0f, 12); e.Note(1, Kind.Damage, 10f, 0f, 12); }
                    else { e.Note(1, Kind.Damage, 10f, 0f, 12); e.Note(1, Kind.Heal, 5f, 0f, 12); }
                    return Show(new List<Emission>(e.Tick(1f, F0)));
                };
                string want = "[1:-10 1:5]";
                string p = run(new Engine(), false);
                string m = run(new HealFirstMutant(), false);
                string c = run(new Engine(), true);
                Check(r, "A16", "a heal and a damage due in one tick emit damage first",
                    p == want, m != want, c == want,
                    "prod=" + p + " mutant(heal first)=" + m + " control(input order reversed)=" + c);
            }

            // A17: ShouldShow - two claims, two mutants.
            {
                const int me = 5, other = 6, spec = SpectatorSentinel;
                Func<Func<Mode, int, int, bool>, string> arms = f =>
                    "off:" + (!f(Mode.Off, me, me) && !f(Mode.Off, other, me))
                    + " me:" + (f(Mode.Me, me, me) && !f(Mode.Me, other, me) && f(Mode.Me, other, spec))
                    + " all:" + (f(Mode.Everyone, other, me) && f(Mode.Everyone, me, me));
                Func<Mode, int, int, bool> prod = ShouldShow;
                Func<Mode, int, int, bool> mutA = (mo, s, l) => mo == Mode.Off ? s == l : ShouldShow(mo, s, l);
                Func<Mode, int, int, bool> mutB = (mo, s, l) => mo == Mode.Me ? s == l : ShouldShow(mo, s, l);
                string want = "off:True me:True all:True";
                string p = arms(prod), a = arms(mutA), b = arms(mutB);
                bool aSplit = a == "off:False me:True all:True";
                bool bRed = b != want;
                bool ctl = prod(Mode.Everyone, other, spec) && mutB(Mode.Everyone, other, spec);
                Check(r, "A17", "ShouldShow: Off never, Me the local fighter (everyone on a spectator seat), Everyone always",
                    p == want, aSplit && bRed, ctl,
                    "prod=" + p + " mutant(a Off shows local)=" + a + " mutant(b Me without the spectator degrade)=" + b
                    + " control(Everyone, spectator)=" + ctl);
            }

            return r;
        }

        /// <summary>One case line: the claim on production, the claim on its
        /// mutant (passes only when it goes red) and the control (passes only
        /// when it stays green). The line passes only when all three do.</summary>
        private static void Check(SelfTestResult r, string id, string claim, bool claimOk, bool mutantRed, bool controlOk, string got)
        {
            bool ok = claimOk && mutantRed && controlOk;
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS " : "FAIL ").Append(id).Append(' ').Append(claim)
             .Append(" | claim=").Append(claimOk ? "green" : "RED")
             .Append(" mutation=").Append(mutantRed ? "red" : "STAYED-GREEN")
             .Append(" control=").Append(controlOk ? "green" : "RED")
             .Append(" | got=").Append(got).Append('\n');
        }
    }
}
