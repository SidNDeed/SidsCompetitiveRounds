using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// The top-centre column's band arithmetic: who gets which y, and how far
    /// down the column has been consumed this frame.
    ///
    /// Deliberately free of Unity, Photon and BepInEx so
    /// tools/client-rules-harness can EXECUTE it under a plain compiler. The
    /// previous shape of this arithmetic lived inline in CompetitiveUI and was
    /// only ever asserted ABOUT by a source-shape test, which is how it kept a
    /// plain maximum for a job that needed a layout (#391, #340, #465). The
    /// frame number arrives as a PARAMETER for the same reason — every caller
    /// passes Time.frameCount, and the harness passes whatever it likes.
    ///
    /// Two guarantees the self-test below proves by running:
    ///   * ORDER — claims are placed in the order they arrive, each under the
    ///     last, so simultaneous surfaces do not overlap. The caller's order is
    ///     DrawUI's call order; there is no priority table to drift from it.
    ///   * MONOTONE — the running bottom never climbs back within a frame. A
    ///     surface that measures itself short cannot pull the ones below it up
    ///     onto the ones above. Closing a band is the only place that was ever
    ///     tempting to write as a plain assignment.
    ///
    /// A new frame resets everything: a surface that stops painting simply
    /// stops claiming, and the column shortens on the next frame rather than
    /// holding space for something that is gone.
    /// </summary>
    internal struct TopStripBand
    {
        /// <summary>Breathing room inserted under every claim that consumed
        /// space. Not applied to a claim of zero height, which consumes
        /// nothing and must leave the column exactly where it found it.</summary>
        internal const float Gap = 2f;

        private int _frame;
        private bool _stamped;
        private float _bottom;
        private float _openAt;
        private bool _open;

        /// <summary>_stamped is separate from _frame because a default(int) of
        /// 0 is a legitimate frame number: without it the first claim of frame
        /// 0 would be treated as a continuation of a frame that never ran.</summary>
        private void Gate(int frame)
        {
            if (_stamped && _frame == frame) return;
            _stamped = true;
            _frame = frame;
            _bottom = 0f;
            _openAt = 0f;
            _open = false;
        }

        /// <summary>Claim a band of <paramref name="height"/> at the bottom of
        /// the column; returns the y to paint at. A height of zero, a negative
        /// height or a NaN claims nothing and still returns the current bottom,
        /// so a caller that cannot measure itself degrades to docking under
        /// whatever is there rather than corrupting the column.</summary>
        internal float Claim(int frame, float height)
        {
            Gate(frame);
            float y = _bottom;
            if (height > 0f) _bottom = y + height + Gap;
            return y;
        }

        /// <summary>Open a band for a claimant that lays ITSELF out downward
        /// and knows its bottom edge only once it has painted. Returns the y to
        /// start at; the claimant must Close with the lowest edge it reached.</summary>
        internal float Open(int frame)
        {
            Gate(frame);
            _open = true;
            _openAt = _bottom;
            return _bottom;
        }

        /// <summary>Close the band Open returned. A bottom at or above the
        /// band's own origin means the claimant painted nothing and the band
        /// consumes nothing. Never lowers the running bottom, so a Claim made
        /// between the Open and the Close survives.</summary>
        internal void Close(int frame, float bottomY)
        {
            if (!_stamped || _frame != frame) return;   // frame ticked: the band is gone
            if (!_open) return;                          // nothing open to close
            float open = _openAt;
            _open = false;
            if (!(bottomY > open)) return;               // painted nothing (NaN-safe)
            float next = bottomY + Gap;
            if (next > _bottom) _bottom = next;
        }

        /// <summary>How far down the column has been consumed this frame; 0 on
        /// any other frame, so a reader can never see a stale total.</summary>
        internal float Bottom(int frame)
        {
            return _stamped && _frame == frame ? _bottom : 0f;
        }

        // ── self-test (EXECUTED by tools/client-rules-harness) ──────────────

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();

            // 1. Two claims stack: the second starts below the first, not on it.
            {
                var b = new TopStripBand();
                float a = b.Claim(1, 34f);
                float c = b.Claim(1, 26f);
                Check(r, "two claims stack", a == 0f && c == 34f + Gap,
                    "first=" + a + " second=" + c);
                Check(r, "stacked bottom", b.Bottom(1) == 34f + Gap + 26f + Gap,
                    "bottom=" + b.Bottom(1));
            }

            // 2. Four simultaneous claimants never overlap. This is the whole
            //    point of the change: spectator, FFA, match, leaver, tournament
            //    and the room-rules strip were all placed at the same y before.
            {
                var b = new TopStripBand();
                float[] h = { 32f, 40f, 62f, 34f, 44f, 22f };
                var y = new float[h.Length];
                for (int i = 0; i < h.Length; i++) y[i] = b.Claim(7, h[i]);
                bool disjoint = true;
                for (int i = 1; i < h.Length; i++)
                    if (y[i] < y[i - 1] + h[i - 1]) disjoint = false;
                Check(r, "six claimants are disjoint", disjoint, Join(y));
                Check(r, "last claimant is last", y[h.Length - 1] > y[0], Join(y));
            }

            // 3. A zero-height claim consumes nothing and reads the bottom.
            {
                var b = new TopStripBand();
                b.Claim(2, 20f);
                float y = b.Claim(2, 0f);
                Check(r, "zero claim consumes nothing",
                    y == 20f + Gap && b.Bottom(2) == 20f + Gap, "y=" + y + " bottom=" + b.Bottom(2));
            }

            // 4. A NaN height cannot poison the column.
            {
                var b = new TopStripBand();
                b.Claim(3, 18f);
                b.Claim(3, float.NaN);
                float after = b.Claim(3, 10f);
                Check(r, "NaN claim consumes nothing",
                    after == 18f + Gap, "after=" + after);
            }

            // 5. An open band that paints nothing consumes nothing — the
            //    casual-match path through DrawMatchStatus reaches Close with a
            //    bottom of 0 on exactly this route.
            {
                var b = new TopStripBand();
                b.Claim(4, 30f);
                float top = b.Open(4);
                b.Close(4, 0f);
                Check(r, "empty open band consumes nothing",
                    top == 30f + Gap && b.Bottom(4) == 30f + Gap,
                    "top=" + top + " bottom=" + b.Bottom(4));
            }

            // 6. An open band that paints advances the column to its edge.
            {
                var b = new TopStripBand();
                float top = b.Open(5);
                b.Close(5, top + 62f);
                float next = b.Claim(5, 22f);
                Check(r, "painted open band advances", next == top + 62f + Gap,
                    "next=" + next);
            }

            // 7. Close NEVER lowers the bottom. A claimant that measures itself
            //    short must not pull later surfaces back onto earlier ones.
            {
                var b = new TopStripBand();
                b.Claim(6, 50f);
                float top = b.Open(6);
                b.Close(6, top - 40f);
                Check(r, "short close does not climb back",
                    b.Bottom(6) == 50f + Gap, "bottom=" + b.Bottom(6));
            }

            // 8. Close with no Open, and a double Close, are both no-ops.
            {
                var b = new TopStripBand();
                b.Claim(8, 12f);
                b.Close(8, 900f);
                float top = b.Open(8);
                b.Close(8, top + 5f);
                b.Close(8, 900f);
                Check(r, "unmatched close is a no-op",
                    b.Bottom(8) == top + 5f + Gap, "bottom=" + b.Bottom(8));
            }

            // 9. A new frame resets the column, and the old total is not
            //    readable from the new frame.
            {
                var b = new TopStripBand();
                b.Claim(9, 40f);
                Check(r, "stale frame reads zero", b.Bottom(10) == 0f,
                    "bottom=" + b.Bottom(10));
                float y = b.Claim(10, 20f);
                Check(r, "new frame restarts at zero", y == 0f, "y=" + y);
            }

            // 10a. A Claim made between an Open and its Close survives the
            //      Close. Writing Close as a plain assignment — the shape that
            //      reads correctly and is wrong — pulls the column back up onto
            //      the surface that claimed in between.
            {
                var b = new TopStripBand();
                float top = b.Open(13);
                b.Claim(13, 60f);
                b.Close(13, top + 10f);
                Check(r, "close does not undo a claim made inside the band",
                    b.Bottom(13) == top + 60f + Gap, "bottom=" + b.Bottom(13));
            }

            // 10b. A band left open when the frame ticks cannot close into the
            //      new frame's column.
            {
                var b = new TopStripBand();
                b.Open(11);
                b.Claim(12, 16f);
                b.Close(12, 500f);
                Check(r, "band does not survive a frame tick",
                    b.Bottom(12) == 16f + Gap, "bottom=" + b.Bottom(12));
            }

            return r;
        }

        private static string Join(float[] v)
        {
            var sb = new StringBuilder();
            for (int i = 0; i < v.Length; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append(v[i]);
            }
            return sb.ToString();
        }

        /// <summary>Every case reports its own MEASUREMENT, not just a verdict:
        /// the gate matches cases on their name and the numbers are what makes
        /// a failure readable without a rerun.</summary>
        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
