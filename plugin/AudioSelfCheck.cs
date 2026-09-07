using System;
using System.Globalization;
using UnityEngine;
using UnityEngine.Audio;
using SoundImplementation;   // vanilla SoundVolumeManager lives here

namespace CompetitiveRounds
{
    /// <summary>Bug 337 ("no SFX", and not one fault signature anywhere in the
    /// log): one line that says what the audio stack is SET to, so the next
    /// report separates "a slider at zero" from a real fault by itself.
    /// Emitted once per match start and at the end of every bug-report bundle,
    /// plus a delta line whenever AudioListener.volume changes, naming the
    /// writer when it is ours. Read-only: nothing here writes audio state.</summary>
    internal static class AudioSelfCheck
    {
        private static float _lastListener = -1f;
        private static string _ourWriter;
        private static float _ourValue;
        private static float _ourWriteAt = -999f;
        private static int _deltaLines;
        private const int DELTA_LINE_CAP = 40;

        /// <summary>Our own AudioListener.volume writers call this right before
        /// the write, so the delta line can attribute the change. Anything the
        /// delta watcher sees without a matching note is "not ours".</summary>
        internal static void NoteOurWrite(string writer, float value)
        {
            _ourWriter = writer; _ourValue = value; _ourWriteAt = Time.unscaledTime;
        }

        /// <summary>Per poll: one float compare; a log line only on change.</summary>
        internal static void Tick()
        {
            try
            {
                float v = AudioListener.volume;
                if (_lastListener < 0f) { _lastListener = v; return; }
                if (Mathf.Abs(v - _lastListener) < 0.001f) return;
                string writer = _ourWriter != null && Time.unscaledTime - _ourWriteAt < 2f
                                && Mathf.Abs(v - _ourValue) < 0.001f
                    ? _ourWriter : "not ours";
                if (_deltaLines < DELTA_LINE_CAP)
                {
                    _deltaLines++;
                    Plugin.Log.LogInfo(string.Format(CultureInfo.InvariantCulture,
                        "[AUDIO] AudioListener.volume {0:F2} -> {1:F2} (writer: {2}){3}",
                        _lastListener, v, writer,
                        _deltaLines == DELTA_LINE_CAP ? " -- further deltas suppressed this session" : ""));
                }
                _lastListener = v;
                _ourWriter = null;
            }
            catch { }
        }

        /// <summary>The snapshot line. Never throws; a part that cannot be read
        /// says so instead of dropping the line.</summary>
        internal static string Snapshot()
        {
            var sb = new System.Text.StringBuilder();
            try
            {
                sb.Append("listener=").Append(AudioListener.volume.ToString("F2", CultureInfo.InvariantCulture))
                  .Append(" paused=").Append(AudioListener.pause);
            }
            catch { sb.Append("listener=?"); }
            // Vanilla's sliders persist under these PlayerPrefs keys
            // (OptionsHandler registers the slider callbacks by key;
            // OptionsData.SettingsData.LoadSettings reads them). The default is
            // a serialized field on the OptionsData asset, not a literal in
            // code, so an UNSET key reads as "default" rather than a guess.
            sb.Append(" | prefs");
            AppendPref(sb, "master", "OPTION_VOLUME_MASTER");
            AppendPref(sb, "music", "OPTION_VOLUME_MUSIC");
            AppendPref(sb, "sfx", "OPTION_VOLUME_SFX");
            // The mixer's exposed parameters, read back through vanilla's own
            // SoundVolumeManager. The parameter names come from its fields, so
            // a renamed mixer parameter cannot make this read the wrong one.
            // Vanilla maps slider 1.0 to +16 dB (master) / +10 dB (music, sfx)
            // and slider 0 to -80 dB.
            sb.Append(" | mixer");
            try
            {
                var svm = SoundVolumeManager.Instance;
                var mixer = svm != null ? svm.audioMixer : null;
                if (mixer == null) sb.Append(" (none)");
                else
                {
                    AppendMixer(sb, mixer, "master", svm.masterName);
                    AppendMixer(sb, mixer, "mus", svm.musName);
                    AppendMixer(sb, mixer, "sfx", svm.sfxName);
                }
            }
            catch (Exception ex) { sb.Append(" ?(").Append(ex.GetType().Name).Append(')'); }
            // Sonigon: voice slots and how many hold a live voice, walked
            // through the reflection surface RoundSoundSweep already resolves.
            int active, slots;
            if (RoundSoundSweep.TryCountVoices(out active, out slots))
                sb.Append(" | sonigon voices active=").Append(active).Append(" slots=").Append(slots);
            else
                sb.Append(" | sonigon voices=?");
            try { sb.Append(" | fps=").Append(Mathf.RoundToInt(1f / Mathf.Max(Time.unscaledDeltaTime, 0.0001f))); } catch { }
            return sb.ToString();
        }

        private static void AppendPref(System.Text.StringBuilder sb, string label, string key)
        {
            try
            {
                sb.Append(' ').Append(label).Append('=');
                if (PlayerPrefs.HasKey(key)) sb.Append(PlayerPrefs.GetFloat(key).ToString("F2", CultureInfo.InvariantCulture));
                else sb.Append("default");
            }
            catch { sb.Append('?'); }
        }

        private static void AppendMixer(System.Text.StringBuilder sb, UnityEngine.Audio.AudioMixer mixer, string label, string param)
        {
            try
            {
                float db;
                sb.Append(' ').Append(label).Append('=');
                if (!string.IsNullOrEmpty(param) && mixer.GetFloat(param, out db))
                    sb.Append(db.ToString("+0.0;-0.0", CultureInfo.InvariantCulture)).Append("dB");
                else sb.Append('?');
            }
            catch { sb.Append('?'); }
        }

        /// <summary>One line per match start (ResetPerMatchCombatCounters is the
        /// seam both the 1v1/2v2 and the FFA start paths share).</summary>
        internal static void LogSnapshot(string when)
        {
            try { Plugin.Log.LogInfo("[AUDIO] " + when + ": " + Snapshot()); } catch { }
        }
    }
}
