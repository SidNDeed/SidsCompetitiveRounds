// PoisonSync.cs — authoritative damage-over-time ticks (bug report #143).
//
// THE PROBLEM
//
// Vanilla: an unblocked poison hit starts a DamageOverTime coroutine, and it
// starts one on EVERY client (RayHitPoison.DoHitEffect runs per replica). Each
// tick calls HealthHandler.DoDamage(..., ignoreBlock: false), and DoDamage
// early-returns while the victim is blocking. So each replica judges each tick
// against ITS OWN copy of the victim's block timing — and block activation
// reaches replicas at different moments (SyncPlayerMovement relays
// RPCAO_DoBlock on the owner's BlockAction, and vanilla can delay that by 200ms
// via delayOtherActions, plus network latency). Clients therefore disagree
// about which ticks landed, which is the ghost-HP desync.
//
// v1.34.5 fixed the desync by forcing ignoreBlock = true on every healthRemoval
// tick. Everyone agreed, but blocking stopped negating poison at all — reported
// by Stan and Archnith as #143. That trade was flagged at the time; Sid has now
// chosen to rebuild it properly.
//
// THE DESIGN
//
// The victim's own client is the only one that knows its block window without
// network translation, so it is the authority. It runs the ONLY damage
// coroutine, decides blocked/not-blocked per tick, and publishes the verdict.
// Every client — INCLUDING THE AUTHORITY — applies damage only when that
// published verdict arrives. That "the event is the sole commit path" rule is
// what stops the authority double-applying, and it means a lost packet delays
// damage rather than diverging it (the events are reliable, so it arrives).
//
// A blocked tick is CONSUMED, not deferred: vanilla does `damageDealt += dpt`
// BEFORE the blockable DoDamage call, so blocking permanently erases that slice
// and the poison still ends at its original time. Sid confirmed that reading.
//
// MIXED LOBBIES
//
// This only works if everyone is running it, so it is gated on every player in
// the room advertising the capability. If anyone is on an older build the room
// silently keeps v1.35.4 behaviour (ticks ignore block, no desync) — a client
// cannot make an unpatched peer stop its own coroutine or honour our verdict,
// and half-applying the protocol would be far worse than not applying it
// (learning #269: a physics/geometry change under a mixed roster produced
// visible jitter for exactly this reason).
//
// The mode is LATCHED per game and never re-evaluated mid-combat, so a player
// joining or leaving cannot flip the protocol underneath a live poison stream.

using HarmonyLib;
using ExitGames.Client.Photon;
using Photon.Pun;
using Photon.Realtime;
using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace CompetitiveRounds
{
    internal static class PoisonSync
    {
        /// <summary>Room-scoped player property advertising that this client
        /// speaks the authoritative-tick protocol. Versioned: a future protocol
        /// change must bump this rather than reuse it, or two incompatible
        /// implementations will both claim capability.</summary>
        // ── NOT YET ACTIVE ────────────────────────────────────────────────
        //
        // Everything below is complete and reviewed EXCEPT the activation
        // barrier, so it is force-disabled and changes nothing at runtime.
        //
        // What is missing, from the second adversarial review: publishing the
        // mode as a room property makes it EVENTUALLY consistent, not
        // atomically activated. Photon guarantees one server-ordered final
        // value, not simultaneous observation - so for a short window at game
        // start client A can already see {epoch 1, AUTH} while B still sees
        // nothing and runs FALLBACK. A then suppresses its local DOT for a
        // victim who is publishing no verdicts, and B runs vanilla ticks that A
        // never applies. That is health divergence, which is strictly worse
        // than the known trade this feature exists to remove.
        //
        // Closing it needs a real activation barrier: publish {epoch, mode,
        // exact roster} as a PROPOSAL, have every roster member acknowledge it,
        // and only then activate - pinning the decision for the whole game
        // rather than live-reading it per tick. Late joiners additionally need
        // the current per-life counters, which are RPC-derived and therefore
        // start at zero for anyone who missed the deaths.
        //
        // Until that exists this ships inert. Poison keeps v1.35.4 behaviour
        // (ticks bypass block, every client agrees), which is a known and
        // stable trade rather than a possible desync.
        internal static bool ProtocolEnabled = false;

        internal const string CapabilityProp = "cr_pois1";
        private const byte EventCode = 47;          // Photon custom codes are 0-199
        private const byte Protocol = 1;

        // ── Mode latch: ONE decision, published by the master ──────────────
        //
        // Every client MUST reach the same answer. My first version had each
        // client compute it from the player properties it had received so far,
        // and Codex was right that this splits: capability props propagate
        // asynchronously and StartGame runs at client-local times, so A can see
        // both capabilities and latch AUTH while B has not yet seen A's and
        // latches FALLBACK. Then B runs its own vanilla DOT *and* applies A's
        // authoritative events — double poison — while A suppresses its local
        // DOT for a victim who never publishes verdicts, so that poison
        // vanishes. Split-brain in both directions.
        //
        // So the master computes it once and publishes {epoch, mode} as a ROOM
        // property; everyone else adopts it verbatim. Room properties are
        // server-ordered and reliable, and the publish happens at game start
        // while DoStartGame still has ~1.25s of map load and wait ahead of it,
        // so it is settled long before the first shot. Absent or stale prop =
        // FALLBACK, which is the safe direction.
        internal const string RoomModeProp = "cr_poismode";

        internal static bool Authoritative
        {
            get
            {
                try
                {
                    if (!ProtocolEnabled) return false;
                    if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return false;
                    return ReadRoomMode(out _, out bool auth) && auth;
                }
                catch { return false; }
            }
        }

        internal static int Epoch
        {
            get { ReadRoomMode(out int e, out _); return e; }
        }

        private static bool ReadRoomMode(out int epoch, out bool auth)
        {
            epoch = 0; auth = false;
            try
            {
                var props = PhotonNetwork.CurrentRoom?.CustomProperties;
                if (props == null) return false;
                if (!props.TryGetValue(RoomModeProp, out object v)) return false;
                var a = v as object[];
                if (a == null || a.Length < 2) return false;
                epoch = (int)a[0];
                auth = ((byte)a[1]) == 1;
                return true;
            }
            catch { return false; }
        }

        // ── Stream + dedup state ──────────────────────────────────────────
        private static int _nextStream = 1;
        private static readonly HashSet<long> _applied = new HashSet<long>();
        // Keyed by (viewId, stream), not stream alone: stream numbers restart at
        // 1 per victim, so a bare stream key merges two players' streams and any
        // "applied=N" readout describes both at once.
        private static readonly Dictionary<long, int[]> _streamTally = new Dictionary<long, int[]>();
        private static bool _hooked;

        // ── Tick sound ────────────────────────────────────────────────────
        // Sonigon (SoundEvent / SoundManager) is deliberately NOT referenced by
        // the csproj — same house rule as UnityEngine.UI and TMPro — so the
        // SoundEvent stays an `object` and is played by reflection.
        //
        // Audio is deliberately NOT authoritative. My first version cached the
        // SoundEvent per victim and played it on the commit path, which was
        // wrong three ways: overlapping poison and Decay streams overwrote each
        // other's sound, blocked ticks fell silent (vanilla plays the sound
        // BEFORE attempting the blockable damage, so a blocked tick still
        // ticks audibly), and a recycled ViewID in a later room could play the
        // previous occupant's sound. Ticks do not need network-consistent
        // timing to sound right, so every replica just runs its own local
        // sound loop on the same schedule — which is exactly what vanilla did.
        private static System.Reflection.MethodInfo _playMi;
        private static object _soundManager;

        private static void PlayTick(object sound, Transform at)
        {
            try
            {
                if (sound == null || at == null) return;
                if (_playMi == null)
                {
                    var smType = AccessTools.TypeByName("Sonigon.SoundManager");
                    if (smType == null) return;
                    var instProp = smType.GetProperty("Instance",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
                    _soundManager = instProp != null ? instProp.GetValue(null) : null;
                    foreach (var mi in smType.GetMethods())
                    {
                        if (mi.Name != "Play") continue;
                        var ps = mi.GetParameters();
                        if (ps.Length == 2 && ps[1].ParameterType == typeof(Transform)) { _playMi = mi; break; }
                    }
                }
                if (_playMi == null || _soundManager == null) return;
                _playMi.Invoke(_soundManager, new object[] { sound, at });
            }
            catch { }
        }

        /// <summary>Local, non-authoritative tick audio — one per replica, same
        /// cadence and same total count as vanilla.</summary>
        internal static IEnumerator LocalTickSound(DamageOverTime host, CharacterData data,
                                                   object sound, float magnitude,
                                                   float total, float interval)
        {
            if (sound == null || interval <= 0f || total <= 0f) yield break;
            // Mirrors vanilla's float accumulation rather than CeilToInt(total /
            // interval): repeated addition of dpt can run one iteration more
            // than the division suggests, so the tidier arithmetic would drop
            // the last tick's sound on some damage values. Same loop shape as
            // the damage path, so the two can never disagree on count.
            float dealt = 0f;
            float dpt = magnitude / total * interval;
            if (dpt <= 0f) yield break;
            while (dealt < magnitude)
            {
                if (host == null || data == null) yield break;
                dealt += dpt;
                if (data.isPlaying && !data.dead) PlayTick(sound, host.transform);
                yield return new WaitForSeconds(interval / TimeHandler.timeScale);
            }
        }

        // ── Capability publish ────────────────────────────────────────────
        private static string _publishedFor = "";

        /// <summary>Publish our capability once per room. Called from the
        /// always-on tick rather than a join hook so it cannot be missed by a
        /// join path that forgot to call it — and re-publishing is a no-op
        /// because we key on the room name.</summary>
        internal static void EnsureCapabilityPublished()
        {
            try
            {
                if (!ProtocolEnabled) return;
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return;
                string room = PhotonNetwork.CurrentRoom?.Name ?? "";
                if (room == _publishedFor) return;
                var props = new ExitGames.Client.Photon.Hashtable { { CapabilityProp, (int)Protocol } };
                PhotonNetwork.LocalPlayer.SetCustomProperties(props);
                _publishedFor = room;
                Plugin.Log.LogInfo($"[POISON-MODE] advertised {CapabilityProp}={Protocol} for room {room}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[POISON-MODE] publish failed: {ex.Message}"); }
        }

        private static bool EveryoneCapable(out string detail)
        {
            detail = "";
            try
            {
                var list = PhotonNetwork.PlayerList;
                if (list == null || list.Length == 0) { detail = "no players"; return false; }
                var parts = new List<string>();
                bool all = true;
                foreach (var p in list)
                {
                    object v = null;
                    bool ok = p != null && p.CustomProperties != null
                              && p.CustomProperties.TryGetValue(CapabilityProp, out v)
                              && v is int && (int)v >= Protocol;
                    parts.Add($"{(p != null ? p.ActorNumber : -1)}:{(ok ? "y" : "n")}");
                    if (!ok) all = false;
                }
                detail = string.Join(",", parts.ToArray());
                return all;
            }
            catch (Exception ex) { detail = "error " + ex.Message; return false; }
        }

        /// <summary>Decide the protocol for the game that is about to start.
        /// Called from GM_ArmsRace.StartGame AND PlayerManager.ResetCharacters —
        /// same-room rematches bypass StartGame entirely (#138), and a rematch
        /// that silently kept a stale latch would be a protocol split.</summary>
        internal static void LatchForGame(string source)
        {
            try
            {
                if (!ProtocolEnabled) return;
                // Local per-game caches reset on EVERY client; only the shared
                // decision itself is master-owned.
                _applied.Clear();
                _streamTally.Clear();
                _lifeGen.Clear();

                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode)
                {
                    Plugin.Log.LogInfo($"[POISON-MODE] OFFLINE-VANILLA ({source}) — vanilla block behaviour, untouched");
                    return;
                }
                if (!PhotonNetwork.IsMasterClient)
                {
                    ReadRoomMode(out int e0, out bool a0);
                    Plugin.Log.LogInfo($"[POISON-MODE] adopting master decision epoch={e0} "
                                       + $"mode={(a0 ? "AUTH" : "FALLBACK")} ({source})");
                    return;
                }

                bool all = EveryoneCapable(out string caps);
                int epoch = 0;
                ReadRoomMode(out epoch, out _);
                epoch++;
                var props = new ExitGames.Client.Photon.Hashtable
                {
                    { RoomModeProp, new object[] { epoch, (byte)(all ? 1 : 0) } }
                };
                PhotonNetwork.CurrentRoom.SetCustomProperties(props);
                Plugin.Log.LogInfo($"[POISON-MODE] MASTER published epoch={epoch} "
                                   + $"mode={(all ? "AUTH" : "FALLBACK")} caps={caps} ({source})");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[POISON-MODE] latch failed: {ex.Message}");
            }
        }

        // ── Per-life generation ───────────────────────────────────────────
        // A reliable event raised just before a death can arrive just after the
        // revive, and would then damage the NEW life at full health. The game
        // epoch cannot catch that — point and round transitions revive without
        // any new game starting. Deaths are the right clock: RPCA_Die and
        // RPCA_Die_Phoenix are both RpcTarget.All, so a counter driven off them
        // increments identically on every client with no extra traffic.
        private static readonly Dictionary<int, int> _lifeGen = new Dictionary<int, int>();

        internal static int LifeGen(int viewId)
            => _lifeGen.TryGetValue(viewId, out int g) ? g : 0;

        internal static void BumpLife(int viewId)
        {
            _lifeGen[viewId] = LifeGen(viewId) + 1;
        }

        // ── Photon event wiring ───────────────────────────────────────────
        internal static void Hook()
        {
            if (_hooked) return;
            try
            {
                PhotonNetwork.NetworkingClient.EventReceived += OnEvent;
                _hooked = true;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[POISON-SYNC] hook failed: {ex.Message}"); }
        }

        // viewId is in the key because every victim's authority numbers its own
        // streams from 1 — without it, two players poisoned at once collide on
        // (stream 1, tick 0) and the second victim's ticks are silently deduped
        // away as duplicates.
        private static long DedupKey(int epoch, int viewId, int stream, int tick)
            => ((long)epoch << 44) ^ ((long)viewId << 24) ^ ((long)stream << 10) ^ (uint)tick;

        private static bool Raise(object[] payload)
        {
            try
            {
                return PhotonNetwork.RaiseEvent(
                    EventCode, payload,
                    // Receivers.All so the AUTHORITY also receives its own event
                    // and commits down the same path as everyone else. Applying
                    // locally at send time instead would give the authority a
                    // different code path, a different ordering, and a second
                    // application when the echo arrives.
                    new RaiseEventOptions { Receivers = ReceiverGroup.All },
                    SendOptions.SendReliable);
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[POISON-AUTH] raise threw: {ex.Message}");
                return false;
            }
        }

        private static void OnEvent(EventData e)
        {
            if (e.Code != EventCode) return;
            try
            {
                var a = e.CustomData as object[];
                if (a == null || a.Length < 17) return;
                if ((byte)a[0] != Protocol) return;

                int epoch = (int)a[1];
                int viewId = (int)a[2];
                int stream = (int)a[3];
                int tick = (int)a[4];
                bool blocked = (bool)a[5];
                int lifeGen = (int)a[15];
                int dmgSource = (int)a[16];

                // Only the victim may speak for the victim. Without this any
                // client could forge ticks against anyone.
                var view = PhotonView.Find(viewId);
                if (view == null) return;
                if (view.Owner == null || view.Owner.ActorNumber != e.Sender)
                {
                    Plugin.Log.LogWarning($"[POISON-SYNC] REJECT forged tick: sender={e.Sender} "
                                          + $"owner={(view.Owner != null ? view.Owner.ActorNumber : -1)} view={viewId}");
                    return;
                }
                if (epoch != Epoch) return;   // stale game (shared, master-owned)
                // Stale LIFE: the victim died between this tick being raised and
                // it arriving. Applying it now would damage a freshly revived
                // player at full health for a hit they took in a previous life.
                if (lifeGen != LifeGen(viewId))
                {
                    Plugin.Log.LogInfo($"[POISON-SYNC] stale-life drop v{viewId}/s{stream}/t{tick} "
                                       + $"(tick life={lifeGen}, now={LifeGen(viewId)})");
                    return;
                }

                long key = DedupKey(epoch, viewId, stream, tick);
                if (!_applied.Add(key)) return;   // reliable retransmit

                long tkey = ((long)viewId << 24) ^ (uint)stream;
                if (!_streamTally.TryGetValue(tkey, out var tally))
                { tally = new int[3]; _streamTally[tkey] = tally; }
                tally[blocked ? 1 : 0]++;

                if (blocked) return;   // consumed, no damage — the vanilla semantic

                var hh = view.GetComponent<HealthHandler>();
                if (hh == null) return;

                var damage = new Vector2((float)a[6], (float)a[7]);
                var pos = new Vector2((float)a[8], (float)a[9]);
                var color = new Color((float)a[10], (float)a[11], (float)a[12], 1f);
                int attackerId = (int)a[13];
                bool lethal = (bool)a[14];

                Player attacker = null;
                GameObject weapon = null;
                try
                {
                    if (attackerId >= 0)
                    {
                        foreach (var p in PlayerManager.instance.players)
                            if (p != null && p.PlayerID == attackerId) { attacker = p; break; }
                        if (attacker != null && attacker.data != null && attacker.data.weaponHandler != null
                            && attacker.data.weaponHandler.gun != null)
                            weapon = attacker.data.weaponHandler.gun.gameObject;
                    }
                }
                catch { }

                // ignoreBlock: true — the block decision was already made, once,
                // by the only client entitled to make it. Re-checking here would
                // reintroduce the per-replica disagreement this exists to remove.
                float hpBefore = 0f;
                try { var cd = view.GetComponent<CharacterData>(); if (cd != null) hpBefore = cd.health; } catch { }
                hh.DoDamage(damage, pos, color, weapon, attacker,
                            healthRemoval: true, lethal: lethal, ignoreBlock: true,
                            damageSource: (HealthHandler.DamageSource)dmgSource);
                // Count APPLIED only when HP actually moved. DoDamage silently
                // no-ops while dead/respawning, and a tally that counts the call
                // rather than the effect reads as agreement when there is none.
                try
                {
                    var cd2 = view.GetComponent<CharacterData>();
                    if (cd2 != null && cd2.health < hpBefore - 0.0001f) tally[2]++;
                }
                catch { }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[POISON-SYNC] apply failed: {ex.Message}"); }
        }

        /// <summary>The authority's replacement for vanilla's DOT loop. Mirrors
        /// vanilla arithmetic exactly (no rounded tick count, no clamped final
        /// tick) so totals and durations are unchanged; the only difference is
        /// that the block verdict is decided here and published instead of being
        /// re-derived by every replica.</summary>
        internal static IEnumerator AuthoritativeDot(
            DamageOverTime host, HealthHandler health, CharacterData data, PhotonView view,
            Vector2 damage, Vector2 position, float time, float interval, Color color,
            Player damagingPlayer, bool lethal, int damageSource)
        {
            int stream = _nextStream++;
            int epoch = Epoch;
            int viewId = view.ViewID;
            int lifeGen = LifeGen(viewId);
            int attackerId = damagingPlayer != null ? damagingPlayer.PlayerID : -1;
            float damageDealt = 0f;
            float damageToDeal = damage.magnitude;
            float dpt = damageToDeal / time * interval;
            int tick = 0;
            int blockedCount = 0;
            int failedSends = 0;

            while (damageDealt < damageToDeal)
            {
                damageDealt += dpt;
                bool blocked = false;
                float sinceBlock = -1f;
                try
                {
                    var block = data != null ? data.block : null;
                    if (block != null) { blocked = block.IsBlocking(); sinceBlock = block.sinceBlock; }
                }
                catch { }
                if (blocked) blockedCount++;

                Vector2 slice = damage.normalized * dpt;
                bool sent = Raise(new object[]
                {
                    Protocol, epoch, viewId, stream, tick, blocked,
                    slice.x, slice.y, position.x, position.y,
                    color.r, color.g, color.b, attackerId, lethal,
                    lifeGen, damageSource
                });
                if (!sent)
                {
                    // RaiseEvent can return false WITHOUT throwing. The tick is
                    // already consumed, and the event is the sole commit path,
                    // so a dropped send is silent damage loss for everyone. Log
                    // it loudly; never fall back to applying locally, which
                    // would damage only this client and recreate the divergence
                    // this whole design exists to remove.
                    failedSends++;
                    Plugin.Log.LogWarning("[POISON-AUTH] SEND FAILED e" + epoch + "/v" + viewId
                                          + "/s" + stream + "/t" + tick + " - tick lost for everyone");
                }
                if (blocked)
                    Plugin.Log.LogInfo($"[POISON-AUTH] BLOCK e{epoch}/v{viewId}/s{stream}/t{tick} "
                                       + $"sinceBlock={sinceBlock:F3} dmg={dpt:F2}");
                tick++;
                yield return new WaitForSeconds(interval / TimeHandler.timeScale);
            }

            long tkey = ((long)viewId << 24) ^ (uint)stream;
            _streamTally.TryGetValue(tkey, out var tally);
            Plugin.Log.LogInfo($"[POISON-SYNC] COMPLETE e{epoch}/v{viewId}/s{stream} life={lifeGen} "
                               + $"sent={tick} blocked={blockedCount} failedSends={failedSends} "
                               + $"recvAccepted={(tally != null ? tally[0] : -1)} "
                               + $"recvBlocked={(tally != null ? tally[1] : -1)} "
                               + $"hpApplied={(tally != null ? tally[2] : -1)}");
        }
    }

    /// <summary>Per-life clock for the poison protocol. Both death RPCs are
    /// RpcTarget.All, so every client increments in lockstep with no extra
    /// traffic - which is what lets a receiver reject a tick that was raised
    /// during the victim's PREVIOUS life and arrived after the revive.</summary>
    [HarmonyPatch(typeof(HealthHandler))]
    internal static class HealthHandlerLifeGenPatch
    {
        [HarmonyPostfix]
        [HarmonyPatch("RPCA_Die")]
        static void AfterDie(HealthHandler __instance) => Bump(__instance);

        [HarmonyPostfix]
        [HarmonyPatch("RPCA_Die_Phoenix")]
        static void AfterPhoenix(HealthHandler __instance) => Bump(__instance);

        static void Bump(HealthHandler hh)
        {
            try
            {
                var v = hh != null ? hh.GetComponent<PhotonView>() : null;
                if (v != null) PoisonSync.BumpLife(v.ViewID);
            }
            catch { }
        }
    }

    /// <summary>Replaces vanilla's per-replica DOT scheduler when the room is
    /// running the authoritative protocol.</summary>
    [HarmonyPatch(typeof(DamageOverTime), "TakeDamageOverTime")]
    internal static class DamageOverTimeAuthoritativePatch
    {
        // object[] __args rather than a typed SoundEvent parameter: Sonigon is
        // not referenced by the csproj, and __args keeps the Prefix
        // signature-agnostic anyway (learning #83).
        static bool Prefix(DamageOverTime __instance, Vector2 damage, Vector2 position,
                           float time, float interval, Color color,
                           Player damagingPlayer, bool lethal,
                           HealthHandler.DamageSource damageSource, object[] __args)
        {
            try
            {
                if (!PoisonSync.Authoritative) return true;   // vanilla + the fallback patch
                if (time <= 0f || interval <= 0f) return true;

                var view = __instance.GetComponent<PhotonView>();
                var health = __instance.GetComponent<HealthHandler>();
                var data = __instance.GetComponent<CharacterData>();
                if (view == null || health == null || data == null) return true;

                // Tick AUDIO is local and unauthoritative, so EVERY replica runs
                // it regardless of who commits the damage. Vanilla plays the
                // sound before attempting the blockable damage, so a blocked
                // tick still ticks audibly - keeping audio off the commit path
                // preserves that for free.
                object snd = (__args != null && __args.Length > 5) ? __args[5] : null;
                if (snd != null)
                    __instance.StartCoroutine(PoisonSync.LocalTickSound(
                        __instance, data, snd, damage.magnitude, time, interval));

                if (!view.IsMine)
                {
                    // A replica must not simulate the victim's poison at all.
                    // It will receive each committed tick as an event.
                    return false;
                }

                // Hosted on the DamageOverTime component deliberately: vanilla's
                // death and revive paths already call dot.StopAllCoroutines(), so
                // our stream inherits that cleanup for free.
                __instance.StartCoroutine(PoisonSync.AuthoritativeDot(
                    __instance, health, data, view, damage, position, time, interval,
                    color, damagingPlayer, lethal, (int)damageSource));
                return false;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[POISON-SYNC] scheduler failed, using vanilla: {ex.Message}");
                return true;
            }
        }
    }
}
