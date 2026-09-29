using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Text;
using CompetitiveRounds;

namespace DanceCardsClientTests
{
    /// <summary>The focused client suite for dance cards: the pure halves the
    /// capture job and the playback run on the seat (plugin/ScrPng.cs,
    /// plugin/DanceMotionCore.cs, plugin/PlayerCardMotionCore.cs), compiled
    /// from the real files. Cases print PASS or FAIL with the reason; the exit
    /// code is the failure count (capped at 1). run_tests.py generates the
    /// server-side reference vectors (Pillow and backend/api/pc_motion.py) into
    /// --ref, runs every case clean, checks what the cases wrote to --out with
    /// Pillow and pc_motion, then runs each mutant against its named cases.
    ///
    ///   DanceCardsClientTests [--ref DIR] [--out DIR] [--list] [case ...]</summary>
    internal static class Program
    {
        private static string RefDir, OutDir;
        private static readonly List<KeyValuePair<string, Action>> Cases = new List<KeyValuePair<string, Action>>();

        private static int Main(string[] args)
        {
            Register();
            var pick = new List<string>();
            bool list = false;
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--ref" && i + 1 < args.Length) RefDir = args[++i];
                else if (args[i] == "--out" && i + 1 < args.Length) OutDir = args[++i];
                else if (args[i] == "--list") list = true;
                else pick.Add(args[i]);
            }
            if (list) { foreach (var c in Cases) Console.WriteLine(c.Key); return 0; }
            var known = new HashSet<string>();
            foreach (var c in Cases) known.Add(c.Key);
            foreach (var p in pick) if (!known.Contains(p)) { Console.WriteLine("FAIL " + p + ": no such case"); return 1; }
            int failed = 0, ran = 0;
            foreach (var c in Cases)
            {
                if (pick.Count > 0 && !pick.Contains(c.Key)) continue;
                ran++;
                try { c.Value(); Console.WriteLine("PASS " + c.Key); }
                catch (Exception ex) { failed++; Console.WriteLine("FAIL " + c.Key + ": " + Flat(ex.Message)); }
            }
            Console.WriteLine("SUMMARY ran=" + ran + " failed=" + failed);
            return failed == 0 ? 0 : 1;
        }

        private static string Flat(string s) { return (s ?? "").Replace('\r', ' ').Replace('\n', ' '); }

        private static void Check(bool ok, string why) { if (!ok) throw new Exception(why); }

        private static void Add(string name, Action a) { Cases.Add(new KeyValuePair<string, Action>(name, a)); }

        private static string Ref(string name)
        {
            Check(RefDir != null, "no --ref directory");
            string p = Path.Combine(RefDir, name);
            Check(File.Exists(p), "missing reference " + name);
            return p;
        }

        private static bool Eq(byte[] a, byte[] b)
        {
            if (a == null || b == null || a.Length != b.Length) return false;
            for (int i = 0; i < a.Length; i++) if (a[i] != b[i]) return false;
            return true;
        }

        private static byte[] Flip(byte[] px, int w, int h)
        {
            var o = new byte[px.Length];
            int s = w * 4;
            for (int y = 0; y < h; y++) Buffer.BlockCopy(px, y * s, o, (h - 1 - y) * s, s);
            return o;
        }

        private static byte[] Rand(Random r, int n) { var b = new byte[n]; r.NextBytes(b); return b; }

        private static byte[] Smooth(int w, int h, int seed)
        {
            var px = new byte[w * h * 4];
            var r = new Random(seed);
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                {
                    int p = (y * w + x) * 4;
                    px[p] = (byte)(x * 3 + y); px[p + 1] = (byte)(y * 2); px[p + 2] = (byte)((x ^ y) & 0xFF); px[p + 3] = (byte)(r.Next(4) == 0 ? 0 : 200 + (x & 31));
                }
            return px;
        }

        private static void Register()
        {
            // -- ScrPng --------------------------------------------------------
            Add("png_roundtrip", PngRoundTrip);
            Add("png_rejects", PngRejects);
            Add("png_bands", PngBands);
            Add("png_emit_for_pillow", PngEmitForPillow);
            Add("pillow_atlas_decode", PillowAtlasDecode);
            // -- DanceMotionCore -------------------------------------------------
            Add("container_layout", ContainerLayout);
            Add("header_grammar", HeaderGrammar);
            Add("matte_arith", MatteArith);
            Add("grade_after_matte", GradeAfterMatte);
            Add("edge_band", EdgeBand);
            Add("luma_pillow", LumaPillow);
            Add("flash_pillow", FlashPillow);
            Add("flash_bounds", FlashBounds);
            Add("selfcheck_order", SelfCheckOrder);
            Add("classify_still", ClassifyStill);
            Add("classify_motion", ClassifyMotion);
            Add("t57_l2_container_after_still", T57);
            Add("t57_still_refusal_sends_no_motion", T57StillRefusal);
            Add("upload_retries_once", UploadRetriesOnce);
            Add("t48_decide_truth_table", DecideTruthTable);
            Add("motion_current_terms", MotionCurrentTerms);
            Add("still_current_rows", StillCurrentRows);
            Add("remember_key_stable", RememberKeyStable);
            Add("frame_emit_for_server", FrameEmitForServer);
            Add("rig_undo_owed_before_pose_clear", () => RigUndo(true));
            Add("rig_undo_clean", () => RigUndo(false));
            // -- PlayerCardMotionCore -------------------------------------------
            Add("read_parse", ReadParse);
            Add("atlas_shape", AtlasShapeCase);
            Add("atlas_ihdr", AtlasIhdr);
            Add("t39_truth_table", T39);
            Add("t41_low_fps", () => T41(10.0));
            Add("t41_high_fps", () => T41(60.0));
            Add("t41_tick_equals_period", () => T41(20.0));
            Add("t49_429_cooldown_across_visits", T49);
            Add("t49_no_429_one_read_per_visit", T49Control);
            Add("t40_budget_cycles", () => T40(100, true));
            Add("t40_single_visit", () => T40(1, false));
            Add("t50_largest_card_gate", () => T50(true));
            Add("t50_tile_alone", () => T50(false));
        }

        // ================================================================ PNG

        private static void PngRoundTrip()
        {
            var r = new Random(1);
            int[][] sizes = { new[] { 1, 1 }, new[] { 3, 2 }, new[] { 17, 9 }, new[] { 64, 33 } };
            foreach (var sz in sizes)
                for (int f = -1; f <= 4; f++)
                    foreach (bool bu in new[] { false, true })
                        foreach (bool smooth in new[] { false, true })
                        {
                            int w = sz[0], h = sz[1];
                            var px = smooth ? Smooth(w, h, w * 31 + h) : Rand(r, w * h * 4);
                            var png = ScrPng.EncodeRgba(px, w, h, bu, f);
                            var back = ScrPng.DecodeRgba8(png, w, h);   // bottom-up
                            Check(back != null, "decode refused " + w + "x" + h + " f=" + f);
                            Check(Eq(back, bu ? px : Flip(px, w, h)), "pixels differ " + w + "x" + h + " f=" + f + " bottomUp=" + bu);
                            int ow, oh, d, ct, il;
                            Check(ScrPng.ReadIhdr(png, out ow, out oh, out d, out ct, out il) && ow == w && oh == h && d == 8 && ct == 6 && il == 0, "IHDR");
                        }
        }

        private static byte[] Chunk(string type, byte[] data)
        {
            var o = new byte[12 + data.Length];
            PutBE(o, 0, (uint)data.Length);
            for (int i = 0; i < 4; i++) o[4 + i] = (byte)type[i];
            Buffer.BlockCopy(data, 0, o, 8, data.Length);
            PutBE(o, 8 + data.Length, ScrPng.Crc32(o, 4, 4 + data.Length));
            return o;
        }

        private static void PutBE(byte[] b, int off, uint v) { b[off] = (byte)(v >> 24); b[off + 1] = (byte)(v >> 16); b[off + 2] = (byte)(v >> 8); b[off + 3] = (byte)v; }

        /// <summary>A PNG assembled by hand from raw (already filtered) scanlines.</summary>
        private static byte[] HandPng(int w, int h, byte[] raw, byte depth = 8, byte ct = 6, byte il = 0, bool badAdler = false)
        {
            var ihdr = new byte[13];
            PutBE(ihdr, 0, (uint)w); PutBE(ihdr, 4, (uint)h);
            ihdr[8] = depth; ihdr[9] = ct; ihdr[12] = il;
            var z = new MemoryStream();
            z.WriteByte(0x78); z.WriteByte(0x9C);
            using (var d = new DeflateStream(z, CompressionLevel.Optimal, true)) d.Write(raw, 0, raw.Length);
            uint ad = ScrPng.Adler32(raw, 0, raw.Length);
            if (badAdler) ad ^= 1;
            var t = new byte[4]; PutBE(t, 0, ad); z.Write(t, 0, 4);
            var o = new MemoryStream();
            o.Write(ScrPng.Signature, 0, 8);
            var c1 = Chunk("IHDR", ihdr); o.Write(c1, 0, c1.Length);
            var zb = z.ToArray();
            var c2 = Chunk("IDAT", zb); o.Write(c2, 0, c2.Length);
            var c3 = Chunk("IEND", new byte[0]); o.Write(c3, 0, c3.Length);
            return o.ToArray();
        }

        private static byte[] RawRows(int w, int h, int filter, int extraRows = 0)
        {
            int s = w * 4;
            var raw = new byte[(s + 1) * (h + extraRows)];
            for (int y = 0; y < h + extraRows; y++) raw[y * (s + 1)] = (byte)filter;
            return raw;
        }

        private static void PngRejects()
        {
            const int w = 8, h = 8;
            var good = HandPng(w, h, RawRows(w, h, 0));
            Check(ScrPng.DecodeRgba8(good, w, h) != null, "the control PNG was refused");
            // a flipped byte of the IHDR chunk's own CRC field, then of the IDAT
            // chunk's: the data is intact, so only the CRC walk can refuse these
            var crc = (byte[])good.Clone(); crc[32] ^= 0x40;
            Check(ScrPng.DecodeRgba8(crc, w, h) == null, "a bad IHDR CRC was accepted");
            crc = (byte[])good.Clone(); crc[good.Length - 13] ^= 0x40;
            Check(ScrPng.DecodeRgba8(crc, w, h) == null, "a bad IDAT CRC was accepted");
            // a wrong Adler-32 under a valid chunk CRC
            Check(ScrPng.DecodeRgba8(HandPng(w, h, RawRows(w, h, 0), badAdler: true), w, h) == null, "a bad Adler-32 was accepted");
            // trailing bytes after IEND
            var tail = new byte[good.Length + 1]; Buffer.BlockCopy(good, 0, tail, 0, good.Length);
            Check(ScrPng.DecodeRgba8(tail, w, h) == null, "bytes after IEND were accepted");
            // the shape the caller did not expect
            Check(ScrPng.DecodeRgba8(good, w, h + 1) == null, "a PNG of another height was accepted");
            Check(ScrPng.DecodeRgba8(HandPng(w, h, RawRows(w, h, 0), ct: 2), w, h) == null, "colour type 2 was accepted");
            Check(ScrPng.DecodeRgba8(HandPng(w, h, RawRows(w, h, 0), depth: 16), w, h) == null, "16-bit depth was accepted");
            Check(ScrPng.DecodeRgba8(HandPng(w, h, RawRows(w, h, 0), il: 1), w, h) == null, "an interlaced PNG was accepted");
            // a filter type above 4
            Check(ScrPng.DecodeRgba8(HandPng(w, h, RawRows(w, h, 5)), w, h) == null, "filter type 5 was accepted");
            // too few and too many inflated bytes
            var shortRaw = new byte[(w * 4 + 1) * (h - 1)];
            Check(ScrPng.DecodeRgba8(HandPng(w, h, shortRaw), w, h) == null, "a short image stream was accepted");
            Check(ScrPng.DecodeRgba8(HandPng(w, h, RawRows(w, h, 0, 1)), w, h) == null, "an image stream with an extra row was accepted");
        }

        private static void PngBands()
        {
            const int w = 16, h = 10, band = 4;
            var px = Smooth(w, h, 7);                         // top-down
            var png = ScrPng.EncodeRgba(px, w, h, false);
            var bands = ScrPng.DecodeBandsRgba8(png, w, h, band);
            Check(bands != null && bands.Count == 3, "band count " + (bands == null ? -1 : bands.Count));
            int s = w * 4, row = 0;
            for (int b = 0; b < bands.Count; b++)
            {
                int rows = Math.Min(band, h - row);
                Check(bands[b].Length == rows * s, "band " + b + " size");
                for (int i = 0; i < rows; i++)
                {
                    // image row (row + i) is the band's buffer row (rows - 1 - i): bottom-up inside the band
                    for (int x = 0; x < s; x++)
                        Check(bands[b][(rows - 1 - i) * s + x] == px[(row + i) * s + x], "band " + b + " row " + i + " byte " + x);
                }
                row += rows;
            }
            int calls = 0;
            Check(ScrPng.DecodeBandsRgba8(png, w, h, band, () => ++calls > 3) == null, "a cancelled decode returned an image");
        }

        /// <summary>Writes PNGs of this encoder for run_tests.py to open with
        /// Pillow (a writer only this reader can read proves nothing).</summary>
        private static void PngEmitForPillow()
        {
            if (OutDir == null) return;
            Directory.CreateDirectory(OutDir);
            var r = new Random(5);
            int[][] sizes = { new[] { 1, 1 }, new[] { 31, 7 }, new[] { 590, 590 } };
            for (int i = 0; i < sizes.Length; i++)
            {
                int w = sizes[i][0], h = sizes[i][1];
                var px = i == 2 ? Smooth(w, h, 11) : Rand(r, w * h * 4);
                File.WriteAllBytes(Path.Combine(OutDir, "enc_" + i + ".png"), ScrPng.EncodeRgba(px, w, h, false));
                File.WriteAllBytes(Path.Combine(OutDir, "enc_" + i + ".rgba"), px);
                File.WriteAllText(Path.Combine(OutDir, "enc_" + i + ".txt"), w + " " + h);
            }
        }

        /// <summary>An atlas-shaped PNG written by the server's own encoder
        /// (pc_face._encode_rgba), decoded here band by band.</summary>
        private static void PillowAtlasDecode()
        {
            var dims = File.ReadAllText(Ref("atlas.txt")).Trim().Split(' ');
            int w = int.Parse(dims[0], CultureInfo.InvariantCulture), h = int.Parse(dims[1], CultureInfo.InvariantCulture), cell = int.Parse(dims[2], CultureInfo.InvariantCulture);
            var png = File.ReadAllBytes(Ref("atlas.png"));
            var raw = File.ReadAllBytes(Ref("atlas.rgba"));       // top-down
            var bands = ScrPng.DecodeBandsRgba8(png, w, h, cell);
            Check(bands != null && bands.Count == h / cell, "the server's atlas PNG was refused");
            int s = w * 4;
            for (int b = 0; b < bands.Count; b++)
                for (int i = 0; i < cell; i++)
                    for (int x = 0; x < s; x++)
                        Check(bands[b][(cell - 1 - i) * s + x] == raw[(b * cell + i) * s + x], "atlas band " + b + " row " + i);
        }

        // ================================================== DanceMotionCore

        private static void ContainerLayout()
        {
            string header = File.ReadAllText(Ref("container_header.txt"));
            int n = int.Parse(File.ReadAllText(Ref("container_count.txt")).Trim(), CultureInfo.InvariantCulture);
            var frames = new List<byte[]>();
            for (int k = 0; k < n; k++) frames.Add(File.ReadAllBytes(Ref("container_frame_" + k + ".bin")));
            var expect = File.ReadAllBytes(Ref("container.bin"));   // pc_motion.build_container
            var ours = DanceMotionCore.BuildContainer(header, frames);
            Check(Eq(ours, expect), "BuildContainer differs from the server's build_container");
            string h2; List<byte[]> f2;
            Check(DanceMotionCore.TryParseContainer(ours, out h2, out f2) && h2 == header && f2.Count == n, "parse round trip");
            for (int k = 0; k < n; k++) Check(Eq(f2[k], frames[k]), "frame " + k + " round trip");
            Check(DanceMotionCore.ContainerLength(Encoding.ASCII.GetByteCount(header), frames) == ours.Length, "ContainerLength");
            Throws(() => DanceMotionCore.BuildContainer(header.Replace(";frames=" + n + ";", ";frames=" + (n + 1) + ";"), frames), "a header frame count other than the frames");
            var big = new List<byte[]>(frames); big[0] = new byte[DanceMotionCore.FRAME_MAX_BYTES + 1];
            Throws(() => DanceMotionCore.BuildContainer(header, big), "a frame above 262144 bytes");
            var empty = new List<byte[]>(frames); empty[0] = new byte[0];
            Throws(() => DanceMotionCore.BuildContainer(header, empty), "an empty frame");
            Throws(() => DanceMotionCore.BuildContainer(new string('a', 513), frames), "a 513-byte header");
            var many = new List<byte[]>();
            for (int k = 0; k < 48; k++) many.Add(new byte[DanceMotionCore.FRAME_MAX_BYTES]);
            string h48 = DanceMotionCore.HeaderText("dance_robot", 1, 48, 50, new string('a', 64));
            Throws(() => DanceMotionCore.BuildContainer(h48, many), "a container above 12 MiB");
            Check(!DanceMotionCore.TryParseContainer(Truncate(ours, ours.Length - 1), out h2, out f2), "a truncated container parsed");
            var extra = new byte[ours.Length + 1]; Buffer.BlockCopy(ours, 0, extra, 0, ours.Length);
            Check(!DanceMotionCore.TryParseContainer(extra, out h2, out f2), "a container with trailing bytes parsed");
        }

        private static byte[] Truncate(byte[] b, int n) { var o = new byte[n]; Buffer.BlockCopy(b, 0, o, 0, n); return o; }

        private static void Throws(Action a, string what)
        {
            try { a(); } catch (ArgumentException) { return; }
            throw new Exception(what + " was not refused");
        }

        private static void HeaderGrammar()
        {
            string hx = new string('0', 63) + "f";
            Check(DanceMotionCore.HeaderText("dance_robot", 1, 120, 50, hx) == "dance=dance_robot;recipe=1;frames=120;ms=50;static=" + hx, "the canonical header");
            Check(DanceMotionCore.HeaderText("Dance_robot", 1, 120, 50, hx) == null, "an uppercase sku");
            Check(DanceMotionCore.HeaderText("dance_", 1, 120, 50, hx) == null, "an empty dance name");
            Check(DanceMotionCore.HeaderText("dance_rob0t", 1, 120, 50, hx) == null, "a digit in the dance name");
            Check(DanceMotionCore.HeaderText("dance_" + new string('a', 25), 1, 120, 50, hx) == null, "a 25-letter dance name");
            Check(DanceMotionCore.HeaderText("dance_" + new string('a', 24), 1, 120, 50, hx) != null, "a 24-letter dance name");
            Check(DanceMotionCore.HeaderText("dance_robot", 0, 120, 50, hx) == null, "recipe 0");
            Check(DanceMotionCore.HeaderText("dance_robot", 1, 1000, 50, hx) == null, "1000 frames");
            Check(DanceMotionCore.HeaderText("dance_robot", 1, 120, 10000, hx) == null, "ms 10000");
            Check(DanceMotionCore.HeaderText("dance_robot", 1, 120, 50, hx.ToUpperInvariant()) == null, "an uppercase hash");
            Check(DanceMotionCore.HeaderText("dance_robot", 1, 120, 50, hx.Substring(1)) == null, "a 63-character hash");
            string h = DanceMotionCore.HeaderText("dance_floss", 1, 100, 50, hx);
            Check(DanceMotionCore.HeaderInt(h, "frames") == 100 && DanceMotionCore.HeaderInt(h, "ms") == 50 && DanceMotionCore.HeaderStr(h, "static") == hx, "header fields read back");
        }

        private static byte[] Px(params int[] v) { var b = new byte[v.Length]; for (int i = 0; i < v.Length; i++) b[i] = (byte)v[i]; return b; }

        private static void MatteArith()
        {
            // pixel: black pass, white pass -> expected straight RGBA
            var black = Px(0, 0, 0, 255, 10, 20, 30, 255, 50, 60, 70, 255, 200, 200, 200, 255, 1, 0, 0, 255, 255, 250, 245, 255);
            var white = Px(255, 255, 255, 255, 10, 20, 30, 255, 177, 187, 197, 255, 100, 100, 100, 255, 255, 254, 253, 255, 255, 250, 245, 255);
            var o = new byte[black.Length];
            int lit, partial, covered;
            DanceMotionCore.Matte(black, white, o, out lit, out partial, out covered);
            var expect = Px(0, 0, 0, 0,          // only the clear colour: a = 0
                            10, 20, 30, 255,     // opaque: unchanged
                            100, 120, 139, 128,  // a = 255 - 381 / 3 = 128; (c * 255 + 64) / 128
                            200, 200, 200, 255,  // white below black: d / 3 = -100, a clamps to 255
                            128, 0, 0, 2,        // a = 255 - 761 / 3 = 2; (1 * 255 + 1) / 2 = 128
                            255, 250, 245, 255); // opaque white
            Check(Eq(o, expect), "matte bytes " + BitConverter.ToString(o));
            Check(covered == 5 && lit == 4 && partial == 2, "counts covered=" + covered + " lit=" + lit + " partial=" + partial);
            // the un-premultiply clamps at 255
            Check(DanceMotionCore.Un(255, 128) == 255 && DanceMotionCore.Un(100, 200) == 128, "Un");
        }

        private static void GradeMap(int r, int g, int b, out byte ro, out byte go, out byte bo)
        {
            ro = (byte)Math.Min(255, r + 7); go = (byte)(g ^ 0x55); bo = (byte)(255 - b);
        }

        private static void GradeAfterMatte()
        {
            const int e = 40;
            var r = new Random(3);
            var black = new byte[e * e * 4]; var white = new byte[e * e * 4];
            for (int p = 0; p < black.Length; p += 4)
            {
                int a = r.Next(4) == 0 ? 0 : r.Next(256);
                for (int c = 0; c < 3; c++)
                {
                    int col = r.Next(256);
                    black[p + c] = (byte)(col * a / 255);
                    white[p + c] = (byte)Math.Min(255, col * a / 255 + (255 - a));
                }
                black[p + 3] = white[p + 3] = 255;
            }
            var expect = new byte[black.Length];
            int l, pa, cv;
            DanceMotionCore.Matte(black, white, expect, out l, out pa, out cv);
            DanceMotionCore.Grade(expect, GradeMap);
            var work = new byte[black.Length];
            var f = DanceMotionCore.ProcessPair(black, white, e, GradeMap, false, work, true);
            var back = ScrPng.DecodeRgba8(f.Png, e, e);
            Check(back != null && Eq(Flip(back, e, e), expect), "ProcessPair is not the matte, then the grade");
            for (int p = 0; p < expect.Length; p += 4)
                if (expect[p + 3] == 0) Check(expect[p] == 0 && expect[p + 1] == 0 && expect[p + 2] == 0, "a transparent pixel was graded");
            Check(f.Covered == cv && f.Lit == l && f.Partial == pa, "ProcessPair counts");
            Throws(() => DanceMotionCore.Grade(expect, null), "an ungraded picture");
        }

        private static void EdgeBand()
        {
            const int e = 590;
            int[][] cases = { new[] { 1, 300, 0 }, new[] { 2, 300, 1 }, new[] { 588, 300, 0 }, new[] { 587, 300, 1 },
                              new[] { 300, 1, 0 }, new[] { 300, 2, 1 }, new[] { 300, 588, 0 }, new[] { 300, 587, 1 }, new[] { 0, 0, 0 } };
            foreach (var c in cases)
            {
                var px = new byte[e * e * 4];
                px[(c[1] * e + c[0]) * 4 + 3] = 1;
                Check(DanceMotionCore.EdgeClear(px, e, e, DanceMotionCore.EDGE_MARGIN) == (c[2] == 1), "pixel (" + c[0] + "," + c[1] + ")");
            }
        }

        private static void LumaPillow()
        {
            int n = int.Parse(File.ReadAllText(Ref("luma_count.txt")).Trim(), CultureInfo.InvariantCulture);
            Check(n > 0, "no luma references");
            long px = 0;
            for (int i = 0; i < n; i++)
            {
                var rgba = File.ReadAllBytes(Ref("luma_" + i + ".rgba"));
                var expect = File.ReadAllBytes(Ref("luma_" + i + ".y"));
                var y = new byte[rgba.Length / 4];
                DanceMotionCore.LumaOverBg(rgba, y);
                for (int k = 0; k < y.Length; k++)
                    Check(y[k] == expect[k], "case " + i + " pixel " + k + " rgba=(" + rgba[4 * k] + "," + rgba[4 * k + 1] + "," + rgba[4 * k + 2] + "," + rgba[4 * k + 3] + ") ours " + y[k] + " Pillow " + expect[k]);
                px += y.Length;
            }
            Console.WriteLine("  luma: " + px + " pixels equal to Pillow's");
        }

        private static void FlashPillow()
        {
            int n = int.Parse(File.ReadAllText(Ref("flash_count.txt")).Trim(), CultureInfo.InvariantCulture);
            Check(n > 0, "no flash references");
            for (int i = 0; i < n; i++)
            {
                var a = File.ReadAllBytes(Ref("flash_" + i + "_a.y"));
                var b = File.ReadAllBytes(Ref("flash_" + i + "_b.y"));
                var t = File.ReadAllText(Ref("flash_" + i + ".txt")).Trim().Split(' ');
                double ec = double.Parse(t[0], CultureInfo.InvariantCulture), em = double.Parse(t[1], CultureInfo.InvariantCulture);
                bool er = t[2] == "1";
                double ch, mn;
                DanceMotionCore.FlashPair(a, b, out ch, out mn);
                Check(ch == ec && mn == em, "pair " + i + " ours " + ch.ToString("R", CultureInfo.InvariantCulture) + "/" + mn.ToString("R", CultureInfo.InvariantCulture) + " server " + t[0] + "/" + t[1]);
                Check(DanceMotionCore.FlashRefused(ch, mn) == er, "pair " + i + " refusal");
            }
        }

        private static void FlashBounds()
        {
            const int n = 1000;
            var a = new byte[n]; var b = new byte[n];
            for (int i = 0; i < 350; i++) b[i] = 13;          // exactly 35% changed, by exactly 13 steps
            double ch, mn;
            DanceMotionCore.FlashPair(a, b, out ch, out mn);
            Check(ch == 0.35 && !DanceMotionCore.FlashRefused(ch, mn), "35% changed is not refused");
            b[350] = 13;
            DanceMotionCore.FlashPair(a, b, out ch, out mn);
            Check(DanceMotionCore.FlashRefused(ch, mn), "35.1% changed is refused");
            var c = new byte[n];
            for (int i = 0; i < n; i++) c[i] = 12;            // 12 steps changes nothing
            DanceMotionCore.FlashPair(a, c, out ch, out mn);
            Check(ch == 0.0, "a 12-step difference counted as changed");
            var d = new byte[n];
            for (int i = 0; i < n; i++) d[i] = 51;            // mean exactly 0.20
            DanceMotionCore.FlashPair(a, d, out ch, out mn);
            Check(mn == 51.0 / 255.0, "mean");
        }

        private static DanceMotionCore.FrameOut FakeFrame(int pngBytes, int covered, bool edge, byte lumaFill)
        {
            var f = new DanceMotionCore.FrameOut { Png = new byte[pngBytes], Covered = covered, Pixels = 1000, EdgeClear = edge, Luma = new byte[1000] };
            for (int i = 0; i < f.Luma.Length; i++) f.Luma[i] = lumaFill;
            return f;
        }

        private static void SelfCheckOrder()
        {
            Func<List<DanceMotionCore.FrameOut>> good = () =>
            {
                var l = new List<DanceMotionCore.FrameOut>();
                for (int k = 0; k < 4; k++) l.Add(FakeFrame(1000, 300, true, (byte)(k == 3 ? 5 : k * 5)));
                return l;
            };
            Check(DanceMotionCore.SelfCheck(good(), 4, 100) == null, "a good set was refused: " + DanceMotionCore.SelfCheck(good(), 4, 100));
            Check((DanceMotionCore.SelfCheck(good(), 5, 100) ?? "").StartsWith("frame count"), "count");
            var s = good(); s[2] = FakeFrame(1000, 19, true, 20);
            Check((DanceMotionCore.SelfCheck(s, 4, 100) ?? "").Contains("coverage"), "coverage 1.9%");
            s = good(); s[2] = FakeFrame(1000, 601, true, 20);
            Check((DanceMotionCore.SelfCheck(s, 4, 100) ?? "").Contains("coverage"), "coverage 60.1%");
            s = good(); s[1] = FakeFrame(1000, 300, false, 10);
            Check((DanceMotionCore.SelfCheck(s, 4, 100) ?? "").Contains("edge"), "edge band");
            s = good(); s[3] = FakeFrame(DanceMotionCore.FRAME_MAX_BYTES + 1, 300, true, 30);
            Check((DanceMotionCore.SelfCheck(s, 4, 100) ?? "").Contains("bytes"), "frame size");
            s = good(); s[2] = FakeFrame(1000, 300, true, 200);
            Check(DanceMotionCore.SelfCheck(s, 4, 100) == "flash at pair 1-2", "pair flash: " + DanceMotionCore.SelfCheck(s, 4, 100));
            s = new List<DanceMotionCore.FrameOut>();
            for (int k = 0; k < 20; k++) s.Add(FakeFrame(1000, 300, true, (byte)(k * 12)));   // 12 steps per pair is no flash; 228 at the wrap is
            Check(DanceMotionCore.SelfCheck(s, 20, 100) == "flash at the loop wrap", "wrap: " + DanceMotionCore.SelfCheck(s, 20, 100));
            s = new List<DanceMotionCore.FrameOut>();
            for (int k = 0; k < 48; k++) s.Add(FakeFrame(DanceMotionCore.FRAME_MAX_BYTES, 300, true, 0));
            Check((DanceMotionCore.SelfCheck(s, 48, 100) ?? "").Contains("container"), "total size");
        }

        private static DanceMotionCore.Answer A(int status, string error = null, string reason = null, int retryAfter = -1, bool applied = false, string hash = null)
        {
            return new DanceMotionCore.Answer { Status = status, Error = error, Reason = reason, RetryAfter = retryAfter, Applied = applied, PortraitHash = hash };
        }

        private static readonly string HashW = "7" + new string('e', 63);

        private static void ClassifyStill()
        {
            var A_ = DanceMotionCore.Act.Proceed;
            Check(DanceMotionCore.ClassifyStill(A(200, hash: HashW)) == A_, "200 with a hash");
            Check(DanceMotionCore.ClassifyStill(A(200)) == DanceMotionCore.Act.Stop, "200 without a hash");
            Check(DanceMotionCore.ClassifyStill(A(200, hash: HashW.ToUpperInvariant())) == DanceMotionCore.Act.Stop, "200 with a malformed hash");
            Check(DanceMotionCore.ClassifyStill(A(409, "retry_after", retryAfter: 12)) == DanceMotionCore.Act.Wait, "pacing");
            Check(DanceMotionCore.ClassifyStill(A(422, "descriptor_invalid")) == DanceMotionCore.Act.Remember, "422");
            Check(DanceMotionCore.ClassifyStill(A(413)) == DanceMotionCore.Act.Remember, "413");
            Check(DanceMotionCore.ClassifyStill(A(429, "rate_limited")) == DanceMotionCore.Act.HoldOff, "429");
            Check(DanceMotionCore.ClassifyStill(A(403, "portrait_locked")) == DanceMotionCore.Act.Stop, "locked");
            Check(DanceMotionCore.ClassifyStill(A(0, "transport")) == DanceMotionCore.Act.Stop, "no answer");
            Check(DanceMotionCore.WaitSeconds(A(409, "retry_after", retryAfter: 12)) == 13, "wait 12 + 1");
            Check(DanceMotionCore.WaitSeconds(A(409, "retry_after", retryAfter: 90)) == 31, "wait capped at 31");
            Check(DanceMotionCore.WaitSeconds(A(409, "retry_after")) == 31, "wait with no retry_after");
        }

        private static void ClassifyMotion()
        {
            var t = new[]
            {
                new object[] { A(200, applied: true), DanceMotionCore.Act.Applied },
                new object[] { A(200, applied: false), DanceMotionCore.Act.Same },
                new object[] { A(0, "transport"), DanceMotionCore.Act.NextVisit },
                new object[] { A(400, "http"), DanceMotionCore.Act.Remember },
                new object[] { A(411, "http"), DanceMotionCore.Act.Remember },
                new object[] { A(413, "motion_too_large"), DanceMotionCore.Act.Remember },
                new object[] { A(415, "http"), DanceMotionCore.Act.Remember },
                new object[] { A(422, "motion_flash"), DanceMotionCore.Act.Remember },
                new object[] { A(401, "session_required"), DanceMotionCore.Act.Stop },
                new object[] { A(403, "nonce_replayed"), DanceMotionCore.Act.Resend },
                new object[] { A(403, "dance_not_owned"), DanceMotionCore.Act.RefreshMe },
                new object[] { A(403, "portrait_refused"), DanceMotionCore.Act.Stop },
                new object[] { A(403, "portrait_locked"), DanceMotionCore.Act.Stop },
                new object[] { A(404, "http"), DanceMotionCore.Act.SessionStop },
                new object[] { A(409, "retry_after", retryAfter: 20), DanceMotionCore.Act.Wait },
                new object[] { A(409, "daily_cap", retryAfter: 5000), DanceMotionCore.Act.HoldOff },
                new object[] { A(409, "motion_capacity"), DanceMotionCore.Act.SessionStop },
                new object[] { A(409, "motion_unbound"), DanceMotionCore.Act.RefreshMe },
                new object[] { A(409, "dance_not_selected"), DanceMotionCore.Act.RefreshMe },
                new object[] { A(410, "http"), DanceMotionCore.Act.Stop },
                new object[] { A(429, "rate_limited"), DanceMotionCore.Act.HoldOff },
                new object[] { A(503, "motion_busy", "admission", 30), DanceMotionCore.Act.Wait },
                new object[] { A(503, "motion_busy", "deadline", 30), DanceMotionCore.Act.NextVisit },
                new object[] { A(503, "motion_busy", "error", 30), DanceMotionCore.Act.NextVisit },
                new object[] { A(503, "http"), DanceMotionCore.Act.HoldOff },
            };
            foreach (var row in t)
            {
                var a = (DanceMotionCore.Answer)row[0];
                var got = DanceMotionCore.ClassifyMotion(a);
                Check(got == (DanceMotionCore.Act)row[1], a.Status + " " + a.Error + " " + a.Reason + " -> " + got + ", expected " + row[1]);
            }
            Check(DanceMotionCore.HoldSeconds(A(409, "daily_cap", retryAfter: 5000)) == 5000, "day cap holds to its retry_after");
            Check(DanceMotionCore.HoldSeconds(A(429, "rate_limited")) == 60, "rate limit holds a minute");
            Check(DanceMotionCore.HoldSeconds(A(503, "http")) == 600, "unconfigured holds ten minutes");
        }

        /// <summary>A port with scripted answers, delivered from a queue the
        /// test pumps -- so an answer is never delivered inside the call that
        /// sent the request, as on the seat.</summary>
        private sealed class FakePort : IDanceUploadPort
        {
            internal readonly Queue<DanceMotionCore.Answer> StillAnswers = new Queue<DanceMotionCore.Answer>();
            internal readonly Queue<DanceMotionCore.Answer> MotionAnswers = new Queue<DanceMotionCore.Answer>();
            internal readonly Queue<Action> Pending = new Queue<Action>();
            internal readonly List<string> Log = new List<string>();
            internal readonly List<byte[]> Containers = new List<byte[]>();
            internal readonly List<int> Waits = new List<int>();
            internal bool Hold = true;
            internal int StillSends, MotionSends;

            public void UploadStill(string descriptor, byte[] png, Action<DanceMotionCore.Answer> done)
            {
                StillSends++;
                Log.Add("still-sent");
                var a = StillAnswers.Count > 0 ? StillAnswers.Dequeue() : A(0, "transport");
                Pending.Enqueue(() => { Log.Add("still-answered"); done(a); });
            }

            public void UploadMotion(string descriptor, byte[] container, Action<DanceMotionCore.Answer> done)
            {
                MotionSends++;
                Log.Add("motion-sent:" + DanceMotionCore.Sha256Hex(container).Substring(0, 12));
                Containers.Add(container);
                var a = MotionAnswers.Count > 0 ? MotionAnswers.Dequeue() : A(0, "transport");
                Pending.Enqueue(() => { Log.Add("motion-answered"); done(a); });
            }

            public void After(int seconds, Action then) { Waits.Add(seconds); Pending.Enqueue(then); }
            public bool Holds() { return Hold; }
            public void Note(string line) { Log.Add("note:" + line); }

            internal void Pump() { int guard = 0; while (Pending.Count > 0 && guard++ < 100) Pending.Dequeue()(); }
        }

        private static List<byte[]> Frames(int n)
        {
            var r = new Random(9);
            var l = new List<byte[]>();
            for (int k = 0; k < n; k++) l.Add(Rand(r, 100 + k));
            return l;
        }

        /// <summary>T57 (finding L2, step C3): the header, the container and so
        /// its SHA-256 and signature are built only after the still writer
        /// answered, from the portrait_hash IT returned -- which is the server's
        /// canonical re-encode, not the hash of the bytes the client sent.</summary>
        private static void T57()
        {
            var port = new FakePort();
            var still = Encoding.ASCII.GetBytes("the still as the client encoded it");
            Check(DanceMotionCore.Sha256Hex(still) != HashW, "fixture: the writer's hash must differ from the sent bytes' hash");
            port.StillAnswers.Enqueue(A(200, applied: true, hash: HashW));
            port.MotionAnswers.Enqueue(A(200, applied: true));
            var frames = Frames(80);
            var job = new DanceUploadJob(port, "v1|desc|dance=dance_bounce|ar=1", still, "dance_bounce", 1, 50, frames);
            job.Start();
            Check(port.MotionSends == 0, "a motion was sent before the still answered");
            port.Pump();
            Check(job.Result == DanceUploadResult.MotionApplied, "result " + job.Result);
            Check(port.Containers.Count == 1, "motion sends " + port.Containers.Count);
            string header; List<byte[]> back;
            Check(DanceMotionCore.TryParseContainer(port.Containers[0], out header, out back), "the sent container does not parse");
            Check(DanceMotionCore.HeaderStr(header, "static") == HashW, "the container is bound to " + DanceMotionCore.HeaderStr(header, "static") + ", not the writer's hash");
            Check(job.BoundHash == HashW && job.Header == header, "the job's record of the binding");
            Check(back.Count == 80 && Eq(back[79], frames[79]), "the frames rode unchanged");
            int iStill = port.Log.IndexOf("still-answered");
            int iMotion = port.Log.FindIndex(x => x.StartsWith("motion-sent:"));
            Check(iStill >= 0 && iMotion > iStill, "the motion left before the still answered: " + string.Join(",", port.Log));
            int tAns = job.Trace.IndexOf("still:200"), tBuilt = job.Trace.FindIndex(x => x.StartsWith("container:"));
            Check(tAns >= 0 && tBuilt > tAns, "the container was built before the still answered: " + string.Join(",", job.Trace));
        }

        private static void T57StillRefusal()
        {
            // a refusal: no motion, and a 422 is remembered
            var port = new FakePort();
            port.StillAnswers.Enqueue(A(422, "descriptor_invalid"));
            var job = new DanceUploadJob(port, "d", new byte[] { 1 }, "dance_wave", 1, 50, Frames(80));
            job.Start(); port.Pump();
            Check(job.Result == DanceUploadResult.StillRefused && job.LastAct == DanceMotionCore.Act.Remember && port.MotionSends == 0, "422: " + job.Result + " " + job.LastAct + " sends=" + port.MotionSends);
            // pacing: waited out ONCE (at most 31 s), then a second pacing refusal ends it
            port = new FakePort();
            port.StillAnswers.Enqueue(A(409, "retry_after", retryAfter: 20));
            port.StillAnswers.Enqueue(A(409, "retry_after", retryAfter: 20));
            job = new DanceUploadJob(port, "d", new byte[] { 1 }, "dance_wave", 1, 50, Frames(80));
            job.Start(); port.Pump();
            Check(port.StillSends == 2 && port.Waits.Count == 1 && port.Waits[0] == 21 && job.Result == DanceUploadResult.StillRefused && port.MotionSends == 0,
                  "pacing: sends=" + port.StillSends + " waits=" + port.Waits.Count + " result=" + job.Result);
            // pacing then 200: the motion follows the second answer
            port = new FakePort();
            port.StillAnswers.Enqueue(A(409, "retry_after", retryAfter: 40));
            port.StillAnswers.Enqueue(A(200, hash: HashW));
            port.MotionAnswers.Enqueue(A(200, applied: false));
            job = new DanceUploadJob(port, "d", new byte[] { 1 }, "dance_wave", 1, 50, Frames(80));
            job.Start(); port.Pump();
            Check(port.Waits.Count == 1 && port.Waits[0] == 31 && job.Result == DanceUploadResult.MotionSame, "pacing then 200: " + job.Result);
            // the state key moved while the still was in flight: nothing more is sent
            port = new FakePort();
            port.StillAnswers.Enqueue(A(200, hash: HashW));
            job = new DanceUploadJob(port, "d", new byte[] { 1 }, "dance_wave", 1, 50, Frames(80));
            job.Start(); port.Hold = false; port.Pump();
            Check(job.Result == DanceUploadResult.Abandoned && port.MotionSends == 0, "moved key: " + job.Result);
        }

        private static void UploadRetriesOnce()
        {
            Func<DanceMotionCore.Answer[], FakePort> run = motion =>
            {
                var p = new FakePort();
                p.StillAnswers.Enqueue(A(200, hash: HashW));
                foreach (var m in motion) p.MotionAnswers.Enqueue(m);
                var j = new DanceUploadJob(p, "d", new byte[] { 1 }, "dance_disco", 1, 50, Frames(100));
                j.Finished = x => p.Note("result:" + x.Result);
                j.Start(); p.Pump();
                return p;
            };
            var q = run(new[] { A(409, "retry_after", retryAfter: 5), A(200, applied: true) });
            Check(q.MotionSends == 2 && q.Waits.Count == 1 && q.Waits[0] == 6 && q.Log.Contains("note:result:MotionApplied"), "pacing then applied");
            q = run(new[] { A(403, "nonce_replayed"), A(200, applied: true) });
            Check(q.MotionSends == 2 && q.Waits.Count == 0 && q.Log.Contains("note:result:MotionApplied"), "nonce then applied");
            q = run(new[] { A(503, "motion_busy", "admission", 30), A(503, "motion_busy", "admission", 30) });
            Check(q.MotionSends == 2 && q.Waits.Count == 1 && q.Waits[0] == 31 && q.Log.Contains("note:result:MotionRefused"), "busy twice");
            q = run(new[] { A(422, "motion_flash") });
            Check(q.MotionSends == 1 && q.Log.Contains("note:result:MotionRefused"), "422 is final");
        }

        /// <summary>A synthetic 590 frame through ProcessPair and a container of
        /// 80 frames under a recipe-1 header, written for run_tests.py to hand
        /// to pc_motion.check_frame and parse_container.</summary>
        private static void FrameEmitForServer()
        {
            if (OutDir == null) return;
            Directory.CreateDirectory(OutDir);
            const int e = DanceMotionCore.FRAME_EDGE;
            var black = new byte[e * e * 4]; var white = new byte[e * e * 4];
            for (int y = 0; y < e; y++)
                for (int x = 0; x < e; x++)
                {
                    int p = (y * e + x) * 4;
                    bool body = (x - 295) * (x - 295) + (y - 295) * (y - 295) < 170 * 170;
                    bool rim = !body && (x - 295) * (x - 295) + (y - 295) * (y - 295) < 176 * 176;
                    int a = body ? 255 : rim ? 120 : 0;
                    int cr = (x * 7) & 255, cg = (y * 5) & 255, cb = 90;
                    black[p] = (byte)(cr * a / 255); black[p + 1] = (byte)(cg * a / 255); black[p + 2] = (byte)(cb * a / 255); black[p + 3] = 255;
                    white[p] = (byte)Math.Min(255, cr * a / 255 + 255 - a); white[p + 1] = (byte)Math.Min(255, cg * a / 255 + 255 - a); white[p + 2] = (byte)Math.Min(255, cb * a / 255 + 255 - a); white[p + 3] = 255;
                }
            var work = new byte[black.Length];
            var f = DanceMotionCore.ProcessPair(black, white, e, GradeMap, true, work, true);
            Check(f.EdgeClear && f.Coverage > 0.02 && f.Coverage < 0.60, "the synthetic frame fails its own checks");
            File.WriteAllBytes(Path.Combine(OutDir, "frame_590.png"), f.Png);
            File.WriteAllText(Path.Combine(OutDir, "frame_590.txt"), f.Png.Length + " " + f.Coverage.ToString("R", CultureInfo.InvariantCulture));
            var frames = Frames(80);
            string h = DanceMotionCore.HeaderText("dance_bounce", 1, 80, 50, HashW);
            File.WriteAllBytes(Path.Combine(OutDir, "container_80.bin"), DanceMotionCore.BuildContainer(h, frames));
        }

        // ============================================== PlayerCardMotionCore

        private static void ReadParse()
        {
            var asked = new List<string> { "a1", "b2", "c3" };
            List<PlayerCardMotionCore.ReadEntry> e;
            Check(PlayerCardMotionCore.ParseRead("a1:f00d:0123456789abcdef:80:50|b2:-|c3:beef:aa:120:40", asked, out e), "a good answer");
            Check(e.Count == 3 && e[0].Has && e[0].FaceRev == "f00d" && e[0].MotionRev == "0123456789abcdef" && e[0].Frames == 80 && e[0].Ms == 50 && !e[1].Has && e[2].Frames == 120 && e[2].Ms == 40, "fields");
            Check(!PlayerCardMotionCore.ParseRead("b2:-|a1:-|c3:-", asked, out e), "out of order");
            Check(!PlayerCardMotionCore.ParseRead("a1:-|b2:-", asked, out e), "fewer entries");
            Check(!PlayerCardMotionCore.ParseRead("a1:-|b2:-|c3:-|d4:-", asked, out e), "more entries");
            Check(!PlayerCardMotionCore.ParseRead("a1:f:m:0:50|b2:-|c3:-", asked, out e), "zero frames");
            Check(!PlayerCardMotionCore.ParseRead("a1:f:m:121:50|b2:-|c3:-", asked, out e), "121 frames");
            Check(!PlayerCardMotionCore.ParseRead("a1:f:m:80:0|b2:-|c3:-", asked, out e), "zero ms");
            Check(!PlayerCardMotionCore.ParseRead("a1:f/x:m:80:50|b2:-|c3:-", asked, out e), "a revision that is not a path segment");
            Check(!PlayerCardMotionCore.ParseRead("a1:f:m:80:50:9|b2:-|c3:-", asked, out e), "an extra field");
            Check(!PlayerCardMotionCore.ParseRead("a1:+|b2:-|c3:-", asked, out e), "a bad none marker");
            var twelve = new List<string>();
            for (int i = 0; i < 12; i++) twelve.Add("p" + i);
            Check(!PlayerCardMotionCore.ParseRead(string.Join("|", twelve.ConvertAll(x => x + ":-")), twelve, out e), "twelve ids");
        }

        private static void AtlasShapeCase()
        {
            int c, w, h;
            Check(PlayerCardMotionCore.AtlasShape(80, "card", out c, out w, out h) && c == 256 && w == 2048 && h == 2560, "card 80");
            Check(PlayerCardMotionCore.AtlasShape(120, "card", out c, out w, out h) && h == 3840, "card 120");
            Check(PlayerCardMotionCore.AtlasShape(90, "tile", out c, out w, out h) && c == 96 && w == 768 && h == 12 * 96, "tile 90");
            Check(!PlayerCardMotionCore.AtlasShape(0, "card", out c, out w, out h), "0 frames");
            Check(!PlayerCardMotionCore.AtlasShape(121, "card", out c, out w, out h), "121 frames");
            Check(!PlayerCardMotionCore.AtlasShape(80, "gif", out c, out w, out h), "unknown size");
        }

        private static void AtlasIhdr()
        {
            var px = new byte[768 * 96 * 4];
            var png = ScrPng.EncodeRgba(px, 768, 96, false);
            Check(PlayerCardMotionCore.AtlasHeaderOk(png, 8, "tile"), "an 8-frame tile atlas");
            Check(!PlayerCardMotionCore.AtlasHeaderOk(png, 9, "tile"), "the height of 8 frames for 9");
            Check(!PlayerCardMotionCore.AtlasHeaderOk(png, 8, "card"), "a tile atlas as a card");
            var il = (byte[])png.Clone(); il[28] = 1;
            PutBE(il, 29, ScrPng.Crc32(il, 12, 17));
            Check(!PlayerCardMotionCore.AtlasHeaderOk(il, 8, "tile"), "an interlaced atlas");
            var rgb = (byte[])png.Clone(); rgb[25] = 2;
            PutBE(rgb, 29, ScrPng.Crc32(rgb, 12, 17));
            Check(!PlayerCardMotionCore.AtlasHeaderOk(rgb, 8, "tile"), "an RGB atlas");
            var big = new byte[PlayerCardMotionCore.TILE_ATLAS_MAX_BYTES + 1];
            Buffer.BlockCopy(png, 0, big, 0, 33);
            Check(!PlayerCardMotionCore.AtlasHeaderOk(big, 8, "tile"), "an atlas above its byte cap");
        }

        /// <summary>T39 playback truth table (S5.3): a clip that ran to DONE in
        /// this visit plays again only after a re-arm event.</summary>
        private static void T39()
        {
            var rows = new List<KeyValuePair<string, bool>>();
            Func<string, Action<MotionVisit, MotionClips, int[]>, bool> run = (name, ev) =>
            {
                var v = new MotionVisit();
                var c = new MotionClips();
                var seq = new[] { 1 };
                double now = 100.0;
                v.ViewShown("binder");
                v.PageShown("binder:0", now);
                c.Sync(v.Serial);
                var clip = c.Get("print-a", seq[0]);
                MotionClips.Start(clip, now, 80, 50);
                Check(MotionClips.Frame(clip, now + 1.0) == 20, "frame at 1 s");
                Check(MotionClips.Frame(clip, now + 4.0) == -1 && clip.State == ClipState.Done, "done at 4 s");
                ev(v, c, seq);
                c.Sync(v.Serial);
                bool rearmed = c.Get("print-a", seq[0]).State == ClipState.None;
                rows.Add(new KeyValuePair<string, bool>(name, rearmed));
                return rearmed;
            };
            double t = 200.0;
            var expect = new List<KeyValuePair<string, bool>>
            {
                new KeyValuePair<string, bool>("page change", true),
                new KeyValuePair<string, bool>("return to a prior page", true),
                new KeyValuePair<string, bool>("history page change", true),
                new KeyValuePair<string, bool>("subview switch", true),
                new KeyValuePair<string, bool>("leave the tab and return", true),
                new KeyValuePair<string, bool>("overlay close and reopen", true),
                new KeyValuePair<string, bool>("hover", false),
                new KeyValuePair<string, bool>("popup open and close", false),
                new KeyValuePair<string, bool>("scroll / recycled tile binding", false),
                new KeyValuePair<string, bool>("sort to page 0", false),
                new KeyValuePair<string, bool>("filter clamps the page", false),
                new KeyValuePair<string, bool>("dirty repaint", false),
                new KeyValuePair<string, bool>("api refresh clamps the page", false),
                new KeyValuePair<string, bool>("atlas eviction and refetch", false),
                new KeyValuePair<string, bool>("focus loss", false),
                new KeyValuePair<string, bool>("AnimatedCosmetics off and on", false),
                new KeyValuePair<string, bool>("next page at the last page", false),
                new KeyValuePair<string, bool>("same subview clicked again", false),
            };
            var got = new Dictionary<string, bool>
            {
                ["page change"] = run("page change", (v, c, s) => { v.NavRequested(t); v.PageShown("binder:1", t); }),
                ["return to a prior page"] = run("return to a prior page", (v, c, s) => { v.NavRequested(t); v.PageShown("binder:1", t); v.NavRequested(t + 1); v.PageShown("binder:0", t + 1); }),
                ["history page change"] = run("history page change", (v, c, s) => { v.ViewShown("open"); v.PageShown("open:pack-9", t); v.NavRequested(t); v.PageShown("open:pack-8", t + 0.5); }),
                ["subview switch"] = run("subview switch", (v, c, s) => { v.ViewShown("open"); v.PageShown("open:pack-9", t); }),
                ["leave the tab and return"] = run("leave the tab and return", (v, c, s) => { v.TabEntered(); }),
                ["overlay close and reopen"] = run("overlay close and reopen", (v, c, s) => { v.TabEntered(); }),
                ["hover"] = run("hover", (v, c, s) => { }),
                ["popup open and close"] = run("popup open and close", (v, c, s) => { }),
                ["scroll / recycled tile binding"] = run("scroll / recycled tile binding", (v, c, s) => { s[0] = 7; }),
                // the sort and the filter move the key while a nav request is still live (a next click at the
                // last page did not move it): only Rebase keeps that from counting as a page change
                ["sort to page 0"] = run("sort to page 0", (v, c, s) => { v.NavRequested(t); v.PageShown("binder:2", t); c.Sync(v.Serial); c.Get("print-a", s[0]).State = ClipState.Done; v.NavRequested(t + 1); v.PageShown("binder:2", t + 1); v.Rebase(); v.PageShown("binder:0", t + 2); }),
                ["filter clamps the page"] = run("filter clamps the page", (v, c, s) => { v.NavRequested(t); v.PageShown("binder:3", t); c.Sync(v.Serial); c.Get("print-a", s[0]).State = ClipState.Done; v.NavRequested(t + 1); v.PageShown("binder:3", t + 1); v.Rebase(); v.PageShown("binder:1", t + 2); }),
                ["dirty repaint"] = run("dirty repaint", (v, c, s) => { v.PageShown("binder:0", t); v.PageShown("binder:0", t + 1); }),
                ["api refresh clamps the page"] = run("api refresh clamps the page", (v, c, s) => { v.PageShown("binder:3", t + 30); }),
                ["atlas eviction and refetch"] = run("atlas eviction and refetch", (v, c, s) => { }),
                ["focus loss"] = run("focus loss", (v, c, s) => { }),
                ["AnimatedCosmetics off and on"] = run("AnimatedCosmetics off and on", (v, c, s) => { c.MarkAllDone(); }),
                ["next page at the last page"] = run("next page at the last page", (v, c, s) => { v.NavRequested(t); v.PageShown("binder:0", t); v.PageShown("binder:4", t + 60); }),
                ["same subview clicked again"] = run("same subview clicked again", (v, c, s) => { v.ViewShown("binder"); }),
            };
            // a new process is a fresh visit object: the clip of the old one is gone
            var v2 = new MotionVisit(); var c2 = new MotionClips(); c2.Sync(v2.Serial);
            Check(c2.Get("print-a", 1).State == ClipState.None, "new process");
            var bad = new List<string>();
            foreach (var kv in expect) if (got[kv.Key] != kv.Value) bad.Add(kv.Key + " re-armed=" + got[kv.Key]);
            foreach (var kv in expect) Console.WriteLine("  t39 " + (kv.Value ? "re-arms   " : "no re-arm ") + kv.Key + ": " + (got[kv.Key] == kv.Value ? "ok" : "WRONG"));
            Check(bad.Count == 0, string.Join("; ", bad));
        }

        /// <summary>T41: at `fps` the clip ends at t0 + N x period within one
        /// frame, on real time.</summary>
        private static void T41(double fps)
        {
            const int frames = 100, ms = 50;
            var clip = new MotionClips.Clip();
            double t0 = 3.0;
            MotionClips.Start(clip, t0, frames, ms);
            double end = t0 + frames * ms / 1000.0, done = double.NaN;
            int shown = 0, last = -1;
            for (int i = 0; i < 100000; i++)
            {
                double now = t0 + i / fps;
                int k = MotionClips.Frame(clip, now);
                if (k < 0) { done = now; break; }
                Check(k >= last, "the index went back");
                if (k != last) shown++;
                last = k;
            }
            Check(!double.IsNaN(done), "never ended");
            Check(done >= end - 1e-9 && done - end <= 1.0 / fps + 1e-9, "at " + fps + " fps the clip ended at " + (done - t0).ToString("F4", CultureInfo.InvariantCulture) + " s, expected " + (end - t0) + " s within " + (1.0 / fps).ToString("F4", CultureInfo.InvariantCulture));
            Console.WriteLine("  t41 " + fps + " fps: ended " + ((done - end) * 1000.0).ToString("F1", CultureInfo.InvariantCulture) + " ms after t0 + N x period, " + shown + " distinct frames shown"
                + (Math.Abs(fps * ms - 1000.0) < 1e-9 ? " (a tick equal to the period aliases single frames on floating time; T41 judges the end bound)" : ""));
        }

        /// <summary>T49: after a motion 429 no motion request for 60 s of real
        /// time, across page changes (new visits).</summary>
        private static void T49()
        {
            var g = new MotionRequestGate();
            var v = new MotionVisit();
            double t = 1000.0, r;
            Check(g.Allowed(v.Serial, t), "the first read of the visit");
            Check(g.OnAnswer(v.Serial, t, 429, "rate_limited", 60, "read", out r) == MotionRequestGate.Next.Stop, "429 stops");
            Check(!g.Allowed(v.Serial, t + 1), "the same visit after a 429");
            v.NavRequested(t + 5); v.PageShown("binder:1", t + 5);
            Check(!g.Allowed(v.Serial, t + 5), "a new visit 5 s after a 429");
            v.TabEntered();
            Check(!g.Allowed(v.Serial, t + 59.9), "a new visit 59.9 s after a 429");
            Check(g.Allowed(v.Serial, t + 60.0), "60 s after the 429");
        }

        private static void T49Control()
        {
            var g = new MotionRequestGate();
            var v = new MotionVisit();
            double t = 50.0, r;
            Check(g.Allowed(v.Serial, t) && g.OnAnswer(v.Serial, t, 200, null, -1, "read", out r) == MotionRequestGate.Next.Use, "visit 1 read");
            v.TabEntered();
            Check(g.Allowed(v.Serial, t + 1), "visit 2 read");
            // any other non-200 stops only its own visit
            Check(g.OnAnswer(v.Serial, t + 1, 404, "http", -1, "atlas-x", out r) == MotionRequestGate.Next.Stop && !g.Allowed(v.Serial, t + 2), "404 stops the visit");
            v.TabEntered();
            Check(g.Allowed(v.Serial, t + 2), "the next visit after a 404");
            // one retry of a 503 motion_pending per key, after its retry_after
            Check(g.OnAnswer(v.Serial, t + 3, 503, "motion_pending", 5, "atlas-y", out r) == MotionRequestGate.Next.Retry && r == t + 8, "pending retry");
            Check(g.OnAnswer(v.Serial, t + 8, 503, "motion_pending", 5, "atlas-y", out r) == MotionRequestGate.Next.Stop, "a second pending stops");
        }

        /// <summary>T40 (arithmetic half): `cycles` page, tab and popup cycles
        /// through the atlas budget. Every admitted atlas is one texture plus
        /// one sprite per cell; an eviction must release both. The budget stays
        /// at or under 64 MiB whenever the pinned set fits, and the live object
        /// count returns to zero after the last Clear. Without the popup one
        /// page of tile atlases fits and nothing is evicted: the control.</summary>
        private static void T40(int cycles, bool popup)
        {
            var b = new AtlasBudget();
            var live = new Dictionary<string, int>();
            long liveObjects = 0, maxTotal = 0;
            Action<string> release = k => { int n; if (live.TryGetValue(k, out n)) { liveObjects -= n; live.Remove(k); } };
            var r = new Random(4);
            double now = 0;
            int page = 0;
            for (int cyc = 0; cyc < cycles; cyc++)
            {
                var pins = new HashSet<string>();
                b.SetPinned(pins);
                for (int i = 0; i < 10; i++)
                {
                    int frames = 80 + r.Next(41);
                    int cell, w, h;
                    PlayerCardMotionCore.AtlasShape(frames, "tile", out cell, out w, out h);
                    string key = "p" + (page * 10 + i) + ":rev:tile";
                    now += 0.1;
                    b.Admit(key, (long)w * h * 4, now, release);
                    live[key] = 1 + frames; liveObjects += 1 + frames;
                    pins.Add(key);
                    b.SetPinned(pins);
                    maxTotal = Math.Max(maxTotal, b.Total);
                }
                if (popup)
                {
                    // the popup: the page's atlases unpin, one card atlas fits
                    pins.Clear(); b.SetPinned(pins);
                    int cf = 120;
                    int cc, cw, ch;
                    PlayerCardMotionCore.AtlasShape(cf, "card", out cc, out cw, out ch);
                    string ck = "p" + (page * 10) + ":rev:card";
                    now += 0.1;
                    b.Admit(ck, (long)cw * ch * 4, now, release);
                    live[ck] = 1 + cf; liveObjects += 1 + cf;
                    Check(b.Total <= b.Cap, "cycle " + cyc + ": " + b.Total + " bytes held with nothing pinned but the card");
                }
                maxTotal = Math.Max(maxTotal, b.Total);
                page++;
            }
            Check(maxTotal <= PlayerCardMotionCore.CACHE_CAP_BYTES, "held " + maxTotal + " bytes");
            long before = liveObjects;
            b.Clear(release);
            Check(liveObjects == 0 && live.Count == 0 && b.Total == 0 && b.Count == 0, "after " + cycles + " cycles: " + liveObjects + " objects of " + live.Count + " atlases still live");
            Console.WriteLine("  t40 cycles=" + cycles + " evictions=" + b.Evictions + " max held=" + maxTotal + " live before the last clear=" + before);
        }

        // ======================================================= S1.2 decision

        private const string H1 = "1111111111111111111111111111111111111111111111111111111111111111";
        private const string H2 = "2222222222222222222222222222222222222222222222222222222222222222";
        private const string BASE = "v1|face=a|off=0,0|color=c:ffffff|effect=|skin=0|anim=0|g=1|r=3";
        private const string DANCE = BASE + "|dance=dance_floss|ar=1";

        /// <summary>S1.2 / T48's pure half: every route of the per-visit
        /// decision, including the remembered key (a refused or failed job is
        /// not captured again) and the seat that cannot dance.</summary>
        private static void DecideTruthTable()
        {
            string cur = H1 + ":" + H2 + ":1";
            Func<bool, string, bool, string, string, string, string, bool, bool, DanceMotionCore.Need> d =
                (sup, sku, owned, mot, hash, stored, dance, can, rem) => DanceMotionCore.Decide(sup, sku, owned, mot, hash, stored, dance, 1, can, rem);
            Check(d(false, "dance_floss", true, cur, H2, DANCE, DANCE, true, false) == DanceMotionCore.Need.None, "older server: None");
            Check(d(true, "", true, cur, H2, DANCE, DANCE, true, false) == DanceMotionCore.Need.None, "no selection: None");
            Check(d(true, "dance_floss", false, cur, H2, DANCE, DANCE, true, false) == DanceMotionCore.Need.None, "not owned here: None");
            Check(d(true, "dance_floss", true, cur, H2, DANCE, null, true, false) == DanceMotionCore.Need.Fallback, "no dance descriptor: Fallback");
            Check(d(true, "dance_floss", true, cur, H2, DANCE, DANCE, true, false) == DanceMotionCore.Need.Current, "bound and current: Current");
            Check(d(true, "dance_floss", true, cur, H2, DANCE, DANCE, false, true) == DanceMotionCore.Need.Current, "current wins over a hold or a memory");
            Check(d(true, "dance_floss", true, "", H2, BASE, DANCE, true, false) == DanceMotionCore.Need.Needed, "no motion: Needed");
            Check(d(true, "dance_floss", true, cur, H1, DANCE, DANCE, true, false) == DanceMotionCore.Need.Needed, "still replaced: Needed");
            Check(d(true, "dance_floss", true, "", H2, BASE, DANCE, false, false) == DanceMotionCore.Need.Fallback, "cannot dance here: Fallback");
            Check(d(true, "dance_floss", true, "", H2, BASE, DANCE, true, true) == DanceMotionCore.Need.Fallback, "remembered key: Fallback (T48)");
        }

        /// <summary>S1.2's four "differs" terms, each alone.</summary>
        private static void MotionCurrentTerms()
        {
            string cur = H1 + ":" + H2 + ":1";
            Check(DanceMotionCore.MotionCurrent(cur, H2, DANCE, DANCE, 1), "all terms equal: current");
            Check(!DanceMotionCore.MotionCurrent("", H2, DANCE, DANCE, 1), "no stored motion");
            Check(!DanceMotionCore.MotionCurrent(cur, H1, DANCE, DANCE, 1), "bound still hash differs");
            Check(!DanceMotionCore.MotionCurrent(cur, H2, DANCE, DANCE, 2), "recipe differs");
            Check(!DanceMotionCore.MotionCurrent(cur, H2, BASE, DANCE, 1), "stored descriptor differs");
            Check(!DanceMotionCore.MotionCurrent(H1 + ":" + H2, H2, DANCE, DANCE, 1), "two fields");
            Check(!DanceMotionCore.MotionCurrent("xyz:" + H2 + ":1", H2, DANCE, DANCE, 1), "not a hash");
        }

        /// <summary>The still-only path's "picture current" rows.</summary>
        private static void StillCurrentRows()
        {
            Check(DanceMotionCore.StillCurrent(H2, BASE, BASE, null), "base still, no selection: current");
            Check(DanceMotionCore.StillCurrent(H2, DANCE, BASE, DANCE), "dancer still on the fallback: current");
            Check(!DanceMotionCore.StillCurrent(H2, DANCE, BASE, null), "suffixed still, selection cleared: replaced");
            Check(!DanceMotionCore.StillCurrent(H2, BASE + "x", BASE, DANCE), "other inputs: replaced");
            Check(!DanceMotionCore.StillCurrent("", BASE, BASE, null), "no stored still: replaced");
        }

        private static void RememberKeyStable()
        {
            string a = DanceMotionCore.RememberKey("7656", DANCE), b = DanceMotionCore.RememberKey("7656", DANCE);
            Check(a == b, "same inputs, same key");
            Check(a != DanceMotionCore.RememberKey("7656", BASE + "|dance=dance_robot|ar=1"), "another dance, another key");
            Check(a != DanceMotionCore.RememberKey("7657", DANCE), "another identity, another key");
        }

        /// <summary>T50's calibrated arm (finding M9): a deterministic stall of
        /// 10 ms per MiB of a texture band stands in for the upload, so one card
        /// band (2 MiB, 20 ms) stays under the 33 ms slice and two cross it.
        /// With the gate at one step per Unity frame the largest card atlas plus
        /// a page of tile atlases never costs a frame more than 33 ms; the tile
        /// atlas alone is the passing control either way.</summary>
        private static void T50(bool withCard)
        {
            const double MS_PER_MIB = 10.0, SLICE_MAX = 33.0;
            var queue = new Queue<double>();
            int cell, w, h;
            if (withCard)
            {
                PlayerCardMotionCore.AtlasShape(120, "card", out cell, out w, out h);
                for (int b = 0; b < h / cell; b++) queue.Enqueue((double)w * cell * 4 / (1 << 20) * MS_PER_MIB);
            }
            int tiles = withCard ? 10 : 1;
            for (int t = 0; t < tiles; t++)
            {
                PlayerCardMotionCore.AtlasShape(120, "tile", out cell, out w, out h);
                for (int b = 0; b < h / cell; b++) queue.Enqueue((double)w * cell * 4 / (1 << 20) * MS_PER_MIB);
            }
            var gate = new FrameGate();
            double worst = 0;
            int frame = 0;
            while (queue.Count > 0 && frame < 100000)
            {
                double cost = 0;
                while (queue.Count > 0 && gate.TryTake(frame)) cost += queue.Dequeue();
                worst = Math.Max(worst, cost);
                frame++;
            }
            Check(worst <= SLICE_MAX, "a frame spent " + worst.ToString("F1", CultureInfo.InvariantCulture) + " ms on band uploads");
            Console.WriteLine("  t50 " + (withCard ? "card+tiles" : "tile alone") + ": worst frame " + worst.ToString("F1", CultureInfo.InvariantCulture) + " ms over " + frame + " frames");
        }

        // ============================================== the rig's teardown (L1)

        /// <summary>Round three, finding RR-R2-2: the teardown of a portrait
        /// pose, through the product's own DanceMotionCore.EndPose and UndoEach
        /// (DanceEmotes.EndPortraitPose and RestorePortraitRig call exactly
        /// these). Six remembered entries: r0-r3 under the rig, x9 outside it,
        /// and one destroyed entry. With `failFirst` the undo of the FIRST rig
        /// entry throws. The pose clear records what is still owed at that
        /// moment. Must hold: nothing under the rig is owed when the pose is
        /// cleared; every rig entry was attempted exactly once and removed;
        /// the outside entry is untouched and still remembered; the dead entry
        /// is forgotten; a second teardown attempts nothing.</summary>
        private static void RigUndo(bool failFirst)
        {
            var owed = new Dictionary<string, int>();
            foreach (var k in new[] { "r0", "r1", "r2", "x9", "dead", "r3" }) owed[k] = 1;
            var attempts = new Dictionary<string, int>();
            var failures = new List<string>();
            int owedAtClear = -1, clears = 0;
            bool posed = true;
            Func<int> restore = () => DanceMotionCore.UndoEach(new List<string>(owed.Keys),
                k => k == "dead",
                k => !k.StartsWith("r", StringComparison.Ordinal),
                k =>
                {
                    Check(posed, "entry " + k + " undone after the pose was cleared");
                    attempts[k] = (attempts.ContainsKey(k) ? attempts[k] : 0) + 1;
                    if (failFirst && k == "r0") throw new InvalidOperationException("injected undo failure on " + k);
                },
                k => { owed.Remove(k); },
                (k, e) => failures.Add(k + ":" + e.GetType().Name));
            Action clearPose = () =>
            {
                clears++;
                if (posed)
                {
                    owedAtClear = 0;
                    foreach (var k in owed.Keys) if (k.StartsWith("r", StringComparison.Ordinal)) owedAtClear++;
                }
                posed = false;
            };
            DanceMotionCore.EndPose(restore, clearPose, false);
            Check(clears == 1, "the pose was cleared " + clears + " times");
            Check(owedAtClear == 0, owedAtClear + " rig entries were still owed when the pose was cleared");
            foreach (var k in new[] { "r0", "r1", "r2", "r3" })
                Check(attempts.ContainsKey(k) && attempts[k] == 1, "rig entry " + k + " attempted " + (attempts.ContainsKey(k) ? attempts[k] : 0) + " times");
            Check(!attempts.ContainsKey("x9") && owed.ContainsKey("x9"), "the entry outside the rig was touched or forgotten");
            Check(!attempts.ContainsKey("dead") && !owed.ContainsKey("dead"), "the dead entry was undone or kept");
            Check(failures.Count == (failFirst ? 1 : 0), "failures logged: " + string.Join(",", failures));
            posed = true;
            int again = restore();
            Check(again == 0 && failures.Count == (failFirst ? 1 : 0), "a second teardown undid " + again + " entries");
            foreach (var k in new[] { "r0", "r1", "r2", "r3" }) Check(attempts[k] == 1, "rig entry " + k + " attempted twice");
            Console.WriteLine("  rig undo " + (failFirst ? "(first entry throws)" : "(clean)") + ": owed at pose clear " + owedAtClear
                + ", attempts r0-r3 " + attempts["r0"] + "/" + attempts["r1"] + "/" + attempts["r2"] + "/" + attempts["r3"]
                + ", outside kept " + owed.ContainsKey("x9") + ", failures " + failures.Count);
        }
    }
}
