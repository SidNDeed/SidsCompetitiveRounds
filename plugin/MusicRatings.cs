using System;
using System.Collections;
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
    /// [N5] Client-side serialization alone cannot order requests the SERVER
    /// is still executing (a timed-out old POST can commit after a newer
    /// one), so every write also carries a per-(sku,track) monotonic
    /// intent_rev the server compares against its stored floor, plus an
    /// op_id idempotency key (#170) so a duplicate landing twice can never
    /// re-arm the 2-24h maturation delay. The server keeps each row's
    /// intent_rev for the row's whole life, so a fresh session must NOT
    /// restart at 1: counters seed from the /mine payload's intent_rev and
    /// mint stored+1, with a one-shot server_rev adopt on a stale 409 for
    /// the rate-before-first-/mine window.
    ///
    /// [N10] A 429 is PACING, not failure: the latest intent stays
    /// optimistic and one coalesced resend is scheduled after the server's
    /// retry_after window (realtime), instead of an immediate retry that
    /// lands inside the same window and rolls the UI back.
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
        // rev = the row's server-stored intent_rev ([N5] seed; 0 = absent).
        // A row may be rev-seed-only (stars outside 1..5, e.g. a pending
        // clear) — it still carries the floor a fresh session must clear.
        internal sealed class OwnRow { public string sku; public int idx; public int stars; public int rev; }

        private struct Agg { public float avg; public int count; public int raters; }

        // A queued write: the CANONICAL catalog sku (original casing, for the
        // wire) + track index + the newest intent value. Present in
        // latestIntent for the whole life of a send sequence — SendLoop reads
        // it, OnSendComplete removes it only once the sent value matches it.
        // [N5] rev/opId are minted per USER intent (Rate call): a transport
        // retry of the same op re-sends both unchanged (idempotent), a newer
        // intent gets a fresh pair.
        private sealed class PendingOp { public string sku; public int idx; public int stars; public int rev; public string opId; }

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

        // [N5] Per-key monotonic intent revision — the highest rev this
        // session has SEEN (server-stored via /mine seeding, max-merged so it
        // never lowers) or MINTED (Rate). The server rejects any write whose
        // rev is not strictly newer than its stored one, which is what stops
        // a timed-out old request from resurrecting a superseded intent.
        private static readonly Dictionary<string, int> intentRev = new Dictionary<string, int>(StringComparer.Ordinal);

        // [N10] Consecutive 429-deferred resends per key (cleared on success
        // or a fresh user intent) + each scheduled resend's realtime deadline.
        // The deadline doubles as the defer claim's OWNERSHIP TOKEN (#367):
        // the coroutine only acts if its exact value is still stored, and
        // Rate() breaks a claim whose deadline is long past (#270c — the
        // coroutine host can die, and a dead claim must not wedge the key
        // for the session).
        private static readonly Dictionary<string, int> deferred429 = new Dictionary<string, int>(StringComparer.Ordinal);
        private static readonly Dictionary<string, float> deferUntil = new Dictionary<string, float>(StringComparer.Ordinal);

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
        /// overlay for keys whose write sequence is still pending.
        /// N9 (stale standby snapshot overwriting a confirmed write) is
        /// REFUTED at the transport: the live edge allowlist routes only
        /// leaderboards/records/histories to the standby — every /music path
        /// hits the primary — so the gen gate below is belt, not fix.</summary>
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
                    // [N5] rev-seed EVERY structurally valid row BEFORE the
                    // stars filter — a pending-clear row can arrive with
                    // stars 0 and a live intent_rev, and skipping its seed
                    // would strand a fresh session under the server's floor.
                    if (r.rev > 0) SeedRev(Key(r.sku, r.idx), r.rev);
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
        /// distinct-rater semantics are the server's [M20] — both carried).
        /// The old 2-out overload was pruned when N12 moved its only caller
        /// to this shape — re-add it only WITH a caller.</summary>
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
            latestIntent[key] = new PendingOp
            {
                sku = album.Sku,
                idx = trackIdx,
                stars = stars,
                // [N5] every USER intent is a new op: the next monotonic
                // revision (seeded from /mine, so stored+1 on a fresh
                // session) + a fresh idempotency id. A transport retry of
                // THIS op re-sends both unchanged.
                rev = NextRev(key),
                opId = Guid.NewGuid().ToString("N"),
            };
            retried.Remove(key);      // a fresh user intent gets a fresh single-retry budget
            deferred429.Remove(key);  // [N10] ...and a fresh pacing budget
            NativeUI.MarkDirty();
            // [N10]/#270c: a 429-deferred resend holds the key via inFlight.
            // If its deadline is long past, the coroutine is dead (host
            // destroyed) — break the claim (removing the token also tells a
            // zombie coroutine it was superseded) so the key can't wedge.
            float dl;
            if (inFlight.Contains(key) && deferUntil.TryGetValue(key, out dl)
                && Time.unscaledTime > dl + 5f)
            {
                deferUntil.Remove(key);
                inFlight.Remove(key);
            }
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
            int sentRev = op.rev;
            ApiClient.PostMusicRating(sid, op.sku, op.idx, sentStars, sentRev, op.opId,
                (ok, resp) => OnSendComplete(key, sid, gen, sentStars, sentRev, ok, resp));
        }

        private static void OnSendComplete(string key, string sentSid, int gen, int sentStars, int sentRev, bool ok, string resp)
        {
            // Invalidated while in flight: every dict was cleared and a NEW
            // sequence may already own the key — touch nothing (deliberately
            // including inFlight, which the new sequence re-added).
            if (gen < genFloor) return;
            inFlight.Remove(key);
            if (ok)
            {
                deferred429.Remove(key);
                string local = null;
                try { local = MatchTracker.LocalSteamId; } catch { }
                if (string.Equals(sentSid, local, StringComparison.Ordinal))
                {
                    if (sentStars == 0) ownConfirmed.Remove(key); else ownConfirmed[key] = sentStars;
                    // R3: a /mine snapshot dispatched BEFORE this write must
                    // not overwrite the freshly confirmed value at landing.
                    if (gen > ownCommittedGen) ownCommittedGen = gen;
                }
                // Deliberately a VALUE compare, not a rev compare: a re-click
                // of the same stars while in flight minted a newer op, but
                // re-sending it would be an identical duplicate that re-arms
                // the server's maturation delay [N5] — drop it instead (the
                // local rev counter staying ahead of the server's is safe).
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
            // [N10] 429 = PACING, not failure: keep the optimistic value and
            // schedule ONE coalesced resend after the server's window
            // (realtime — pick-phase slow-mo must not stretch it). The resend
            // reads the CURRENT latest intent, so later clicks coalesce into
            // it. Bounded: two consecutive defers per standing intent, then
            // the normal failure path (retry-once → rollback) takes over.
            if (resp != null && resp.StartsWith("HTTP 429", StringComparison.Ordinal))
            {
                int defers;
                deferred429.TryGetValue(key, out defers);
                if (defers < 2 && latestIntent.ContainsKey(key))
                {
                    deferred429[key] = defers + 1;
                    // retry_after rides the 429 JSON body (the header never
                    // reaches this callback — coordination item with the
                    // server half); tolerant parse, clamped, 2.5s default
                    // (server debounce is 2.0s).
                    float wait = ExtractNumberAfter(resp, "retry_after", 2.5f);
                    if (wait < 0.5f) wait = 0.5f;
                    if (wait > 30f) wait = 30f;
                    float deadline = Time.unscaledTime + wait;
                    deferUntil[key] = deadline;
                    inFlight.Add(key);   // hold the claim so Rate() only coalesces
                    Plugin.Log?.LogInfo($"[MUSIC-RATE] rating debounced (429) — resending latest intent in {wait:F1}s");
                    Plugin.Instance.StartCoroutine(DeferredResend(key, deadline));
                    return;
                }
            }
            // [N5] stale_intent 409: the server already stores a rev >= ours,
            // so re-sending THIS rev is a guaranteed loop. If a newer local
            // intent coalesced meanwhile, send that; else adopt the server's
            // floor once (server_rev in the body — covers rating before the
            // first /mine snapshot seeds the counter) and re-rev this intent;
            // else the newer write came from ANOTHER session/device — roll
            // back and resync /mine.
            if (resp != null && resp.StartsWith("HTTP 409", StringComparison.Ordinal)
                && resp.IndexOf("stale_intent", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                PendingOp curOp;
                latestIntent.TryGetValue(key, out curOp);
                if (curOp != null && curOp.rev != sentRev)
                {
                    retried.Remove(key);
                    SendLoop(key);
                    return;
                }
                int serverRev = (int)ExtractNumberAfter(resp, "server_rev", 0f);
                if (curOp != null && serverRev > 0 && !retried.Contains(key))
                {
                    retried.Add(key);   // one floor-adopt recovery per op
                    SeedRev(key, serverRev);
                    curOp.rev = NextRev(key);
                    Plugin.Log?.LogInfo($"[MUSIC-RATE] rating rev stale — adopting server floor {serverRev} and resending");
                    SendLoop(key);
                    return;
                }
                retried.Remove(key);
                latestIntent.Remove(key);
                deferred429.Remove(key);
                int confS;
                if (ownConfirmed.TryGetValue(key, out confS)) ownShown[key] = confS; else ownShown.Remove(key);
                Plugin.Log?.LogWarning("[MUSIC-RATE] rating write stale (409) — rolled back; resyncing own ratings");
                ForceOwnRefetch();
                NativeUI.MarkDirty();
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
            deferred429.Remove(key);
            int conf;
            if (ownConfirmed.TryGetValue(key, out conf)) ownShown[key] = conf; else ownShown.Remove(key);
            Plugin.Log?.LogWarning($"[MUSIC-RATE] rating write failed twice ({resp}) — optimistic value rolled back");
            NativeUI.MarkDirty();
        }

        /// <summary>[N10] The scheduled post-429 resend. Ownership-token
        /// pattern (#367): this run may act only while deferUntil still holds
        /// ITS exact deadline — Rate()'s dead-claim break and every
        /// invalidation remove/replace the token, superseding the run.</summary>
        private static IEnumerator DeferredResend(string key, float deadline)
        {
            while (Time.unscaledTime < deadline) yield return null;
            float cur;
            if (!deferUntil.TryGetValue(key, out cur) || cur != deadline) yield break;
            deferUntil.Remove(key);
            inFlight.Remove(key);
            if (latestIntent.ContainsKey(key)) SendLoop(key);
        }

        /// <summary>[N5] Mint the next per-key revision: highest seen/minted
        /// + 1 (the /mine seed makes that stored+1 on a fresh session).</summary>
        private static int NextRev(string key)
        {
            int cur;
            intentRev.TryGetValue(key, out cur);
            intentRev[key] = cur + 1;
            return cur + 1;
        }

        /// <summary>[N5] Max-merge a server-observed revision into the local
        /// counter — never lowers it (in-session mints may already be ahead
        /// of the snapshot that carried the seed).</summary>
        private static void SeedRev(string key, int rev)
        {
            int cur;
            if (!intentRev.TryGetValue(key, out cur) || rev > cur) intentRev[key] = rev;
        }

        /// <summary>Tolerant "number after a named token" scan over an error
        /// string ("HTTP 429: {\"detail\":\"rate_debounced\",\"retry_after\":1.3}").
        /// fallback on any shape mismatch.</summary>
        private static float ExtractNumberAfter(string s, string token, float fallback)
        {
            try
            {
                if (string.IsNullOrEmpty(s)) return fallback;
                int at = s.IndexOf(token, StringComparison.OrdinalIgnoreCase);
                if (at < 0) return fallback;
                int i = at + token.Length;
                while (i < s.Length && (s[i] == '"' || s[i] == ':' || s[i] == ' ')) i++;
                int start = i;
                while (i < s.Length && (char.IsDigit(s[i]) || s[i] == '.')) i++;
                float v;
                if (i == start || !float.TryParse(s.Substring(start, i - start),
                        System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture, out v))
                    return fallback;
                return v;
            }
            catch { return fallback; }
        }

        /// <summary>[N5] Post-stale resync: un-throttle the own-mirror fetch
        /// and dispatch immediately when identity + session allow (else the
        /// next Music-tab open refetches).</summary>
        private static void ForceOwnRefetch()
        {
            lastOwnFetchAt = -9999f;
            string sid = null;
            try { sid = MatchTracker.LocalSteamId; } catch { }
            if (string.IsNullOrEmpty(sid) || sid == "unknown") return;
            if (string.IsNullOrEmpty(SteamAuth.SessionToken)) return;
            lastOwnFetchAt = Time.unscaledTime;
            ApiClient.FetchMusicRatingsOwn(sid, ++dispatchGen);
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
            // [N5] rev counters are per-IDENTITY: the new identity's /mine
            // reseeds them, and the stale-409 floor-adopt covers the window
            // before that snapshot lands. [N10] clearing deferUntil also
            // supersedes every scheduled resend (ownership token gone).
            intentRev.Clear();
            deferred429.Clear();
            deferUntil.Clear();
            // Un-throttle so the next Music-tab open refetches immediately
            // (a consent re-grant / new identity starts from a cold store).
            lastAggFetchAt = -9999f;
            lastOwnFetchAt = -9999f;
            Plugin.Log?.LogInfo($"[MUSIC-RATE] ratings cleared on {reason} ({hadOwn} own rating(s) dropped); acceptance floor now gen {genFloor}");
            NativeUI.MarkDirty();
        }
    }
}
