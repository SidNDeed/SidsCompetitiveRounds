using System;
using System.Collections.Generic;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Music track/album rating store (music batch 2 design §2, as gated by the
    /// v4 design review) — the client half of the delayed-aggregate rating
    /// system. Fenced exactly like MusicEntitlements [M14]: every response
    /// application passes a generation gate (dispatch-stamped from ONE counter
    /// shared by fetches and writes; an invalidation advances the acceptance
    /// floor past everything ever dispatched, so no in-flight response can
    /// repopulate cleared state) and — for the PRIVATE own-intent data — an
    /// identity gate (the steam id captured at dispatch must equal the
    /// resolved local id at landing, ordinal).
    ///
    /// Aggregates are PUBLIC server data (effective rows only, 2-24h delayed
    /// server-side); the own-intent dict is PRIVATE identity data, fetched via
    /// the separate strict /music/ratings/mine endpoint and NEVER inferred
    /// from a failed fetch (an auth failure must not masquerade as "no own
    /// ratings" — [M17]/[M21], so ApplyOwn is only ever called on success).
    ///
    /// Writes are serialized per (sku, track_idx) with latest-intent
    /// coalescing and a single retry [M16]: at most one POST per track key is
    /// ever in flight, and every (re)send reads the CURRENT latest intent, so
    /// an older intent can never land after a newer one from this client. A
    /// twice-failed send rolls the optimistic value back to the last
    /// server-confirmed intent and repaints.
    ///
    /// Vanilla tracks are NOT ratable in v1.40 [M18]: Rate() validates the
    /// sku + track_idx against MusicCatalog.Albums (vanilla_ost is never a
    /// catalog row), and the UI hides stars on vanilla rows. Ownership is
    /// additionally required client-side as defense in depth [M13]; the
    /// server enforces it authoritatively.
    ///
    /// All entry points run on the main thread (Unity coroutine callbacks +
    /// UI clicks), matching MusicEntitlements — no locking.
    /// </summary>
    internal static class MusicRatings
    {
        // ── row shapes handed over by ApiClient's parsers ──
        internal sealed class TrackAggRow { public string sku; public int idx; public float avg; public int count; public int raters; }
        internal sealed class AlbumAggRow { public string sku; public float avg; public int count; public int raters; }
        internal sealed class OwnRow { public string sku; public int idx; public int stars; }

        private struct Agg { public float avg; public int count; public int raters; }

        // A queued write: the CANONICAL catalog sku (original casing, for the
        // wire) + track index + the newest intent value. Present in
        // latestIntent for the whole life of a send sequence — SendLoop reads
        // it, OnSendComplete removes it only once the sent value matches it.
        private sealed class PendingOp { public string sku; public int idx; public int stars; }

        // PUBLIC aggregates (server-effective rows only).
        private static readonly Dictionary<string, Agg> trackAgg = new Dictionary<string, Agg>(StringComparer.Ordinal);
        private static readonly Dictionary<string, Agg> albumAgg = new Dictionary<string, Agg>(StringComparer.OrdinalIgnoreCase);

        // PRIVATE own intent: shown = what the UI renders (optimistic overlay
        // included); confirmed = last server-acknowledged value (/mine fetch
        // + successful POSTs). Rollback target on terminal write failure.
        private static readonly Dictionary<string, int> ownShown = new Dictionary<string, int>(StringComparer.Ordinal);
        private static readonly Dictionary<string, int> ownConfirmed = new Dictionary<string, int>(StringComparer.Ordinal);

        // Per-key write serialization [M16].
        private static readonly Dictionary<string, PendingOp> latestIntent = new Dictionary<string, PendingOp>(StringComparer.Ordinal);
        private static readonly HashSet<string> inFlight = new HashSet<string>(StringComparer.Ordinal);
        private static readonly HashSet<string> retried = new HashSet<string>(StringComparer.Ordinal);

        // Dispatch-stamped generation shared by every fetch AND write this
        // store issues. genFloor is raised past dispatchGen on invalidation,
        // so anything in flight at revoke/identity-change time lands into the
        // void (MusicEntitlements' floor pattern, self-contained because the
        // counter lives here). aggCommittedGen/ownCommittedGen are the
        // newest-committed gates (R3: dispatch order is the truth — a slow
        // older response must never overwrite a newer commit, and a stale
        // /mine snapshot must never overwrite a just-confirmed write).
        private static int dispatchGen;
        private static int genFloor;
        private static int aggCommittedGen;
        private static int ownCommittedGen;

        private const float FETCH_THROTTLE_SECONDS = 60f;
        private static float lastAggFetchAt = -9999f;
        private static float lastOwnFetchAt = -9999f;

        /// <summary>Aggregate dict key. Lowercased sku so server-cased and
        /// catalog-cased rows meet; '#' can't appear in a sku.</summary>
        private static string Key(string sku, int idx) => sku.ToLowerInvariant() + "#" + idx;

        // ─────────────────────────── fetch ───────────────────────────

        /// <summary>Music-tab open hook (NativeUI calls this when the tab
        /// paints). 60s throttle per endpoint. Aggregates are public and
        /// always eligible; the own-mirror fetch dispatches only when the
        /// local identity is resolved AND a session token is held (its
        /// throttle stamps only on a real dispatch, so a pre-session tab
        /// open doesn't burn the window).</summary>
        internal static void FetchIfStale()
        {
            if (!Plugin.DataConsentGranted) return;
            float now = Time.unscaledTime;
            if (now - lastAggFetchAt >= FETCH_THROTTLE_SECONDS)
            {
                lastAggFetchAt = now;
                ApiClient.FetchMusicRatingAggregates(++dispatchGen);
            }
            string sid = null;
            try { sid = MatchTracker.LocalSteamId; } catch { }
            if (string.IsNullOrEmpty(sid) || sid == "unknown") return;
            if (string.IsNullOrEmpty(SteamAuth.SessionToken)) return;
            if (now - lastOwnFetchAt >= FETCH_THROTTLE_SECONDS)
            {
                lastOwnFetchAt = now;
                ApiClient.FetchMusicRatingsOwn(sid, ++dispatchGen);
            }
        }

        /// <summary>Landing site for GET /music/ratings (called by ApiClient
        /// on SUCCESS only). Floor + committed-gen + landing-side consent
        /// gates, then wholesale rebuild — the server list is authoritative
        /// for public aggregates.</summary>
        internal static void ApplyAggregates(int gen, List<TrackAggRow> tracks, List<AlbumAggRow> albums)
        {
            if (gen < genFloor || gen <= aggCommittedGen) return;
            if (!Plugin.DataConsentGranted) return;   // revoke raced the flight (G11 pattern)
            aggCommittedGen = gen;
            trackAgg.Clear();
            albumAgg.Clear();
            if (tracks != null)
                foreach (var t in tracks)
                {
                    if (t == null || string.IsNullOrEmpty(t.sku)) continue;
                    trackAgg[Key(t.sku, t.idx)] = new Agg { avg = t.avg, count = t.count, raters = t.raters };
                }
            if (albums != null)
                foreach (var a in albums)
                {
                    if (a == null || string.IsNullOrEmpty(a.sku)) continue;
                    albumAgg[a.sku] = new Agg { avg = a.avg, count = a.count, raters = a.raters };
                }
            NativeUI.MarkDirty();
        }

        /// <summary>Landing site for GET /music/ratings/mine (SUCCESS only —
        /// see class doc). Identity equality at landing [M14]: the dispatch
        /// id must equal the CURRENT resolved local id, so a response that
        /// raced an identity change renders nobody else's private stars.
        /// Rebuilds confirmed, then shown = confirmed + the optimistic
        /// overlay for keys whose write sequence is still pending.</summary>
        internal static void ApplyOwn(string steamId, int gen, List<OwnRow> rows)
        {
            if (gen < genFloor || gen <= ownCommittedGen) return;
            if (!Plugin.DataConsentGranted) return;
            string local = null;
            try { local = MatchTracker.LocalSteamId; } catch { }
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") return;
            if (string.IsNullOrEmpty(local) || local == "unknown") return;
            if (!string.Equals(steamId, local, StringComparison.Ordinal)) return;
            ownCommittedGen = gen;
            ownConfirmed.Clear();
            if (rows != null)
                foreach (var r in rows)
                {
                    if (r == null || string.IsNullOrEmpty(r.sku)) continue;
                    if (r.stars < 1 || r.stars > 5) continue;
                    ownConfirmed[Key(r.sku, r.idx)] = r.stars;
                }
            ownShown.Clear();
            foreach (var kv in ownConfirmed) ownShown[kv.Key] = kv.Value;
            foreach (var kv in latestIntent)
            {
                if (kv.Value.stars == 0) ownShown.Remove(kv.Key);
                else ownShown[kv.Key] = kv.Value.stars;
            }
            NativeUI.MarkDirty();
        }

        // ─────────────────────────── reads ───────────────────────────

        /// <summary>Public track aggregate. False (render a dash) when the
        /// server holds no effective ratings for the track.</summary>
        internal static bool TryGetTrack(string sku, int trackIdx, out float avg, out int ratingCount, out int raterCount)
        {
            avg = 0f; ratingCount = 0; raterCount = 0;
            if (string.IsNullOrEmpty(sku)) return false;
            Agg a;
            if (!trackAgg.TryGetValue(Key(sku, trackIdx), out a) || a.count <= 0) return false;
            avg = a.avg; ratingCount = a.count; raterCount = a.raters;
            return true;
        }

        /// <summary>Short form — what the Music-tab rows render ("4.2 (12)").
        /// ratingCount is the RATING count; the distinct-rater count stays
        /// available on the full overload [M20].</summary>
        internal static bool TryGetTrack(string sku, int trackIdx, out float avg, out int ratingCount)
        {
            int raters;
            return TryGetTrack(sku, trackIdx, out avg, out ratingCount, out raters);
        }

        /// <summary>Public album aggregate (server-computed; count vs
        /// distinct-rater semantics are the server's [M20] — both carried).</summary>
        internal static bool TryGetAlbum(string sku, out float avg, out int ratingCount)
        {
            int raters;
            return TryGetAlbum(sku, out avg, out ratingCount, out raters);
        }

        internal static bool TryGetAlbum(string sku, out float avg, out int ratingCount, out int raterCount)
        {
            avg = 0f; ratingCount = 0; raterCount = 0;
            if (string.IsNullOrEmpty(sku)) return false;
            Agg a;
            if (!albumAgg.TryGetValue(sku, out a) || a.count <= 0) return false;
            avg = a.avg; ratingCount = a.count; raterCount = a.raters;
            return true;
        }

        /// <summary>The caller's OWN stars for a track — optimistic value
        /// while a write is pending, else the last server-confirmed one.
        /// 0 = none. The UI derives "click same star = clear" from this and
        /// calls Rate(..., 0).</summary>
        internal static int GetOwn(string sku, int trackIdx)
        {
            if (string.IsNullOrEmpty(sku)) return 0;
            int v;
            return ownShown.TryGetValue(Key(sku, trackIdx), out v) ? v : 0;
        }

        // ─────────────────────────── writes ───────────────────────────

        /// <summary>Rate a track: stars 1..5 sets, 0 clears. Optimistic
        /// own-intent update + per-key serialized send [M16]. Refuses (log
        /// only — the UI never shows stars on refusable rows): no consent,
        /// unresolved identity, broadcast seat, a sku/idx outside the
        /// compiled catalog (vanilla_ost included — [M12]/[M18] client half),
        /// or an album the local player does not own ([M13] defense in depth;
        /// the server enforces ownership authoritatively).</summary>
        internal static void Rate(string sku, int trackIdx, int stars)
        {
            if (stars < 0 || stars > 5) return;
            if (!Plugin.DataConsentGranted) return;
            string sid = null;
            try { sid = MatchTracker.LocalSteamId; } catch { }
            if (string.IsNullOrEmpty(sid) || sid == "unknown")
            {
                Plugin.Log?.LogInfo("[MUSIC-RATE] rate refused: identity unresolved");
                return;
            }
            // The broadcast seat's Owns() is PLAYBACK authority, not a
            // purchase — its bot account must not rate.
            try { if (BroadcastMode.IsBroadcastIdentity) return; } catch { }
            var album = MusicCatalog.Get(sku);
            if (album == null || album.Tracks == null || trackIdx < 0 || trackIdx >= album.Tracks.Length)
            {
                Plugin.Log?.LogWarning($"[MUSIC-RATE] rate refused: unknown track {sku}#{trackIdx}");
                return;
            }
            if (!MusicEntitlements.Owns(album.Sku))
            {
                Plugin.Log?.LogInfo($"[MUSIC-RATE] rate refused: album not owned ({album.Sku})");
                return;
            }

            string key = Key(album.Sku, trackIdx);
            if (stars == 0) ownShown.Remove(key); else ownShown[key] = stars;
            latestIntent[key] = new PendingOp { sku = album.Sku, idx = trackIdx, stars = stars };
            retried.Remove(key);   // a fresh user intent gets a fresh single-retry budget
            NativeUI.MarkDirty();
            if (!inFlight.Contains(key)) SendLoop(key);
        }

        /// <summary>Dispatch the CURRENT latest intent for a key. At most one
        /// POST per key in flight — callers check inFlight (Rate) or own the
        /// completing flight (OnSendComplete).</summary>
        private static void SendLoop(string key)
        {
            PendingOp op;
            if (!latestIntent.TryGetValue(key, out op)) return;
            string sid = null;
            try { sid = MatchTracker.LocalSteamId; } catch { }
            if (string.IsNullOrEmpty(sid) || sid == "unknown")
            {
                // Near-unreachable (identity loss fires OnIdentityChanged,
                // which clears everything) — hygiene rollback, not a path.
                latestIntent.Remove(key);
                retried.Remove(key);
                int conf0;
                if (ownConfirmed.TryGetValue(key, out conf0)) ownShown[key] = conf0; else ownShown.Remove(key);
                NativeUI.MarkDirty();
                return;
            }
            inFlight.Add(key);
            int gen = ++dispatchGen;
            int sentStars = op.stars;
            ApiClient.PostMusicRating(sid, op.sku, op.idx, sentStars,
                (ok, resp) => OnSendComplete(key, sid, gen, sentStars, ok, resp));
        }

        private static void OnSendComplete(string key, string sentSid, int gen, int sentStars, bool ok, string resp)
        {
            // Invalidated while in flight: every dict was cleared and a NEW
            // sequence may already own the key — touch nothing (deliberately
            // including inFlight, which the new sequence re-added).
            if (gen < genFloor) return;
            inFlight.Remove(key);
            if (ok)
            {
                string local = null;
                try { local = MatchTracker.LocalSteamId; } catch { }
                if (string.Equals(sentSid, local, StringComparison.Ordinal))
                {
                    if (sentStars == 0) ownConfirmed.Remove(key); else ownConfirmed[key] = sentStars;
                    // R3: a /mine snapshot dispatched BEFORE this write must
                    // not overwrite the freshly confirmed value at landing.
                    if (gen > ownCommittedGen) ownCommittedGen = gen;
                }
                PendingOp cur;
                if (latestIntent.TryGetValue(key, out cur) && cur.stars != sentStars)
                {
                    retried.Remove(key);   // the newer coalesced intent gets its own retry budget
                    SendLoop(key);
                }
                else
                {
                    latestIntent.Remove(key);
                    retried.Remove(key);
                }
                return;
            }
            // Failure: retry ONCE with the CURRENT latest intent (which may
            // have coalesced past the value that just failed), then roll the
            // optimistic value back to the last server-confirmed one [M16].
            if (!retried.Contains(key))
            {
                retried.Add(key);
                Plugin.Log?.LogInfo($"[MUSIC-RATE] rating send failed ({resp}) — one retry with current intent");
                SendLoop(key);
                return;
            }
            retried.Remove(key);
            latestIntent.Remove(key);
            int conf;
            if (ownConfirmed.TryGetValue(key, out conf)) ownShown[key] = conf; else ownShown.Remove(key);
            Plugin.Log?.LogWarning($"[MUSIC-RATE] rating write failed twice ({resp}) — optimistic value rolled back");
            NativeUI.MarkDirty();
        }

        // ─────────────────────── invalidation ───────────────────────

        /// <summary>[G11-equivalent] Consent revoked: clear everything and
        /// outrank every in-flight response/write. Wired from ApiClient.
        /// OnConsentChanged's revoke branch, beside MusicEntitlements'.</summary>
        internal static void OnConsentRevoked() => InvalidateAndClear("consent revoke");

        /// <summary>[I11-equivalent] The RESOLVED local identity changed.
        /// Wired from GameStateWatcher.NoteIdentityTransition, beside
        /// MusicEntitlements.OnIdentityChanged(). FIRST resolution
        /// (unknown→resolved) needs no call here — anonymous own-fetches are
        /// never dispatched and ApplyOwn's landing gate rejects them, same
        /// reasoning as MusicEntitlements.</summary>
        internal static void OnIdentityChanged() => InvalidateAndClear("identity change");

        private static void InvalidateAndClear(string reason)
        {
            // The floor outranks every generation this store ever handed out
            // (fetches AND writes come from the one counter), so anything in
            // flight lands into the void.
            genFloor = dispatchGen + 1;
            int hadOwn = ownShown.Count;
            trackAgg.Clear();
            albumAgg.Clear();
            ownShown.Clear();
            ownConfirmed.Clear();
            latestIntent.Clear();
            inFlight.Clear();
            retried.Clear();
            // Un-throttle so the next Music-tab open refetches immediately
            // (a consent re-grant / new identity starts from a cold store).
            lastAggFetchAt = -9999f;
            lastOwnFetchAt = -9999f;
            Plugin.Log?.LogInfo($"[MUSIC-RATE] ratings cleared on {reason} ({hadOwn} own rating(s) dropped); acceptance floor now gen {genFloor}");
            NativeUI.MarkDirty();
        }
    }
}
