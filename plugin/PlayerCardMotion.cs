using System;
using System.Collections.Generic;
using System.Threading;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Dance cards playback (design S5.1-S5.7): the visit's motion
    /// read, the decoded-atlas cache, the overlays and the tick. The pure half
    /// (visit identity, clip clock, request gate, budget, decode gate) is
    /// PlayerCardMotionCore; this file drives it from PlayerCardsUI.MaybeTick.
    ///
    /// Per visit, ONE read asks the motion state of the page's visible,
    /// non-discarded prints that carry a face revision (at most ten, plus the
    /// popup's print when it opens); a print plays only when the answer's
    /// face_rev equals the one its face is showing. An atlas is downloaded
    /// (at most two in flight), its IHDR checked before anything allocates by
    /// it, inflated and unfiltered into one-cell-row bands on a worker thread,
    /// and uploaded ONE band per Unity frame (finding M9: never a whole-atlas
    /// LoadImage on the main thread), each band a non-readable texture with
    /// its cells' sprites. The clip is NONE -> PLAYING(t0) -> DONE by real
    /// time; at DONE the overlay hides and the static face beneath shows.</summary>
    internal static partial class PlayerCardMotion
    {
        internal const int MAX_DOWNLOADS = 2;   // S5.6
        internal const int READ_TILES = 10;     // S5.2: ten tiles, plus the popup's print

        /// <summary>One face the playback may cover, a tile's or the popup's.
        /// PlayerCardsUI refills a pooled list of these every tick.</summary>
        internal sealed class Slot
        {
            internal GameObject Face;          // the Image the static face is on (null until it lands, for the popup)
            internal ApiClient.PcPrint Print;  // the print bound to it now
            internal int BindSeq;              // the tile's binding sequence (never a visit identity, S5.3)
        }

        private sealed class Entry
        {
            internal string FaceRev, MotionRev, Locale, TileKey, CardKey;
            internal int Frames, Ms;
            internal bool Has;
        }

        private enum AtlasState { Queued, Downloading, Decoding, Uploading, Ready, Failed }

        private sealed class Atlas
        {
            internal string Key, PrintId, MotionRev, Locale, Size;
            internal int Frames, Ms, Cell, W, H, Rows, NextBand;
            internal long Bytes;
            internal AtlasState State;
            internal bool Wanted, Admitted;
            internal double RetryAt;
            internal volatile bool Cancel, DecodeDone;
            internal List<byte[]> Bands;   // written by the worker before DecodeDone
            internal Texture2D[] Tex;
            internal Sprite[] Cells;
        }

        private sealed class Overlay
        {
            internal GameObject Go, Face;
            internal Sprite Shown;
        }

        private static readonly MotionVisit visit = new MotionVisit();
        private static readonly MotionClips clips = new MotionClips();
        private static readonly MotionRequestGate gate = new MotionRequestGate();
        private static readonly AtlasBudget budget = new AtlasBudget();
        private static readonly FrameGate frameGate = new FrameGate();
        private static readonly Dictionary<string, Entry> entries = new Dictionary<string, Entry>(StringComparer.Ordinal);
        private static readonly HashSet<string> asked = new HashSet<string>(StringComparer.Ordinal);
        private static readonly Dictionary<string, Atlas> atlases = new Dictionary<string, Atlas>(StringComparer.Ordinal);
        private static readonly List<Atlas> queue = new List<Atlas>();
        private static readonly Dictionary<int, Overlay> overlays = new Dictionary<int, Overlay>();
        private static readonly HashSet<string> pinned = new HashSet<string>(StringComparer.Ordinal);
        private static readonly HashSet<int> driven = new HashSet<int>();
        private static readonly List<string> scratchIds = new List<string>(PlayerCardMotionCore.READ_MAX_IDS);
        private static readonly List<int> scratchInts = new List<int>();
        private static readonly List<Atlas> scratchAtlas = new List<Atlas>();
        private static int generation, entriesSerial = -1, readToken, downloads, popupFaceId;
        private static bool readInFlight, animOn = true;
        private static double readRetryAt;
        private static readonly Action<string> releaseKey = ReleaseKey;

        internal static int Serial => visit.Serial;
        internal static int Generation => generation;
        internal static long CachedBytes => budget.Total;
        internal static int CachedCount => budget.Count;
        internal static int OverlayCount => overlays.Count;

        // -- visit events (S5.3), called by PlayerCardsUI -------------------------

        /// <summary>The Collection tab was entered (leaving and returning,
        /// closing the overlay and reopening onto it).</summary>
        internal static void TabEntered() { visit.TabEntered(); }

        /// <summary>A binder or history page change was asked for; it counts
        /// when the shown page then moves (MotionVisit.PageShown).</summary>
        internal static void NavRequested() { visit.NavRequested(Time.unscaledTime); }

        /// <summary>The page order changed (sort): the next page move is a
        /// reorder, not a visit.</summary>
        internal static void Rebase() { visit.Rebase(); }

        // -- teardown (S5.7) -------------------------------------------------------

        /// <summary>OnOverlayClosed: every overlay stops; state is kept.</summary>
        internal static void Stop() { HideAll(); }

        /// <summary>HideCardPopup: the popup's overlay goes with the popup (its
        /// face is destroyed with it); the clip state is kept.</summary>
        internal static void PopupClosed()
        {
            if (popupFaceId == 0) return;
            Overlay ov;
            if (overlays.TryGetValue(popupFaceId, out ov))
            {
                overlays.Remove(popupFaceId);
                if (ov.Go != null) { try { UnityEngine.Object.Destroy(ov.Go); } catch { } }
            }
            popupFaceId = 0;
        }

        /// <summary>Every PlayerCardFaces.Clear() site and TeardownOverlaySurfaces:
        /// the generation moves (every answer in flight is dropped), every
        /// overlay, sprite and texture is destroyed, and the visit's reads and
        /// clips are forgotten. The 429 cooldown survives (S2.7).</summary>
        internal static void Clear()
        {
            generation++;
            readToken++; readInFlight = false; readRetryAt = 0; downloads = 0; popupFaceId = 0;
            foreach (var ov in overlays.Values)
                if (ov.Go != null) { try { UnityEngine.Object.Destroy(ov.Go); } catch { } }
            overlays.Clear();
            budget.Clear(releaseKey);
            foreach (var a in atlases.Values) { a.Cancel = true; DestroyAtlas(a); }
            atlases.Clear(); queue.Clear();
            entries.Clear(); asked.Clear(); clips.Clear(); gate.Reset();
            entriesSerial = -1;
            DevOnClear();
        }

        // -- the tick (S5.7) -------------------------------------------------------

        /// <summary>From PlayerCardsUI.MaybeTick on every call, before its
        /// two-second throttle. `showing`: the Collection tab or the popup is
        /// up. `pending`: the overlay was closed and reopened and that visit is
        /// not counted yet (nothing is asked under the old serial). `tiles`:
        /// the page's active tiles with a print; `popup`: the card view, or null.</summary>
        internal static void Tick(bool showing, bool pending, string view, string pageKey, List<Slot> tiles, Slot popup)
        {
            long t0 = DevTickStart();
            try { TickInner(showing, pending, view, pageKey, tiles, popup); }
            finally { DevTickEnd(t0); }
        }

        private static void TickInner(bool showing, bool pending, string view, string pageKey, List<Slot> tiles, Slot popup)
        {
            DevPumpDue();
            double now = Time.unscaledTime;
            if (!showing || pending) { HideAll(); return; }   // stops every overlay, advances nothing
            visit.ViewShown(view);
            if (pageKey != null) visit.PageShown(pageKey, now);
            int serial = visit.Serial;
            if (serial != entriesSerial) NewVisit(serial);
            popupFaceId = popup != null && popup.Face != null ? popup.Face.GetInstanceID() : 0;

            bool anim = !DevAnimOff && (Plugin.AnimatedCosmetics == null || Plugin.AnimatedCosmetics.Value);
            if (!anim)
            {
                // S5.8: static at once, and the visit's prints DONE; this
                // viewer's reads and playback only.
                if (animOn) { clips.MarkAllDone(); animOn = false; }
                if (tiles != null) for (int i = 0; i < tiles.Count; i++) MarkDone(tiles[i]);
                MarkDone(popup);
                HideAll();
                return;
            }
            animOn = true;

            MaybeRead(serial, now, tiles, popup);
            for (int i = 0; i < queue.Count; i++) queue[i].Wanted = false;
            pinned.Clear(); driven.Clear();
            // With the popup up the page beneath is hidden: its overlays stop and
            // its atlases unpin, so one card atlas fits (S5.6).
            if (popup != null) Drive(popup, now, true);
            else if (tiles != null) for (int i = 0; i < tiles.Count; i++) Drive(tiles[i], now, false);
            budget.SetPinned(pinned);
            HideUndriven();
            Pump(now, serial);
            UploadBands();
        }

        private static void NewVisit(int serial)
        {
            entriesSerial = serial;
            entries.Clear(); asked.Clear();
            readToken++; readInFlight = false; readRetryAt = 0;
            clips.Sync(serial);
            // Queued and failed atlases were this visit's: nothing is retried
            // until the next one (S5.6), and the next one is now.
            scratchAtlas.Clear();
            foreach (var a in atlases.Values) if (a.State == AtlasState.Queued || a.State == AtlasState.Failed) scratchAtlas.Add(a);
            foreach (var a in scratchAtlas) { atlases.Remove(a.Key); DestroyAtlas(a); }
            queue.Clear();
        }

        private static void MarkDone(Slot s)
        {
            if (s == null || s.Print == null || string.IsNullOrEmpty(s.Print.print_id)) return;
            var c = clips.Get(ClipKey(s), s.BindSeq);
            c.State = ClipState.Done;
        }

        private static string ClipKey(Slot s)
        {
            return DevT39KeyByBind ? s.Print.print_id + "#" + s.BindSeq : s.Print.print_id;
        }

        // -- the per-visit read (S5.2) ---------------------------------------------

        private static bool ReadsAllowed()
        {
            // Only a server whose /pc/me carries the dance keys has the motion
            // routes: a new client never asks an older server for a route it
            // does not have (S5.8 still reads any 404 as static).
            if (DevFake != null) return true;
            var me = ApiClient.CachedPcMe;
            return me != null && me.dance_supported;
        }

        private static bool Eligible(ApiClient.PcPrint p)
        {
            return p != null && !p.discarded && !string.IsNullOrEmpty(p.print_id) && !string.IsNullOrEmpty(p.face_rev);
        }

        private static void Collect(ApiClient.PcPrint p, ref string locale)
        {
            if (!Eligible(p) || asked.Contains(p.print_id) || scratchIds.Contains(p.print_id)) return;
            string loc = string.IsNullOrEmpty(p.face_locale) ? "en" : p.face_locale;
            if (locale == null) locale = loc;
            else if (loc != locale) return;   // another language's face: the next read
            scratchIds.Add(p.print_id);
        }

        private static void MaybeRead(int serial, double now, List<Slot> tiles, Slot popup)
        {
            if (readInFlight || now < readRetryAt || !ReadsAllowed() || !gate.Allowed(serial, now)) return;
            scratchIds.Clear();
            string locale = null;
            if (popup != null) Collect(popup.Print, ref locale);
            else if (tiles != null)
                for (int i = 0; i < tiles.Count && scratchIds.Count < READ_TILES; i++) Collect(tiles[i].Print, ref locale);
            if (scratchIds.Count == 0) return;
            var ids = new List<string>(scratchIds);
            foreach (var id in ids) asked.Add(id);
            readInFlight = true;
            int token = ++readToken, gen = generation;
            string loc = locale ?? "en";
            SendRead(ids, loc, (ok, resp) => OnRead(token, gen, serial, ids, loc, ok, resp));
        }

        private static void OnRead(int token, int gen, int serial, List<string> ids, string locale, bool ok, string resp)
        {
            if (token != readToken || gen != generation) return;
            readInFlight = false;
            if (serial != visit.Serial) return;   // another visit's answer (S5.3)
            double now = Time.unscaledTime;
            List<PlayerCardMotionCore.ReadEntry> list = null;
            string m = ok ? ApiClient.PcStr(ApiClient.PcTopLevel(resp, "m")) : null;
            if (ok && m != null && PlayerCardMotionCore.ParseRead(m, ids, out list))
            {
                int has = 0;
                foreach (var r in list)
                {
                    var e = new Entry { Has = r.Has, Locale = locale };
                    if (r.Has)
                    {
                        e.FaceRev = r.FaceRev; e.MotionRev = r.MotionRev; e.Frames = r.Frames; e.Ms = r.Ms;
                        e.TileKey = AtlasKey(r.PrintId, r.MotionRev, locale, "tile");
                        e.CardKey = AtlasKey(r.PrintId, r.MotionRev, locale, "card");
                        has++;
                    }
                    entries[r.PrintId] = e;
                }
                Plugin.Log.LogInfo($"[MOTION] read {ids.Count} print(s): {has} with motion (visit {serial})");
                return;
            }
            // A refusal, or a 200 this client cannot read, ends the visit's motion
            // requests; a 429 also stops them for 60 s across visits (S5.6, S2.7).
            int code = ok ? 0 : ApiClient.PcHttpCode(resp);
            string err = ok ? "unreadable" : ApiClient.PcErrorCode(resp);
            double retryAt;
            var next = gate.OnAnswer(serial, now, DevStatus(code), err, ApiClient.PcRetryAfterRaw(resp), "read", out retryAt);
            if (next == MotionRequestGate.Next.Retry) { foreach (var id in ids) asked.Remove(id); readRetryAt = retryAt; }
            Plugin.Log.LogInfo($"[MOTION] read refused: HTTP {code} {err} -> {next} (visit {serial})");
        }

        private static string AtlasKey(string printId, string rev, string locale, string size)
        {
            return printId + "/" + rev + "/" + locale + "/" + size;
        }

        // -- the overlays (S5.4, S5.5) ---------------------------------------------

        private static void Drive(Slot s, double now, bool card)
        {
            var face = s.Face; var p = s.Print;
            if (face == null || !Eligible(p) || !face.activeInHierarchy) return;
            Entry e;
            string loc = string.IsNullOrEmpty(p.face_locale) ? "en" : p.face_locale;
            if (!entries.TryGetValue(p.print_id, out e) || !e.Has || e.FaceRev != p.face_rev || e.Locale != loc) return;
            var c = clips.Get(ClipKey(s), s.BindSeq);
            if (c.State == ClipState.Done) return;
            string key = card ? e.CardKey : e.TileKey;
            Atlas a;
            if (!atlases.TryGetValue(key, out a)) a = Want(key, p.print_id, e, card ? "card" : "tile", card);
            pinned.Add(key);   // wanted on screen now: never evicted from under it
            if (a.State == AtlasState.Queued) a.Wanted = true;
            if (a.State != AtlasState.Ready) return;
            budget.Touch(key, now);
            if (c.State == ClipState.None) MotionClips.Start(c, now, e.Frames, e.Ms);
            int k = FrameOf(c, now);
            if (k < 0 || k >= a.Cells.Length || a.Cells[k] == null) return;
            Show(face, a.Cells[k]);
        }

        private static int FrameOf(MotionClips.Clip c, double now)
        {
            if (!DevFrameByTicks) return MotionClips.Frame(c, now);
            // T41's mutant arm only: the index counted in ticks
            if (c.State != ClipState.Playing) return -1;
            int k = c.Ticks++;
            if (k >= c.Frames) { c.State = ClipState.Done; return -1; }
            return k;
        }

        private static void Show(GameObject face, Sprite spr)
        {
            int id = face.GetInstanceID();
            Overlay ov;
            if (!overlays.TryGetValue(id, out ov) || ov.Go == null)
            {
                var go = PlayerCardsUI.CreateMotionOverlay(face);
                if (go == null) return;
                ov = new Overlay { Go = go, Face = face };
                overlays[id] = ov;
            }
            driven.Add(id);
            PlayerCardsUI.PlaceMotionOverlay(face, ov.Go);   // every tick: the slot settles after the face lands
            if (ov.Shown != spr) { UIFactory.SetImageSprite(ov.Go, spr); ov.Shown = spr; }
            if (!ov.Go.activeSelf) ov.Go.SetActive(true);
        }

        private static void HideUndriven()
        {
            scratchInts.Clear();
            foreach (var kv in overlays)
            {
                var ov = kv.Value;
                if (ov.Face == null || ov.Go == null) { scratchInts.Add(kv.Key); continue; }
                if (!driven.Contains(kv.Key) && ov.Go.activeSelf) ov.Go.SetActive(false);
            }
            foreach (int id in scratchInts) Forget(id);
        }

        private static void HideAll()
        {
            scratchInts.Clear();
            foreach (var kv in overlays)
            {
                var ov = kv.Value;
                if (ov.Face == null || ov.Go == null) { scratchInts.Add(kv.Key); continue; }
                if (ov.Go.activeSelf) ov.Go.SetActive(false);
            }
            foreach (int id in scratchInts) Forget(id);
        }

        private static void Forget(int id)
        {
            Overlay ov;
            if (!overlays.TryGetValue(id, out ov)) return;
            overlays.Remove(id);
            if (ov.Go != null) { try { UnityEngine.Object.Destroy(ov.Go); } catch { } }
        }

        // -- fetch and memory (S5.6) -----------------------------------------------

        private static Atlas Want(string key, string printId, Entry e, string size, bool front)
        {
            var a = new Atlas { Key = key, PrintId = printId, MotionRev = e.MotionRev, Locale = e.Locale, Size = size, Frames = e.Frames, Ms = e.Ms, State = AtlasState.Queued, Wanted = true };
            int cell, w, h;
            if (!PlayerCardMotionCore.AtlasShape(e.Frames, size, out cell, out w, out h)) a.State = AtlasState.Failed;
            else { a.Cell = cell; a.W = w; a.H = h; a.Rows = h / cell; a.Bytes = (long)w * h * 4; }
            atlases[key] = a;
            if (a.State == AtlasState.Queued) { if (front) queue.Insert(0, a); else queue.Add(a); }
            return a;
        }

        private static void Pump(double now, int serial)
        {
            if (!gate.Allowed(serial, now)) return;   // any refusal ends the visit's requests
            for (int i = 0; i < queue.Count && downloads < MAX_DOWNLOADS;)
            {
                var a = queue[i];
                if (a.State != AtlasState.Queued) { queue.RemoveAt(i); continue; }
                if (!a.Wanted) { queue.RemoveAt(i); atlases.Remove(a.Key); continue; }   // off screen before it started
                if (now < a.RetryAt) { i++; continue; }
                queue.RemoveAt(i);
                Download(a, serial);
            }
        }

        private static void Download(Atlas a, int serial)
        {
            a.State = AtlasState.Downloading;
            downloads++;
            int gen = generation;
            string url = ApiClient.PcMotionAtlasUrl(a.PrintId, a.MotionRev, a.Locale, a.Size);
            SendAtlas(url, PlayerCardMotionCore.AtlasByteCap(a.Size), a.PrintId, a.Size, (ok, data, code, err) => OnAtlas(gen, serial, a, ok, data, code, err));
        }

        private static void OnAtlas(int gen, int serial, Atlas a, bool ok, byte[] data, long code, string err)
        {
            if (gen != generation) return;   // Clear() moved: dropped undecoded
            if (downloads > 0) downloads--;
            Atlas live;
            if (a.Cancel || !atlases.TryGetValue(a.Key, out live) || live != a) return;
            double now = Time.unscaledTime;
            if (!ok || data == null)
            {
                double retryAt;
                var next = gate.OnAnswer(serial, now, DevStatus((int)code), ApiClient.PcErrorCode(err), ApiClient.PcRetryAfterRaw(err), a.Key, out retryAt);
                if (serial != visit.Serial) atlases.Remove(a.Key);   // an older visit's request: the current visit may ask once itself
                else if (next == MotionRequestGate.Next.Retry)
                {
                    a.State = AtlasState.Queued; a.RetryAt = retryAt; a.Wanted = true;
                    queue.Add(a);
                }
                else a.State = AtlasState.Failed;
                Plugin.Log.LogInfo($"[MOTION] atlas {a.Size} {a.PrintId}: HTTP {code} -> {next}");
                return;
            }
            if (!PlayerCardMotionCore.AtlasHeaderOk(data, a.Frames, a.Size))
            {
                a.State = AtlasState.Failed;
                Plugin.Log.LogWarning($"[MOTION] atlas {a.Size} {a.PrintId}: header refused");
                return;
            }
            budget.Admit(a.Key, a.Bytes, now, releaseKey);
            a.Admitted = true;
            a.State = AtlasState.Decoding;
            var png = data;
            ThreadPool.QueueUserWorkItem(_ => Decode(a, png));
        }

        /// <summary>The worker half (M9): inflate and unfilter of the checked
        /// 8-bit RGBA subset into one-cell-row bands, each stored bottom-up for
        /// LoadRawTextureData. Nothing Unity is touched here.</summary>
        private static void Decode(Atlas a, byte[] png)
        {
            List<byte[]> bands = null;
            try { bands = ScrPng.DecodeBandsRgba8(png, a.W, a.H, a.Cell, () => a.Cancel); }
            catch { bands = null; }
            a.Bands = bands;
            a.DecodeDone = true;
        }

        /// <summary>The main-thread half (M9): at most one band upload per Unity
        /// frame across every atlas (FrameGate), the band's cell sprites made
        /// with it; a decoded atlas is Ready when its last band is up.</summary>
        private static void UploadBands()
        {
            scratchAtlas.Clear();
            Atlas next = null;
            foreach (var a in atlases.Values)
            {
                if (a.State == AtlasState.Decoding && a.DecodeDone)
                {
                    if (a.Bands == null || a.Bands.Count != a.Rows) { scratchAtlas.Add(a); continue; }
                    a.State = AtlasState.Uploading;
                    a.Tex = new Texture2D[a.Rows];
                    a.Cells = new Sprite[a.Frames];
                    a.NextBand = 0;
                }
                if (a.State == AtlasState.Uploading && (next == null || (pinned.Contains(a.Key) && !pinned.Contains(next.Key)))) next = a;
            }
            foreach (var a in scratchAtlas) FailDecoded(a, "decode refused");
            // Finding S2F10: the FrameGate is the only limit on uploads per Unity
            // frame. It is asked again after every band, so a gate that admits two
            // (T50's mutant, max=2) really puts two bands in one frame; with the
            // product's Max = 1 the second ask is refused, as the single call was.
            while (next != null && frameGate.TryTake(Time.frameCount))
            {
                try { UploadBand(next); }
                catch (Exception ex) { FailDecoded(next, "band upload threw " + ex.Message); }
                next = NextUploading();
            }
        }

        /// <summary>The atlas whose band goes up next: an Uploading one, a
        /// pinned one first (UploadBands' own rule).</summary>
        private static Atlas NextUploading()
        {
            Atlas next = null;
            foreach (var a in atlases.Values)
                if (a.State == AtlasState.Uploading && (next == null || (pinned.Contains(a.Key) && !pinned.Contains(next.Key)))) next = a;
            return next;
        }

        private static void UploadBand(Atlas a)
        {
            int b = a.NextBand;
            var band = a.Bands[b];
            int rows = band.Length / (a.W * 4);
            var tex = new Texture2D(a.W, rows, TextureFormat.RGBA32, false);
            tex.name = "DcMoTex";   // T40 counts these by name
            tex.filterMode = FilterMode.Bilinear;
            tex.wrapMode = TextureWrapMode.Clamp;
            a.Tex[b] = tex;
            tex.LoadRawTextureData(band);
            tex.Apply(false, true);   // on the GPU; the CPU copy is released (non-readable)
            DevStall(band.Length);
            a.Bands[b] = null;
            int first = b * PlayerCardMotionCore.ATLAS_COLUMNS;
            for (int col = 0; col < PlayerCardMotionCore.ATLAS_COLUMNS && first + col < a.Frames; col++)
            {
                var spr = Sprite.Create(tex, new Rect(col * a.Cell, 0, a.Cell, a.Cell), new Vector2(0.5f, 0.5f), 100f);
                spr.name = "DcMoCell";
                a.Cells[first + col] = spr;
            }
            a.NextBand++;
            if (a.NextBand >= a.Rows) { a.State = AtlasState.Ready; a.Bands = null; DevAtlasReady(a.Key, a.Size); }
        }

        private static void FailDecoded(Atlas a, string why)
        {
            if (a.Admitted) { budget.Remove(a.Key, null); a.Admitted = false; }
            DestroyAtlas(a);
            a.State = AtlasState.Failed;   // kept for the visit: never re-fetched in a loop
            Plugin.Log.LogWarning($"[MOTION] atlas {a.Size} {a.PrintId}: {why}");
        }

        /// <summary>The budget evicted `key` (or Clear() emptied it): every cell
        /// sprite, then the textures (S5.6).</summary>
        private static void ReleaseKey(string key)
        {
            Atlas a;
            if (!atlases.TryGetValue(key, out a)) return;
            atlases.Remove(key);
            a.Admitted = false;
            DestroyAtlas(a);
        }

        private static void DestroyAtlas(Atlas a)
        {
            a.Cancel = true;
            a.Bands = null;
            if (a.Cells != null)
            {
                foreach (var ov in overlays.Values)
                    if (ov.Shown != null && Array.IndexOf(a.Cells, ov.Shown) >= 0)
                    {
                        if (ov.Go != null) { UIFactory.SetImageSprite(ov.Go, null); ov.Go.SetActive(false); }
                        ov.Shown = null;
                    }
                if (!DevSkipSpriteDestroy)
                    for (int i = 0; i < a.Cells.Length; i++)
                        if (a.Cells[i] != null) { try { UnityEngine.Object.Destroy(a.Cells[i]); } catch { } }
                a.Cells = null;
            }
            if (a.Tex != null)
            {
                for (int i = 0; i < a.Tex.Length; i++)
                    if (a.Tex[i] != null) { try { UnityEngine.Object.Destroy(a.Tex[i]); } catch { } }
                a.Tex = null;
            }
        }

        // -- transport -------------------------------------------------------------

        private static void SendRead(List<string> ids, string locale, Action<bool, string> cb)
        {
            DevCount(true);
            if (DevFake != null) { DevFakeRead(ids, locale, cb); return; }
            ApiClient.PcMotionRead(ids, locale, cb);
        }

        private static void SendAtlas(string url, int cap, string printId, string size, Action<bool, byte[], long, string> cb)
        {
            DevCount(false);
            if (DevFake != null) { DevFakeAtlas(printId, size, cb); return; }
            ApiClient.FetchMotionAtlas(url, cap, cb);
        }
    }
}
