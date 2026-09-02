using System;

namespace CompetitiveRounds
{
    /// <summary>
    /// Compiled music catalog — the client-side authority for every custom album
    /// the mod can render and play (music design v2 §2 as amended by v3). The
    /// server's shop row only gates PURCHASE; a music sku the compiled catalog
    /// does not know is dropped before any render/partition [F3], and the
    /// per-file sizes + SHA-256 here — not filename presence — are the validity
    /// authority for downloaded assets (MusicAssets builds its install manifest
    /// from these rows) [F22]/[F23].
    ///
    /// Album/track names and the artist credit are AUTHORED text: they render
    /// raw everywhere and are never routed through I18n.Tr (the artist-text rule,
    /// learning #368 — harvesting them would invite translations no render path
    /// consults).
    /// </summary>
    internal sealed class MusicAlbumDef
    {
        public string Sku;           // shop_items.sku (kind='music_album')
        public string AlbumName;
        public string ArtistName;
        public string Genre;
        public string CoverPngFile;  // file inside the PREVIEWS asset tier
        public MusicTrackDef[] Tracks;
    }

    internal sealed class MusicTrackDef
    {
        public string Title;
        public string OggFile;              // full-quality file (FULL tier)
        public string PreviewFile;          // 30s snippet (PREVIEWS tier)
        public float DurationSeconds;
        public float PreviewStartSeconds;   // loudest-30s window start in the full track
        public long OggSize;
        public long PreviewSize;
        public string OggSha256;
        public string PreviewSha256;
    }

    internal static class MusicCatalog
    {
        /// <summary>Virtual album id for the runtime-enumerated ROUNDS OST —
        /// never a shop row, never in Albums (design §2 [F21]).</summary>
        internal const string VANILLA_SKU = "vanilla_ost";

        // ── Catalog — APPEND ONLY. Sizes/hashes are the mastering pipeline's
        // ground truth (plugin/music/manifest.json, revision ar1); regenerate on
        // any re-master and bump MusicAssets.ASSET_REVISION in the same change —
        // changed bytes are a NEW immutable asset release, never a re-upload.
        internal static readonly MusicAlbumDef[] Albums = new[]
        {
            new MusicAlbumDef
            {
                Sku = "music_album_another_round",
                AlbumName = "Another Round",
                ArtistName = "Sid",
                Genre = "Metal / Phonk",
                CoverPngFile = "music_album_another_round.png",
                Tracks = new[]
                {
                    new MusicTrackDef { Title = "A Very Heavy Vintage Indeed", OggFile = "mus_ar_01_a_very_heavy_vintage_indeed.ogg", PreviewFile = "mus_ar_01_a_very_heavy_vintage_indeed_preview.ogg",
                        DurationSeconds = 161.7f, PreviewStartSeconds = 130.7f,
                        OggSize = 3128907L, OggSha256 = "5ce5591c2f7c96d400cb489127c374b43734bc93f96752231beadd7e87b4a0e9",
                        PreviewSize = 335887L, PreviewSha256 = "ef87faf454f242367c20d29345726d027645b0f06b84d8a1afd45e795a3e4de6" },
                    new MusicTrackDef { Title = "Combo Of The Doom", OggFile = "mus_ar_02_combo_of_the_doom.ogg", PreviewFile = "mus_ar_02_combo_of_the_doom_preview.ogg",
                        DurationSeconds = 154.8f, PreviewStartSeconds = 123.8f,
                        OggSize = 2750811L, OggSha256 = "960026c30cc5753829992b1b5d3c32278af730222bb693d1f84e10d50209db0d",
                        PreviewSize = 325198L, PreviewSha256 = "97a950736c371fc48173836a2bf069586e7134e4f2f19d3eff6cb4b0cb6900ab" },
                    new MusicTrackDef { Title = "Take Me Head On", OggFile = "mus_ar_03_take_me_head_on.ogg", PreviewFile = "mus_ar_03_take_me_head_on_preview.ogg",
                        DurationSeconds = 268.4f, PreviewStartSeconds = 177.9f,
                        OggSize = 5079431L, OggSha256 = "41f00edb7b82699c3a90060eb2fe4536074add52235488c1fa9467df5cbbda95",
                        PreviewSize = 342608L, PreviewSha256 = "1047a19920d1b7e9792debd25ba70184d6246245a6754e7e7895540f2c73ad95" },
                    new MusicTrackDef { Title = "Stealing The Lead", OggFile = "mus_ar_04_stealing_the_lead.ogg", PreviewFile = "mus_ar_04_stealing_the_lead_preview.ogg",
                        DurationSeconds = 255.2f, PreviewStartSeconds = 224.0f,
                        OggSize = 4784064L, OggSha256 = "8c32c8bfadc2de3d6f930c3ade7d69dcefee4896da9abec01930e5ba3ec18bf0",
                        PreviewSize = 340138L, PreviewSha256 = "4e062812151fcf8d88b5382517f14517d04ccaeb0b6b847ae0b7997f21f4967b" },
                    new MusicTrackDef { Title = "Push It Even Further", OggFile = "mus_ar_05_push_it_even_further.ogg", PreviewFile = "mus_ar_05_push_it_even_further_preview.ogg",
                        DurationSeconds = 137.1f, PreviewStartSeconds = 91.8f,
                        OggSize = 2619349L, OggSha256 = "38e997929c6a99497669a8ccc129a80cbf7c7cc40f6364c13c6206ae889c533e",
                        PreviewSize = 336443L, PreviewSha256 = "bef7a09ff77b1d230fca62ed220e5dee041257d0da7af4ed07a7b177be37f198" },
                    new MusicTrackDef { Title = "Set To Deep Fry", OggFile = "mus_ar_06_set_to_deep_fry.ogg", PreviewFile = "mus_ar_06_set_to_deep_fry_preview.ogg",
                        DurationSeconds = 144.2f, PreviewStartSeconds = 108.3f,
                        OggSize = 2673518L, OggSha256 = "93413cca4bca6c65c3435e2e040da8145583820dad7aa16d7acef017b7797f8c",
                        PreviewSize = 371820L, PreviewSha256 = "ec3a50af72f4ebf719bdf21c2213ea83eaba5b1e9164d79ca8e5bdf02ef970f5" },
                    new MusicTrackDef { Title = "Another Round", OggFile = "mus_ar_07_another_round.ogg", PreviewFile = "mus_ar_07_another_round_preview.ogg",
                        DurationSeconds = 300.4f, PreviewStartSeconds = 236.4f,
                        OggSize = 5357625L, OggSha256 = "9950533bc76a509ca4f0cba00a931d3e54e72e672ecc0931115b97dac14e9299",
                        PreviewSize = 385443L, PreviewSha256 = "3b3cf542978e5737d9cfb193cbb3788ac1be1832cd2154f0d77d7fbc7f574643" },
                },
            },
        };

        internal static MusicAlbumDef Get(string sku)
        {
            if (string.IsNullOrEmpty(sku)) return null;
            for (int i = 0; i < Albums.Length; i++)
                if (string.Equals(Albums[i].Sku, sku, StringComparison.OrdinalIgnoreCase))
                    return Albums[i];
            return null;
        }
    }
}
