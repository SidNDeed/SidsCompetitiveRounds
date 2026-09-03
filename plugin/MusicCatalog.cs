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
        // ground truth (plugin/music/manifest.json — ar1 = album 1, ar2 = album 2
        // tracks 1-12, ar3 = album 2 tracks 13-14 appended); regenerate on
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
            new MusicAlbumDef
            {
                Sku = "music_album_clavar_la_bala",
                AlbumName = "Clavar la Bala",
                ArtistName = "Sid",
                Genre = "Flamenco Metal",
                CoverPngFile = "music_album_clavar_la_bala.png",
                Tracks = new[]
                {
                    new MusicTrackDef { Title = "Clavar la Bala", OggFile = "mus_cb_01_clavar_la_bala.ogg", PreviewFile = "mus_cb_01_clavar_la_bala_preview.ogg",
                    DurationSeconds = 237.2f, PreviewStartSeconds = 170.1f,
                    OggSize = 4635184L, OggSha256 = "190c4d45856403ef96779aa84ca4ea0b0e72f11546d2d288f59f025de3e8bec1",
                    PreviewSize = 377513L, PreviewSha256 = "63a8a4b76c09c3be56ce65ce90b63a1fd28a92b899a6a07ef2b457319bf27ba3" },
                    new MusicTrackDef { Title = "A Cinco Rondas", OggFile = "mus_cb_02_a_cinco_rondas.ogg", PreviewFile = "mus_cb_02_a_cinco_rondas_preview.ogg",
                    DurationSeconds = 239.6f, PreviewStartSeconds = 187.6f,
                    OggSize = 4907451L, OggSha256 = "a367a3f1503319fdbc50cd5caf9fc66239704bbb6bffded0c6824f82848dbe9e",
                    PreviewSize = 381027L, PreviewSha256 = "c3ad6f5998933da42a1e53e6d2a095fc1314aba379cea2cc249151b1b66dc4a3" },
                    new MusicTrackDef { Title = "A Cinco Rondas II", OggFile = "mus_cb_03_a_cinco_rondas_ii.ogg", PreviewFile = "mus_cb_03_a_cinco_rondas_ii_preview.ogg",
                    DurationSeconds = 194.4f, PreviewStartSeconds = 157.3f,
                    OggSize = 3995537L, OggSha256 = "4dd310c24fbf3818684fffca416d7ef324691d712ea916387a910288604a6570",
                    PreviewSize = 388984L, PreviewSha256 = "c04cad601500e4066105d4d46e6e06cc772b8fbe2ca48873a82c6a6b375d9439" },
                    new MusicTrackDef { Title = "Bloqueo Perfecto", OggFile = "mus_cb_04_bloqueo_perfecto.ogg", PreviewFile = "mus_cb_04_bloqueo_perfecto_preview.ogg",
                    DurationSeconds = 82.7f, PreviewStartSeconds = 33.2f,
                    OggSize = 1657385L, OggSha256 = "c1cde983c56d4f8066df71a69823d4e05a422ed45e543af13beab45646d06cdd",
                    PreviewSize = 333446L, PreviewSha256 = "ff9e49f29fb6e1e83ec3b9717b78c40d3f050bc12f8e9117c5e3641e73987db2" },
                    new MusicTrackDef { Title = "El Que Pierde Elige", OggFile = "mus_cb_05_el_que_pierde_elige.ogg", PreviewFile = "mus_cb_05_el_que_pierde_elige_preview.ogg",
                    DurationSeconds = 200.9f, PreviewStartSeconds = 148.7f,
                    OggSize = 3850265L, OggSha256 = "7c2562d662dddbeb42cc37687ca3abcb3c4e77fa808397ec0dcb537f146ab927",
                    PreviewSize = 361349L, PreviewSha256 = "cb90f42732410ae22be3ba7d41fe8dc45a81d431b39629561eedc849b13663a2" },
                    new MusicTrackDef { Title = "El Que Pierde Elige II", OggFile = "mus_cb_06_el_que_pierde_elige_ii.ogg", PreviewFile = "mus_cb_06_el_que_pierde_elige_ii_preview.ogg",
                    DurationSeconds = 206.0f, PreviewStartSeconds = 146.2f,
                    OggSize = 4058199L, OggSha256 = "5d90b64d62037f9e869313230a6be4d7355bd3270f38d009e65c736d8645eadb",
                    PreviewSize = 333489L, PreviewSha256 = "e34c5e687dd9e01670611d2634cedf0a89dd89388803881e4f786ab43bc7b705" },
                    new MusicTrackDef { Title = "Corona Prestada", OggFile = "mus_cb_07_corona_prestada.ogg", PreviewFile = "mus_cb_07_corona_prestada_preview.ogg",
                    DurationSeconds = 177.4f, PreviewStartSeconds = 139.3f,
                    OggSize = 3419110L, OggSha256 = "b3178178e9a1804561b20223064bbbc4c5e617c80d3c82682dba998fb5d651bc",
                    PreviewSize = 380869L, PreviewSha256 = "173c33607262fa8af58dc4b9919c0b0f6fb9544a95efd3077af0c08723f9a1cf" },
                    new MusicTrackDef { Title = "Corona Prestada II", OggFile = "mus_cb_08_corona_prestada_ii.ogg", PreviewFile = "mus_cb_08_corona_prestada_ii_preview.ogg",
                    DurationSeconds = 238.3f, PreviewStartSeconds = 198.0f,
                    OggSize = 4474272L, OggSha256 = "e2e35805fcfc0790c3977a3da4075228c52424204e958f5d627074164aa784da",
                    PreviewSize = 333803L, PreviewSha256 = "6095f0863bc563d3a204345371c18181e61db484060ad7b5d522970da0d4f5ef" },
                    new MusicTrackDef { Title = "La Distancia para una Revancha", OggFile = "mus_cb_09_la_distancia_para_una_revancha.ogg", PreviewFile = "mus_cb_09_la_distancia_para_una_revancha_preview.ogg",
                    DurationSeconds = 239.4f, PreviewStartSeconds = 49.4f,
                    OggSize = 4778248L, OggSha256 = "e236ac0fca352ed1ea517a384849f42fc00bf7fc91eed1a968003d1a6c8d612f",
                    PreviewSize = 311754L, PreviewSha256 = "237897f6fee244fb7d2388b8c27b01245b3e879ec3806f8c632360b28af5b4c8" },
                    new MusicTrackDef { Title = "Muerte Súbita", OggFile = "mus_cb_10_muerte_subita.ogg", PreviewFile = "mus_cb_10_muerte_subita_preview.ogg",
                    DurationSeconds = 240.2f, PreviewStartSeconds = 123.9f,
                    OggSize = 4694361L, OggSha256 = "0e02f95d09cd522384489da8a771bb2b2c870e911da0ebd846873daa31e7a845",
                    PreviewSize = 372372L, PreviewSha256 = "7d62fc823d0d6750a742f8314b405cbd25c6c764a5db70006e06a7f53c0e3557" },
                    new MusicTrackDef { Title = "Muerte Súbita II", OggFile = "mus_cb_11_muerte_subita_ii.ogg", PreviewFile = "mus_cb_11_muerte_subita_ii_preview.ogg",
                    DurationSeconds = 236.3f, PreviewStartSeconds = 161.1f,
                    OggSize = 4722446L, OggSha256 = "5cf18959760d927d63088d315ebea6ec950cfd4322dc51eb384c0b6ff2e93887",
                    PreviewSize = 392598L, PreviewSha256 = "ba7a5e4b820511eed73e3deed1014342e7f665aeefa3c1d35b8b3fe174f2d575" },
                    new MusicTrackDef { Title = "Muerte Súbita III", OggFile = "mus_cb_12_muerte_subita_iii.ogg", PreviewFile = "mus_cb_12_muerte_subita_iii_preview.ogg",
                    DurationSeconds = 239.8f, PreviewStartSeconds = 188.1f,
                    OggSize = 4602250L, OggSha256 = "32d3ccfd48559de4f80059a57b79ad85d13b1f83e9df38a678b792fb73978319",
                    PreviewSize = 392007L, PreviewSha256 = "4f99707da918fe006f21c2b546cf3c18b25e0015bfa6b5e243e3b85588bd0e74" },
                    new MusicTrackDef { Title = "Principio de Ronda", OggFile = "mus_cb_13_principio_de_ronda.ogg", PreviewFile = "mus_cb_13_principio_de_ronda_preview.ogg",
                    DurationSeconds = 239.4f, PreviewStartSeconds = 53.3f,
                    OggSize = 4920551L, OggSha256 = "df4b2a8ce5e5452cfeb84c3db3d6dfa5f672335358ab794fdd5c4e432cb2abcf",
                    PreviewSize = 376831L, PreviewSha256 = "6c4a18f951150dd6128de359c6ca1bbe58e8762ed45a3699eeca4961cac29146" },
                    new MusicTrackDef { Title = "Nube Tóxica", OggFile = "mus_cb_14_nube_toxica.ogg", PreviewFile = "mus_cb_14_nube_toxica_preview.ogg",
                    DurationSeconds = 239.8f, PreviewStartSeconds = 95.1f,
                    OggSize = 4856138L, OggSha256 = "173c51a68f18467b5819c59b34568b2d9433bc836bde8985256d333120f393dd",
                    PreviewSize = 374493L, PreviewSha256 = "648ed11bf36542c943b4cff6346b05798095ff7ac93ee1d84da755dbd65b5cda" },
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
