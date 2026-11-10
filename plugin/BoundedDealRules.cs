using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>
    /// Ask 16(a) R4, the pure half: the bound on vanilla's card deal, kept free
    /// of Unity, Photon and BepInEx so the harness runs it (suite `dealbound`).
    ///
    /// Vanilla's CardChoice.SpawnUniqueCard draws a card by rarity weight and
    /// rejects it for any of four reasons, checked only once the hand holds a
    /// card (its check loop runs over the cards already spawned, so a hand's
    /// first slot is never checked):
    ///   1. in hand: a card already spawned in this hand has it as its source;
    ///   2. gun lock: the card and the picker's gun both lock the gun to default;
    ///   3. blacklist: a card the picker holds blacklists one of its categories;
    ///   4. held: the picker holds a card of its name that does not allow multiples.
    /// A rejected draw calls SpawnUniqueCard again, with no bound. The picker's
    /// held cards are never cleared while the room lasts (lesson 138), so once no
    /// card the draw can produce passes all four, the deal recurses until the
    /// stack overflows.
    ///
    /// Decide answers, for one slot, whether vanilla's draw can complete it.
    /// Vanilla: at least one drawable card passes all four, and vanilla's draw
    /// runs unchanged, with its odds and its order. Otherwise the answer names
    /// the bounded path's level: the held-card rule is relaxed first, then the
    /// in-hand rule; the blacklist and the gun lock are never relaxed, except at
    /// the last level, which takes any drawable card (what vanilla's own first
    /// slot does; with the shipped cards it is unreachable).
    /// </summary>
    internal static class BoundedDealRules
    {
        internal enum Answer
        {
            /// <summary>Vanilla's draw completes the slot: run it unchanged.</summary>
            Vanilla = 0,
            /// <summary>Rules 1 to 3 hold; the held-card rule is relaxed.</summary>
            RelaxHeld = 1,
            /// <summary>Rules 2 and 3 hold; the held-card and in-hand rules are relaxed.</summary>
            RelaxHeldAndHand = 2,
            /// <summary>Any card the draw can produce.</summary>
            AnyDrawable = 3,
            /// <summary>No card has a weight above 0. Left to vanilla, as today.</summary>
            NothingDrawable = 4,
        }

        /// <summary>One card of the pool, as the four rejections see it for
        /// this slot. Weight is vanilla's rarity weight (Common 10, Uncommon 4,
        /// Rare 1, any other 0); a card of weight 0 is never counted.</summary>
        internal struct Candidate
        {
            internal float Weight;
            internal bool InHand;
            internal bool GunLock;
            internal bool Blacklisted;
            internal bool Held;

            internal Candidate(float weight, bool inHand, bool gunLock, bool blacklisted, bool held)
            {
                Weight = weight;
                InHand = inHand;
                GunLock = gunLock;
                Blacklisted = blacklisted;
                Held = held;
            }
        }

        /// <summary>Whether the level admits the card, its weight aside.</summary>
        internal static bool Admits(Answer level, Candidate c)
        {
            switch (level)
            {
                case Answer.Vanilla: return !c.InHand && !c.GunLock && !c.Blacklisted && !c.Held;
                case Answer.RelaxHeld: return !c.InHand && !c.GunLock && !c.Blacklisted;
                case Answer.RelaxHeldAndHand: return !c.GunLock && !c.Blacklisted;
                case Answer.AnyDrawable: return true;
                default: return false;
            }
        }

        /// <summary>The slot's answer. handCount is the number of cards already
        /// spawned in this hand: at 0, vanilla checks nothing and completes the
        /// slot by itself.</summary>
        internal static Answer Decide(int handCount, IList<Candidate> pool)
        {
            if (handCount <= 0) return Answer.Vanilla;
            if (pool == null) return Answer.NothingDrawable;
            for (var level = Answer.Vanilla; level <= Answer.AnyDrawable; level++)
                for (int i = 0; i < pool.Count; i++)
                    if (pool[i].Weight > 0f && Admits(level, pool[i])) return level;
            return Answer.NothingDrawable;
        }

        /// <summary>The bounded path's draw: vanilla's weighted pick, over the
        /// cards the level admits. roll01 is a uniform number in [0, 1]. Answers
        /// the pool index, or -1 when the level admits no drawable card.</summary>
        internal static int Pick(Answer level, IList<Candidate> pool, float roll01)
        {
            if (pool == null || level == Answer.Vanilla || level == Answer.NothingDrawable) return -1;
            float total = 0f;
            int last = -1;
            for (int i = 0; i < pool.Count; i++)
                if (pool[i].Weight > 0f && Admits(level, pool[i])) { total += pool[i].Weight; last = i; }
            if (last < 0) return -1;
            if (!(roll01 >= 0f)) roll01 = 0f;
            if (roll01 > 1f) roll01 = 1f;
            float left = roll01 * total;
            for (int i = 0; i < pool.Count; i++)
            {
                if (!(pool[i].Weight > 0f) || !Admits(level, pool[i])) continue;
                left -= pool[i].Weight;
                if (left <= 0f) return i;
            }
            return last;
        }
    }
}
