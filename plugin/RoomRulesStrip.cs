using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// Which line the standing room-rules strip paints (v1.41.0 item 22), kept
    /// free of Unity, Photon, BepInEx and I18n so it runs under a plain
    /// compiler: CompetitiveUI.DrawRoomRulesBanner hands it the facts it has
    /// already read (the latched friendly-fire rule, the card engine's latched
    /// same-cards state, the [UI] ShowRoomRulesIndicator key) and paints the
    /// catalogue string of the line that comes back. The same SelfTest runs
    /// under tools/client-rules-harness, so the choice is EXECUTED rather than
    /// asserted about as source text (#391).
    ///
    /// No catalogue string lives here: each line's I18n.Tr call stays in
    /// DrawRoomRulesBanner, where tools/i18n_extract.py reads it, so this file
    /// is deliberately NOT in the extractor's FILES list (#464).
    /// </summary>
    internal static class RoomRulesStrip
    {
        /// <summary>The card engine's latched same-cards state
        /// (FfaCardSequence.StripState), reduced to what the strip says about
        /// it: Off (no rule), On (Pending or Active: the room's configured rule,
        /// which a room lobby shows before the deal latches) and FellBack (the
        /// dealer latched a fallback for this game, so this seat rolls
        /// privately).</summary>
        internal enum SameCards { Off, On, FellBack }

        /// <summary>One value per sentence the strip can say. None paints
        /// nothing.</summary>
        internal enum Line
        {
            None,
            SameCards,                    // Room rule: same cards for everyone
            SameCardsOff,                 // Room rule: same cards is off this game
            FriendlyFireOff,              // Room rules: friendly fire OFF
            FriendlyFireOffSameCards,     // Room rules: friendly fire OFF, same cards for everyone
            FriendlyFireOffSameCardsOff,  // Room rules: friendly fire OFF, same cards is off this game
        }

        /// <summary>The sentence naming every game-changing rule the room
        /// plays: friendly fire when it is OFF (the default is on), and the
        /// same-cards state whenever the room has the rule, fell-back included,
        /// because "same cards is off this game" is the one state in which the
        /// strip has something new to say.</summary>
        internal static Line Choose(bool friendlyFireOff, SameCards sameCards)
        {
            switch (sameCards)
            {
                case SameCards.On:
                    return friendlyFireOff ? Line.FriendlyFireOffSameCards : Line.SameCards;
                case SameCards.FellBack:
                    return friendlyFireOff ? Line.FriendlyFireOffSameCardsOff : Line.SameCardsOff;
                default:
                    return friendlyFireOff ? Line.FriendlyFireOff : Line.None;
            }
        }

        /// <summary>Whether the strip paints: a line to say, and the player has
        /// not turned the strip off ([UI] ShowRoomRulesIndicator, default
        /// true). The game-start toast is not behind this key.</summary>
        internal static bool Paints(bool enabled, Line line)
        {
            return enabled && line != Line.None;
        }

        /// <summary>The amber (downgrade) colour belongs to a line that
        /// reports a fallback, whatever else it names.</summary>
        internal static bool IsFallback(Line line)
        {
            return line == Line.SameCardsOff || line == Line.FriendlyFireOffSameCardsOff;
        }

        // -- self-test (EXECUTED by tools/client-rules-harness) --------------

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        /// <summary>The chooser as it was before item 22: the same-cards state
        /// alone, friendly fire never named. Kept as the NEGATIVE CONTROL for
        /// the friendly-fire cases: the measurement that shows those cases can
        /// fail is that this chooser fails them (#391). Never called by
        /// anything that paints.</summary>
        private static Line ChooseSameCardsOnly(bool friendlyFireOff, SameCards sameCards)
        {
            if (sameCards == SameCards.On) return Line.SameCards;
            if (sameCards == SameCards.FellBack) return Line.SameCardsOff;
            return Line.None;
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            SameCards[] states = { SameCards.Off, SameCards.On, SameCards.FellBack };

            Check(r, "default rules paint nothing",
                  Choose(false, SameCards.Off) == Line.None, Choose(false, SameCards.Off).ToString());
            Check(r, "same cards alone names same cards",
                  Choose(false, SameCards.On) == Line.SameCards, Choose(false, SameCards.On).ToString());
            Check(r, "a fell-back dealer alone says same cards is off",
                  Choose(false, SameCards.FellBack) == Line.SameCardsOff,
                  Choose(false, SameCards.FellBack).ToString());
            Check(r, "friendly fire off alone names friendly fire",
                  Choose(true, SameCards.Off) == Line.FriendlyFireOff, Choose(true, SameCards.Off).ToString());
            Check(r, "friendly fire off with same cards names both",
                  Choose(true, SameCards.On) == Line.FriendlyFireOffSameCards,
                  Choose(true, SameCards.On).ToString());
            Check(r, "friendly fire off with a fell-back dealer names both",
                  Choose(true, SameCards.FellBack) == Line.FriendlyFireOffSameCardsOff,
                  Choose(true, SameCards.FellBack).ToString());

            // Every non-default pair has its own sentence: five pairs, five
            // distinct lines, none of them None.
            var seen = new System.Collections.Generic.HashSet<Line>();
            int pairs = 0;
            foreach (bool ff in new[] { false, true })
                foreach (SameCards sc in states)
                {
                    if (!ff && sc == SameCards.Off) continue;
                    pairs++;
                    seen.Add(Choose(ff, sc));
                }
            Check(r, "every non-default pair has its own line",
                  pairs == 5 && seen.Count == 5 && !seen.Contains(Line.None),
                  "pairs=" + pairs + " distinct=" + seen.Count);

            // Friendly fire is named in every line that has it, and only there.
            bool ffNamed = true;
            foreach (bool ff in new[] { false, true })
                foreach (SameCards sc in states)
                {
                    Line l = Choose(ff, sc);
                    bool names = l == Line.FriendlyFireOff || l == Line.FriendlyFireOffSameCards
                                 || l == Line.FriendlyFireOffSameCardsOff;
                    if (names != ff) ffNamed = false;
                }
            Check(r, "friendly fire is named exactly when it is off", ffNamed, ffNamed.ToString());

            // The cfg key: off hides every line, on paints every line but None.
            bool offHides = true, onPaints = true;
            foreach (bool ff in new[] { false, true })
                foreach (SameCards sc in states)
                {
                    Line l = Choose(ff, sc);
                    if (Paints(false, l)) offHides = false;
                    if (Paints(true, l) != (l != Line.None)) onPaints = false;
                }
            Check(r, "the cfg key off hides every line", offHides, offHides.ToString());
            Check(r, "the cfg key on paints every line but None", onPaints, onPaints.ToString());

            Check(r, "only the fell-back lines are amber",
                  IsFallback(Line.SameCardsOff) && IsFallback(Line.FriendlyFireOffSameCardsOff)
                  && !IsFallback(Line.SameCards) && !IsFallback(Line.FriendlyFireOff)
                  && !IsFallback(Line.FriendlyFireOffSameCards) && !IsFallback(Line.None),
                  "SameCardsOff=" + IsFallback(Line.SameCardsOff)
                  + " FriendlyFireOffSameCardsOff=" + IsFallback(Line.FriendlyFireOffSameCardsOff));

            // Negative control: the pre-item-22 chooser, run through the same
            // friendly-fire case, answers None -- so that case is a real gate.
            Line old = ChooseSameCardsOnly(true, SameCards.Off);
            Check(r, "the same-cards-only chooser says nothing for a friendly-fire-off room (control)",
                  old == Line.None && Choose(true, SameCards.Off) != old,
                  "old=" + old + " new=" + Choose(true, SameCards.Off));

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
