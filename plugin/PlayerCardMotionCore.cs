using System;
using System.Collections.Generic;
using System.Globalization;

namespace CompetitiveRounds
{
    /// <summary>The playback's pure half (dance cards design S5.2-S5.7): the
    /// visit identity, the clip clock, the motion read's answer, the request
    /// gate, the atlas shape, the atlas memory budget and the one-decode-per-
    /// frame gate. No UnityEngine reference: PlayerCardMotion drives these
    /// from the Player Cards tick, and tools/tests/dance-cards-client compiles
    /// this same file (T39, T40, T41, T49, T50's calibrated arm).</summary>
    internal static class PlayerCardMotionCore
    {
        internal const int READ_MAX_IDS = 11;              // ten visible tiles and the popup's print
        internal const int ATLAS_COLUMNS = 8;              // pc_motion.ATLAS_COLUMNS
        internal const int CARD_CELL = 256, TILE_CELL = 96; // pc_motion.CARD_CELL / TILE_CELL
        internal const int CARD_ATLAS_MAX_BYTES = 12 << 20, TILE_ATLAS_MAX_BYTES = 6 << 20;
        internal const int FRAMES_MAX = 120;
        internal const double COOLDOWN_429_S = 60.0;       // S2.7: a 429 stops every motion request this long
        internal const long CACHE_CAP_BYTES = 64L << 20;   // S5.6: decoded atlases, width x height x 4

        // The overlay's box on the face, as fractions of the 750x1050 card (the
        // tile is the same box at half size): the portrait window
        // (pc_motion.CARD_WINDOW = 80,150,670,740) that the atlas cells crop.
        internal const float WIN_X = 80f / 750f, WIN_Y = 150f / 1050f, WIN_W = 590f / 750f, WIN_H = 590f / 1050f;

        /// <summary>Cell edge, atlas width and height for `frames` at `size`
        /// ("card" or "tile"): eight columns, row-major, ceil(frames / 8) rows.
        /// False for an unknown size or a frame count outside 1-120.</summary>
        internal static bool AtlasShape(int frames, string size, out int cell, out int w, out int h)
        {
            cell = size == "card" ? CARD_CELL : size == "tile" ? TILE_CELL : 0;
            w = h = 0;
            if (cell == 0 || frames < 1 || frames > FRAMES_MAX) return false;
            w = ATLAS_COLUMNS * cell;
            h = ((frames + ATLAS_COLUMNS - 1) / ATLAS_COLUMNS) * cell;
            return true;
        }

        internal static int AtlasByteCap(string size) { return size == "card" ? CARD_ATLAS_MAX_BYTES : TILE_ATLAS_MAX_BYTES; }

        /// <summary>The IHDR before anything allocates by it: exactly the shape
        /// the frame count implies, 8-bit RGBA, not interlaced.</summary>
        internal static bool AtlasHeaderOk(byte[] png, int frames, string size)
        {
            int cell, w, h, rw, rh, depth, ct, il;
            if (!AtlasShape(frames, size, out cell, out w, out h)) return false;
            if (png == null || png.Length > AtlasByteCap(size)) return false;
            if (!ScrPng.ReadIhdr(png, out rw, out rh, out depth, out ct, out il)) return false;
            return rw == w && rh == h && depth == 8 && ct == 6 && il == 0;
        }

        /// <summary>A revision as a path segment may carry it: 1-64 of
        /// [0-9a-z]. The server's are 16 lowercase hex characters.</summary>
        internal static bool RevOk(string r)
        {
            if (string.IsNullOrEmpty(r) || r.Length > 64) return false;
            foreach (char c in r) if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'z'))) return false;
            return true;
        }

        /// <summary>One entry of the motion read (S5.2).</summary>
        internal struct ReadEntry
        {
            internal string PrintId, FaceRev, MotionRev;
            internal int Frames, Ms;
            internal bool Has;
        }

        /// <summary>The `m` value of `GET /api/v1/pc-face/motion`: one entry per
        /// asked id, in request order, each `<pid>:<face_rev>:<motion_rev>:
        /// <frames>:<ms>` or `<pid>:-`. False (nothing usable) when the count,
        /// the order, an id or a field is not what was asked or allowed.</summary>
        internal static bool ParseRead(string m, IList<string> asked, out List<ReadEntry> entries)
        {
            entries = null;
            if (m == null || asked == null || asked.Count < 1 || asked.Count > READ_MAX_IDS) return false;
            var parts = m.Split('|');
            if (parts.Length != asked.Count) return false;
            var list = new List<ReadEntry>(parts.Length);
            for (int i = 0; i < parts.Length; i++)
            {
                var f = parts[i].Split(':');
                if (f.Length < 2 || f[0] != asked[i]) return false;
                if (f.Length == 2)
                {
                    if (f[1] != "-") return false;
                    list.Add(new ReadEntry { PrintId = f[0], Has = false });
                    continue;
                }
                int frames, ms;
                if (f.Length != 5 || !RevOk(f[1]) || !RevOk(f[2])
                    || !int.TryParse(f[3], NumberStyles.None, CultureInfo.InvariantCulture, out frames)
                    || !int.TryParse(f[4], NumberStyles.None, CultureInfo.InvariantCulture, out ms)
                    || frames < 1 || frames > FRAMES_MAX || ms < 1 || ms > 9999) return false;
                list.Add(new ReadEntry { PrintId = f[0], FaceRev = f[1], MotionRev = f[2], Frames = frames, Ms = ms, Has = true });
            }
            entries = list;
            return true;
        }
    }

    /// <summary>Visit identity (S5.3). The serial advances ONLY on: a
    /// successful binder or history page change (returning to a prior page
    /// included), a switch between Player Cards subviews, entering the tab
    /// (OnTabEntered: leaving and returning, closing the overlay and
    /// reopening), and a new process (a fresh instance). A page change counts
    /// only when a navigation asked for it within NAV_TTL_S and the shown page
    /// key then moved; a key moved by a sort (Rebase), an api refresh or a
    /// clamp is adopted without advancing. Nothing else calls in: hover, the
    /// popup, scroll, a recycled tile's bindSeq, a repaint, an eviction, focus
    /// and the AnimatedCosmetics toggle never move it.</summary>
    internal sealed class MotionVisit
    {
        internal const double NAV_TTL_S = 10.0;
        internal int Serial { get; private set; } = 1;
        private string _pageKey;
        private string _view;
        private double _navAt = double.NegativeInfinity;
        private bool _rebase;

        internal void TabEntered() { Serial++; }

        internal void ViewShown(string view)
        {
            if (_view != null && view != _view) Serial++;
            _view = view;
        }

        internal void NavRequested(double now) { _navAt = now; }

        /// <summary>The next page key moves by a reorder, not a navigation.</summary>
        internal void Rebase() { _rebase = true; }

        internal void PageShown(string key, double now)
        {
            if (key == _pageKey) { _rebase = false; return; }
            bool nav = _pageKey != null && !_rebase && now - _navAt <= NAV_TTL_S;
            _pageKey = key;
            _rebase = false;
            if (nav) { _navAt = double.NegativeInfinity; Serial++; }
        }
    }

    internal enum ClipState { None, Playing, Done }

    /// <summary>The clip per (visit, print) (S5.4): NONE -> PLAYING(t0) ->
    /// DONE. State is keyed by the print within the CURRENT visit only;
    /// entries of older visits are dropped when the serial moves. The frame
    /// index is floor((now - t0) * 1000 / ms) of real time (Time.unscaledTime
    /// on the seat), never a count of ticks; at index >= frames the clip is
    /// DONE and the static face beneath shows.</summary>
    internal sealed class MotionClips
    {
        internal sealed class Clip
        {
            internal ClipState State;
            internal double T0;
            internal int Frames, Ms, Ticks;
        }

        private int _serial;
        private readonly Dictionary<string, Clip> _clips = new Dictionary<string, Clip>(StringComparer.Ordinal);

        internal int Count { get { return _clips.Count; } }

        internal void Sync(int serial)
        {
            if (serial == _serial) return;
            _serial = serial;
            _clips.Clear();
        }

        /// <summary>The clip of `printId` in the current visit (created NONE).
        /// `bindSeq` is the tile's binding sequence; it is NOT part of the key
        /// (a recycled tile binding is not a new visit, S5.3).</summary>
        internal Clip Get(string printId, int bindSeq)
        {
            string key = printId;
            Clip c;
            if (!_clips.TryGetValue(key, out c)) { c = new Clip(); _clips[key] = c; }
            return c;
        }

        internal bool TryGet(string printId, out Clip c) { return _clips.TryGetValue(printId, out c); }

        internal static void Start(Clip c, double now, int frames, int ms)
        {
            c.State = ClipState.Playing; c.T0 = now; c.Frames = frames; c.Ms = ms; c.Ticks = 0;
        }

        /// <summary>The frame to show now, or -1 when the clip is not playing
        /// (DONE after its last frame). Called once per tick per playing clip.</summary>
        internal static int Frame(Clip c, double now)
        {
            if (c == null || c.State != ClipState.Playing || c.Ms <= 0) return -1;
            c.Ticks++;
            double el = now - c.T0;
            int k = el <= 0 ? 0 : (int)Math.Floor(el * 1000.0 / c.Ms);
            if (k >= c.Frames) { c.State = ClipState.Done; return -1; }
            return k;
        }

        /// <summary>AnimatedCosmetics turned off (S5.8): every clip of the
        /// current visit is DONE at once, so the static face shows.</summary>
        internal void MarkAllDone()
        {
            foreach (var c in _clips.Values) c.State = ClipState.Done;
        }

        internal void Clear() { _clips.Clear(); }
    }

    /// <summary>The motion request policy (S5.6, S2.7): any non-200 ends
    /// motion requests for the current visit, except ONE retry per key of a
    /// 503 motion_pending after its retry_after; a 429 also stops every motion
    /// request for 60 s of real time, across visits.</summary>
    internal sealed class MotionRequestGate
    {
        internal enum Next { Use, Retry, Stop }
        private int _stoppedSerial = -1;
        private int _retrySerial = -1;
        private double _coolUntil = double.NegativeInfinity;
        private readonly HashSet<string> _retried = new HashSet<string>(StringComparer.Ordinal);

        internal double CoolUntil { get { return _coolUntil; } }

        internal bool Allowed(int serial, double now) { return serial != _stoppedSerial && now >= _coolUntil; }

        internal Next OnAnswer(int serial, double now, int status, string error, int retryAfter, string key, out double retryAt)
        {
            retryAt = 0;
            if (status == 200) return Next.Use;
            if (status == 429)
            {
                _coolUntil = now + PlayerCardMotionCore.COOLDOWN_429_S;
                _stoppedSerial = serial;
                return Next.Stop;
            }
            if (serial != _retrySerial) { _retrySerial = serial; _retried.Clear(); }
            if (status == 503 && error == "motion_pending" && key != null && _retried.Add(key))
            {
                retryAt = now + Math.Max(1, retryAfter);
                return Next.Retry;
            }
            _stoppedSerial = serial;
            return Next.Stop;
        }

        internal void Reset() { _stoppedSerial = -1; _retrySerial = -1; _retried.Clear(); }
    }

    /// <summary>The decoded-atlas budget (S5.6): an LRU keyed (print,
    /// motion_rev, size), each entry counted as width x height x 4, capped at
    /// 64 MiB. Entries with a live overlay are pinned and never evicted; when
    /// every remaining entry is pinned the cap is exceeded rather than a face
    /// blanked (PlayerCardFaces.Admit's rule). An evicted key is handed to
    /// `release`, which destroys every cell sprite and then the texture.</summary>
    internal sealed class AtlasBudget
    {
        private sealed class E { internal long Bytes; internal double LastUse; }
        private readonly Dictionary<string, E> _e = new Dictionary<string, E>(StringComparer.Ordinal);
        private HashSet<string> _pinned = new HashSet<string>(StringComparer.Ordinal);
        internal long Cap = PlayerCardMotionCore.CACHE_CAP_BYTES;
        internal long Total { get; private set; }
        internal int Count { get { return _e.Count; } }
        internal long Evictions { get; private set; }

        internal bool Contains(string key) { return _e.ContainsKey(key); }

        internal void Touch(string key, double now) { E e; if (_e.TryGetValue(key, out e)) e.LastUse = now; }

        /// <summary>The keys with a live overlay now (recomputed every tick).</summary>
        internal void SetPinned(HashSet<string> keys) { _pinned = keys ?? new HashSet<string>(StringComparer.Ordinal); }

        /// <summary>Make room for `bytes` under the cap, then add `key`.</summary>
        internal void Admit(string key, long bytes, double now, Action<string> release)
        {
            if (_e.ContainsKey(key)) Remove(key, release);
            while (Total + bytes > Cap && _e.Count > 0)
            {
                string oldest = null; double t = double.MaxValue;
                foreach (var kv in _e)
                {
                    if (_pinned.Contains(kv.Key)) continue;
                    if (kv.Value.LastUse < t) { t = kv.Value.LastUse; oldest = kv.Key; }
                }
                if (oldest == null) break;
                Remove(oldest, release);
                Evictions++;
            }
            _e[key] = new E { Bytes = bytes, LastUse = now };
            Total += bytes;
        }

        internal void Remove(string key, Action<string> release)
        {
            E e;
            if (!_e.TryGetValue(key, out e)) return;
            _e.Remove(key);
            Total -= e.Bytes;
            if (release != null) release(key);
        }

        internal void Clear(Action<string> release)
        {
            var keys = new List<string>(_e.Keys);
            foreach (var k in keys) Remove(k, release);
            Total = 0;
        }
    }

    /// <summary>At most `Max` main-thread decode steps (one texture band
    /// upload) per Unity frame (S5.6, finding M9): the caller asks with the
    /// frame number before each step.</summary>
    internal sealed class FrameGate
    {
        internal int Max = 1;
        private int _frame = int.MinValue;
        private int _used;

        internal bool TryTake(int frame)
        {
            if (frame != _frame) { _frame = frame; _used = 0; }
            if (_used >= Max) return false;
            _used++;
            return true;
        }
    }
}
