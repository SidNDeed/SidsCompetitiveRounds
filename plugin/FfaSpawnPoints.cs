using System;
using System.Collections.Generic;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Bug #116: real spawn positions for FFA players 5..10.
    ///
    /// Every vanilla ROUNDS map ships exactly FOUR SpawnPoints, and the FFA
    /// padding in Plugin.MapManager_GetSpawnPoints_2v2_Patch fills the rest by
    /// cyclic reuse (`__result[i % len]`) — so at 5 players two people are
    /// teleported to the IDENTICAL coordinate, and the deterministic
    /// per-half-point shuffle only changes WHICH pair shares a spot.
    ///
    /// Sid's requirement, verbatim: "Ensure all players 5+ spawn on solid
    /// platforms (not the brown moving or moveable pieces) unless there's no
    /// other options or the base game already spawns players there. There was
    /// an issue where players were spawning in/on moveable objects that
    /// immediately discombobulated and killed the players."
    ///
    /// So: scan the freshly-loaded map for STATIC ground, keep only landing
    /// spots that are well clear of the vanilla points, of each other, and of
    /// anything that moves — and fall back to the vanilla duplicate when a map
    /// simply has nowhere else to stand ("unless there's no other options").
    ///
    /// DETERMINISM. Every client runs this independently, so every input has to
    /// be identical everywhere: the scan runs at MapTransition.SetStartPos (the
    /// map is freshly instantiated from the same prefab, its colliders are in
    /// their authored state, MapTransition.Move has not begun staggering child
    /// re-enables with its per-child Random delay, and no PhotonMapObject has
    /// swapped in its networked replacement yet), the sample grid is fixed, the
    /// iteration order is fixed, dynamic bodies are excluded outright, and
    /// there is no Random anywhere. A divergence would be cosmetic rather than
    /// a physics desync (player positions are owner-authoritative and resync
    /// within a frame), but it is avoidable, so it is avoided.
    /// </summary>
    internal static class FfaSpawnPoints
    {
        // Sample columns across the playfield. Fixed count => identical grid on
        // every client regardless of map width.
        private const int SampleColumns = 71;
        private const float StandOffset = 1.10f;   // body centre above the surface
        private const float ClearRadius = 0.80f;   // headroom / no-overlap probe
        private const float MinSeparation = 5.0f;  // from a vanilla point or another extra
        private const float EdgeMargin = 3.0f;     // keep clear of the kill boundary

        private static int cachedMapId = int.MinValue;
        private static float cachedFactor = -1f;
        private static readonly List<Vector3> cached = new List<Vector3>();

        /// <summary>Extra spawn positions in FINAL world space (post-Enter),
        /// best-first. May be shorter than requested — callers must fall back.</summary>
        public static IList<Vector3> Extras => cached;

        public static void Clear()
        {
            cachedMapId = int.MinValue;
            cachedFactor = -1f;
            cached.Clear();
        }

        /// <summary>
        /// Scan the parked map for static standing room. Call from the
        /// MapTransition.SetStartPos postfix, AFTER the scale has been applied.
        /// `parkedOrigin` is where MapTransition parked the root (Vector3.right
        /// * 90); every result is returned in post-Enter coordinates.
        /// </summary>
        public static void ScanForMap(Map map, float factor, Vector3 parkedOrigin, int needExtra)
        {
            try
            {
                if (map == null) { Clear(); return; }
                int id = map.GetInstanceID();
                if (id == cachedMapId && Mathf.Approximately(factor, cachedFactor)) return;
                cachedMapId = id;
                cachedFactor = factor;
                cached.Clear();
                if (needExtra <= 0) return;

                // The root position and scale were both written this frame and
                // autoSyncTransforms is off by default, so the physics world
                // still holds the pre-write pose without this.
                Physics2D.SyncTransforms();

                float f = Mathf.Max(1f, factor);
                float xMax = 35.56f * f - EdgeMargin;
                float yTop = 20f * f;
                int mask = LayerMask.GetMask("Default");

                // Vanilla points in FINAL coordinates, so extras can be kept
                // away from them.
                var avoid = new List<Vector3>();
                try
                {
                    var pts = map.GetComponentsInChildren<SpawnPoint>(true);
                    if (pts != null)
                        foreach (var sp in pts)
                            if (sp != null) avoid.Add(sp.localStartPos * f);
                }
                catch { }

                var candidates = new List<Vector3>();
                for (int k = 0; k < SampleColumns; k++)
                {
                    float finalX = -xMax + 2f * xMax * ((k + 0.5f) / SampleColumns);
                    var origin = new Vector2(parkedOrigin.x + finalX, parkedOrigin.y + yTop);
                    var hits = Physics2D.RaycastAll(origin, Vector2.down, 2f * yTop + 4f, mask);
                    if (hits == null || hits.Length == 0) continue;

                    // Topmost STATIC surface. RaycastAll is distance-sorted, so
                    // the first acceptable hit is the highest one.
                    RaycastHit2D ground = default(RaycastHit2D);
                    bool found = false;
                    for (int h = 0; h < hits.Length; h++)
                    {
                        var hit = hits[h];
                        if (hit.collider == null) continue;
                        if (hit.rigidbody != null) continue;          // dynamic => movable
                        if (IsMovable(hit.collider.gameObject)) continue;
                        if (hit.normal.y < 0.7f) continue;            // walls / steep slopes
                        ground = hit; found = true; break;
                    }
                    if (!found) continue;

                    var finalPos = new Vector3(finalX,
                                               ground.point.y - parkedOrigin.y + StandOffset, 0f);
                    if (Mathf.Abs(finalPos.y) > 20f * f - EdgeMargin) continue;

                    // Headroom: nothing at all may overlap where the body goes -
                    // a static ceiling means no room, a movable piece is exactly
                    // the "spawned inside the brown box" case.
                    var probe = new Vector2(origin.x, ground.point.y + StandOffset);
                    var overlaps = Physics2D.OverlapCircleAll(probe, ClearRadius, mask);
                    if (overlaps != null && overlaps.Length > 0) continue;

                    if (TooClose(finalPos, avoid) || TooClose(finalPos, candidates)) continue;
                    candidates.Add(finalPos);
                }

                // Greedy farthest-point: spread the extras out instead of
                // clustering them at the left edge of the sweep. Deterministic -
                // ties broken by the fixed candidate order.
                var chosen = new List<Vector3>();
                var pool = new List<Vector3>(candidates);
                while (chosen.Count < needExtra && pool.Count > 0)
                {
                    int best = 0;
                    float bestScore = float.NegativeInfinity;
                    for (int i = 0; i < pool.Count; i++)
                    {
                        float score = NearestDistance(pool[i], avoid, chosen);
                        if (score > bestScore) { bestScore = score; best = i; }
                    }
                    chosen.Add(pool[best]);
                    pool.RemoveAt(best);
                }
                cached.AddRange(chosen);
                Plugin.Log.LogInfo($"[FFA-SPAWN] scanned map {id} x{f:F2}: " +
                                   $"{candidates.Count} candidate(s), {cached.Count}/{needExtra} used");
            }
            catch (Exception ex)
            {
                // A throw here would abort the map load. Fall back to vanilla
                // duplicate points (today's behaviour) rather than break the round.
                cached.Clear();
                Plugin.Log.LogWarning($"[FFA-SPAWN] scan failed, using duplicates: {ex.Message}");
            }
        }

        /// <summary>Vanilla's own "this piece moves" markers: MapTransition.Toggle
        /// keys off Rigidbody2D and CodeAnimation, and the networked crates carry
        /// PhotonMapObject / NetworkPhysicsObject. Checked by NAME through the
        /// string GetComponent overload so a type this build does not know about
        /// costs a null instead of a compile error.</summary>
        private static bool IsMovable(GameObject go)
        {
            if (go == null) return false;
            var t = go.transform;
            while (t != null)
            {
                var o = t.gameObject;
                if (o.GetComponent("Rigidbody2D") != null) return true;
                if (o.GetComponent("CodeAnimation") != null) return true;
                if (o.GetComponent("PhotonMapObject") != null) return true;
                if (o.GetComponent("NetworkPhysicsObject") != null) return true;
                t = t.parent;
            }
            return false;
        }

        private static bool TooClose(Vector3 p, List<Vector3> others)
        {
            for (int i = 0; i < others.Count; i++)
                if ((others[i] - p).sqrMagnitude < MinSeparation * MinSeparation) return true;
            return false;
        }

        private static float NearestDistance(Vector3 p, List<Vector3> a, List<Vector3> b)
        {
            float best = float.MaxValue;
            for (int i = 0; i < a.Count; i++) best = Mathf.Min(best, (a[i] - p).sqrMagnitude);
            for (int i = 0; i < b.Count; i++) best = Mathf.Min(best, (b[i] - p).sqrMagnitude);
            return best == float.MaxValue ? 0f : best;
        }
    }
}
