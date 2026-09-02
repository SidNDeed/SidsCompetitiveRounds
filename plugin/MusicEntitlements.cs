using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>
    /// Music ownership store (design v2 §4 [F15]/[F16] as amended by v3 [G11]) —
    /// the engine's entitlement authority, deliberately NOT raw
    /// ApiClient.CachedShopItems: every write passes an identity gate and a
    /// generation gate so an anonymous or stale shop response can never revoke
    /// (or grant) authenticated ownership.
    ///
    /// Writers: ApplyShopSnapshot is the ONLY grant path — called from
    /// ApiClient.FetchShopItems, the single funnel every shop-items fetch
    /// rides, generation stamped there at dispatch; OnConsentRevoked and
    /// OnIdentityChanged are the only other mutations (clear + invalidate).
    /// No offline cache (design R4'): a cold-start fetch failure leaves custom
    /// albums unplayable that session; vanilla plays.
    /// </summary>
    internal static class MusicEntitlements
    {
        // Owned music_album skus for the AUTHENTICATED local identity.
        private static readonly HashSet<string> owned = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        private static int lastAppliedGen;   // highest generation actually applied
        private static int maxSeenGen;       // highest generation ever handed to us (incl. rejected)
        private static int genFloor;         // minimum acceptable generation, raised by OnConsentRevoked

        /// <summary>Fired on a real ownership delta — and unconditionally from
        /// OnConsentRevoked, because a consent mutation must invalidate any live
        /// preview and re-run Reconcile even when the store was already empty
        /// [G10]/[G11]. MusicEngine subscribes.</summary>
        internal static event Action Changed;

        /// <summary>The ONLY grant path. Rejects (without touching the store)
        /// any snapshot whose identity is not the resolved local steam id, or
        /// whose generation is below the acceptance floor / the last applied
        /// one [F15]. Main thread (ApiClient response callbacks).</summary>
        internal static void ApplyShopSnapshot(string steamId, int generation, List<ApiClient.ShopItemData> items)
        {
            if (generation > maxSeenGen) maxSeenGen = generation;

            // Identity gate: an anonymous fetch arrives as "", and an id for
            // anyone but the resolved local player is meaningless here.
            string local = null;
            try { local = MatchTracker.LocalSteamId; } catch { }
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") return;
            if (string.IsNullOrEmpty(local) || local == "unknown") return;
            if (!string.Equals(steamId, local, StringComparison.Ordinal)) return;

            // Generation gate: >= last applied (F15), and >= the revoke floor.
            if (generation < genFloor || generation < lastAppliedGen) return;
            lastAppliedGen = generation;

            var fresh = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            if (items != null)
            {
                foreach (var it in items)
                {
                    if (it == null || !it.owned || string.IsNullOrEmpty(it.sku)) continue;
                    if (!string.Equals(it.kind, "music_album", StringComparison.OrdinalIgnoreCase)) continue;
                    fresh.Add(it.sku);
                }
            }
            if (owned.SetEquals(fresh)) return;   // no delta — Changed stays quiet

            owned.Clear();
            owned.UnionWith(fresh);
            Plugin.Log?.LogInfo($"[MUSIC] entitlements applied (gen {generation}): {owned.Count} album(s) owned");
            // Ownership is the full-tier trigger (design §3): idempotent and
            // coalesced, so firing before Changed just means the engine's
            // Reconcile sees the download already in flight (Loading, not Fault).
            if (owned.Count > 0)
            {
                try { MusicAssets.EnsureTier(MusicTier.Full, "entitlement"); } catch { }
            }
            FireChanged();
        }

        /// <summary>[G11] Consent revoked: clear the store and invalidate every
        /// in-flight response (see InvalidateAndClear). Never re-arms itself:
        /// the consent-grant refetch dispatches a fresh, larger generation and
        /// applies normally, so no wedge is possible.</summary>
        internal static void OnConsentRevoked() => InvalidateAndClear("consent revoke");

        /// <summary>Impl review I11 (called by GameStateWatcher's identity-
        /// transition hook): the RESOLVED local identity changed (A→B or
        /// A→unknown). Identity B must not inherit A's local playback
        /// authority, and an A→B→A round trip must not let an old A-era
        /// response through ApplyShopSnapshot's landing-time equality check —
        /// the floor advance rejects every generation dispatched before the
        /// change. The hook's refetch for the new identity dispatches above
        /// the floor and applies normally.</summary>
        internal static void OnIdentityChanged() => InvalidateAndClear("identity change");

        /// <summary>Shared invalidation: advance the acceptance floor past
        /// BOTH the highest generation this store has ever seen AND
        /// ApiClient's dispatch high-water — a response whose request was
        /// dispatched before the invalidation but has not landed yet carries
        /// a generation at or below that high-water, so it can never apply
        /// ("revoke outranks every in-flight response", design R3). Then
        /// clear the store and fire Changed so the engine invalidates any
        /// live preview, stops affected playback, repairs the selection and
        /// reconciles to vanilla.</summary>
        private static void InvalidateAndClear(string reason)
        {
            int dispatchHighWater = 0;
            try { dispatchHighWater = ApiClient.ShopSnapshotGenHighWater; } catch { }
            genFloor = Math.Max(genFloor, Math.Max(maxSeenGen, dispatchHighWater) + 1);
            int had = owned.Count;
            owned.Clear();
            Plugin.Log?.LogInfo($"[MUSIC] entitlements cleared on {reason} ({had} album(s) dropped); acceptance floor now gen {genFloor}");
            FireChanged();
        }

        /// <summary>True when the local player may play the album: purchased,
        /// or the broadcast seat with custom music enabled (the ONE broadcast
        /// predicate, design §7 — gated on catalog membership so it never
        /// claims an unknown sku).</summary>
        internal static bool Owns(string albumSku)
        {
            if (string.IsNullOrEmpty(albumSku)) return false;
            try
            {
                if (BroadcastMode.IsBroadcastIdentity
                    && Plugin.BroadcastCustomMusic != null && Plugin.BroadcastCustomMusic.Value
                    && MusicCatalog.Get(albumSku) != null)
                    return true;
            }
            catch { }
            return owned.Contains(albumSku);
        }

        private static void FireChanged()
        {
            try { Changed?.Invoke(); }
            catch (Exception ex) { Plugin.Log?.LogWarning($"[MUSIC] entitlements Changed handler threw: {ex.Message}"); }
        }
    }
}
