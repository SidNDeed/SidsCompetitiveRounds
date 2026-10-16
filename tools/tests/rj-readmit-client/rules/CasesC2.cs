// C2: RJ readmission P2 (V3:55-100), the offer record and the absent-seat
// automatic pick, run against the REAL plugin/FfaReadmitRules.cs.
using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds
{
    using R = FfaReadmitRules;

    internal static class CasesC2
    {
        private static R.CardFacts F(string n, int w, string[] cats, string[] black = null, bool lockGun = false, bool allowMulti = true)
        {
            return new R.CardFacts { Name = n, Weight = w, Categories = cats, Blacklisted = black ?? new string[0], LockGun = lockGun, AllowMultiple = allowMulti };
        }

        /// <summary>A general pool: ten cards, mixed weights, one no-repeat
        /// card, a blacklister (BL, weight 0 so never drawn) and two lockGun cards.</summary>
        private static R.OfferPool GeneralPool()
        {
            var p = new R.OfferPool();
            p.Add(F("P1", 10, new[] { "cA" }));
            p.Add(F("P2", 10, new[] { "cB" }));
            p.Add(F("P3", 4, new[] { "cX" }));
            p.Add(F("P4", 10, new[] { "cC" }));
            p.Add(F("P5", 1, new[] { "cD" }));
            p.Add(F("P6", 10, new[] { "cE" }));
            p.Add(F("P7", 4, new[] { "cX", null }));
            p.Add(F("P8", 10, new[] { "cF" }));
            p.Add(F("NR1", 4, new[] { "cG" }));
            p.Add(F("NR2", 4, new[] { "cH" }));
            p.Add(F("BL", 0, new[] { "cZ" }, new[] { "cX" }));
            p.Add(F("G1", 0, new[] { "cY" }, null, true, false));
            p.NoRepeat.Add("NR1");
            p.NoRepeat.Add("NR2");
            return p;
        }

        private static readonly string[][] GeneralSets =
        {
            new[] { "P1", "P2", "P3", "P4", "P5" },
            new[] { "P3", "P6", "P7", "P1", "P8" },
            new[] { "P7", "P2", "P4", "P3", "P6" },
            new[] { "P8", "P3", "P1", "P2", "P7" },
        };

        private static R.SeqState Seq(string[][] sets, uint seed = 12345u, int opening = 1)
        {
            return new R.SeqState
            {
                Seed = seed,
                OpeningDraws = opening,
                SetAt = i => i >= 0 && i < sets.Length ? sets[i] : null,
                UsedNoRepeatFold = new HashSet<string>(),
            };
        }

        private static Func<int, IList<string>> Decks(Dictionary<int, List<string>> d)
        {
            return pid => d.TryGetValue(pid, out var l) ? l : new List<string>();
        }

        private static R.GrantView View(Func<int, bool> hasBody) { return new R.GrantView { HasKeptBody = hasBody }; }

        private static R.FfaOfferRecord GeneralRecord(R.SpendState spend)
        {
            var decks = new Dictionary<int, List<string>> { { 1, new List<string> { "BL" } }, { 3, new List<string> { "P6" } } };
            return R.BuildRuleS("e1", 2, 3, new List<int> { 0, 1, 2, 3 }, pid => 2, Decks(decks), GeneralPool(),
                                Seq(GeneralSets), spend);
        }

        /// <summary>The twin of V3 T2.1 for one record: for every listed pid,
        /// the card an idling present seat confirms (entry 0's visual failed)
        /// equals the card the close grants when the seat is absent.</summary>
        private static void Twin(R.FfaOfferRecord rec, IList<int> manifest, string label)
        {
            int checkedN = 0;
            foreach (var pid in manifest)
            {
                var list = rec.ListOf(pid);
                if (list == null || list.Count == 0) continue;
                var shownWithoutEntry0 = list.Skip(1).ToList();
                string idle = R.TimeoutPick(list, shownWithoutEntry0, 0, false);
                var got = manifest.Where(p => p != pid).ToDictionary(p => p, p => "picked" + p);
                var granted = R.GrantMissing(manifest, got, rec, View(p => p != pid));
                Check.Seq(new[] { pid }, granted, label + ": only the absent pid is granted");
                Check.Eq(idle, got[pid], label + ": idling and absence reach one card for pid " + pid);
                Check.Eq(list[0], got[pid], label + ": the grant is entry 0");
                checkedN++;
            }
            Check.True(checkedN >= 2, label + ": the twin ran on at least two lists");
        }

        internal static void Register()
        {
            // ---- T2.1 twin run (the integrator acceptance, A15)
            RulesProgram.Add("C2.T2.1.twin_rule_s_ledger", () =>
            {
                var spend = new R.SpendState();
                spend.Ledger.Add("NR2");
                var rec = GeneralRecord(spend);
                Check.True(!rec.ListOf(1).SequenceEqual(GeneralSets[1]), "pid 1's blacklist forced a substitution (the fixture exercises it)");
                Check.True(rec.Ledger.Contains("NR2"), "the record carries the ledger it was built on");
                Twin(rec, new List<int> { 0, 1, 2, 3 }, "rule s");
            });
            RulesProgram.Add("C2.T2.1.twin_rule_p", () =>
            {
                var rolls = new Queue<string>(new[] { "P1", "P1", "P2", "G1", "P4", "P5", "P6", "P2", "P8", "P1", "P3", "P4",
                                                      "P5", "P6", "P7", "P8", "P1", "P2", "P3", "P4" });
                var decks = new Dictionary<int, List<string>> { { 2, new List<string> { "G1" } } };
                var rec = R.BuildRuleP("e2", 1, 4, new List<int> { 0, 2, 3 }, Decks(decks), GeneralPool(), 3,
                                       () => rolls.Count > 0 ? rolls.Dequeue() : null, new R.SpendState());
                Check.Eq('p', rec.Rule, "rule p");
                Check.True(rec.Entries.Values.All(e => e.K == 0), "rule p carries k = 0");
                Check.True(!rec.ListOf(2).Contains("G1"), "allowMultiple false: a deck card is not re-offered");
                Twin(rec, new List<int> { 0, 2, 3 }, "rule p");
            });
            RulesProgram.Add("C2.T2.1.twin_after_promotion", () =>
            {
                var rec = GeneralRecord(new R.SpendState());
                string published = R.Encode(rec);
                Check.True(published != null, "the record encodes");
                var adopted = R.Parse(published);
                Check.True(adopted != null, "a promoted master reads the published record");
                var manifest = new List<int> { 0, 1, 2, 3 };
                foreach (var pid in manifest)
                {
                    var gotA = manifest.Where(p => p != pid).ToDictionary(p => p, p => "x");
                    var gotB = manifest.Where(p => p != pid).ToDictionary(p => p, p => "x");
                    R.GrantMissing(manifest, gotA, rec, View(p => true));
                    R.GrantMissing(manifest, gotB, adopted, View(p => true));
                    Check.Eq(gotA[pid], gotB[pid], "the promoted master grants what the first master would, pid " + pid);
                }
                Twin(adopted, manifest, "promoted");
            });

            // ---- T2.2 the ledger (A16)
            RulesProgram.Add("C2.T2.2.ledger_substitute_never_reoffered", () =>
            {
                var p = new R.OfferPool();
                foreach (var s in new[] { "S1", "S2", "S3", "S4", "S5" }) p.Add(F(s, 10, new[] { "c1" }));
                p.Add(F("X", 4, new[] { "c2" }));
                p.Add(F("Q", 10, new[] { "c6" }));
                p.Add(F("BL", 0, new[] { "c3" }, new[] { "c1" }));
                p.NoRepeat.Add("X");
                var sets = new[]
                {
                    new[] { "S1", "S2", "S3", "S4", "S5" }, new[] { "S2", "S1", "S3", "S5", "S4" },
                    new[] { "S3", "S4", "S5", "S1", "S2" }, new[] { "S5", "S4", "S3", "S2", "S1" },
                };
                var decks = Decks(new Dictionary<int, List<string>> { { 0, new List<string> { "BL" } }, { 1, new List<string> { "BL" } } });
                // cycle 2: master M1 builds seat A's (pid 0) list at k = 2
                var m1 = new R.SpendState();
                var rec2 = R.BuildRuleS("e", 1, 2, new List<int> { 0 }, pid => 2, decks, p, Seq(sets), m1);
                Check.True(rec2.ListOf(0).Contains("X"), "seat A is offered the no-repeat substitute X in cycle 2");
                Check.True(rec2.ListOf(0).Contains("Q"), "seat A is offered another card too");
                // every client adopts the published record; A picks Q, not X
                var m2 = new R.SpendState();
                R.AdoptRecord(R.Parse(R.Encode(rec2)), m2, null);
                R.NoteApplied(m2, 0, "Q");
                // cycle 4: a PROMOTED master M2 builds seat B's (pid 1) list at k = 4
                var rec4 = R.BuildRuleS("e", 1, 4, new List<int> { 1 }, pid => 4, decks, p, Seq(sets), m2);
                Check.True(!rec4.ListOf(1).Contains("X"), "X is never offered to seat B later in the game");
                Check.True(rec4.Ledger.Contains("X"), "the ledger carries X forward");
            });

            // ---- T2.3 opening draws take the raw entry
            RulesProgram.Add("C2.T2.3.opening_draw_raw_entry", () =>
            {
                var decks = Decks(new Dictionary<int, List<string>> { { 0, new List<string> { "BL" } } });
                var rec = R.BuildRuleS("e", 1, 1, new List<int> { 0 }, pid => 1, decks, GeneralPool(), Seq(GeneralSets), new R.SpendState());
                Check.Seq(GeneralSets[0], rec.ListOf(0), "an opening draw is the raw set even when deck-illegal (P3 blacklisted)");
                var rec2 = R.BuildRuleS("e", 1, 2, new List<int> { 0 }, pid => 2, decks, GeneralPool(), Seq(GeneralSets), new R.SpendState());
                Check.True(!rec2.ListOf(0).Contains("P3") && !rec2.ListOf(0).Contains("P7"), "a later draw substitutes the illegal entries");
            });

            // ---- T2.4 the walk: seat C leaves before its pick, after its pick, after the close
            RulesProgram.Add("C2.T2.4.walk_seat_leaves", () =>
            {
                var rec = GeneralRecord(new R.SpendState());
                var manifest = new List<int> { 0, 1, 2, 3 };
                const int C = 2;
                string cPick = rec.ListOf(C)[Math.Min(2, rec.ListOf(C).Count - 1)];
                var legs = new[]
                {
                    // (label, C's pick in got at the close, C kept on the master at the close, expected deck card)
                    Tuple.Create("before its pick", false, false, rec.ListOf(C)[0]),
                    Tuple.Create("after its pick published", true, false, cPick),
                    Tuple.Create("after the close", true, true, cPick),
                };
                foreach (var leg in legs)
                {
                    var got = new Dictionary<int, string> { { 0, "P1" }, { 1, "P2" }, { 3, "P4" } };
                    if (leg.Item2) got[C] = cPick;
                    bool cKept = leg.Item3;
                    R.GrantMissing(manifest, got, rec, View(p => p != C || cKept));
                    // three clients apply the one published result
                    var decksPerClient = new List<Dictionary<int, List<string>>>();
                    for (int client = 0; client < 3; client++)
                    {
                        var d = new Dictionary<int, List<string>>();
                        foreach (var kv in got.OrderBy(k => k.Key)) d[kv.Key] = new List<string> { kv.Value };
                        decksPerClient.Add(d);
                    }
                    foreach (var d in decksPerClient)
                        Check.Seq(new[] { leg.Item4 }, d[C], "decks[C] " + leg.Item1);
                }
            });

            // ---- T2.5 the missed arm: a present seat whose pick lost the close race
            RulesProgram.Add("C2.T2.5.present_missed_gets_entry0", () =>
            {
                var rec = GeneralRecord(new R.SpendState());
                var manifest = new List<int> { 0, 1, 2, 3 };
                var got = new Dictionary<int, string> { { 0, "P1" }, { 1, "P2" }, { 2, "P4" } };
                var granted = R.GrantMissing(manifest, got, rec, View(p => true));
                Check.Seq(new[] { 3 }, granted, "the present seat D is granted");
                Check.Eq(rec.ListOf(3)[0], got[3], "D receives entry 0 of its own list");
            });
            RulesProgram.Add("C2.no_record_no_grant", () =>
            {
                var got = new Dictionary<int, string> { { 0, "P1" } };
                var granted = R.GrantMissing(new List<int> { 0, 1 }, got, null, View(p => false));
                Check.True(granted.Count == 0 && !got.ContainsKey(1), "no record held: no grant, today's outcome");
            });

            // ---- T2.6 the gate latch (A17)
            RulesProgram.Add("C2.T2.6.gate_pinned_at_lock", () =>
            {
                bool presentAll = false;   // a member without the token is present
                var pin = R.PinFromLock(null, "L1", "room1", 0);
                var view = new R.GateView { Pin = pin, Room = "room1", PresentAllAdvertise = () => presentAll };
                Check.True(!R.GateOn(view), "a mixed lobby locks with the flag false");
                presentAll = true;          // the only incompatible seat drops
                Check.True(!R.GateOn(view), "a later drop cannot turn the gate on");
                pin = R.PinFromLock(pin, "L1", "room1", 1);
                view.Pin = pin;
                Check.True(!R.GateOn(view), "a later payload of the same lobby never re-derives the pin");
                var pickers = R.PickerSet(R.GateOn(view), 4, new List<int> { 0, 1, 3 }, -1);
                Check.Seq(new[] { 0, 1, 3 }, pickers, "absent seats stay out of the manifest");
                Check.True(!R.Bodiless(R.GateOn(view), false), "no bodiless apply with the gate off");
            });
            RulesProgram.Add("C2.T2.6.gate_on_readmission_lobby", () =>
            {
                var pin = R.PinFromLock(null, "L2", "room2", 1);
                var view = new R.GateView { Pin = pin, Room = "room2", PresentAllAdvertise = () => false };
                Check.True(R.GateOn(view), "a readmission lobby's room runs the rules");
                view.Room = "other";
                Check.True(!R.GateOn(view), "another room does not");
                var reform = R.PinFromLock(pin, "L2", "room2b", 0);
                Check.True(reform.Flag && reform.Room == "room2b", "a re-form keeps the flag and moves the room");
                Check.Seq(new[] { 0, 1, 3 }, R.PickerSet(true, 4, new List<int> { 0, 1 }, 2),
                          "every roster slot but the winner's, with or without a body");
                Check.True(R.Bodiless(true, false) && !R.Bodiless(true, true), "bodiless exactly when no kept body");
            });

            // ---- T2.7 master mutation: honest clients log the mismatch and apply the published record
            RulesProgram.Add("C2.T2.7.master_mutation_audited", () =>
            {
                var honestSpend = new R.SpendState();
                var deterministic = GeneralRecord(honestSpend);
                var forged = R.Parse(R.Encode(deterministic));
                forged.Entries[1].Names.Reverse();
                forged.Ledger.Add("NR1");
                var published = R.Parse(R.Encode(forged));
                var masterSpend = new R.SpendState();
                R.AdoptRecord(published, masterSpend, null);
                for (int client = 0; client < 2; client++)
                {
                    var spend = new R.SpendState();
                    var mine = GeneralRecord(spend);
                    var audit = R.Audit(published, mine);
                    Check.True(audit.Any(a => a.Key == 1 && !a.Value), "an honest client logs match=0 for the forged list");
                    Check.True(audit.Any(a => a.Key == 0 && a.Value), "and match=1 for an untouched list");
                    var draws = new Dictionary<int, int>();
                    R.AdoptRecord(R.AfterAudit(published, mine), spend, (pid, k) => draws[pid] = k);
                    Check.Seq(masterSpend.Ledger, spend.Ledger, "every client holds the master's published ledger");
                    Check.True(draws.Count == 4 && draws.Values.All(k => k == 2), "every client sets the published draw indices");
                }
            });

            // ---- codecs and legality
            RulesProgram.Add("C2.codec_roundtrip", () =>
            {
                var rec = GeneralRecord(new R.SpendState());
                rec.Ledger.Add("NR1");
                string v = R.Encode(rec);
                var back = R.Parse(v);
                Check.Eq(v, R.Encode(back), "encode(parse(v)) == v");
                Check.True(back.Game == 2 && back.Cycle == 3 && back.Rule == 's' && back.Epoch == "e1", "header fields");
                var bad = R.Parse(v);
                bad.Entries[0].Names.Add("A:B");
                Check.True(R.Encode(bad) == null, "a reserved separator in a name: no record");
                Check.True(R.Parse("garbage") == null && R.Parse("e:1:2:q::") == null && R.Parse("e:x:2:s::") == null, "bad values do not parse");
                string g = R.GrantMarker("ep", 3, 5, new List<int> { 1, 4 });
                Check.True(R.ParseGrantMarker(g, out int gg, out int gc, out List<int> gp) && gg == 3 && gc == 5 && gp.SequenceEqual(new[] { 1, 4 }), "grant marker roundtrip");
                Check.True(R.ParseGrantMarker(R.GrantMarker("ep", 3, 5, new List<int>()), out gg, out gc, out gp) && gp.Count == 0, "empty grant marker");
            });
            RulesProgram.Add("C2.deck_legal", () =>
            {
                var p = GeneralPool();
                Check.True(!R.DeckLegal(new List<string> { "BL" }, p.Facts("P3"), new List<string>(), p), "blacklist against the deck");
                Check.True(!R.DeckLegal(new List<string> { "BL" }, p.Facts("P7"), new List<string>(), p), "blacklist with a null category beside");
                Check.True(R.DeckLegal(new List<string> { "BL" }, p.Facts("P1"), new List<string>(), p), "an unrelated card is legal");
                Check.True(!R.DeckLegal(new List<string>(), p.Facts("P1"), new List<string> { "P1" }, p), "no duplicate within the list");
                var lg = F("G2", 1, new[] { "cW" }, null, true);
                p.Add(lg);
                Check.True(!R.DeckLegal(new List<string> { "G1" }, lg, new List<string>(), p), "the lockGun clash");
                Check.True(!R.DeckAllowed(new List<string> { "G1" }, p.Facts("G1"), new List<string>(), p), "allowMultiple false (rule p)");
                Check.True(R.TimeoutPick(new[] { "A", "B" }, new[] { "B" }, 0, true) == "B", "a moved highlight confirms what it shows");
            });
        }
    }
}
