using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.ExceptionServices;

namespace CompetitiveRounds
{
    /// <summary>
    /// FFA mid-game readmission (design V3, ai-collab/rejoin/RJ-READMIT-DESIGN-V3.md):
    /// the pure rules. Nothing in this file touches Unity, Photon or BepInEx,
    /// so tools/tests/rj-readmit-client compiles it under a plain compiler and
    /// RUNS the rules rather than asserting about their source (#391).
    ///
    /// Every behaviour these rules drive is confined to a readmission lobby:
    /// a lobby whose readmit flag the server wrote at lock and every client
    /// pinned for the sitting (V3 P4.6). Outside one, nothing here is called.
    /// </summary>
    internal static class FfaReadmitRules
    {
        // ------------------------------------------------------------------ P1: the apply plan

        /// <summary>The values ApplyManifestPick computes from the deck and the
        /// card name before it writes anything: the prefab, whether the deck
        /// rolls, the survivors and the dropped card's raw name. Computed once,
        /// read at the statements that read them (V3 P1).</summary>
        internal sealed class ApplyPlan<T> where T : class
        {
            internal T Prefab;
            internal bool Rolls;
            internal List<T> Survivors;
            private string _droppedRaw;
            private ExceptionDispatchInfo _droppedFault;

            /// <summary>The raw name of the card that rolls off. A fault while
            /// reading it surfaces HERE, where the pre-split reducer read it,
            /// so a throw stops the reducer at the same statement as before.</summary>
            internal string DroppedRaw()
            {
                if (_droppedFault != null) _droppedFault.Throw();
                return _droppedRaw;
            }

            internal void SetDropped(Func<string> read)
            {
                try { _droppedRaw = read(); }
                catch (Exception ex) { _droppedFault = ExceptionDispatchInfo.Capture(ex); }
            }
        }

        /// <summary>PlanApply: no side effect. The prefab is resolve(cardName);
        /// the deck rolls when it holds cardCap or more cards; the survivors
        /// are its LAST cardCap - 1 entries and the dropped card is entry 0,
        /// "(Clone)" removed. A null deck is an empty one.</summary>
        internal static ApplyPlan<T> PlanApply<T>(IList<T> deck, string cardName, int cardCap,
                                                  Func<string, T> resolve, Func<T, string> rawName) where T : class
        {
            var plan = new ApplyPlan<T> { Prefab = resolve(cardName) };
            int count = deck == null ? 0 : deck.Count;
            if (count >= cardCap)
            {
                plan.Rolls = true;
                plan.Survivors = deck.Skip(count - (cardCap - 1)).ToList();
                var first = deck[0];
                plan.SetDropped(() => rawName(first).Replace("(Clone)", ""));
            }
            return plan;
        }

        // ------------------------------------------------------------------ P4.6: the pinned lobby flag

        /// <summary>The readmit flag of a sitting, pinned from the lock payload
        /// (V3 P4.6). The server writes it once at lock from every locked
        /// member's caps; a client pins it at the first lock of the lobby and
        /// never re-derives it (#280: a decision every client must share is
        /// pinned, not live-read). A re-form of the same lobby moves the room
        /// and keeps the flag.</summary>
        internal sealed class ReadmitPin
        {
            internal string Lobby = "";
            internal string Room = "";
            internal bool Flag;
        }

        /// <summary>The pin after a gated lock payload for lobby/room carrying
        /// readmit = payloadReadmit (1 is true, anything else false; an absent
        /// key is an older server, false).</summary>
        internal static ReadmitPin PinFromLock(ReadmitPin held, string lobby, string room, int payloadReadmit)
        {
            if (held != null && !string.IsNullOrEmpty(lobby) && held.Lobby == lobby)
                return new ReadmitPin { Lobby = held.Lobby, Room = string.IsNullOrEmpty(room) ? held.Room : room, Flag = held.Flag };
            return new ReadmitPin { Lobby = lobby ?? "", Room = room ?? "", Flag = payloadReadmit == 1 };
        }

        /// <summary>What a client sees when it decides whether its room runs the
        /// readmission rules. Only the pin and the room are read; the present
        /// members' capability is in the view because it is visible at every
        /// call site, and the gate must not read it (V3 P2 gate, RJ2-H3).</summary>
        internal sealed class GateView
        {
            internal ReadmitPin Pin;
            internal string Room;
            internal Func<bool> PresentAllAdvertise;
        }

        /// <summary>The readmission gate: the pinned flag, for the pinned room.</summary>
        internal static bool GateOn(GateView v)
        {
            return v != null && v.Pin != null && v.Pin.Flag && !string.IsNullOrEmpty(v.Room) && v.Room == v.Pin.Room;
        }

        // ------------------------------------------------------------------ P2: picker set and the bodiless apply

        /// <summary>V3 P2 step 1: with the gate on, every roster slot except the
        /// round winner's, with or without a kept body; with it off, the kept
        /// bodies except the round winner's (today). Ascending.</summary>
        internal static List<int> PickerSet(bool gate, int rosterCount, IList<int> keptBodySlots, int winnerSlot)
        {
            var o = new List<int>();
            if (gate && rosterCount > 0)
            {
                for (int s = 0; s < rosterCount; s++)
                    if (s != winnerSlot) o.Add(s);
                return o;
            }
            if (keptBodySlots != null)
                foreach (var s in keptBodySlots)
                    if (s != winnerSlot && !o.Contains(s)) o.Add(s);
            o.Sort();
            return o;
        }

        /// <summary>V3 P2 step 7: a pid is applied bodiless only with the gate
        /// on and no kept body for it on this client.</summary>
        internal static bool Bodiless(bool gate, bool hasKeptBody)
        {
            return gate && !hasKeptBody;
        }

        // ------------------------------------------------------------------ P2: the deterministic stream

        /// <summary>The same-card engine's PRNG (xorshift128, integer only).
        /// FfaCardSequence uses THIS struct, so the shared fold and the offer
        /// record roll from one implementation.</summary>
        internal struct XorShift128
        {
            private uint x, y, z, w;
            public XorShift128(uint seed)
            {
                x = seed == 0 ? 2463534242u : seed;
                y = x * 1812433253u + 1;
                z = y * 1812433253u + 1;
                w = z * 1812433253u + 1;
                // warm up so near-zero seeds decorrelate
                for (int i = 0; i < 8; i++) Next8();
            }
            private uint Next8()
            {
                uint t = x ^ (x << 11);
                x = y; y = z; z = w;
                w = w ^ (w >> 19) ^ (t ^ (t >> 8));
                return w;
            }
            public uint Next() { return Next8(); }
            public int NextInt(int maxExclusive)
            {
                return maxExclusive <= 0 ? 0 : (int)(Next() % (uint)maxExclusive);
            }
        }

        /// <summary>What the record needs to know about one card of the pool,
        /// read once from the prefab: name, integer weight, categories, the
        /// categories it blacklists, allowMultiple, and lockGunToDefault on its
        /// Gun component.</summary>
        internal sealed class CardFacts
        {
            internal string Name;
            internal int Weight;
            internal string[] Categories = new string[0];
            internal string[] Blacklisted = new string[0];
            internal bool AllowMultiple = true;
            internal bool LockGun;
        }

        /// <summary>The snapshot pool in ARRAY order with its weights, as the
        /// shared sequence holds it, plus the no-repeat names.</summary>
        internal sealed class OfferPool
        {
            internal readonly List<CardFacts> Cards = new List<CardFacts>();
            internal readonly HashSet<string> NoRepeat = new HashSet<string>(StringComparer.Ordinal);
            internal readonly Dictionary<string, CardFacts> ByName = new Dictionary<string, CardFacts>(StringComparer.Ordinal);
            internal int Total;

            internal void Add(CardFacts c)
            {
                Cards.Add(c);
                ByName[c.Name] = c;
                Total += c.Weight;
            }

            internal CardFacts Facts(string name)
            {
                CardFacts f;
                return name != null && ByName.TryGetValue(name, out f) ? f : null;
            }

            /// <summary>One weighted draw, exactly as the shared engine draws.</summary>
            internal CardFacts Draw(ref XorShift128 rng)
            {
                int roll = rng.NextInt(Total);
                int pi = 0;
                for (; pi < Cards.Count; pi++)
                {
                    roll -= Cards[pi].Weight;
                    if (roll < 0) break;
                }
                if (pi >= Cards.Count) pi = Cards.Count - 1;
                return Cards[pi];
            }
        }

        /// <summary>The no-repeat state the record spends (V3 P2 step 3). Ledger
        /// is the REPLICATED ledger of the game: every client replaces it with
        /// the ledger of the latest record and clears it at game start. The
        /// record never reads any process's own memory (the live path's
        /// local-only set): per-process memory is never authority.</summary>
        internal sealed class SpendState
        {
            internal readonly List<string> Ledger = new List<string>();

            internal void Reset() { Ledger.Clear(); }
        }

        /// <summary>The shared sequence's state the rule-s build reads: the seed,
        /// the opening-draw count, the set at an index (extending the fold,
        /// never restarting it), and the fold's own no-repeat set.</summary>
        internal sealed class SeqState
        {
            internal uint Seed;
            internal int OpeningDraws;
            internal Func<int, string[]> SetAt;
            internal ICollection<string> UsedNoRepeatFold;
        }

        /// <summary>DeckLegal (V3 P2 step 2): the live LocallyLegal with the body
        /// replaced by the logical deck: no duplicate within the list, no deck
        /// card blacklisting a category of the candidate, no lockGunToDefault
        /// clash between the candidate and a deck card.</summary>
        internal static bool DeckLegal(IList<string> deck, CardFacts cand, IList<string> chosen, OfferPool pool)
        {
            if (cand == null) return false;
            if (chosen != null)
                foreach (var o in chosen) if (o == cand.Name) return false;
            if (deck == null) return true;
            foreach (var hn in deck)
            {
                var have = pool.Facts(hn);
                if (have == null) continue;
                if (cand.LockGun && have.LockGun) return false;
                if (have.Blacklisted != null && cand.Categories != null)
                    foreach (var black in have.Blacklisted)
                    {
                        if (black == null) continue;
                        foreach (var cat in cand.Categories)
                            if (cat != null && cat == black) return false;
                    }
            }
            return true;
        }

        /// <summary>The deck form of FfaMode.IsCardAllowedFor (rule p): DeckLegal
        /// plus the allowMultiple rule against the deck.</summary>
        internal static bool DeckAllowed(IList<string> deck, CardFacts cand, IList<string> chosen, OfferPool pool)
        {
            if (!DeckLegal(deck, cand, chosen, pool)) return false;
            if (deck != null)
                foreach (var hn in deck)
                {
                    var have = pool.Facts(hn);
                    if (have != null && !have.AllowMultiple && have.Name == cand.Name) return false;
                }
            return true;
        }

        // ------------------------------------------------------------------ P2: the offer record

        internal sealed class OfferEntry
        {
            internal int K;
            internal readonly List<string> Names = new List<string>();
        }

        /// <summary>The canonical offer record of one pick cycle (V3 P2 step 2):
        /// room key cr_ffa_off = "{epoch}:{game}:{cycle}:{rule}:{ledger}:{entries}",
        /// rule s (shared sequence) or p (private roll), ledger the game's
        /// no-repeat substitute ledger AFTER this cycle (names, comma-joined),
        /// entries per manifest pid ascending "pid/k/name,name" joined by '|'.</summary>
        internal sealed class FfaOfferRecord
        {
            internal string Epoch = "";
            internal int Game;
            internal int Cycle;
            internal char Rule = 's';
            internal readonly List<string> Ledger = new List<string>();
            internal readonly SortedDictionary<int, OfferEntry> Entries = new SortedDictionary<int, OfferEntry>();

            internal string FirstOf(int pid)
            {
                OfferEntry e;
                return Entries.TryGetValue(pid, out e) && e.Names.Count > 0 ? e.Names[0] : null;
            }

            internal List<string> ListOf(int pid)
            {
                OfferEntry e;
                return Entries.TryGetValue(pid, out e) ? new List<string>(e.Names) : null;
            }
        }

        internal const string OfferProp = "cr_ffa_off";
        internal const string GrantProp = "cr_ffa_ag";

        private static readonly char[] Reserved = { ':', '/', ',', '|' };

        private static bool CleanName(string n)
        {
            return !string.IsNullOrEmpty(n) && n.IndexOfAny(Reserved) < 0;
        }

        private static string I(int v) { return v.ToString(System.Globalization.CultureInfo.InvariantCulture); }

        private static bool TryInt(string s, out int v)
        {
            return int.TryParse(s, System.Globalization.NumberStyles.Integer,
                                System.Globalization.CultureInfo.InvariantCulture, out v);
        }

        /// <summary>The cr_ffa_off value, or null when any name carries a
        /// reserved separator (then no record is written: today's outcome).</summary>
        internal static string Encode(FfaOfferRecord r)
        {
            if (r == null || string.IsNullOrEmpty(r.Epoch) || r.Epoch.IndexOfAny(Reserved) >= 0) return null;
            foreach (var n in r.Ledger) if (!CleanName(n)) return null;
            var parts = new List<string>();
            foreach (var kv in r.Entries)
            {
                foreach (var n in kv.Value.Names) if (!CleanName(n)) return null;
                parts.Add(I(kv.Key) + "/" + I(kv.Value.K) + "/" + string.Join(",", kv.Value.Names));
            }
            return r.Epoch + ":" + I(r.Game) + ":" + I(r.Cycle) + ":" + r.Rule + ":"
                   + string.Join(",", r.Ledger) + ":" + string.Join("|", parts);
        }

        /// <summary>The record a cr_ffa_off value carries, or null when it does
        /// not parse.</summary>
        internal static FfaOfferRecord Parse(string v)
        {
            if (string.IsNullOrEmpty(v)) return null;
            var f = v.Split(':');
            if (f.Length != 6) return null;
            var r = new FfaOfferRecord { Epoch = f[0] };
            if (string.IsNullOrEmpty(r.Epoch) || !TryInt(f[1], out r.Game) || !TryInt(f[2], out r.Cycle)) return null;
            if (f[3] != "s" && f[3] != "p") return null;
            r.Rule = f[3][0];
            if (f[4].Length > 0) r.Ledger.AddRange(f[4].Split(','));
            if (f[5].Length > 0)
                foreach (var e in f[5].Split('|'))
                {
                    var g = e.Split('/');
                    if (g.Length != 3) return null;
                    int pid, k;
                    if (!TryInt(g[0], out pid) || !TryInt(g[1], out k) || pid < 0 || r.Entries.ContainsKey(pid)) return null;
                    var oe = new OfferEntry { K = k };
                    if (g[2].Length > 0) oe.Names.AddRange(g[2].Split(','));
                    r.Entries[pid] = oe;
                }
            return r;
        }

        /// <summary>Rule s (V3 P2 step 2): per manifest pid ascending, the
        /// shared set at idx = k - 1; each name taken on an opening draw, else
        /// taken when DeckLegal holds, else substituted from the per-(pid, idx)
        /// stream under the live substitution rules, the no-repeat test reading
        /// the replicated ledger; a no-repeat substitute joins the ledger as it
        /// is chosen (spent at OFFER, as the live path spends it). A pid with no
        /// consumed index, or whose set is unavailable, gets no entry.</summary>
        internal static FfaOfferRecord BuildRuleS(string epoch, int game, int cycle, IList<int> manifest,
                                                  Func<int, int> kOf, Func<int, IList<string>> deckOf,
                                                  OfferPool pool, SeqState seq, SpendState spend)
        {
            var r = new FfaOfferRecord { Epoch = epoch, Game = game, Cycle = cycle, Rule = 's' };
            // Built on a copy: the caller adopts the record (AdoptRecord) once
            // it is published, so a build that is never written spends nothing,
            // and an audit's recompute never moves this client's state.
            var ledger = new List<string>(spend.Ledger);
            var pids = new List<int>(manifest);
            pids.Sort();
            foreach (var pid in pids)
            {
                if (r.Entries.ContainsKey(pid)) continue;
                int k = kOf(pid);
                if (k <= 0) continue;
                int idx = k - 1;
                string[] names = seq.SetAt(idx);
                if (names == null) continue;
                var deck = deckOf(pid);
                var chosen = new List<string>();
                var subRng = new XorShift128(seq.Seed ^ (uint)(pid * 2654435761u) ^ ((uint)idx * 40503u));
                bool openingDraw = k <= seq.OpeningDraws;
                foreach (var nm in names)
                {
                    var card = pool.Facts(nm);
                    if (card == null) continue;
                    if (!openingDraw && !DeckLegal(deck, card, chosen, pool))
                    {
                        int guard = 0;
                        CardFacts sub = null;
                        while (guard++ < 512)
                        {
                            var cand = pool.Draw(ref subRng);
                            string cn = cand.Name;
                            if (chosen.Contains(cn)) continue;
                            bool namedInSet = false;
                            foreach (var n2 in names) if (n2 == cn) { namedInSet = true; break; }
                            if (namedInSet) continue;
                            if (pool.NoRepeat.Contains(cn)
                                && (seq.UsedNoRepeatFold.Contains(cn) || ledger.Contains(cn))) continue;
                            if (!DeckLegal(deck, cand, chosen, pool)) continue;
                            sub = cand; break;
                        }
                        if (sub != null)
                        {
                            chosen.Add(sub.Name);
                            if (pool.NoRepeat.Contains(sub.Name)) ledger.Add(sub.Name);
                        }
                        continue;
                    }
                    chosen.Add(card.Name);
                }
                var e = new OfferEntry { K = k };
                e.Names.AddRange(chosen);
                r.Entries[pid] = e;
            }
            r.Ledger.AddRange(ledger);
            return r;
        }

        /// <summary>Rule p (V3 P2 step 2, Q2): the master's own private roll per
        /// manifest pid ascending, count names each, rolled by roll() and kept
        /// when DeckAllowed holds (the live screen's 200-roll guard). k is 0.</summary>
        internal static FfaOfferRecord BuildRuleP(string epoch, int game, int cycle, IList<int> manifest,
                                                  Func<int, IList<string>> deckOf, OfferPool pool, int count,
                                                  Func<string> roll, SpendState spend)
        {
            var r = new FfaOfferRecord { Epoch = epoch, Game = game, Cycle = cycle, Rule = 'p' };
            var pids = new List<int>(manifest);
            pids.Sort();
            foreach (var pid in pids)
            {
                if (r.Entries.ContainsKey(pid)) continue;
                var deck = deckOf(pid);
                var e = new OfferEntry { K = 0 };
                int guard = 0;
                while (e.Names.Count < count && guard++ < 200)
                {
                    var c = pool.Facts(roll());
                    if (c == null) break;
                    if (!DeckAllowed(deck, c, e.Names, pool)) continue;
                    e.Names.Add(c.Name);
                }
                r.Entries[pid] = e;
            }
            r.Ledger.AddRange(spend.Ledger);
            return r;
        }

        /// <summary>Called by the apply loop for every applied card. The
        /// no-repeat state is spent at record build, never at apply (V3 P2 step
        /// 3, M2.3): this changes nothing.</summary>
        internal static void NoteApplied(SpendState spend, int pid, string card)
        {
        }

        /// <summary>V3 P2 step 4 and step 3's replacement: a client that reads
        /// the record of the cycle replaces its ledger with the record's and,
        /// under rule s, sets every listed pid's draw index to the record's k.</summary>
        internal static void AdoptRecord(FfaOfferRecord rec, SpendState spend, Action<int, int> setDrawIndex)
        {
            if (rec == null) return;
            spend.Ledger.Clear();
            spend.Ledger.AddRange(rec.Ledger);
            if (rec.Rule == 's' && setDrawIndex != null)
                foreach (var kv in rec.Entries)
                    if (kv.Value.K > 0) setDrawIndex(kv.Key, kv.Value.K);
        }

        /// <summary>V3 P2 step 9: the record a non-master client goes on with
        /// after its audit. The published record, always: the audit is evidence,
        /// never a correction.</summary>
        internal static FfaOfferRecord AfterAudit(FfaOfferRecord published, FfaOfferRecord recomputed)
        {
            return published;
        }

        /// <summary>The audit lines' values: per published pid ascending, whether
        /// the recomputed list is the published list, name for name.</summary>
        internal static List<KeyValuePair<int, bool>> Audit(FfaOfferRecord published, FfaOfferRecord recomputed)
        {
            var o = new List<KeyValuePair<int, bool>>();
            if (published == null) return o;
            foreach (var kv in published.Entries)
            {
                var mine = recomputed == null ? null : recomputed.ListOf(kv.Key);
                bool match = mine != null && mine.SequenceEqual(kv.Value.Names, StringComparer.Ordinal)
                             && recomputed.Entries[kv.Key].K == kv.Value.K;
                o.Add(new KeyValuePair<int, bool>(kv.Key, match));
            }
            return o;
        }

        /// <summary>The screen's confirm at the countdown's end (V3 P2 step 5):
        /// a seat that never moved the highlight confirms entry 0 of its own
        /// record list BY NAME, whether or not entry 0's visual spawned, so idling
        /// always reaches entry 0; a seat that moved confirms what it highlights.</summary>
        internal static string TimeoutPick(IList<string> recordList, IList<string> shownNames, int selected, bool moved)
        {
            if (!moved && recordList != null && recordList.Count > 0) return recordList[0];
            if (shownNames != null && selected >= 0 && selected < shownNames.Count) return shownNames[selected];
            return null;
        }

        /// <summary>What the master needs to decide a grant. HasKeptBody is in
        /// the view because the close has it; the grant must not read it: absence
        /// is "no pick in got", never a body view (V3 P2 step 6, lesson a).</summary>
        internal sealed class GrantView
        {
            internal Func<int, bool> HasKeptBody;
        }

        /// <summary>V3 P2 step 6: at the close the master adds, for each manifest
        /// pid with no entry in got, that pid's entry 0 of the record it holds.
        /// With no record held it grants nothing (today's outcome). Returns the
        /// granted pids, ascending.</summary>
        internal static List<int> GrantMissing(IList<int> manifest, IDictionary<int, string> got,
                                               FfaOfferRecord held, GrantView view)
        {
            var granted = new List<int>();
            if (held == null || manifest == null) return granted;
            var pids = new List<int>(manifest);
            pids.Sort();
            foreach (var pid in pids)
            {
                if (got.ContainsKey(pid)) continue;
                string first = held.FirstOf(pid);
                if (first == null) continue;
                got[pid] = first;
                granted.Add(pid);
            }
            return granted;
        }

        /// <summary>cr_ffa_ag = "{epoch}:{game}:{cycle}:{pid,pid}".</summary>
        internal static string GrantMarker(string epoch, int game, int cycle, IList<int> granted)
        {
            return (epoch ?? "") + ":" + I(game) + ":" + I(cycle) + ":"
                   + string.Join(",", (granted ?? new List<int>()).Select(I));
        }

        internal static bool ParseGrantMarker(string v, out int game, out int cycle, out List<int> pids)
        {
            game = cycle = 0;
            pids = new List<int>();
            if (string.IsNullOrEmpty(v)) return false;
            var f = v.Split(':');
            if (f.Length != 4 || !TryInt(f[1], out game) || !TryInt(f[2], out cycle)) return false;
            if (f[3].Length > 0)
                foreach (var s in f[3].Split(','))
                {
                    int p;
                    if (!TryInt(s, out p)) return false;
                    pids.Add(p);
                }
            return true;
        }
    }
}
