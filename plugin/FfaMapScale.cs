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
                    n = PhotonNetwork.CurrentRoom?.PlayerCount ?? 0;
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
                    if (f <= 1.001f || !FfaMode.EngineActive()) return true;   // vanilla
                    if (__instance?.players == null || spawnPoints == null) return true;

                    // Bug #116 second half: the padded array repeats vanilla
                    // points, so any index whose target was already claimed this
                    // pass gets a scanned static-ground position instead. If the
                    // scan came up short (a map with nowhere else to stand) the
                    // duplicate is kept — Sid's "unless there's no other options".
                    // Substituting only on COLLISION means the deterministic
                    // per-half-point shuffle still decides who gets which of the
                    // real spawn points; extras just fill the clashes.
                    var used = new System.Collections.Generic.List<Vector3>();
                    var extras = FfaSpawnPoints.Extras;
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
