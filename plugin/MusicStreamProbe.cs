using System;
using System.Diagnostics;
using System.Globalization;
using UnityEngine;
using UnityEngine.Networking;

namespace CompetitiveRounds
{
    /// <summary>Music v7 spike (music-v7-design.md §2): measures STREAMED decode
    /// (DownloadHandlerAudioClip.streamAudio = true) on this seat. Broadcast
    /// identity only. Lever: [Broadcast] MusicStreamProbe = "&lt;albumSku&gt;:&lt;trackIdx&gt;[:stress]".
    /// Plays the track on a private AudioSource for 120 s (stress: 600 s) and
    /// logs [MUSIC-PROBE] lines: GetContent cost, drift between the DSP clock and
    /// AudioSource.time (integrated stall time), the largest single stall, heap
    /// delta. A new lever value re-runs; an empty value does nothing. The probe
    /// never touches MusicEngine state.</summary>
    internal static class MusicStreamProbe
    {
        private static string _last;
        private static UnityWebRequest _req;      // in flight
        private static UnityWebRequest _reqKeep;  // kept alive for the streamed clip's lifetime
        private static AudioClip _clip;
        private static GameObject _go;
        private static AudioSource _src;
        private static double _dsp0;
        private static float _lastDrift, _stallMax, _nextLog, _endAt, _getContentMs, _startRt;
        private static long _heap0;
        private static int _stalls;
        private static bool _stress;
        private static string _key;

        internal static void Tick()
        {
            try
            {
                if (Plugin.BroadcastMusicStreamProbe == null || !BroadcastMode.IsBroadcastIdentity) return;
                float now = Time.realtimeSinceStartup;
                if (_req == null && _src == null)
                {
                    // TickTestOpenTab (which runs just before this) reloads the
                    // lever cfg file every 2 s, so Value tracks disk edits.
                    string raw = (Plugin.BroadcastMusicStreamProbe.Value ?? "").Trim();
                    // The value present at launch is the baseline (same rule as
                    // TestOpenTab): a stale lever never fires on its own.
                    if (_last == null) { _last = raw; return; }
                    if (raw.Length == 0 || raw == _last) return;
                    _last = raw;
                    Start(raw, now);
                    return;
                }
                if (_req != null) { PumpRequest(now); return; }
                if (_src != null) PumpPlayback(now);
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning("[MUSIC-PROBE] tick threw: " + ex.Message);
                Stop("exception");
            }
        }

        private static void Start(string raw, float now)
        {
            string[] parts = raw.Split(':');
            if (parts.Length < 2) { Plugin.Log?.LogWarning("[MUSIC-PROBE] bad lever '" + raw + "' (want sku:idx[:stress])"); return; }
            var album = MusicCatalog.Get(parts[0]);
            int idx;
            if (album == null || !int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out idx)
                || idx < 0 || idx >= album.Tracks.Length)
            { Plugin.Log?.LogWarning("[MUSIC-PROBE] unknown album/track '" + raw + "'"); return; }
            _stress = parts.Length > 2 && string.Equals(parts[2], "stress", StringComparison.OrdinalIgnoreCase);
            string path = MusicAssets.PathFor(album.Tracks[idx].OggFile);
            if (path == null) { Plugin.Log?.LogWarning("[MUSIC-PROBE] file not ready for " + raw + " (full tier not installed?)"); return; }
            string url;
            try { url = new Uri(path).AbsoluteUri; }
            catch { url = "file:///" + path.Replace('\\', '/'); }
            _key = parts[0] + ":" + idx.ToString(CultureInfo.InvariantCulture);
            _req = UnityWebRequestMultimedia.GetAudioClip(url, AudioType.OGGVORBIS);
            var dh = _req.downloadHandler as DownloadHandlerAudioClip;
            if (dh != null) dh.streamAudio = true;
            _req.SendWebRequest();
            _startRt = now;
            Plugin.Log?.LogInfo("[MUSIC-PROBE] request " + _key + " stream=1 stress=" + (_stress ? 1 : 0));
        }

        private static void PumpRequest(float now)
        {
            if (!_req.isDone)
            {
                if (now - _startRt > 30f) { Plugin.Log?.LogWarning("[MUSIC-PROBE] request timeout"); Stop("timeout"); }
                return;
            }
            if (!string.IsNullOrEmpty(_req.error))
            {
                Plugin.Log?.LogWarning("[MUSIC-PROBE] request error: " + _req.error);
                Stop("error");
                return;
            }
            var sw = Stopwatch.StartNew();
            _clip = DownloadHandlerAudioClip.GetContent(_req);
            sw.Stop();
            _getContentMs = (float)sw.Elapsed.TotalMilliseconds;
            _reqKeep = _req; _req = null;
            if (_clip == null) { Plugin.Log?.LogWarning("[MUSIC-PROBE] GetContent returned null"); Stop("null clip"); return; }
            _go = new GameObject("SCR_MusicProbe") { hideFlags = HideFlags.HideAndDontSave };
            _src = _go.AddComponent<AudioSource>();
            _src.clip = _clip; _src.loop = false; _src.playOnAwake = false; _src.volume = 0.5f;
            _heap0 = GC.GetTotalMemory(false);
            _src.Play();
            _dsp0 = AudioSettings.dspTime;
            _lastDrift = 0f; _stallMax = 0f; _stalls = 0;
            _nextLog = now + 5f;
            _endAt = now + (_stress ? 600f : 120f);
            Plugin.Log?.LogInfo("[MUSIC-PROBE] start " + _key + " getcontent_ms=" + _getContentMs.ToString("F1", CultureInfo.InvariantCulture)
                + " loadState=" + _clip.loadState + " loadType=" + _clip.loadType
                + " length_s=" + _clip.length.ToString("F1", CultureInfo.InvariantCulture)
                + " freq=" + _clip.frequency + " ch=" + _clip.channels + " request_ms=" + ((now - _startRt) * 1000f).ToString("F0", CultureInfo.InvariantCulture));
        }

        private static void PumpPlayback(float now)
        {
            float t = _src.time;
            float drift = (float)(AudioSettings.dspTime - _dsp0) - t;
            float jump = drift - _lastDrift;
            // AudioSource.time advances once per DSP buffer (1024 samples at
            // 48 kHz = 21.3 ms), so drift oscillates by one or two buffers with
            // no underrun at all (first run: 2288 "stalls" of 21-43 ms in 120 s
            // with drift returning to 0). A stall is a jump of three buffers or
            // more; the accumulated drift is the primary underrun measure.
            if (jump > 0.06f) { _stalls++; if (jump > _stallMax) _stallMax = jump; }
            _lastDrift = drift;
            bool ended = !_src.isPlaying && t > 1f;
            if (now >= _nextLog || ended || now >= _endAt)
            {
                _nextLog = now + 5f;
                long heap = GC.GetTotalMemory(false);
                Plugin.Log?.LogInfo("[MUSIC-PROBE] t=" + t.ToString("F1", CultureInfo.InvariantCulture)
                    + " drift_ms=" + (drift * 1000f).ToString("F0", CultureInfo.InvariantCulture)
                    + " stalls=" + _stalls + " stall_max_ms=" + (_stallMax * 1000f).ToString("F0", CultureInfo.InvariantCulture)
                    + " heap_delta_mb=" + ((heap - _heap0) / 1048576.0).ToString("F1", CultureInfo.InvariantCulture)
                    + " fps=" + (Time.smoothDeltaTime > 0f ? (1f / Time.smoothDeltaTime).ToString("F0", CultureInfo.InvariantCulture) : "?")
                    + " playing=" + (_src.isPlaying ? 1 : 0) + " loadState=" + _clip.loadState);
            }
            if (ended) Stop("clip ended");
            else if (now >= _endAt) Stop("budget");
        }

        private static void Stop(string why)
        {
            Plugin.Log?.LogInfo("[MUSIC-PROBE] end key=" + _key + " why=" + why + " stalls=" + _stalls
                + " stall_max_ms=" + (_stallMax * 1000f).ToString("F0", CultureInfo.InvariantCulture)
                + " drift_ms=" + (_lastDrift * 1000f).ToString("F0", CultureInfo.InvariantCulture));
            try { if (_src != null) _src.Stop(); } catch { }
            try { if (_go != null) UnityEngine.Object.Destroy(_go); } catch { }
            try { if (_clip != null) UnityEngine.Object.Destroy(_clip); } catch { }
            try { if (_req != null) _req.Dispose(); } catch { }
            try { if (_reqKeep != null) _reqKeep.Dispose(); } catch { }
            _src = null; _go = null; _clip = null; _req = null; _reqKeep = null;
        }
    }
}
