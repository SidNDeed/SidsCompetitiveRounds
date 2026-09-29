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
    /// 1.41 (Sid's ruling of 2026-09-28: at most half, lower still if the
    /// loudness measurement says so). The factor is applied on the source,
    /// before the game's own music slider, which keeps working on the mixer
    /// group downstream; every stored slider value is scaled by the same
    /// factor.
    ///
    /// The measurement (2026-09-28, the broadcast seat, listener output
    /// through the game's music mixer group): the game's own soundtrack plays
    /// at source gain 0.01 (its sound container's -40 dB), and the mod's
    /// source at 0.0098 on the same clip measured within 0.1 dB of it, so the
    /// two share one chain and only the source gain differs. The custom
    /// albums' integrated loudness averages within 0.2 LU of the game's
    /// in-round clips. Before 1.41 the slider's 100 was source gain 1.0, about
    /// 40 dB over the soundtrack at the source, and already at half of that
    /// the output peaked above full scale. VOLUME_CEILING = 0.02 puts 100 at
    /// about 6 dB over the soundtrack and DEFAULT_PERCENT at its level.
    ///
    /// Migration. 100 was the default before 1.41, so a stored 100 is read as
    /// never chosen, once: MigratedPercent turns it into DEFAULT_PERCENT
    /// unless the one-time flag is already set, and returns every other value
    /// unchanged (Plugin binds the flag and applies it).
    ///
    /// Fade-in. Every track start and resume keeps the 0.6 s linear envelope
    /// it always had. The first start after a silent main menu (the menu to
    /// game transition) takes LONG_FADE_SECONDS on the squared curve, the same
    /// law the slider uses, so the first note is not at full volume.
    ///
    /// Per-clip level (round 2). The custom clips differ among themselves by
    /// 3.13 dB RMS (the full tracks; 4.22 dB with the previews), over the 3 dB
    /// bar, so every clip the album catalog names carries its own linear gain
    /// to ONE target, TRACK_TARGET_RMS_DBFS, in TrackLevels; the engine
    /// multiplies it into the slider law and never replaces the law with it.
    /// The target is the whole-clip RMS of the game's own round clip the
    /// slider was calibrated against (CALIBRATION_CLIP_RMS_DBFS), so at the
    /// default percent a custom clip plays where that clip plays: the
    /// soundtrack's level. Measured once per clip by one method: the whole
    /// clip decoded at its native rate and channel count, RMS over every
    /// sample of every channel pooled (no window, no weighting), peak the
    /// largest absolute sample, both in dBFS.
    /// </summary>
    internal static class MusicLevels
    {
        /// <summary>The amplitude the slider's 100 maps to, as a fraction of
        /// what 100 produced before 1.41. At most 0.5 by ruling; 0.02 by the
        /// measurement in the summary above.</summary>
        internal const float VOLUME_CEILING = 0.02f;

        /// <summary>The percent a fresh install starts at, and the one a
        /// stored LEGACY_DEFAULT_PERCENT moves to once: the level of the
        /// game's own soundtrack under VOLUME_CEILING.</summary>
        internal const int DEFAULT_PERCENT = 70;

        /// <summary>The slider's default before 1.41.</summary>
        internal const int LEGACY_DEFAULT_PERCENT = 100;

        /// <summary>The source gain the game's own soundtrack plays at (its
        /// sound container's -40 dB), measured on the broadcast seat; the
        /// reference the self-test holds the default and the top against.</summary>
        internal const float SOUNDTRACK_SOURCE_GAIN = 0.01f;

        /// <summary>The envelope every track start and resume has always had.</summary>
        internal const float SHORT_FADE_SECONDS = 0.6f;

        /// <summary>The first start after a silent main menu.</summary>
        internal const float LONG_FADE_SECONDS = 2.5f;

        /// <summary>One frame never counts for more than this, so a hitch
        /// (a scene load, a decode) cannot jump the envelope to full gain.</summary>
        internal const float MAX_FRAME_SECONDS = 0.1f;

        // -- per-clip level (round 2) -----------------------------------------

        /// <summary>The whole-clip RMS of MUS_Level_Limits_Of_The_Possible_Game,
        /// the game's own round clip the slider was calibrated against.</summary>
        internal const float CALIBRATION_CLIP_RMS_DBFS = -9.55f;

        /// <summary>That clip at SOUNDTRACK_SOURCE_GAIN, measured at the game's
        /// output on the broadcast seat (game sliders at max: mixer master
        /// +16 dB, music +10 dB): the soundtrack's level.</summary>
        internal const float CALIBRATION_OUTPUT_RMS_DBFS = -23.50f;

        /// <summary>The ONE RMS every custom clip is brought to. Equal to the
        /// calibration clip's own RMS, so the default percent keeps playing a
        /// custom clip at the soundtrack's level; at the slider's 100 the
        /// loudest peak after its gain stays 3.5 dB under full scale at the
        /// game's output, so the target did not have to come down.</summary>
        internal const float TRACK_TARGET_RMS_DBFS = -9.55f;

        /// <summary>One measured clip: its file name (MusicTrackDef.OggFile or
        /// PreviewFile), the measured RMS and peak in dBFS, and the linear gain
        /// 10^((TRACK_TARGET_RMS_DBFS - RmsDbfs) / 20), rounded to four places.</summary>
        internal sealed class TrackLevel
        {
            internal readonly string Clip;
            internal readonly float RmsDbfs;
            internal readonly float PeakDbfs;
            internal readonly float Gain;
            internal TrackLevel(string clip, float rmsDbfs, float peakDbfs, float gain)
            {
                Clip = clip; RmsDbfs = rmsDbfs; PeakDbfs = peakDbfs; Gain = gain;
            }
        }

        /// <summary>Every clip the album catalog names (MusicCatalog.Albums:
        /// each track's OggFile and PreviewFile), measured 2026-09-29 from the
        /// shipped bytes (hash-checked against the catalog and the asset
        /// manifest). A catalog clip missing here fails the structure gate
        /// (test_music_levels_client.py); a re-mastered clip is re-measured and
        /// its row replaced in the same change as its hash.</summary>
        internal static readonly TrackLevel[] TrackLevels = new[]
        {
            new TrackLevel("mus_ar_01_a_very_heavy_vintage_indeed.ogg", -12.11f, -1.13f, 1.3428f),
            new TrackLevel("mus_ar_01_a_very_heavy_vintage_indeed_preview.ogg", -11.34f, -0.15f, 1.2289f),
            new TrackLevel("mus_ar_02_combo_of_the_doom.ogg", -12.62f, -1.06f, 1.4240f),
            new TrackLevel("mus_ar_02_combo_of_the_doom_preview.ogg", -10.83f, 0.25f, 1.1588f),
            new TrackLevel("mus_ar_03_take_me_head_on.ogg", -13.13f, -0.85f, 1.5101f),
            new TrackLevel("mus_ar_03_take_me_head_on_preview.ogg", -12.04f, -0.99f, 1.3320f),
            new TrackLevel("mus_ar_04_stealing_the_lead.ogg", -11.07f, -1.70f, 1.1912f),
            new TrackLevel("mus_ar_04_stealing_the_lead_preview.ogg", -10.19f, -0.96f, 1.0765f),
            new TrackLevel("mus_ar_05_push_it_even_further.ogg", -10.48f, -1.53f, 1.1130f),
            new TrackLevel("mus_ar_05_push_it_even_further_preview.ogg", -9.39f, -1.45f, 0.9817f),
            new TrackLevel("mus_ar_06_set_to_deep_fry.ogg", -10.62f, -1.53f, 1.1311f),
            new TrackLevel("mus_ar_06_set_to_deep_fry_preview.ogg", -9.43f, -0.77f, 0.9863f),
            new TrackLevel("mus_ar_07_another_round.ogg", -11.28f, -0.90f, 1.2204f),
            new TrackLevel("mus_ar_07_another_round_preview.ogg", -10.91f, -1.03f, 1.1695f),
            new TrackLevel("mus_cb_01_clavar_la_bala.ogg", -12.80f, 0.29f, 1.4538f),
            new TrackLevel("mus_cb_01_clavar_la_bala_preview.ogg", -12.01f, 0.40f, 1.3274f),
            new TrackLevel("mus_cb_02_a_cinco_rondas.ogg", -13.09f, 0.08f, 1.5031f),
            new TrackLevel("mus_cb_02_a_cinco_rondas_preview.ogg", -12.30f, 0.13f, 1.3725f),
            new TrackLevel("mus_cb_03_a_cinco_rondas_ii.ogg", -13.38f, 0.00f, 1.5542f),
            new TrackLevel("mus_cb_03_a_cinco_rondas_ii_preview.ogg", -12.42f, 0.61f, 1.3916f),
            new TrackLevel("mus_cb_04_bloqueo_perfecto.ogg", -12.96f, -0.10f, 1.4808f),
            new TrackLevel("mus_cb_04_bloqueo_perfecto_preview.ogg", -11.96f, 1.01f, 1.3198f),
            new TrackLevel("mus_cb_05_el_que_pierde_elige.ogg", -13.06f, 0.15f, 1.4980f),
            new TrackLevel("mus_cb_05_el_que_pierde_elige_preview.ogg", -12.19f, 0.49f, 1.3552f),
            new TrackLevel("mus_cb_06_el_que_pierde_elige_ii.ogg", -13.05f, 0.40f, 1.4962f),
            new TrackLevel("mus_cb_06_el_que_pierde_elige_ii_preview.ogg", -12.01f, 0.42f, 1.3274f),
            new TrackLevel("mus_cb_07_corona_prestada.ogg", -12.82f, -0.32f, 1.4571f),
            new TrackLevel("mus_cb_07_corona_prestada_preview.ogg", -11.20f, 0.63f, 1.2092f),
            new TrackLevel("mus_cb_08_corona_prestada_ii.ogg", -12.76f, -0.24f, 1.4471f),
            new TrackLevel("mus_cb_08_corona_prestada_ii_preview.ogg", -11.63f, 0.22f, 1.2706f),
            new TrackLevel("mus_cb_09_la_distancia_para_una_revancha.ogg", -12.80f, -0.07f, 1.4538f),
            new TrackLevel("mus_cb_09_la_distancia_para_una_revancha_preview.ogg", -12.02f, 0.76f, 1.3289f),
            new TrackLevel("mus_cb_10_muerte_subita.ogg", -12.98f, -0.04f, 1.4842f),
            new TrackLevel("mus_cb_10_muerte_subita_preview.ogg", -12.29f, 0.29f, 1.3709f),
            new TrackLevel("mus_cb_11_muerte_subita_ii.ogg", -12.94f, -0.08f, 1.4774f),
            new TrackLevel("mus_cb_11_muerte_subita_ii_preview.ogg", -11.74f, 0.22f, 1.2868f),
            new TrackLevel("mus_cb_12_muerte_subita_iii.ogg", -12.59f, 0.00f, 1.4191f),
            new TrackLevel("mus_cb_12_muerte_subita_iii_preview.ogg", -11.63f, -0.20f, 1.2706f),
            new TrackLevel("mus_cb_13_principio_de_ronda.ogg", -13.61f, 0.32f, 1.5959f),
            new TrackLevel("mus_cb_13_principio_de_ronda_preview.ogg", -13.12f, 0.40f, 1.5083f),
            new TrackLevel("mus_cb_14_nube_toxica.ogg", -12.76f, -0.17f, 1.4471f),
            new TrackLevel("mus_cb_14_nube_toxica_preview.ogg", -11.88f, 0.15f, 1.3077f),
        };

        /// <summary>The measured gain of a catalog clip. False (gain 1) for a
        /// clip the table does not carry: the caller logs it, and the
        /// structure gate keeps a shipped catalog from ever reaching it.</summary>
        internal static bool TryTrackGain(string clip, out float gain)
        {
            gain = 1f;
            if (string.IsNullOrEmpty(clip)) return false;
            for (int i = 0; i < TrackLevels.Length; i++)
            {
                if (string.Equals(TrackLevels[i].Clip, clip, System.StringComparison.Ordinal))
                {
                    gain = TrackLevels[i].Gain;
                    return true;
                }
            }
            return false;
        }

        /// <summary>Source gain for a slider percent: the squared law times the
        /// ceiling. Values outside 0..100 clamp.</summary>
        internal static float SliderGain(int percent)
        {
            if (percent <= 0) return 0f;
            float f = percent >= 100 ? 1f : percent / 100f;
            return f * f * VOLUME_CEILING;
        }

        /// <summary>The one-time migration of a stored slider percent: the
        /// pre-1.41 default becomes DEFAULT_PERCENT; every other value, and
        /// every value once the migration has run, comes back unchanged.</summary>
        internal static int MigratedPercent(int stored, bool alreadyMigrated)
        {
            if (alreadyMigrated) return stored;
            return stored == LEGACY_DEFAULT_PERCENT ? DEFAULT_PERCENT : stored;
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

        private static double Db(double ratio)
        {
            return 20.0 * System.Math.Log10(ratio);
        }

        private static string D(double v)
        {
            return v.ToString("0.00", CultureInfo.InvariantCulture);
        }

        /// <summary>Null when the migration leaves every value but the legacy
        /// default unchanged, with the flag clear and with it set; otherwise
        /// the first value it moved.</summary>
        private static string LeaveAloneFailure(System.Func<int, bool, int> migrate)
        {
            var values = new System.Collections.Generic.List<int> { -5, 101, 250 };
            for (int v = 0; v < LEGACY_DEFAULT_PERCENT; v++) values.Add(v);
            foreach (int v in values)
                foreach (bool done in new[] { false, true })
                {
                    int got = migrate(v, done);
                    if (got != v) return "value=" + v + " flag=" + done + " became " + got;
                }
            return null;
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

            // The measured levels, in dB against the game's own soundtrack.
            double dbDefault = Db(SliderGain(DEFAULT_PERCENT) / SOUNDTRACK_SOURCE_GAIN);
            double dbTop = Db(SliderGain(100) / SOUNDTRACK_SOURCE_GAIN);
            double dbOld = Db(SliderGainBefore(LEGACY_DEFAULT_PERCENT) / SOUNDTRACK_SOURCE_GAIN);
            Check(r, "the default plays at the soundtrack's level, within 1 dB",
                  System.Math.Abs(dbDefault) <= 1.0,
                  "default=" + DEFAULT_PERCENT + " gain=" + F(SliderGain(DEFAULT_PERCENT)) + " dB=" + D(dbDefault));
            Check(r, "the slider's 100 is at most 6.5 dB over the soundtrack",
                  dbTop > 0.0 && dbTop <= 6.5,
                  "gain=" + F(SliderGain(100)) + " dB=" + D(dbTop));
            Check(r, "the default sits below the ceiling",
                  DEFAULT_PERCENT > 0 && DEFAULT_PERCENT < 100 && SliderGain(DEFAULT_PERCENT) < SliderGain(100),
                  "default=" + DEFAULT_PERCENT + " g(default)=" + F(SliderGain(DEFAULT_PERCENT)) + " g(100)=" + F(SliderGain(100)));
            Check(r, "the pre-1.41 default sat over 30 dB above the soundtrack (control)",
                  dbOld > 30.0,
                  "old100 dB=" + D(dbOld));

            // The one-time migration of a stored percent.
            Check(r, "a stored 100 becomes the default once",
                  MigratedPercent(LEGACY_DEFAULT_PERCENT, false) == DEFAULT_PERCENT,
                  "m(100,false)=" + MigratedPercent(LEGACY_DEFAULT_PERCENT, false));
            Check(r, "a stored 100 stays once the migration has run",
                  MigratedPercent(LEGACY_DEFAULT_PERCENT, true) == LEGACY_DEFAULT_PERCENT,
                  "m(100,true)=" + MigratedPercent(LEGACY_DEFAULT_PERCENT, true));
            string moved = LeaveAloneFailure(MigratedPercent);
            Check(r, "the migration never changes any other value", moved == null,
                  moved ?? "-5, 0..99, 101 and 250 unchanged with the flag clear and set");
            string caught = LeaveAloneFailure((s, done) => done ? s : DEFAULT_PERCENT);
            Check(r, "a migration that resets every value fails the leave-alone check (control)",
                  caught != null, caught ?? "the check missed a reset");

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

            PerClipCases(r);
            return r;
        }

        private static bool IsPreview(TrackLevel t)
        {
            return t.Clip.EndsWith("_preview.ogg", System.StringComparison.Ordinal);
        }

        /// <summary>Post-gain RMS spread in dB over the full tracks (previews
        /// false) or the previews (true), with each clip's gain from pick.</summary>
        private static double Spread(bool previews, System.Func<TrackLevel, float> pick, out int n)
        {
            double lo = double.MaxValue, hi = double.MinValue;
            n = 0;
            foreach (var t in TrackLevels)
            {
                if (IsPreview(t) != previews) continue;
                double post = t.RmsDbfs + Db(pick(t));
                if (post < lo) lo = post;
                if (post > hi) hi = post;
                n++;
            }
            return n == 0 ? double.MaxValue : hi - lo;
        }

        /// <summary>The loudest peak at the game's output at the slider's 100
        /// for a target moved by shiftDb, on the calibrated chain.</summary>
        private static double WorstOutputPeakAt100(double shiftDb, out string clip)
        {
            double worst = double.MinValue;
            clip = "";
            double chain = Db(SliderGain(100) / SOUNDTRACK_SOURCE_GAIN) + (CALIBRATION_OUTPUT_RMS_DBFS - CALIBRATION_CLIP_RMS_DBFS);
            foreach (var t in TrackLevels)
            {
                double pk = t.PeakDbfs + Db(t.Gain) + shiftDb + chain;
                if (pk > worst) { worst = pk; clip = t.Clip; }
            }
            return worst;
        }

        private static void PerClipCases(SelfTestResult r)
        {
            double worstDev = 0;
            string worstClip = "";
            bool positive = true;
            foreach (var t in TrackLevels)
            {
                if (!(t.Gain > 0f)) positive = false;
                double dev = System.Math.Abs(t.RmsDbfs + Db(t.Gain) - TRACK_TARGET_RMS_DBFS);
                if (dev > worstDev) { worstDev = dev; worstClip = t.Clip; }
            }
            Check(r, "every catalog clip's gain brings it to the one target",
                  positive && TrackLevels.Length > 0 && worstDev <= 0.01,
                  "clips=" + TrackLevels.Length + " target=" + D(TRACK_TARGET_RMS_DBFS)
                  + " worst deviation=" + worstDev.ToString("0.0000", CultureInfo.InvariantCulture) + " dB (" + worstClip + ")");

            double fullAfter = Spread(false, t => t.Gain, out int nFull);
            double fullBefore = Spread(false, t => 1f, out _);
            Check(r, "the full tracks' post-gain RMS spread is at most 3.0 dB",
                  nFull > 0 && fullAfter <= 3.0,
                  "tracks=" + nFull + " spread=" + fullAfter.ToString("0.000", CultureInfo.InvariantCulture)
                  + " dB (one global gain: " + D(fullBefore) + " dB)");
            double prevAfter = Spread(true, t => t.Gain, out int nPrev);
            Check(r, "the previews' post-gain RMS spread is at most 3.0 dB",
                  nPrev > 0 && prevAfter <= 3.0,
                  "previews=" + nPrev + " spread=" + prevAfter.ToString("0.000", CultureInfo.InvariantCulture) + " dB");
            Check(r, "one global gain leaves the full tracks over 3 dB apart (control)",
                  fullBefore > 3.0, "spread=" + D(fullBefore) + " dB");

            double pred70 = CALIBRATION_OUTPUT_RMS_DBFS + (TRACK_TARGET_RMS_DBFS - CALIBRATION_CLIP_RMS_DBFS)
                            + Db(SliderGain(DEFAULT_PERCENT) / SOUNDTRACK_SOURCE_GAIN);
            Check(r, "the default percent plays a custom clip within 1 dB of the calibration point",
                  System.Math.Abs(pred70 - CALIBRATION_OUTPUT_RMS_DBFS) <= 1.0,
                  "default=" + DEFAULT_PERCENT + " predicted=" + D(pred70) + " dBFS calibration=" + D(CALIBRATION_OUTPUT_RMS_DBFS));

            double worstOut = WorstOutputPeakAt100(0.0, out string peakClip);
            double worstSrc = double.MinValue;
            foreach (var t in TrackLevels)
                worstSrc = System.Math.Max(worstSrc, t.PeakDbfs + Db(t.Gain) + Db(SliderGain(100)));
            Check(r, "no clip peaks at or above 0 dBFS at the slider's 100 after its gain",
                  worstOut < 0.0 && worstSrc < 0.0 && SliderGain(100) * 2f <= 1f,
                  "output peak=" + D(worstOut) + " dBFS (" + peakClip + ") source peak=" + D(worstSrc) + " dBFS");
            double over = WorstOutputPeakAt100(4.0, out _);
            Check(r, "a target 4 dB higher would peak over full scale at 100 (control)",
                  over >= 0.0, "output peak=" + D(over) + " dBFS");

            bool found = true;
            foreach (var t in TrackLevels)
                if (!TryTrackGain(t.Clip, out float g) || g != t.Gain) found = false;
            bool missing = !TryTrackGain("mus_zz_not_in_the_catalog.ogg", out float g0) && g0 == 1f
                           && !TryTrackGain(null, out _) && !TryTrackGain("", out _);
            Check(r, "every table clip is found and an unknown clip reads false at gain 1",
                  found && missing, "found=" + found + " unknown=" + missing);
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
