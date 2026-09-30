using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;

namespace CompetitiveRounds
{
    /// <summary>A PNG writer and reader for straight 8-bit RGBA, and nothing
    /// else (dance cards, design S1.4 step 7 and S5.6). Pure managed code with
    /// no UnityEngine reference, so it runs on a worker thread -- the capture's
    /// frame encode, the card atlas decode -- and in the console harness
    /// (tools/tests/dance-cards-client) against these same bytes.
    ///
    /// The writer emits the one shape the motion upload accepts per frame
    /// (pc_motion.check_frame): signature, IHDR (8-bit, colour type 6, no
    /// interlace), one IDAT, IEND -- no ancillary chunk. Each row takes the
    /// filter whose output has the smallest sum of absolute signed bytes (the
    /// adaptive heuristic Pillow's writer uses), and the stream is zlib:
    /// header, raw deflate at CompressionLevel.Optimal, Adler-32. Same input,
    /// same runtime, same bytes (the capture's determinism, S1.7).
    ///
    /// The reader accepts only what the atlas route publishes (8-bit RGBA, no
    /// interlace), verifies every chunk CRC, the zlib header and the Adler-32,
    /// requires the inflated size to be exactly the image's, and refuses
    /// anything else by returning null -- never a partial image.</summary>
    internal static class ScrPng
    {
        internal static readonly byte[] Signature = { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A };
        private static readonly uint[] CrcTable = MakeCrcTable();

        private static uint[] MakeCrcTable()
        {
            var t = new uint[256];
            for (uint n = 0; n < 256; n++)
            {
                uint c = n;
                for (int k = 0; k < 8; k++) c = (c & 1u) != 0 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
                t[n] = c;
            }
            return t;
        }

        internal static uint Crc32(byte[] b, int off, int len)
        {
            uint c = 0xFFFFFFFFu;
            for (int i = off, end = off + len; i < end; i++) c = CrcTable[(c ^ b[i]) & 0xFFu] ^ (c >> 8);
            return c ^ 0xFFFFFFFFu;
        }

        private static uint Crc32Update(uint c, byte[] b, int off, int len)
        {
            for (int i = off, end = off + len; i < end; i++) c = CrcTable[(c ^ b[i]) & 0xFFu] ^ (c >> 8);
            return c;
        }

        internal static uint Adler32(byte[] b, int off, int len)
        {
            uint a = 1, s = 0;
            int i = off, end = off + len;
            while (i < end)
            {
                int n = Math.Min(end - i, 5552);
                for (int j = 0; j < n; j++) { a += b[i++]; s += a; }
                a %= 65521u; s %= 65521u;
            }
            return (s << 16) | a;
        }

        private static void PutBE(byte[] b, int off, uint v)
        {
            b[off] = (byte)(v >> 24); b[off + 1] = (byte)(v >> 16); b[off + 2] = (byte)(v >> 8); b[off + 3] = (byte)v;
        }

        private static uint GetBE(byte[] b, int off)
        {
            return ((uint)b[off] << 24) | ((uint)b[off + 1] << 16) | ((uint)b[off + 2] << 8) | b[off + 3];
        }

        private static void WriteChunk(Stream s, string type, byte[] data, int off, int len)
        {
            var head = new byte[8];
            PutBE(head, 0, (uint)len);
            for (int i = 0; i < 4; i++) head[4 + i] = (byte)type[i];
            s.Write(head, 0, 8);
            if (len > 0) s.Write(data, off, len);
            uint c = Crc32Update(0xFFFFFFFFu, head, 4, 4);
            c = Crc32Update(c, data, off, len) ^ 0xFFFFFFFFu;
            var tail = new byte[4];
            PutBE(tail, 0, c);
            s.Write(tail, 0, 4);
        }

        /// <summary>Straight RGBA8 (w x h x 4 bytes) as a PNG. `bottomUp`: the
        /// buffer's first row is the image's BOTTOM row, the order a Unity
        /// texture and an AsyncGPUReadback of it hold; the PNG's first row is
        /// always the image's top. `forceFilter` 0-4 pins every row to one
        /// filter (the harness's round-trip cases); -1 is the adaptive choice.</summary>
        internal static byte[] EncodeRgba(byte[] rgba, int w, int h, bool bottomUp, int forceFilter = -1)
        {
            if (rgba == null || w <= 0 || h <= 0 || (long)w * h * 4 != rgba.Length) throw new ArgumentException("rgba is not w x h x 4 bytes");
            int stride = w * 4;
            var raw = new byte[(long)(stride + 1) * h];
            var cand = new byte[5][];
            for (int f = 0; f < 5; f++) cand[f] = new byte[stride];
            var prev = new byte[stride];
            var cur = new byte[stride];
            for (int y = 0; y < h; y++)
            {
                Buffer.BlockCopy(rgba, (bottomUp ? h - 1 - y : y) * stride, cur, 0, stride);
                int best = 0;
                if (forceFilter >= 0 && forceFilter <= 4)
                {
                    best = forceFilter;
                    Filter(best, cur, prev, cand[best]);
                }
                else
                {
                    long bestSum = long.MaxValue;
                    for (int f = 0; f < 5; f++)
                    {
                        long s = Filter(f, cur, prev, cand[f]);
                        if (s < bestSum) { bestSum = s; best = f; }
                    }
                }
                int o = y * (stride + 1);
                raw[o] = (byte)best;
                Buffer.BlockCopy(cand[best], 0, raw, o + 1, stride);
                var t = prev; prev = cur; cur = t;
            }
            byte[] z = Zlib(raw);
            using (var ms = new MemoryStream(z.Length + 64))
            {
                ms.Write(Signature, 0, 8);
                var ihdr = new byte[13];
                PutBE(ihdr, 0, (uint)w);
                PutBE(ihdr, 4, (uint)h);
                ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
                WriteChunk(ms, "IHDR", ihdr, 0, 13);
                WriteChunk(ms, "IDAT", z, 0, z.Length);
                WriteChunk(ms, "IEND", new byte[0], 0, 0);
                return ms.ToArray();
            }
        }

        /// <summary>One row through filter `f` into `o`; returns the sum of the
        /// output bytes' absolute values read as signed (the adaptive heuristic).</summary>
        private static long Filter(int f, byte[] cur, byte[] prev, byte[] o)
        {
            const int bpp = 4;
            long sum = 0;
            int n = cur.Length;
            for (int i = 0; i < n; i++)
            {
                int left = i >= bpp ? cur[i - bpp] : 0;
                int up = prev[i];
                int v;
                switch (f)
                {
                    case 1: v = cur[i] - left; break;
                    case 2: v = cur[i] - up; break;
                    case 3: v = cur[i] - ((left + up) >> 1); break;
                    case 4: v = cur[i] - Paeth(left, up, i >= bpp ? prev[i - bpp] : 0); break;
                    default: v = cur[i]; break;
                }
                byte b = (byte)v;
                o[i] = b;
                sum += b < 128 ? b : 256 - b;
            }
            return sum;
        }

        private static int Paeth(int a, int b, int c)
        {
            int p = a + b - c;
            int pa = Math.Abs(p - a), pb = Math.Abs(p - b), pc = Math.Abs(p - c);
            if (pa <= pb && pa <= pc) return a;
            return pb <= pc ? b : c;
        }

        private static byte[] Zlib(byte[] raw)
        {
            using (var ms = new MemoryStream(raw.Length / 4 + 64))
            {
                ms.WriteByte(0x78); ms.WriteByte(0x9C);
                using (var d = new DeflateStream(ms, CompressionLevel.Optimal, true)) d.Write(raw, 0, raw.Length);
                uint ad = Adler32(raw, 0, raw.Length);
                var tail = new byte[4];
                PutBE(tail, 0, ad);
                ms.Write(tail, 0, 4);
                return ms.ToArray();
            }
        }

        /// <summary>The signature and the IHDR, which must be the first chunk
        /// and exactly 13 bytes; false for anything else. The values are read,
        /// not judged: the caller compares them with the shape it expects.</summary>
        internal static bool ReadIhdr(byte[] d, out int w, out int h, out int depth, out int colourType, out int interlace)
        {
            w = h = depth = colourType = interlace = -1;
            if (d == null || d.Length < 33) return false;
            for (int i = 0; i < 8; i++) if (d[i] != Signature[i]) return false;
            if (GetBE(d, 8) != 13 || d[12] != (byte)'I' || d[13] != (byte)'H' || d[14] != (byte)'D' || d[15] != (byte)'R') return false;
            uint uw = GetBE(d, 16), uh = GetBE(d, 20);
            if (uw == 0 || uh == 0 || uw > int.MaxValue || uh > int.MaxValue) return false;
            if (d[26] != 0 || d[27] != 0) return false;   // compression and filter method: the only defined ones
            w = (int)uw; h = (int)uh; depth = d[24]; colourType = d[25]; interlace = d[28];
            return true;
        }

        /// <summary>Decode an 8-bit RGBA, non-interlaced PNG of exactly
        /// expectW x expectH into bands of `band` image rows each (the last
        /// band may be shorter), band 0 being the image's TOP band and each
        /// band's rows stored BOTTOM-UP, the order Texture2D.LoadRawTextureData
        /// reads. Null on any deviation: signature, IHDR, a chunk CRC, a chunk
        /// before IHDR or after IEND, no IDAT, the zlib header (method 8,
        /// window <= 32 KiB, no preset dictionary, check bits), a filter type
        /// above 4, too few or too many inflated bytes, the Adler-32.
        /// `cancelled` is asked between rows; true abandons the decode (null).
        /// The inflate is streamed row by row, so the peak is one band plus two
        /// rows, never the whole image twice.</summary>
        internal static List<byte[]> DecodeBandsRgba8(byte[] png, int expectW, int expectH, int band, Func<bool> cancelled = null)
        {
            int w, h, depth, ct, il;
            if (band <= 0 || !ReadIhdr(png, out w, out h, out depth, out ct, out il)) return null;
            if (depth != 8 || ct != 6 || il != 0 || w != expectW || h != expectH) return null;
            byte[] z = Idat(png);
            if (z == null || z.Length < 6) return null;
            int cmf = z[0], flg = z[1];
            if ((cmf & 0x0F) != 8 || (cmf >> 4) > 7 || (flg & 0x20) != 0 || ((cmf << 8) | flg) % 31 != 0) return null;
            uint want = GetBE(z, z.Length - 4);
            int stride = w * 4;
            var bands = new List<byte[]>();
            var prev = new byte[stride];
            var cur = new byte[stride];
            var one = new byte[1];
            uint a = 1, s = 0;   // Adler-32 over the inflated stream, as it is read
            try
            {
                using (var src = new MemoryStream(z, 2, z.Length - 6, false))
                using (var inf = new DeflateStream(src, CompressionMode.Decompress))
                {
                    byte[] cb = null; int cbRows = 0, cbFill = 0;
                    for (int y = 0; y < h; y++)
                    {
                        if (cancelled != null && cancelled()) return null;
                        if (!ReadFully(inf, one, 1)) return null;
                        int f = one[0];
                        if (f > 4) return null;
                        if (!ReadFully(inf, cur, stride)) return null;
                        AdlerStep(ref a, ref s, one, 1);
                        AdlerStep(ref a, ref s, cur, stride);
                        Unfilter(f, cur, prev);
                        if (cb == null)
                        {
                            cbRows = Math.Min(band, h - y);
                            cb = new byte[cbRows * stride];
                            cbFill = 0;
                        }
                        // bottom-up inside the band: the band's first image row is its LAST buffer row
                        Buffer.BlockCopy(cur, 0, cb, (cbRows - 1 - cbFill) * stride, stride);
                        cbFill++;
                        if (cbFill == cbRows) { bands.Add(cb); cb = null; }
                        var t = prev; prev = cur; cur = t;
                    }
                    if (inf.Read(one, 0, 1) != 0) return null;   // more inflated data than the image holds
                }
            }
            catch (Exception) { return null; }
            if (((s << 16) | a) != want) return null;
            return bands;
        }

        /// <summary>The whole image (bands of the full height), bottom-up: the
        /// harness's round trip and small reads.</summary>
        internal static byte[] DecodeRgba8(byte[] png, int expectW, int expectH)
        {
            var b = DecodeBandsRgba8(png, expectW, expectH, expectH);
            return b != null && b.Count == 1 ? b[0] : null;
        }

        private static void AdlerStep(ref uint a, ref uint s, byte[] b, int len)
        {
            int i = 0;
            while (i < len)
            {
                int n = Math.Min(len - i, 5552);
                for (int j = 0; j < n; j++) { a += b[i++]; s += a; }
                a %= 65521u; s %= 65521u;
            }
        }

        private static bool ReadFully(Stream s, byte[] buf, int len)
        {
            int got = 0;
            while (got < len)
            {
                int n = s.Read(buf, got, len - got);
                if (n <= 0) return false;
                got += n;
            }
            return true;
        }

        private static void Unfilter(int f, byte[] cur, byte[] prev)
        {
            const int bpp = 4;
            int n = cur.Length;
            switch (f)
            {
                case 0: return;
                case 1: for (int i = bpp; i < n; i++) cur[i] = (byte)(cur[i] + cur[i - bpp]); return;
                case 2: for (int i = 0; i < n; i++) cur[i] = (byte)(cur[i] + prev[i]); return;
                case 3:
                    for (int i = 0; i < n; i++) cur[i] = (byte)(cur[i] + (((i >= bpp ? cur[i - bpp] : 0) + prev[i]) >> 1));
                    return;
                default:
                    for (int i = 0; i < n; i++)
                        cur[i] = (byte)(cur[i] + Paeth(i >= bpp ? cur[i - bpp] : 0, prev[i], i >= bpp ? prev[i - bpp] : 0));
                    return;
            }
        }

        /// <summary>Every IDAT's data concatenated, after checking the chunk
        /// walk: IHDR first, every CRC, IEND last with nothing after it, and
        /// at most 4096 chunks (pc_face.png_chunks' own bound). Null otherwise.</summary>
        private static byte[] Idat(byte[] d)
        {
            int off = 8, count = 0;
            bool sawIend = false, sawIdat = false;
            var ms = new MemoryStream();
            while (off + 12 <= d.Length)
            {
                if (++count > 4096) return null;
                uint len = GetBE(d, off);
                if (len > int.MaxValue || off + 12L + len > d.Length) return null;
                int n = (int)len;
                string type = new string(new[] { (char)d[off + 4], (char)d[off + 5], (char)d[off + 6], (char)d[off + 7] });
                if (count == 1 && type != "IHDR") return null;
                uint crc = Crc32(d, off + 4, 4 + n);
                if (crc != GetBE(d, off + 8 + n)) return null;
                if (type == "IDAT") { sawIdat = true; ms.Write(d, off + 8, n); }
                off += 12 + n;
                if (type == "IEND") { sawIend = true; break; }
            }
            if (!sawIend || !sawIdat || off != d.Length) return null;
            return ms.ToArray();
        }
    }
}
