using HarmonyLib;
using Photon.Pun;
using System;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Scales fresh FFA maps, their camera target, and their kill boundary by
    /// a master-published player count. Missing or small-lobby counts leave
    /// vanilla behavior untouched.
    /// </summary>
    internal static class FfaMapScale
    {
        public const string PropKey = "cr_ffa_scl";
        // Bug #117 (Sid: "check map size is increasing as it should"). It WAS
        // increasing — by 3% at 5 players, which is imperceptible, and the old
        // 1.30 clamp needed 14 players to reach so it was unreachable dead
        // code at FFA_MAX_PLAYERS = 10. 6%/player above 4: 5p -> 1.06,
        // 10p -> 1.36. Raised only together with the MovePlayers fix below —
        // before that fix, raising the factor multiplied the spawn error.
        public const float PerPlayer = 0.06f;
        public const float MaxFactor = 1.40f;

        /// <summary>Factor applied to the current map (1 when unscaled).</summary>
        public static float CurrentFactor { get; private set; } = 1f;

        public static void Reset()
        {
            try { CurrentFactor = 1f; }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA-SCALE] Reset: {ex.Message}"); }
        }

        /// <summary>
        /// Master only: publish the live player count before triggering a map
        /// load so every client derives the same scale factor.
        /// </summary>
        public static void MasterPublishCount()
        {
            try
            {
                if (!PhotonNetwork.IsMasterClient || !PhotonNetwork.InRoom ||
                    PhotonNetwork.CurrentRoom == null) return;

                int n = 0;
                var players = PlayerManager.instance?.players;
                if (players != null)
                {
                    foreach (var p in players)
                        if (p != null && p.gameObject != null) n++;
                }

                if (n == 0)
                    n = RoomActors.ActiveFighterCount();   // census: scale by fighters, not actors
                n = Math.Max(2, n);

                var h = new ExitGames.Client.Photon.Hashtable();
                h[PropKey] = n;
                PhotonNetwork.CurrentRoom.SetCustomProperties(h);
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[FFA-SCALE] MasterPublishCount: {ex.Message}");
            }
        }

        private static float FactorFor(int playerCount)
        {
            return Mathf.Clamp(1f + PerPlayer * (playerCount - 4), 1f, MaxFactor);
        }

        private static int ReadPublishedCount()
        {
            try
            {
                var props = PhotonNetwork.CurrentRoom?.CustomProperties;
                if (props == null || !props.ContainsKey(PropKey)) return -1;
                if (props[PropKey] is int i) return i;
                if (props[PropKey] is string s && int.TryParse(s, out var parsed))
                    return parsed;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[FFA-SCALE] ReadPublishedCount: {ex.Message}");
            }
            return -1;
        }

        [HarmonyPatch(typeof(MapTransition), "SetStartPos")]
        class MapTransition_SetStartPos_FfaScale_Patch
        {
            static void Postfix(Map map)
            {
                try
                {
                    if (map == null) return;
                    if (!FfaMode.EngineActive())
                    {
                        Reset();
                        return;
                    }

                    int n = ReadPublishedCount();
                    if (n <= 0)
                    {
                        Reset();
                        return;
                    }

                    float f = FactorFor(n);
                    if (f <= 1.001f)
                    {
                        Reset();
                        return;
                    }

                    map.transform.localScale = new Vector3(f, f, 1f);
                    map.size *= f;
                    CurrentFactor = f;
                    Plugin.Log.LogInfo(
                        $"[FFA-SCALE] map scaled x{f:F2} for {n} players (size {map.size:F1})");
                    // Bug #116: while the map is still parked and untouched, look
                    // for static ground for players 5+. Vanilla ships 4 points and
                    // the FFA padding duplicates them, so without this two players
                    // land on the same coordinate. Must run HERE — once
                    // MapTransition.Move starts, each child re-enables its collider
                    // after its own Random delay, so a physics query is
                    // non-deterministic across clients by construction.
                    try
                    {
                        FfaSpawnPoints.ScanForMap(map, f, map.transform.position,
                                                  Math.Max(0, Diag2v2.PlayersNeeded() - 4));
                    }
                    catch (Exception sx)
                    { Plugin.Log.LogWarning($"[FFA-SPAWN] scan hook: {sx.Message}"); }
                }
                catch (Exception ex)
                {
                    Reset();
                    Plugin.Log.LogWarning($"[FFA-SCALE] SetStartPos: {ex.Message}");
                }
            }
        }

        /// <summary>
        /// Bug #116: scale the SPAWN TARGET too, or every player lands off
        /// their marker.
        ///
        /// SpawnPoint.Awake caches `localStartPos = transform.localPosition`
        /// once, at scene load, and PlayerManager.MovePlayers consumes THAT
        /// FIELD - not the live transform. localPosition is scale-independent,
        /// so scaling the map root moves the geometry to f*L while every
        /// player is still teleported to L. Vanilla is correct only because
        /// f == 1: MapTransition parks the root at +90 and Enter shifts each
        /// child by -90, so a child lands at exactly localStartPos.
        ///
        /// The error is (f-1)*|L|, directed toward map centre in both axes, on
        /// every round of every 5+ player FFA. Move ends by re-enabling physics
        /// while the player overlaps geometry; PlayerCollision then depenetrates
        /// and, if the overlapped collider is a movable piece, NetworkPhysicsObject
        /// .OnPlayerCollision applies CallTakeDamage + CallTakeForce - which is
        /// exactly Sid's "spawning in/on moveable objects that immediately
        /// discombobulated and killed the players".
        ///
        /// Fixed at the single consumption site rather than by multiplying
        /// SpawnPoint.localStartPos in the GetSpawnPoints postfix: that would
        /// mutate a live component and compound the factor, because
        /// CallInNewMapAndMovePlayers runs more than once per map instance.
        /// </summary>
        // Vanilla's spawn SFX, reached by reflection: SoundEvent lives in
        // SonigonAudioEngine.Runtime and the csproj deliberately does not
        // reference it (same discipline as the UI: no new assembly references
        // for something a MethodInfo can reach). Purely cosmetic - every
        // failure is swallowed, because a missing spawn blip must never be
        // able to take down the round transition.
        private static System.Reflection.FieldInfo fiSpawnSounds;
        private static System.Reflection.PropertyInfo piSoundInstance;
        private static System.Reflection.MethodInfo miSoundPlay;
        private static bool soundReflectResolved;

        private static void PlaySpawnSound(PlayerManager pm, int index, Transform at)
        {
            try
            {
                if (!soundReflectResolved)
                {
                    soundReflectResolved = true;
                    fiSpawnSounds = typeof(PlayerManager).GetField("soundCharacterSpawn",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic
                        | System.Reflection.BindingFlags.Instance);
                    var tSm = AccessTools.TypeByName("Sonigon.SoundManager");
                    if (tSm != null)
                    {
                        piSoundInstance = tSm.GetProperty("Instance",
                            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
                        foreach (var m in tSm.GetMethods(System.Reflection.BindingFlags.Public
                                                         | System.Reflection.BindingFlags.Instance))
                        {
                            if (m.Name != "Play") continue;
                            var ps = m.GetParameters();
                            if (ps.Length == 2 && ps[1].ParameterType == typeof(Transform))
                            { miSoundPlay = m; break; }
                        }
                    }
                }
                if (fiSpawnSounds == null || miSoundPlay == null || piSoundInstance == null) return;
                var arr = fiSpawnSounds.GetValue(pm) as Array;
                if (arr == null || arr.Length == 0) return;
                var inst = piSoundInstance.GetValue(null, null);
                if (inst == null) return;
                miSoundPlay.Invoke(inst, new object[] { arr.GetValue(index % arr.Length), at });
            }
            catch { }
        }

        [HarmonyPatch(typeof(PlayerManager), "MovePlayers")]
        class PlayerManager_MovePlayers_FfaScale_Patch
        {
            static bool Prefix(PlayerManager __instance, SpawnPoint[] spawnPoints)
            {
                try
                {
                    float f = CurrentFactor;
                    // Bug #140 analysis (HIGH): this used to early-out to vanilla
                    // whenever f == 1, which is EXACTLY the case at 3 and 4
                    // players (FactorFor clamps to 1.0 below 5) — i.e. the whole
                    // lower half of FFA's supported range ran vanilla's
                    // MovePlayers. That loop has no null check and no try/catch,
                    // and StartCoroutine runs the first MoveNext SYNCHRONOUSLY,
                    // so a departed player still sitting in PlayerManager.players
                    // (FFA suppresses vanilla's leave teardown by design, #222)
                    // throws and ABORTS the loop — every player at a higher index
                    // never gets moved at all. That is the "stuck where I was
                    // while the map changed" symptom, reached by a different route
                    // than #45/#85. The live log caught the race one step short of
                    // failing: the purge removed 2 dead entries immediately AFTER
                    // MovePlayers had already run.
                    //
                    // So: in FFA this patch now always takes over the loop for its
                    // null-skip, and the SCALE is applied only when there is one.
                    if (!FfaMode.EngineActive()) return true;   // vanilla
                    if (__instance?.players == null || spawnPoints == null) return true;
                    if (f < 1f) f = 1f;

                    // Bug #116 second half: the padded array repeats vanilla
                    // points, so any index whose target was already claimed this
                    // pass gets a scanned static-ground position instead. If the
                    // scan came up short (a map with nowhere else to stand) the
                    // duplicate is kept — Sid's "unless there's no other options".
                    // Substituting only on COLLISION means the deterministic
                    // per-half-point shuffle still decides who gets which of the
                    // real spawn points; extras just fill the clashes.
                    var used = new System.Collections.Generic.List<Vector3>();
                    // Extras are only scanned on a SCALED map (the SetStartPos
                    // postfix returns before ScanForMap when f == 1), so the
                    // cached list can still hold positions from an earlier,
                    // larger map. Only consult it while scaling is actually
                    // active; at 3-4 players vanilla's four distinct points
                    // cannot clash anyway.
                    var extras = f > 1.001f ? FfaSpawnPoints.Extras : null;
                    int nextExtra = 0;
                    for (int i = 0; i < __instance.players.Count && i < spawnPoints.Length; i++)
                    {
                        var pl = __instance.players[i];
                        if (pl == null || spawnPoints[i] == null) continue;
                        Vector3 target = spawnPoints[i].localStartPos * f;
                        bool clash = false;
                        for (int u = 0; u < used.Count; u++)
                            if ((used[u] - target).sqrMagnitude < 0.01f) { clash = true; break; }
                        if (clash && extras != null && nextExtra < extras.Count)
                            target = extras[nextExtra++];
                        used.Add(target);
                        __instance.StartCoroutine(__instance.Move(pl.data.playerVel, target));
                        PlaySpawnSound(__instance, i, pl.transform);
                    }
                    return false;
                }
                catch (Exception ex)
                {
                    // MovePlayers runs inside MapManager's map-load coroutine,
                    // which is the round-transition critical path - a throw
                    // here is the #45/#85 class of stall. Degrade to vanilla
                    // placement rather than killing the transition.
                    Plugin.Log.LogWarning($"[FFA-SCALE] MovePlayers: {ex.Message}");
                    return true;
                }
            }
        }

        /// <summary>
        /// Bugs #133/#134: rope-hung crates and saws fell at round start on
        /// scaled FFA maps.
        ///
        /// Vanilla replaces every authored physics piece with a networked copy
        /// AFTER the map has entered: the master calls PhotonNetwork.Instantiate
        /// at the placeholder's world position (correct — the placeholder is a
        /// scaled child), and PhotonMapObject.Start re-parents the copy under
        /// the map root with worldPositionStays: true. worldPositionStays
        /// preserves world SCALE as well as position, so the copy keeps its
        /// ORIGINAL prefab world scale (not generally 1 — observed 2, 5,
        /// 3.1179) while every authored sibling carries the extra f — the
        /// networked piece is (f-1)/f smaller than the placeholder it replaced.
        ///
        /// MapObjet_Rope then attaches by Collider2D.OverlapPoint(endpoint)
        /// over map.allRigs (captured after the placeholders are destroyed, so
        /// only the undersized copies remain). The endpoint sits at f*authored,
        /// the copy's collider extents at 1*authored around a correct centre:
        /// a rope endpoint authored within ~(f-1)/f of the collider edge
        /// misses. ONE missed endpoint is enough to leave that piece
        /// jointless (the level32 saw case: the box end still attaches, the
        /// saw end misses, the saw falls); both missed destroys the rope
        /// outright (the level41 crate case). Three frames later the copy's
        /// physics enables with no joint and the master's piece free-falls,
        /// which NetworkPhysicsObject syncs to everyone (non-owner copies
        /// have gravityScale=0 on rope maps — the fall always originates on
        /// the master). Codex extracted the serialized scene data and proved
        /// the two reported cases cross the miss threshold exactly between
        /// f=1.03 (v1.35.0) and f=1.06 (v1.35.2): level41 crate margin
        /// +0.0044 -> -0.0099, level32 saw +0.0271 -> -0.0056; with this fix
        /// both are comfortably inside at 1.06. A few tight corner
        /// attachments were already failing at 1.03.
        ///
        /// Fix at the root: give the copy the map's factor. Multiply — not set
        /// to one — so the original prefab scale is preserved. localScale is
        /// multiplied while the body is still simulated=false (Start set
        /// that), so the fixtures bake at the right size when IGo enables
        /// physics. Positions need no correction: worldPositionStays already
        /// preserved the correct scaled world pos. Mixed versions: scale is
        /// never serialized, so an unpatched client keeps smaller colliders —
        /// never WORSE than today's all-old behaviour, but fold this into the
        /// staged MIN_MOD_VERSION raise for full consistency (Codex find 2).
        /// </summary>
        /// <summary>Capability key: this client rescales networked map objects
        /// on scaled FFA maps. Published as a PLAYER prop pre-join (rides the
        /// Photon Player record, so it is visible to every client from the
        /// moment the player is — the #79-family pre-join pattern).</summary>
        public const string ScaleCapabilityProp = "cr_msv2";

        /// <summary>True when the CURRENT master client advertises the
        /// rescale capability. The networked pieces are simulated by the
        /// MASTER and streamed to everyone else, so the master's geometry is
        /// the only one that may define collider sizes: a patched peer
        /// rescaling under an unpatched master gets copies 6% larger than the
        /// authoritative simulation, and every NetworkPhysicsObject snap then
        /// fights local depenetration — Sid's "boxes are vibrating" report,
        /// live, the day this patch first ran on one machine in a 1.35.2
        /// lobby.
        ///
        /// EVERY player must advertise, not just the current master (bug #140
        /// analysis): the gate is evaluated once per piece at
        /// PhotonMapObject.Start and is never revisited, so a master HANDOFF
        /// mid-map silently invalidates a master-only decision — pieces stay
        /// scaled on patched peers while an unpatched client takes over the
        /// authoritative simulation, reproducing the vibration. Sid's own
        /// 4-hour session contained two genuine handoffs, so this is reachable,
        /// not theoretical. Requiring the whole room makes any successor master
        /// patched BY CONSTRUCTION.
        ///
        /// Degradation is deliberate and safe in both directions: a mixed room
        /// scales nothing (exactly today's shipped behaviour — ropes still
        /// break there, no new symptom), and an unpatched player who joins
        /// mid-map keeps SMALLER colliders for the remainder of that one map,
        /// which overlap less rather than more — the benign direction. The next
        /// map load re-evaluates and the whole room agrees again.</summary>
        private static bool RoomAdvertisesScaleCapability()
        {
            try
            {
                if (PhotonNetwork.OfflineMode) return true;
                // Capability consensus over FIGHTERS only (census): a
                // spectator publishes no scale capability and must not
                // disable map scaling room-wide.
                var players = RoomActors.ActiveFighters();
                if (players == null || players.Length == 0) return false;
                foreach (var p in players)
                {
                    if (p == null) return false;
                    var props = p.CustomProperties;
                    if (props == null || !props.ContainsKey(ScaleCapabilityProp)) return false;
                }
                return true;
            }
            catch { return false; }
        }

        [HarmonyPatch(typeof(PhotonMapObject), "Start")]
        class PhotonMapObject_Start_FfaScale_Patch
        {
            // One aggregate log line per map load (Codex find 4: per-object
            // INFO on a 77-object map over a long sitting is thousands of
            // redundant lines).
            private static int lastLogMapId = int.MinValue;
            private static int lastSkipLogMapId = int.MinValue;

            static void Postfix(PhotonMapObject __instance)
            {
                try
                {
                    float f = CurrentFactor;
                    if (f <= 1.001f || !FfaMode.EngineActive()) return;
                    if (__instance == null || !__instance.photonSpawned) return;

                    var t = __instance.transform;
                    int mapId = 0;
                    try { mapId = t.parent != null ? t.parent.GetInstanceID() : 0; }
                    catch { }

                    if (!RoomAdvertisesScaleCapability())
                    {
                        if (mapId != lastSkipLogMapId)
                        {
                            lastSkipLogMapId = mapId;
                            Plugin.Log.LogInfo(
                                "[FFA-SCALE] not every client in the room has the rescale capability — networked map objects stay vanilla-scaled this map");
                        }
                        return;
                    }

                    t.localScale = new Vector3(
                        t.localScale.x * f, t.localScale.y * f, t.localScale.z);

                    if (mapId != lastLogMapId)
                    {
                        lastLogMapId = mapId;
                        Plugin.Log.LogInfo(
                            $"[FFA-SCALE] networked map objects rescaled x{f:F2} (logged once per map)");
                    }
                }
                catch (Exception ex)
                {
                    Plugin.Log.LogWarning($"[FFA-SCALE] PhotonMapObject.Start: {ex.Message}");
                }
            }
        }

        [HarmonyPatch(typeof(OutOfBoundsHandler), "LateUpdate")]
        class OutOfBoundsHandler_FfaScale_Patch
        {
            static bool Prefix(OutOfBoundsHandler __instance)
            {
                try
                {
                    float f = CurrentFactor;
                    if (f <= 1.001f || !FfaMode.EngineActive()) return true;

                    Vector3 GetPoint(Vector3 p)
                    {
                        float x = Mathf.Lerp(-35.56f * f, 35.56f * f, p.x);
                        float y = Mathf.Lerp(-20f * f, 20f * f, p.y);
                        return new Vector3(x, y, 0f);
                    }

                    if (!__instance.data)
                    {
                        UnityEngine.Object.Destroy(__instance.gameObject);
                    }
                    else
                    {
                        if (!__instance.data.playerVel.simulated || !__instance.data.isPlaying)
                            return false;

                        float x = Mathf.InverseLerp(
                            -35.56f * f, 35.56f * f, __instance.data.transform.position.x);
                        float y = Mathf.InverseLerp(
                            -20f * f, 20f * f, __instance.data.transform.position.y);
                        Vector3 vector = new Vector3(x, y, 0f);
                        vector = new Vector3(
                            Mathf.Clamp(vector.x, 0f, 1f),
                            Mathf.Clamp(vector.y, 0f, 1f),
                            vector.z);
                        __instance.almostOutOfBounds = false;
                        __instance.outOfBounds = false;
                        if (vector.x <= 0f || vector.x >= 1f ||
                            vector.y >= 1f || vector.y <= 0f)
                        {
                            __instance.outOfBounds = true;
                        }
                        else if (vector.x < __instance.warningPercentage ||
                                 vector.x > 1f - __instance.warningPercentage ||
                                 vector.y > 1f - __instance.warningPercentage ||
                                 vector.y < __instance.warningPercentage)
                        {
                            __instance.almostOutOfBounds = true;
                            if (vector.x < __instance.warningPercentage) vector.x = 0f;
                            if (vector.x > 1f - __instance.warningPercentage) vector.x = 1f;
                            if (vector.y < __instance.warningPercentage) vector.y = 0f;
                            if (vector.y > 1f - __instance.warningPercentage) vector.y = 1f;
                        }

                        __instance.counter += TimeHandler.deltaTime;
                        if (__instance.almostOutOfBounds && !__instance.data.dead)
                        {
                            __instance.transform.position = GetPoint(vector);
                            __instance.transform.rotation = Quaternion.LookRotation(
                                Vector3.forward,
                                -(__instance.data.transform.position -
                                  __instance.transform.position));
                            if (__instance.counter > 0.1f)
                            {
                                __instance.counter = 0f;
                                __instance.warning.Play();
                            }
                        }

                        if (!__instance.outOfBounds || __instance.data.dead) return false;
                        __instance.data.sinceGrounded = 0f;
                        __instance.transform.position = GetPoint(vector);
                        __instance.transform.rotation = Quaternion.LookRotation(
                            Vector3.forward,
                            -(__instance.data.transform.position -
                              __instance.transform.position));
                        if (__instance.counter > 0.1f && __instance.data.view.IsMine)
                        {
                            __instance.counter = 0f;
                            if (__instance.data.block.IsBlocking())
                            {
                                __instance.rpc.CallFunction("ShieldOutOfBounds");
                                __instance.data.playerVel.velocity *= 0f;
                                __instance.data.healthHandler.CallTakeForce(
                                    __instance.transform.up * 400f *
                                    __instance.data.playerVel.mass,
                                    ForceMode2D.Impulse,
                                    forceIgnoreMass: false,
                                    ignoreBlock: true);
                                __instance.data.transform.position =
                                    __instance.transform.position;
                            }
                            else
                            {
                                __instance.rpc.CallFunction("OutOfBounds");
                                __instance.data.healthHandler.CallTakeForce(
                                    __instance.transform.up * 200f *
                                    __instance.data.playerVel.mass,
                                    ForceMode2D.Impulse,
                                    forceIgnoreMass: false,
                                    ignoreBlock: true);
                                __instance.data.healthHandler.CallTakeDamage(
                                    51f * __instance.transform.up,
                                    __instance.data.transform.position,
                                    null,
                                    null,
                                    lethal: true,
                                    HealthHandler.DamageSource.OutOfBounds);
                            }
                        }
                    }

                    return false;
                }
                catch (Exception ex)
                {
                    Plugin.Log.LogWarning($"[FFA-SCALE] OutOfBounds: {ex.Message}");
                    return true;
                }
            }
        }
    }
}
