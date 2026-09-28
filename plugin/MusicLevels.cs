using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// The custom-music level math (v1.41.0 item 23), kept free of Unity,
    /// Photon, BepInEx and I18n so it runs under a plain compiler:
    /// MusicEngine.TickDuckAndVolume hands it the slider percent and the fade
    /// progress and applies what comes back. The same SelfTest runs under
    /// tools/client-rules-harness, so the curves are EXECUTED rather than
    /// asserted about as source text (#391).
    ///
    /// Ceiling. The mod's slider feeds a squared (perceptual) law, and its 100
    /// now maps to VOLUME_CEILING of the amplitude that 100 produced before
    /// 1.41 (Sid's ruling of 2026-09-28: at most half). The factor is applied
    /// on the source, before the game's own music slider, which keeps working
    /// on the mixer group downstream; every stored slider value is scaled by
    /// the same factor, so no player's cfg has to be rewritten for it.
    ///
    /// Fade-in. Every track start and resume keeps the 0.6 s linear envelope
    /// it always had. The first start after a silent main menu (the menu to
    /// game transition) takes LONG_FADE_SECONDS on the squared curve, the same
    /// law the slider uses, so the first note is not at full volume.
    /// </summary>
    internal static class MusicLevels
    {
        /// <summary>The amplitude the slider's 100 maps to, as a fraction of
        /// what 100 produced before 1.41. At most 0.5 by ruling.</summary>
        internal const float VOLUME_CEILING = 0.5f;

        /// <summary>The envelope every track start and resume has always had.</summary>
        internal const float SHORT_FADE_SECONDS = 0.6f;

        /// <summary>The first start after a silent main menu.</summary>
        internal const float LONG_FADE_SECONDS = 2.5f;

        /// <summary>One frame never counts for more than this, so a hitch
        /// (a scene load, a decode) cannot jump the envelope to full gain.</summary>
        internal const float MAX_FRAME_SECONDS = 0.1f;

        /// <summary>Source gain for a slider percent: the squared law times the
        /// ceiling. Values outside 0..100 clamp.</summary>
        internal static float SliderGain(int percent)
        {
            if (percent <= 0) return 0f;
            float f = percent >= 100 ? 1f : percent / 100f;
            return f * f * VOLUME_CEILING;
        }

        /// <summary>Envelope progress after one audible frame of dt seconds.
        /// A non-positive (or NaN) dt does not advance it.</summary>
        internal static float AdvanceFade(float progress, float dt, bool longFade)
        {
            if (!(dt > 0f)) return progress;
            float counted = dt < MAX_FRAME_SECONDS ? dt : MAX_FRAME_SECONDS;
            float p = progress + counted / (longFade ? LONG_FADE_SECONDS : SHORT_FADE_SECONDS);
            return p >= 1f ? 1f : p;
        }

        /// <summary>Gain multiplier for an envelope progress: linear for the
        /// short envelope (unchanged since v4 2.5), squared for the long one.</summary>
        internal static float FadeGain(float progress, bool longFade)
        {
            float p = progress <= 0f ? 0f : progress >= 1f ? 1f : progress;
            return longFade ? p * p : p;
        }

        // -- self-test (EXECUTED by tools/client-rules-harness) --------------

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        /// <summary>The slider law before 1.41: the squared curve with no
        /// ceiling. NEGATIVE CONTROL for the ceiling cases (#391); never called
        /// by anything that plays.</summary>
        private static float SliderGainBefore(int percent)
        {
            if (percent <= 0) return 0f;
            float f = percent >= 100 ? 1f : percent / 100f;
            return f * f;
        }

        private static string F(float v)
        {
            return v.ToString("0.#####", CultureInfo.InvariantCulture);
        }

        /// <summary>Drives an envelope from arming at a fixed frame time and
        /// returns the audible seconds at which the gain first reached 1, and
        /// the largest gain seen strictly before the envelope's nominal length
        /// (minus one frame of slack for float rounding).</summary>
        private static void Drive(bool longFade, float frame, out float reachedAt, out float maxBefore,
                                  out float firstGain)
        {
            float nominal = longFade ? LONG_FADE_SECONDS : SHORT_FADE_SECONDS;
            float p = 0f, t = 0f;
            firstGain = FadeGain(p, longFade);
            maxBefore = firstGain;
            reachedAt = -1f;
            for (int i = 0; i < 100000 && reachedAt < 0f; i++)
            {
                p = AdvanceFade(p, frame, longFade);
                t += frame;
                float g = FadeGain(p, longFade);
                if (t < nominal - frame && g > maxBefore) maxBefore = g;
                if (g >= 1f) reachedAt = t;
            }
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();

            // Ceiling.
            Check(r, "the slider's 100 maps to at most half of the old output",
                  SliderGain(100) <= 0.5f * SliderGainBefore(100) + 1e-6f && SliderGain(100) > 0f,
                  "new100=" + F(SliderGain(100)) + " old100=" + F(SliderGainBefore(100)));
            bool fixedFactor = true;
            string worst = "";
            for (int pct = 0; pct <= 100; pct++)
            {
                float want = VOLUME_CEILING * SliderGainBefore(pct);
                if (System.Math.Abs(SliderGain(pct) - want) > 1e-6f)
                {
                    fixedFactor = false;
                    worst = "pct=" + pct + " new=" + F(SliderGain(pct)) + " want=" + F(want);
                    break;
                }
            }
            Check(r, "every stored percent is scaled by the same factor", fixedFactor,
                  fixedFactor ? "factor=" + F(VOLUME_CEILING) + " over 0..100" : worst);
            bool mono = true;
            for (int pct = 1; pct <= 100; pct++)
                if (SliderGain(pct) < SliderGain(pct - 1)) mono = false;
            Check(r, "the slider never gets quieter as it rises", mono, mono.ToString());
            Check(r, "the slider clamps outside 0..100",
                  SliderGain(-5) == 0f && SliderGain(0) == 0f && SliderGain(250) == SliderGain(100),
                  "g(-5)=" + F(SliderGain(-5)) + " g(0)=" + F(SliderGain(0)) + " g(250)=" + F(SliderGain(250)));
            Check(r, "the pre-1.41 slider is louder than half at 100 (control)",
                  SliderGainBefore(100) > 0.5f,
                  "old100=" + F(SliderGainBefore(100)));

            // Envelopes, driven at 60 fps and at this seat's ~10 fps.
            foreach (float frame in new[] { 1f / 60f, 0.1f })
            {
                string fps = frame < 0.05f ? "60fps" : "10fps";
                Drive(false, frame, out float sAt, out float sMax, out float sFirst);
                Drive(true, frame, out float lAt, out float lMax, out float lFirst);
                Check(r, "the short fade starts at zero gain (" + fps + ")", sFirst == 0f, F(sFirst));
                Check(r, "the short fade reaches full gain at 0.6 s, not before (" + fps + ")",
                      sAt >= SHORT_FADE_SECONDS - frame && sAt <= SHORT_FADE_SECONDS + frame && sMax < 1f,
                      "reached=" + F(sAt) + "s maxBefore=" + F(sMax));
                Check(r, "the long fade starts at zero gain (" + fps + ")", lFirst == 0f, F(lFirst));
                Check(r, "the long fade reaches full gain at 2.5 s, not before (" + fps + ")",
                      lAt >= LONG_FADE_SECONDS - frame && lAt <= LONG_FADE_SECONDS + frame && lMax < 1f,
                      "reached=" + F(lAt) + "s maxBefore=" + F(lMax));
            }

            // The long curve is the squared law: a quarter of full gain at half
            // time, below the linear envelope's half.
            float mid = FadeGain(0.5f, true);
            Check(r, "the long fade is perceptual: a quarter gain at half time",
                  System.Math.Abs(mid - 0.25f) < 1e-6f && mid < FadeGain(0.5f, false),
                  "long(0.5)=" + F(mid) + " short(0.5)=" + F(FadeGain(0.5f, false)));
            // At the moment the short envelope is done, the long one is still quiet.
            float p06 = 0f;
            for (int i = 0; i < 36; i++) p06 = AdvanceFade(p06, 1f / 60f, true);
            Check(r, "at 0.6 s the long fade is still under a tenth of full gain",
                  FadeGain(p06, true) < 0.1f,
                  "long(0.6s)=" + F(FadeGain(p06, true)));
            Check(r, "a one-second hitch counts as a tenth of a second",
                  System.Math.Abs(AdvanceFade(0f, 1f, true) - MAX_FRAME_SECONDS / LONG_FADE_SECONDS) < 1e-6f,
                  "p=" + F(AdvanceFade(0f, 1f, true)));
            Check(r, "a zero or negative frame does not advance the fade",
                  AdvanceFade(0.3f, 0f, true) == 0.3f && AdvanceFade(0.3f, -1f, false) == 0.3f
                  && AdvanceFade(0.3f, float.NaN, true) == 0.3f,
                  "p(0)=" + F(AdvanceFade(0.3f, 0f, true)) + " p(-1)=" + F(AdvanceFade(0.3f, -1f, false)));
            // Negative control: the short envelope, used for the first track,
            // reaches full gain long before 2.5 s -- so the long-fade case can fail.
            Drive(false, 1f / 60f, out float ctlAt, out _, out _);
            Check(r, "the short envelope reaches full gain well before 2.5 s (control)",
                  ctlAt > 0f && ctlAt < LONG_FADE_SECONDS - 1f,
                  "reached=" + F(ctlAt) + "s");

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
