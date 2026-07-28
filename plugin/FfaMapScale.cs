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
        public const float PerPlayer = 0.03f;
        public const float MaxFactor = 1.30f;

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
                }
                catch (Exception ex)
                {
                    Reset();
                    Plugin.Log.LogWarning($"[FFA-SCALE] SetStartPos: {ex.Message}");
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
