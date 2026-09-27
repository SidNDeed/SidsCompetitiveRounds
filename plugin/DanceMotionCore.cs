using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>The capture's pure half (dance cards design S1.4 steps 7-9,
    /// S1.6, S2.3-S2.5): the container, the frame matte and grade, the
    /// client's own copy of the server's content checks, and the upload order.
    /// No UnityEngine reference: the capture job runs these on its worker
    /// thread, and tools/tests/dance-cards-client compiles this same file.
    ///
    /// Every constant below is the server's (backend/api/pc_motion.py); the
    /// client checks them so a defect costs the owner a log line, not an
    /// upload (S1.6). The server measures everything again and trusts none of
    /// it (S1.9).</summary>
    internal static class DanceMotionCore
    {
        internal const string CONTENT_TYPE = "application/x-scr-motion";
        internal static readonly byte[] MAGIC = Encoding.ASCII.GetBytes("SCRMOT1\n");
        internal const int HEADER_MAX = 512;
        internal const int FRAME_MAX_BYTES = 262144;
        internal const int TOTAL_MAX_BYTES = 12 << 20;
        internal const int FRAME_EDGE = 590;
        internal const int FRAMES_MAX = 120;
        internal const int EDGE_MARGIN = 2;
        internal const double COVERAGE_MIN = 0.02, COVERAGE_MAX = 0.60;
        /// <summary>|dY| at or above this many 8-bit steps counts a pixel as
        /// changed: int(0.05 * 255) + 1, pc_motion._CHANGED_STEPS.</summary>
        internal const int FLASH_CHANGED_STEPS = 13;
        internal const double FLASH_CHANGED_MAX = 0.35, FLASH_MEAN_MAX = 0.20;
        /// <summary>The portrait background the flash check composites over:
        /// face_layout_v1.json portrait_bg #0C0F20.</summary>
        internal const int BG_R = 12, BG_G = 15, BG_B = 32;
        /// <summary>PortraitRender.PROBE_FLOOR: an alpha above it counts as lit.</summary>
        internal const int LIT_FLOOR = 8;

        // -- the container (S2.3) ------------------------------------------------

        /// <summary>The header grammar's dance group: `dance_` then 1-24 of a-z.</summary>
        internal static bool SkuOk(string sku)
        {
            if (sku == null || sku.Length < 7 || sku.Length > 30 || !sku.StartsWith("dance_", StringComparison.Ordinal)) return false;
            for (int i = 6; i < sku.Length; i++) if (sku[i] < 'a' || sku[i] > 'z') return false;
            return true;
        }

        /// <summary>64 lowercase hex characters: a still hash as the server
        /// writes it.</summary>
        internal static bool HexHashOk(string h)
        {
            if (h == null || h.Length != 64) return false;
            foreach (char c in h) if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
            return true;
        }

        /// <summary>`dance=SKU;recipe=R;frames=N;ms=M;static=HASH`, or null
        /// when any field is outside the server's header grammar.</summary>
        internal static string HeaderText(string sku, int recipe, int frames, int ms, string staticHash)
        {
            if (!SkuOk(sku) || recipe < 1 || recipe > 999 || frames < 1 || frames > 999 || ms < 1 || ms > 9999 || !HexHashOk(staticHash)) return null;
            var ci = CultureInfo.InvariantCulture;
            return "dance=" + sku + ";recipe=" + recipe.ToString(ci) + ";frames=" + frames.ToString(ci)
                 + ";ms=" + ms.ToString(ci) + ";static=" + staticHash;
        }

        /// <summary>The bytes the container of these frames will occupy under a
        /// header of `headerLength` bytes: magic, header length, header, and a
        /// 4-byte length before every frame.</summary>
        internal static long ContainerLength(int headerLength, IList<byte[]> frames)
        {
            long n = MAGIC.Length + 4L + headerLength;
            foreach (var f in frames) n += 4L + (f != null ? f.Length : 0);
            return n;
        }

        /// <summary>The one accepted layout (S2.3). Throws ArgumentException
        /// when the header is not 1-512 ASCII bytes, its frame count is not the
        /// number of frames, a frame is empty or above 262144 bytes, or the
        /// whole is above 12 MiB -- the caller has already checked all of it,
        /// so a throw is a defect, never a refusal to report.</summary>
        internal static byte[] BuildContainer(string header, IList<byte[]> frames)
        {
            if (header == null || frames == null) throw new ArgumentException("no header or frames");
            byte[] head = Encoding.ASCII.GetBytes(header);
            if (head.Length < 1 || head.Length > HEADER_MAX || Encoding.ASCII.GetString(head) != header) throw new ArgumentException("header is not 1-512 ASCII bytes");
            if (!header.Contains(";frames=" + frames.Count.ToString(CultureInfo.InvariantCulture) + ";")) throw new ArgumentException("header frame count is not the frame count");
            foreach (var f in frames) if (f == null || f.Length < 1 || f.Length > FRAME_MAX_BYTES) throw new ArgumentException("a frame is empty or above the per-frame cap");
            long total = ContainerLength(head.Length, frames);
            if (total > TOTAL_MAX_BYTES) throw new ArgumentException("the container is above 12 MiB");
            var o = new byte[total];
            int off = 0;
            Buffer.BlockCopy(MAGIC, 0, o, off, MAGIC.Length); off += MAGIC.Length;
            PutBE(o, off, head.Length); off += 4;
            Buffer.BlockCopy(head, 0, o, off, head.Length); off += head.Length;
            foreach (var f in frames)
            {
                PutBE(o, off, f.Length); off += 4;
                Buffer.BlockCopy(f, 0, o, off, f.Length); off += f.Length;
            }
            return o;
        }

        /// <summary>The header and frames of a container of the accepted
        /// layout, or false. The frame count is the header's (the harness and
        /// the seat's corpus check read it back).</summary>
        internal static bool TryParseContainer(byte[] c, out string header, out List<byte[]> frames)
        {
            header = null; frames = null;
            if (c == null || c.Length < 12) return false;
            for (int i = 0; i < MAGIC.Length; i++) if (c[i] != MAGIC[i]) return false;
            int hl = GetBE(c, 8);
            if (hl < 1 || hl > HEADER_MAX || 12L + hl > c.Length) return false;
            for (int i = 12; i < 12 + hl; i++) if (c[i] > 127) return false;
            header = Encoding.ASCII.GetString(c, 12, hl);
            int count = HeaderInt(header, "frames");
            if (count < 1) { header = null; return false; }
            frames = new List<byte[]>(count);
            int off = 12 + hl;
            for (int k = 0; k < count; k++)
            {
                if (off + 4 > c.Length) { header = null; frames = null; return false; }
                int n = GetBE(c, off); off += 4;
                if (n < 1 || n > FRAME_MAX_BYTES || off + (long)n > c.Length) { header = null; frames = null; return false; }
                var f = new byte[n];
                Buffer.BlockCopy(c, off, f, 0, n); off += n;
                frames.Add(f);
            }
            if (off != c.Length) { header = null; frames = null; return false; }
            return true;
        }

        /// <summary>An integer field of a header (`frames`, `ms`, `recipe`), -1 when absent.</summary>
        internal static int HeaderInt(string header, string key)
        {
            if (header == null) return -1;
            foreach (var part in header.Split(';'))
            {
                int eq = part.IndexOf('=');
                if (eq > 0 && part.Substring(0, eq) == key)
                {
                    int v;
                    return int.TryParse(part.Substring(eq + 1), NumberStyles.None, CultureInfo.InvariantCulture, out v) ? v : -1;
                }
            }
            return -1;
        }

        /// <summary>A string field of a header (`dance`, `static`), null when absent.</summary>
        internal static string HeaderStr(string header, string key)
        {
            if (header == null) return null;
            foreach (var part in header.Split(';'))
            {
                int eq = part.IndexOf('=');
                if (eq > 0 && part.Substring(0, eq) == key) return part.Substring(eq + 1);
            }
            return null;
        }

        internal static string Sha256Hex(byte[] data)
        {
            using (var h = SHA256.Create())
            {
                var d = h.ComputeHash(data);
                var sb = new StringBuilder(64);
                foreach (var b in d) sb.Append(b.ToString("x2", CultureInfo.InvariantCulture));
                return sb.ToString();
            }
        }

        private static void PutBE(byte[] b, int off, int v)
        {
            b[off] = (byte)(v >> 24); b[off + 1] = (byte)(v >> 16); b[off + 2] = (byte)(v >> 8); b[off + 3] = (byte)v;
        }

        private static int GetBE(byte[] b, int off)
        {
            return (b[off] << 24) | (b[off + 1] << 16) | (b[off + 2] << 8) | b[off + 3];
        }

        // -- the matte, the grade, the checks (S1.4 steps 6-7, S1.6, S2.5) ----------

        /// <summary>One colour through the baked grade table (PortraitRender.LutSample).</summary>
        internal delegate void RgbMap(int r, int g, int b, out byte ro, out byte go, out byte bo);

        /// <summary>The #630 difference matte as straight RGBA, the arithmetic of
        /// PortraitRender.MattePixels byte for byte: a = 255 - (the white pass
        /// minus the black pass, summed over r, g, b) / 3, clamped; alpha 0 is
        /// (0,0,0,0); colour is the black pass un-premultiplied, rounded. Counts
        /// what the checks read: lit (a above LIT_FLOOR, the still's gate),
        /// partial (a below 250) and covered (a above 0, the frames' coverage).
        /// The seat's `portrait:dance,matteq` lever proves this equal to
        /// MattePixels on the same pair.</summary>
        internal static void Matte(byte[] black, byte[] white, byte[] o, out int lit, out int partial, out int covered)
        {
            lit = partial = covered = 0;
            int n = black.Length;
            for (int p = 0; p < n; p += 4)
            {
                int br = black[p], bg = black[p + 1], bb = black[p + 2];
                int d = (white[p] - br) + (white[p + 1] - bg) + (white[p + 2] - bb);
                int a = 255 - d / 3;
                if (a < 0) a = 0; else if (a > 255) a = 255;
                if (a == 0) { o[p] = 0; o[p + 1] = 0; o[p + 2] = 0; o[p + 3] = 0; continue; }
                o[p] = Un(br, a); o[p + 1] = Un(bg, a); o[p + 2] = Un(bb, a); o[p + 3] = (byte)a;
                covered++;
                if (a > LIT_FLOOR) lit++;
                if (a < 250) partial++;
            }
        }

        internal static byte Un(int c, int a) { int v = (c * 255 + a / 2) / a; return (byte)(v > 255 ? 255 : v); }

        /// <summary>The grade on straight colour, AFTER the matte and only where
        /// alpha is above 0 (PortraitRender.GradePixels). A null map is a defect:
        /// every product picture is graded.</summary>
        internal static void Grade(byte[] rgba, RgbMap map)
        {
            if (map == null) throw new ArgumentException("no grade table");
            for (int p = 0; p < rgba.Length; p += 4)
            {
                if (rgba[p + 3] == 0) continue;
                byte r, g, b;
                map(rgba[p], rgba[p + 1], rgba[p + 2], out r, out g, out b);
                rgba[p] = r; rgba[p + 1] = g; rgba[p + 2] = b;
            }
        }

        /// <summary>True when no pixel within `margin` of any edge has alpha
        /// above 0 (the server's motion_edge check).</summary>
        internal static bool EdgeClear(byte[] rgba, int w, int h, int margin)
        {
            for (int y = 0; y < h; y++)
            {
                bool band = y < margin || y >= h - margin;
                int row = y * w * 4;
                if (band)
                {
                    for (int x = 0; x < w; x++) if (rgba[row + x * 4 + 3] != 0) return false;
                }
                else
                {
                    for (int x = 0; x < margin; x++)
                        if (rgba[row + x * 4 + 3] != 0 || rgba[row + (w - 1 - x) * 4 + 3] != 0) return false;
                }
            }
            return true;
        }

        /// <summary>The 8-bit Rec. 709 luma of the frame composited over the
        /// portrait background, as pc_motion.luma computes it with Pillow:
        /// alpha_composite (integer, 7 precision bits, SHIFTFORDIV255), then
        /// the RGB-to-L matrix in single precision, left to right, plus 0.5
        /// and truncated. The harness case luma_pillow (tools/tests/
        /// dance-cards-client) compares it with pc_motion.luma over every
        /// opaque RGB triple and every (value, alpha) pair.</summary>
        internal static void LumaOverBg(byte[] rgba, byte[] y)
        {
            for (int i = 0, p = 0; i < y.Length; i++, p += 4)
            {
                int a = rgba[p + 3];
                int r, g, b;
                if (a == 0) { r = BG_R; g = BG_G; b = BG_B; }
                else
                {
                    // Pillow AlphaComposite.c with dst alpha 255
                    uint blend = 255u * (uint)(255 - a);
                    uint outa255 = (uint)a * 255u + blend;
                    uint coef1 = (uint)a * 255u * 255u * 128u / outa255;
                    uint coef2 = 255u * 128u - coef1;
                    r = Comp(rgba[p], BG_R, coef1, coef2);
                    g = Comp(rgba[p + 1], BG_G, coef1, coef2);
                    b = Comp(rgba[p + 2], BG_B, coef1, coef2);
                }
                float s = (float)((float)(0.2126f * r) + (float)(0.7152f * g));
                s = (float)(s + (float)(0.0722f * b));
                s = (float)(s + 0.0f);
                double v = (double)s + 0.5;
                y[i] = v <= 0.0 ? (byte)0 : v >= 255.0 ? (byte)255 : (byte)(int)v;
            }
        }

        private static int Comp(int src, int dst, uint coef1, uint coef2)
        {
            uint t = (uint)src * coef1 + (uint)dst * coef2 + (0x80u << 7);
            t = ((t >> 8) + t) >> 8;   // SHIFTFORDIV255
            return (int)(t >> 7);
        }

        /// <summary>(changed fraction, mean |dY|) of two luma images, as
        /// pc_motion.flash_pair reads its difference histogram.</summary>
        internal static void FlashPair(byte[] ya, byte[] yb, out double changed, out double mean)
        {
            long nChanged = 0, sum = 0;
            for (int i = 0; i < ya.Length; i++)
            {
                int d = ya[i] - yb[i];
                if (d < 0) d = -d;
                sum += d;
                if (d >= FLASH_CHANGED_STEPS) nChanged++;
            }
            double n = ya.Length;
            changed = nChanged / n;
            mean = sum / (n * 255.0);
        }

        internal static bool FlashRefused(double changed, double mean) { return changed > FLASH_CHANGED_MAX || mean > FLASH_MEAN_MAX; }

        /// <summary>reduce(4) of a straight RGBA square: the premultiplied 4x4
        /// box average PortraitRender.Reduce4 draws the Settings preview with,
        /// on bytes (rows in, rows out, in the buffer's own order).</summary>
        internal static byte[] Reduce4(byte[] rgba, int size)
        {
            int n = size / 4;
            var o = new byte[n * n * 4];
            for (int y = 0; y < n; y++)
                for (int x = 0; x < n; x++)
                {
                    int r = 0, g = 0, b = 0, a = 0;
                    for (int dy = 0; dy < 4; dy++)
                        for (int dx = 0; dx < 4; dx++)
                        {
                            int p = ((y * 4 + dy) * size + x * 4 + dx) * 4;
                            int ca = rgba[p + 3];
                            r += rgba[p] * ca; g += rgba[p + 1] * ca; b += rgba[p + 2] * ca; a += ca;
                        }
                    int q = (y * n + x) * 4;
                    if (a == 0) continue;
                    o[q] = (byte)(r / a); o[q + 1] = (byte)(g / a); o[q + 2] = (byte)(b / a); o[q + 3] = (byte)(a / 16);
                }
            return o;
        }

        /// <summary>One processed pass pair: the graded straight-RGBA PNG and
        /// what the self-checks read.</summary>
        internal sealed class FrameOut
        {
            internal byte[] Png;
            internal int Covered, Lit, Partial, Pixels;
            internal bool EdgeClear;
            internal byte[] Luma;            // frames only: the flash check's input
            internal byte[] Preview;         // the still only: reduce(4), for the Settings preview
            internal double Coverage { get { return Pixels > 0 ? (double)Covered / Pixels : 0.0; } }
            internal double LitFraction { get { return Pixels > 0 ? (double)Lit / Pixels : 0.0; } }
        }

        /// <summary>Matte, THEN grade (never before the matte), then the PNG,
        /// the edge band, and the luma (frames) or the preview (the still).
        /// `work` is the caller's w x w x 4 scratch; the black and white passes
        /// are read, never written.</summary>
        internal static FrameOut ProcessPair(byte[] black, byte[] white, int edge, RgbMap grade, bool bottomUp, byte[] work, bool frame)
        {
            if (black == null || white == null || work == null || black.Length != edge * edge * 4 || white.Length != black.Length || work.Length != black.Length)
                throw new ArgumentException("pass buffers are not edge x edge x 4");
            var f = new FrameOut { Pixels = edge * edge };
            Matte(black, white, work, out f.Lit, out f.Partial, out f.Covered);
            Grade(work, grade);
            f.EdgeClear = EdgeClear(work, edge, edge, EDGE_MARGIN);
            f.Png = ScrPng.EncodeRgba(work, edge, edge, bottomUp);
            if (frame) { f.Luma = new byte[edge * edge]; LumaOverBg(work, f.Luma); }
            else f.Preview = Reduce4(work, edge);
            return f;
        }

        /// <summary>The S1.6 self-checks over a finished frame set, in the
        /// server's order: count equal to the table, every frame's coverage
        /// (2-60%), edge band and size (at most 262144), the flash pairs (k,
        /// k+1) then the loop wrap (N-1, 0), and the container's total at a
        /// header of `headerLength` bytes. Null when every check holds, else
        /// the first failure.</summary>
        internal static string SelfCheck(IList<FrameOut> frames, int tableCount, int headerLength)
        {
            if (frames == null || frames.Count != tableCount) return "frame count " + (frames == null ? 0 : frames.Count) + " is not the table's " + tableCount;
            var pngs = new List<byte[]>(frames.Count);
            for (int k = 0; k < frames.Count; k++)
            {
                var f = frames[k];
                if (f == null || f.Png == null) return "frame " + k + " missing";
                if (f.Coverage < COVERAGE_MIN || f.Coverage > COVERAGE_MAX) return "frame " + k + " coverage " + f.Coverage.ToString("F4", CultureInfo.InvariantCulture);
                if (!f.EdgeClear) return "frame " + k + " touches the edge band";
                if (f.Png.Length > FRAME_MAX_BYTES) return "frame " + k + " is " + f.Png.Length + " bytes";
                if (k > 0)
                {
                    double ch, mn;
                    FlashPair(frames[k - 1].Luma, f.Luma, out ch, out mn);
                    if (FlashRefused(ch, mn)) return "flash at pair " + (k - 1) + "-" + k;
                }
                pngs.Add(f.Png);
            }
            if (frames.Count > 1)
            {
                double ch, mn;
                FlashPair(frames[frames.Count - 1].Luma, frames[0].Luma, out ch, out mn);
                if (FlashRefused(ch, mn)) return "flash at the loop wrap";
            }
            long total = ContainerLength(headerLength, pngs);
            if (total > TOTAL_MAX_BYTES) return "the container would be " + total + " bytes";
            return null;
        }

        // -- the answers (S1.4 step 9, S2.6, S2.11) ----------------------------------

        /// <summary>What an upload's answer asks the job to do next.</summary>
        internal enum Act
        {
            Proceed,      // the still: 200 with the writer's hash -- bind the motion to it
            Applied,      // the motion stored
            Same,         // the motion already stored, binding repaired if it moved (L3)
            Wait,         // a pacing refusal: wait retry_after (at most 31 s) and send again, once
            Resend,       // a replayed nonce: send again with a new nonce, once
            Remember,     // the key is not captured again this process (S1.2, S2.11)
            RefreshMe,    // the selection or the binding moved: /pc/me again, the next check decides
            HoldOff,      // no motion upload until HoldSeconds pass (day cap, rate limit, unconfigured)
            SessionStop,  // no motion upload for the rest of the process
            NextVisit,    // nothing now; the next visit's check may try again
            Stop,         // the job ends; nothing is remembered
        }

        /// <summary>One upload answer as the job reads it: Status 200 for a
        /// success, the HTTP status of a refusal, 0 when none arrived.</summary>
        internal struct Answer
        {
            internal int Status;
            internal string Error;          // detail.error, or top-level error, or "http" for a plain detail
            internal string Reason;         // detail.reason (motion_busy)
            internal string PortraitHash;   // the still writer's canonical hash (200)
            internal bool Applied;          // 200's `applied`
            internal int RetryAfter;        // detail.retry_after, -1 when absent
        }

        internal const int HOLD_RATE_LIMITED_S = 60;
        internal const int HOLD_UNCONFIGURED_S = 600;
        internal const int WAIT_MAX_S = 31;

        /// <summary>The still writer's answer (S1.4 step 9): 200 with a hash
        /// binds the motion to THAT hash; a pacing refusal is waited out once;
        /// a 422 or 413 is remembered (S2.11); a rate limit holds motion work
        /// for a minute; anything else ends the job with no motion sent.</summary>
        internal static Act ClassifyStill(Answer a)
        {
            if (a.Status == 200) return HexHashOk(a.PortraitHash) ? Act.Proceed : Act.Stop;
            if (a.Status == 409 && a.Error == "retry_after") return Act.Wait;
            if (a.Status == 422 || a.Status == 413) return Act.Remember;
            if (a.Status == 429) return Act.HoldOff;
            return Act.Stop;
        }

        /// <summary>The motion writer's answer (S2.6, S2.11).</summary>
        internal static Act ClassifyMotion(Answer a)
        {
            string e = a.Error ?? "";
            switch (a.Status)
            {
                case 200: return a.Applied ? Act.Applied : Act.Same;
                case 0: return Act.NextVisit;
                case 400: case 411: case 413: case 415: case 422: return Act.Remember;
                case 401: return Act.Stop;
                case 403:
                    if (e == "nonce_replayed") return Act.Resend;
                    if (e == "dance_not_owned") return Act.RefreshMe;
                    return Act.Stop;
                case 404: return Act.SessionStop;
                case 409:
                    if (e == "retry_after") return Act.Wait;
                    if (e == "daily_cap") return Act.HoldOff;
                    if (e == "motion_capacity") return Act.SessionStop;
                    if (e == "motion_unbound" || e == "dance_not_selected") return Act.RefreshMe;
                    return Act.Stop;
                case 410: return Act.Stop;
                case 429: return Act.HoldOff;
                case 503:
                    if (e == "motion_busy") return a.Reason == "admission" ? Act.Wait : Act.NextVisit;
                    return Act.HoldOff;   // unconfigured HMAC key, motion module not loaded
                default: return Act.NextVisit;
            }
        }

        /// <summary>How long a HoldOff lasts: the day cap's own retry_after (to
        /// midnight), a minute for a rate limit, ten minutes for an unconfigured
        /// or unavailable motion module.</summary>
        internal static int HoldSeconds(Answer a)
        {
            if (a.Status == 409 && a.Error == "daily_cap") return a.RetryAfter > 0 ? a.RetryAfter : 3600;
            if (a.Status == 429) return Math.Max(HOLD_RATE_LIMITED_S, a.RetryAfter);
            return HOLD_UNCONFIGURED_S;
        }

        /// <summary>A Wait's delay: retry_after + 1, at least 1 and at most 31
        /// seconds (the still's pacing refusal is waited out once, at most 31 s,
        /// S1.4 step 9; the motion's admission refusal says 30).</summary>
        internal static int WaitSeconds(Answer a)
        {
            int s = a.RetryAfter > 0 ? a.RetryAfter + 1 : WAIT_MAX_S;
            return Math.Max(1, Math.Min(WAIT_MAX_S, s));
        }
    }

    /// <summary>What the upload job needs from the world: the two writers, a
    /// timer, the state-key fence and a log line. The capture job implements it
    /// over ApiClient on the seat; the harness implements it with scripted
    /// answers.</summary>
    internal interface IDanceUploadPort
    {
        void UploadStill(string descriptor, byte[] png, Action<DanceMotionCore.Answer> done);
        void UploadMotion(string descriptor, byte[] container, Action<DanceMotionCore.Answer> done);
        void After(int seconds, Action then);
        bool Holds();
        void Note(string line);
    }

    internal enum DanceUploadResult { Pending, MotionApplied, MotionSame, StillRefused, MotionRefused, Abandoned, Invalid }

    /// <summary>S1.4 step 9 with finding L2: the still first, through the
    /// existing writer with the dance suffix; on 200 the motion, bound to the
    /// still hash the WRITER RETURNED. The frames arrive checked (S1.6) but
    /// unassembled: the header, the container -- and so its SHA-256 and its
    /// signature, which the motion port computes over these bytes -- are built
    /// only inside the still's answer, from its portrait_hash. The client
    /// cannot predict that hash (it is the server's canonical re-encode), so a
    /// container assembled earlier would be bound to the wrong still
    /// (motion_unbound) or need re-signing. A still refusal ends the job with
    /// no motion sent; a pacing refusal is waited out once while the state key
    /// holds. Each writer gets at most one second attempt of any kind.</summary>
    internal sealed class DanceUploadJob
    {
        private readonly IDanceUploadPort _port;
        private readonly string _descriptor;
        private readonly byte[] _still;
        private readonly string _sku;
        private readonly int _recipe, _ms;
        private readonly IList<byte[]> _frames;
        private bool _stillRetried, _motionRetried;
        private byte[] _container;

        /// <summary>The order of events, for the log and for T57.</summary>
        internal readonly List<string> Trace = new List<string>();
        internal DanceUploadResult Result { get; private set; }
        internal DanceMotionCore.Act LastAct { get; private set; }
        internal DanceMotionCore.Answer LastAnswer { get; private set; }
        internal string BoundHash { get; private set; }
        internal string Header { get; private set; }
        internal Action<DanceUploadJob> Finished;

        internal DanceUploadJob(IDanceUploadPort port, string descriptor, byte[] stillPng, string sku, int recipe, int ms, IList<byte[]> frames)
        {
            _port = port; _descriptor = descriptor; _still = stillPng; _sku = sku; _recipe = recipe; _ms = ms; _frames = frames;
            Result = DanceUploadResult.Pending;
        }

        internal void Start()
        {
            if (_still == null || _frames == null || _frames.Count == 0) { Finish(DanceUploadResult.Invalid); return; }
            SendStill();
        }

        private void SendStill()
        {
            Trace.Add("still:send");
            _port.UploadStill(_descriptor, _still, OnStill);
        }

        private void OnStill(DanceMotionCore.Answer a)
        {
            if (Result != DanceUploadResult.Pending) return;
            LastAnswer = a;
            Trace.Add("still:" + a.Status + (string.IsNullOrEmpty(a.Error) ? "" : ":" + a.Error));
            if (!_port.Holds()) { Finish(DanceUploadResult.Abandoned); return; }
            var act = DanceMotionCore.ClassifyStill(a);
            LastAct = act;
            if (act == DanceMotionCore.Act.Wait && !_stillRetried)
            {
                _stillRetried = true;
                int s = DanceMotionCore.WaitSeconds(a);
                Trace.Add("still:wait:" + s);
                _port.After(s, () =>
                {
                    if (Result != DanceUploadResult.Pending) return;
                    if (!_port.Holds()) { Finish(DanceUploadResult.Abandoned); return; }
                    SendStill();
                });
                return;
            }
            if (act != DanceMotionCore.Act.Proceed) { Finish(DanceUploadResult.StillRefused); return; }
            // L2: the header, the container, its SHA-256 and its HMAC exist only
            // from here on, from the hash the still writer returned.
            string header = DanceMotionCore.HeaderText(_sku, _recipe, _frames.Count, _ms, a.PortraitHash);
            if (header == null) { Finish(DanceUploadResult.Invalid); return; }
            try { _container = DanceMotionCore.BuildContainer(header, _frames); }
            catch (ArgumentException ex) { _port.Note("container refused: " + ex.Message); Finish(DanceUploadResult.Invalid); return; }
            Header = header;
            BoundHash = a.PortraitHash;
            Trace.Add("container:" + a.PortraitHash.Substring(0, 12));
            SendMotion();
        }

        private void SendMotion()
        {
            Trace.Add("motion:send");
            _port.UploadMotion(_descriptor, _container, OnMotion);
        }

        private void OnMotion(DanceMotionCore.Answer a)
        {
            if (Result != DanceUploadResult.Pending) return;
            LastAnswer = a;
            Trace.Add("motion:" + a.Status + (string.IsNullOrEmpty(a.Error) ? "" : ":" + a.Error));
            var act = DanceMotionCore.ClassifyMotion(a);
            LastAct = act;
            if (act == DanceMotionCore.Act.Applied) { Finish(DanceUploadResult.MotionApplied); return; }
            if (act == DanceMotionCore.Act.Same) { Finish(DanceUploadResult.MotionSame); return; }
            if ((act == DanceMotionCore.Act.Wait || act == DanceMotionCore.Act.Resend) && !_motionRetried)
            {
                _motionRetried = true;
                if (!_port.Holds()) { Finish(DanceUploadResult.Abandoned); return; }
                if (act == DanceMotionCore.Act.Resend) { SendMotion(); return; }
                int s = DanceMotionCore.WaitSeconds(a);
                Trace.Add("motion:wait:" + s);
                _port.After(s, () =>
                {
                    if (Result != DanceUploadResult.Pending) return;
                    if (!_port.Holds()) { Finish(DanceUploadResult.Abandoned); return; }
                    SendMotion();
                });
                return;
            }
            Finish(DanceUploadResult.MotionRefused);
        }

        private void Finish(DanceUploadResult r)
        {
            if (Result != DanceUploadResult.Pending) return;
            Result = r;
            Trace.Add("end:" + r);
            _container = null;
            try { Finished?.Invoke(this); } catch (Exception ex) { _port.Note("finish callback threw: " + ex.Message); }
        }
    }
}
