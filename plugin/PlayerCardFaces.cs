using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Player Cards faces as images (design v22 §5.1, Tier 1). A face is
    /// fetched from the public immutable face route by (print, face_rev,
    /// locale, size), verified BEFORE decode (PNG signature by the transport,
    /// IHDR = the size's exact dimensions, 8-bit RGBA, non-interlaced here),
    /// decoded into a non-readable, mip-less Texture2D and kept in an LRU
    /// bounded by GPU bytes (w·h·4 per texture). Callers bind through fences
    /// they own (tile sequence, UI epoch, this cache's generation): a callback
    /// whose fence moved paints nothing. Nothing here is a Steam or Discord
    /// picture — the only source is the mod's api.
    ///
    /// Deferred by name (Tier 2 of the batch plan): the pending-destroy
    /// ledger, the disk cache, the embedded back placeholder and the retry
    /// glyph. Pinned entries are NOT deferred any more -- a visible tile's
    /// sprite could be evicted and destroyed under it, so SetFace records what
    /// is on screen and the LRU steps over it.
    ///
    /// One review finding is deliberately NOT fixed here: an answer for a tile
    /// that has since scrolled away is still decoded before the caller's own
    /// binding fence rejects it. Cancellation per request would be the fix, and
    /// it is not worth its complexity while the decode is not waste -- the
    /// texture lands in this cache under the key the page will ask for again on
    /// the way back, and the pins above are what made that decode safe. Recorded
    /// rather than dropped (#327).</summary>
    internal static class PlayerCardFaces
    {
        internal const int CARD_W = 750, CARD_H = 1050, TILE_W = 375, TILE_H = 525;
        private const long CACHE_CAP_BYTES = 64L * 1024 * 1024;
        private const int MAX_IN_FLIGHT = 4;
        private const int RETRY_404 = 3;
        private const float RETRY_404_DELAY = 2f;
        private const float RETRY_5XX_DELAY = 1f;

        private class Entry { public Texture2D tex; public Sprite spr; public long bytes; public float lastUse; }
        private class Pending
        {
            public string key, url, size;
            public int cap;
            public int tries404, tries5xx;
            public readonly List<Action<Sprite>> waiters = new List<Action<Sprite>>();
        }

        private static readonly Dictionary<string, Entry> cache = new Dictionary<string, Entry>(StringComparer.Ordinal);
        private static readonly Dictionary<string, Pending> inflight = new Dictionary<string, Pending>(StringComparer.Ordinal);
        private static readonly Queue<Pending> queue = new Queue<Pending>();
        private static long cacheBytes;
        private static int generation;

        // The in-flight requests, as objects with a deadline rather than a
        // count. `active++` / `active--` put the decrement inside a callback
        // owned by a replaceable coroutine host: a scene change during four
        // requests left the counter at MAX_IN_FLIGHT with nothing running and
        // Pump() started nothing again for the life of the process (#508). A
        // slot that outlives its budget is reclaimed, so the pool refills even
        // when an answer never arrives at all -- expiring by default, which
        // self-heals, rather than blocking by default (#276).
        private sealed class Slot { internal Pending p; internal float until; }
        private static readonly List<Slot> slots = new List<Slot>();
        private const float REQUEST_BUDGET = 60f;   // the transport's own timeout, with slack

        // The faces a live Image is showing right now. The LRU used to pick its
        // victim by lastUse alone, so paging fast enough evicted and DESTROYED
        // a Sprite still bound to a tile on screen and blanked it. A binding is
        // (GameObject, Sprite) so a destroyed tile's hold disappears with it --
        // an instance id could not be asked whether it was still alive.
        private sealed class Binding { internal GameObject go; internal Sprite spr; }
        private static readonly List<Binding> bindings = new List<Binding>();
        private static PropertyInfo pPreserveAspect;

        /// <summary>Bumped by Clear(): a byte answer from an older generation is
        /// dropped undecoded.</summary>
        internal static int Generation => generation;
        /// <summary>The version gate answered 426 for a face: no face is retried
        /// until the next launch (the mod updates itself on relaunch).</summary>
        internal static bool Outdated { get; private set; }
        internal static int CachedCount => cache.Count;
        internal static long CachedBytes => cacheBytes;

        internal static string Key(string printId, string faceRev, string locale, string size)
            => printId + "/" + faceRev + "/" + (string.IsNullOrEmpty(locale) ? "en" : locale) + "/" + size;

        /// <summary>The cached sprite or null; a hit touches the LRU clock.</summary>
        internal static Sprite Cached(string printId, string faceRev, string locale, string size)
        {
            Entry e;
            if (string.IsNullOrEmpty(printId) || string.IsNullOrEmpty(faceRev)) return null;
            if (!cache.TryGetValue(Key(printId, faceRev, locale, size), out e) || e.spr == null) return null;
            e.lastUse = Time.realtimeSinceStartup;
            return e.spr;
        }

        /// <summary>Request one face at one size ("tile" or "card"). `onReady`
        /// runs on the main thread with the sprite, immediately when cached,
        /// with null when the face could not be had (the caller keeps its
        /// placeholder; the next binding asks again). Returns false when
        /// nothing could be requested (no revision, or the version gate).</summary>
        internal static bool Get(string printId, string faceRev, string locale, string size, Action<Sprite> onReady)
        {
            if (string.IsNullOrEmpty(printId) || string.IsNullOrEmpty(faceRev) || Outdated) return false;
            if (size != "tile" && size != "card") return false;
            string key = Key(printId, faceRev, locale, size);
            Entry e;
            if (cache.TryGetValue(key, out e) && e.spr != null)
            {
                e.lastUse = Time.realtimeSinceStartup;
                Safe(onReady, e.spr);
                return true;
            }
            Pending p;
            if (inflight.TryGetValue(key, out p)) { if (onReady != null) p.waiters.Add(onReady); return true; }
            p = new Pending
            {
                key = key, size = size, url = ApiClient.PcFaceUrl(printId, faceRev, locale, size),
                cap = size == "card" ? ApiClient.PC_FACE_MAX_BYTES : ApiClient.PC_TILE_MAX_BYTES,
            };
            if (onReady != null) p.waiters.Add(onReady);
            inflight[key] = p;
            queue.Enqueue(p);
            Pump();
            return true;
        }

        /// <summary>The live slot count, expired slots swept first.</summary>
        private static int Active()
        {
            for (int i = slots.Count - 1; i >= 0; i--)
            {
                if (Time.realtimeSinceStartup <= slots[i].until) continue;
                Plugin.Log.LogWarning("[PC-FACE] a request never answered within " + REQUEST_BUDGET + "s; reclaiming its slot");
                slots.RemoveAt(i);
            }
            return slots.Count;
        }

        private static void Release(Pending p)
        {
            for (int i = 0; i < slots.Count; i++)
                if (slots[i].p == p) { slots.RemoveAt(i); return; }
        }

        /// <summary>Called from the Player Cards tick: a queue left waiting on
        /// slots that expired needs something other than the next answer to
        /// restart it, because the answer is exactly what did not come.</summary>
        internal static void Tick()
        {
            if (queue.Count > 0 && Active() < MAX_IN_FLIGHT) Pump();
        }

        private static void Pump()
        {
            while (Active() < MAX_IN_FLIGHT && queue.Count > 0)
            {
                var p = queue.Dequeue();
                Pending live;
                if (!inflight.TryGetValue(p.key, out live) || live != p) continue;   // cancelled by Clear()
                Start(p);
            }
        }

        private static void Start(Pending p)
        {
            slots.Add(new Slot { p = p, until = Time.realtimeSinceStartup + REQUEST_BUDGET });
            int gen = generation;
            ApiClient.FetchBytes(p.url, p.cap, (ok, data, code) =>
            {
                Release(p);
                try { OnAnswer(p, gen, ok, data, code); }
                catch (Exception ex) { Plugin.Log.LogWarning($"[PC-FACE] answer handling threw: {ex.Message}"); Finish(p, null); }
                Pump();
            });
        }

        private static void OnAnswer(Pending p, int gen, bool ok, byte[] data, long code)
        {
            Pending live;
            if (gen != generation || !inflight.TryGetValue(p.key, out live) || live != p) { Finish(p, null); return; }   // fence moved: drop undecoded
            if (code == 426) { GoOutdated(); Finish(p, null); return; }
            if (!ok || data == null)
            {
                // 404 = a revision this box does not serve yet (or a stale key):
                // the same key again after 2 s, three times; 5xx / no answer once.
                if (code == 404 && p.tries404 < RETRY_404) { p.tries404++; Retry(p, RETRY_404_DELAY); return; }
                if ((code == 0 || code >= 500) && p.tries5xx < 1) { p.tries5xx++; Retry(p, RETRY_5XX_DELAY); return; }
                Plugin.Log.LogInfo($"[PC-FACE] {p.key} failed (HTTP {code})");
                Finish(p, null);
                return;
            }
            int w, h;
            if (!IhdrOk(data, p.size, out w, out h))
            {
                Plugin.Log.LogWarning($"[PC-FACE] {p.key}: header refused ({w}x{h})");
                Finish(p, null);
                return;
            }
            long incoming = (long)w * h * 4;
            Admit(incoming);
            Texture2D tex = null; Sprite spr = null;
            try
            {
                tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                if (!tex.LoadImage(data, true) || tex.width != w || tex.height != h)
                {
                    UnityEngine.Object.Destroy(tex);
                    Plugin.Log.LogWarning($"[PC-FACE] {p.key}: decode failed");
                    Finish(p, null);
                    return;
                }
                tex.filterMode = FilterMode.Bilinear;
                tex.wrapMode = TextureWrapMode.Clamp;
                spr = Sprite.Create(tex, new Rect(0, 0, w, h), new Vector2(0.5f, 0.5f), 100f);
            }
            catch (Exception ex)
            {
                if (spr != null) UnityEngine.Object.Destroy(spr);
                if (tex != null) UnityEngine.Object.Destroy(tex);
                Plugin.Log.LogWarning($"[PC-FACE] {p.key}: texture threw {ex.Message}");
                Finish(p, null);
                return;
            }
            cache[p.key] = new Entry { tex = tex, spr = spr, bytes = incoming, lastUse = Time.realtimeSinceStartup };
            cacheBytes += incoming;
            Finish(p, spr);
        }

        /// <summary>The version gate answered: this build is not served faces
        /// until it relaunches. Reading the flag at Get()'s door was not the
        /// gate it claimed to be -- everything already queued kept fetching and
        /// painting, and each retry re-queued itself, so the "paused" log line
        /// was followed by more requests. Stopping means draining the queue and
        /// fencing the answers still outstanding.
        ///
        /// Faces already decoded stay on screen and keep serving from the
        /// cache. They came from this same server before the gate closed and
        /// are not made wrong by it; blanking them would cost the player their
        /// collection view and buy nothing.</summary>
        private static void GoOutdated()
        {
            if (Outdated) return;
            Outdated = true;
            Plugin.Log.LogWarning("[PC-FACE] version gate: faces paused until relaunch ("
                                  + queue.Count + " queued, " + Active() + " in flight dropped)");
            generation++;                     // every outstanding answer is now off-fence
            var pending = new List<Pending>(inflight.Values);
            inflight.Clear();
            queue.Clear();
            slots.Clear();
            foreach (var p in pending) { var w = p.waiters.ToArray(); p.waiters.Clear(); foreach (var cb in w) Safe(cb, null); }
        }

        private static void Retry(Pending p, float delay)
        {
            if (Plugin.Instance == null) { Finish(p, null); return; }
            int gen = generation;
            Plugin.Instance.StartCoroutine(RetryCo(p, gen, delay));
        }

        private static IEnumerator RetryCo(Pending p, int gen, float delay)
        {
            yield return new WaitForSecondsRealtime(delay);
            Pending live;
            if (gen != generation || !inflight.TryGetValue(p.key, out live) || live != p) { Finish(p, null); yield break; }
            queue.Enqueue(p);
            Pump();
        }

        private static void Finish(Pending p, Sprite spr)
        {
            Pending live;
            if (inflight.TryGetValue(p.key, out live) && live == p) inflight.Remove(p.key);
            var waiters = p.waiters.ToArray();
            p.waiters.Clear();
            foreach (var w in waiters) Safe(w, spr);
        }

        private static void Safe(Action<Sprite> cb, Sprite spr)
        {
            if (cb == null) return;
            try { cb(spr); } catch (Exception ex) { Plugin.Log.LogWarning($"[PC-FACE] callback threw: {ex.Message}"); }
        }

        /// <summary>The 8-byte signature was checked by the transport; here the
        /// IHDR: exact dimensions for the size, bit depth 8, colour type 6
        /// (RGBA), no interlace — LoadImage allocates by the DECLARED size.</summary>
        internal static bool IhdrOk(byte[] d, string size, out int w, out int h)
        {
            w = h = 0;
            if (d == null || d.Length < 33) return false;
            if (d[12] != (byte)'I' || d[13] != (byte)'H' || d[14] != (byte)'D' || d[15] != (byte)'R') return false;
            w = (d[16] << 24) | (d[17] << 16) | (d[18] << 8) | d[19];
            h = (d[20] << 24) | (d[21] << 16) | (d[22] << 8) | d[23];
            if (d[24] != 8 || d[25] != 6 || d[28] != 0) return false;
            int ew = size == "card" ? CARD_W : TILE_W, eh = size == "card" ? CARD_H : TILE_H;
            return w == ew && h == eh;
        }

        /// <summary>Forget bindings whose tile has been destroyed.</summary>
        private static void SweepBindings()
        {
            for (int i = bindings.Count - 1; i >= 0; i--)
                if (bindings[i].go == null || bindings[i].spr == null) bindings.RemoveAt(i);
        }

        private static bool Pinned(Sprite spr)
        {
            if (spr == null) return false;
            for (int i = 0; i < bindings.Count; i++) if (bindings[i].spr == spr) return true;
            return false;
        }

        /// <summary>Evict least-recently-used UNPINNED entries until the
        /// incoming texture fits.
        ///
        /// When everything left is on screen the cap is exceeded rather than
        /// enforced, and the line below says so. That is the deliberate choice
        /// between two costs: going over a soft byte budget for as long as a
        /// page is visible is recoverable the moment the player pages away,
        /// while destroying a Sprite an Image still holds blanks a card in
        /// front of them and no later frame repairs it.
        ///
        /// The transient overshoot from Unity's deferred Destroy -- the evicted
        /// textures' memory is still resident this frame -- is NOT charged
        /// here; the pending-destroy ledger is Tier 2 of the batch plan and is
        /// named in this class's own summary.</summary>
        private static void Admit(long incoming)
        {
            SweepBindings();
            while (cacheBytes + incoming > CACHE_CAP_BYTES && cache.Count > 0)
            {
                string oldest = null; float t = float.MaxValue;
                foreach (var kv in cache)
                {
                    if (Pinned(kv.Value.spr)) continue;
                    if (kv.Value.lastUse < t) { t = kv.Value.lastUse; oldest = kv.Key; }
                }
                if (oldest == null)
                {
                    Plugin.Log.LogInfo("[PC-FACE] every cached face is on screen; over cap by "
                                       + (cacheBytes + incoming - CACHE_CAP_BYTES) + " bytes");
                    break;
                }
                Drop(oldest);
            }
        }

        private static void Drop(string key)
        {
            Entry e;
            if (!cache.TryGetValue(key, out e)) return;
            cache.Remove(key);
            cacheBytes -= e.bytes;
            for (int i = bindings.Count - 1; i >= 0; i--) if (bindings[i].spr == e.spr) bindings.RemoveAt(i);
            // the sprite first, then its texture (CardSnapshot.DestroySprite's order)
            try { if (e.spr != null) UnityEngine.Object.Destroy(e.spr); } catch { }
            try { if (e.tex != null) UnityEngine.Object.Destroy(e.tex); } catch { }
        }

        /// <summary>ONE cleanup: every cached sprite and texture destroyed, the
        /// queue cancelled, every in-flight answer fenced out. Identity change,
        /// consent revoke, overlay teardown.</summary>
        internal static void Clear()
        {
            generation++;
            var keys = new List<string>(cache.Keys);
            foreach (var k in keys) Drop(k);
            cacheBytes = 0;
            foreach (var p in inflight.Values) p.waiters.Clear();
            inflight.Clear();
            queue.Clear();
            slots.Clear();
            bindings.Clear();
        }

        /// <summary>Put a sprite on a panel's Image: preserveAspect, white tint,
        /// no raycast (clicks fall through to the tile's own handlers).</summary>
        internal static void SetFace(GameObject imageGO, Sprite spr)
        {
            if (imageGO == null || UIFactory.tImage == null) return;
            var img = imageGO.GetComponent(UIFactory.tImage);
            if (img == null) return;
            // Every face reaches an Image through here, so this is the one
            // place that knows what is on screen. Recording it here rather than
            // at the call sites is what keeps the pin from drifting out of step
            // with the binding it describes.
            SweepBindings();
            for (int i = bindings.Count - 1; i >= 0; i--) if (bindings[i].go == imageGO) bindings.RemoveAt(i);
            if (spr != null) bindings.Add(new Binding { go = imageGO, spr = spr });
            try
            {
                if (pPreserveAspect == null) pPreserveAspect = UIFactory.tImage.GetProperty("preserveAspect", BindingFlags.Public | BindingFlags.Instance);
                pPreserveAspect?.SetValue(img, true);
                UIFactory.tImage.GetProperty("raycastTarget", BindingFlags.Public | BindingFlags.Instance)?.SetValue(img, false);
            }
            catch { }
            UIFactory.SetImageSprite(imageGO, spr);
            UIFactory.SetImageColor(imageGO, spr != null ? Color.white : new Color(1f, 1f, 1f, 0f));
        }

        /// <summary>A sprite over a runtime texture (the preset preview): the
        /// caller owns both and destroys the previous pair itself.</summary>
        internal static Sprite SpriteOf(Texture2D tex)
        {
            if (tex == null) return null;
            try { return Sprite.Create(tex, new Rect(0, 0, tex.width, tex.height), new Vector2(0.5f, 0.5f), 100f); }
            catch { return null; }
        }
    }
}
