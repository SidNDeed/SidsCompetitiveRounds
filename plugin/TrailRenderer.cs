using System;
using System.Collections;
using System.Collections.Generic;
using ExitGames.Client.Photon;
using Photon.Pun;
using Photon.Realtime;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Cosmetic trail system. Attaches a Unity TrailRenderer to each mod-equipped
    /// player's GameObject during a match. Cross-visibility is handled via Photon
    /// custom player properties — each mod publishes its own trail info, and all
    /// other mod clients read them to render opponents' trails.
    ///
    /// Photon property keys (per-Player):
    ///   cr_trail_sku   string (empty = no trail)
    ///   cr_trail_color string hex "#RRGGBB"
    ///   cr_trail_price int    (used to scale length: 3k=short, 5k=medium, 10k=long)
    ///
    /// Lifecycle:
    ///   Plugin init → TrailCosmetic.PublishLocalProps (called on stats refresh + consent flip)
    ///   GameStateWatcher.OnMatchStarted → TrailCosmetic.OnMatchStart → attach to every player
    ///   GameStateWatcher.ResetMatchState → TrailCosmetic.OnMatchEnd → destroy all
    ///
    /// The prismatic trail (sku == "trail_prism") runs a per-frame hue cycle so
    /// the color actually shifts, which the screenshot user saw as static before.
    /// </summary>
    internal static class TrailCosmetic
    {
        private const string PROP_SKU   = "cr_trail_sku";
        private const string PROP_COLOR = "cr_trail_color";
        private const string PROP_PRICE = "cr_trail_price";

        // actorNumber → trail GameObject (one per player currently carrying a trail).
        private static readonly Dictionary<int, GameObject> attached = new Dictionary<int, GameObject>();

        /// <summary>Publish our own trail selection to Photon so opponents can render it.
        /// Called whenever the local stats refresh, on consent flip, and on room join.</summary>
        public static void PublishLocalProps()
        {
            try
            {
                if (!PhotonNetwork.IsConnected || PhotonNetwork.LocalPlayer == null) return;
                var s = ApiClient.CachedPlayerStats;
                var props = new ExitGames.Client.Photon.Hashtable();
                props[PROP_SKU]   = s?.active_trail_sku ?? "";
                props[PROP_COLOR] = s?.active_trail_color ?? "";
                props[PROP_PRICE] = s?.active_trail_price ?? 0;
                PhotonNetwork.LocalPlayer.SetCustomProperties(props);
                Plugin.Log.LogInfo($"[TRAIL] Published local props sku={props[PROP_SKU]} color={props[PROP_COLOR]} price={props[PROP_PRICE]}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[TRAIL] PublishLocalProps failed: {ex.Message}"); }
        }

        /// <summary>Called on match start. Attaches a trail to every player with one equipped.</summary>
        public static void OnMatchStart()
        {
            try
            {
                if (Plugin.ShowTrails != null && !Plugin.ShowTrails.Value)
                {
                    Plugin.Log.LogInfo("[TRAIL] Skipped — ShowTrails is off");
                    return;
                }
                // Give PlayerManager a moment to spawn all Player GameObjects.
                Plugin.Instance.StartCoroutine(DelayedAttachAll());
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[TRAIL] OnMatchStart error: {ex.Message}"); }
        }

        /// <summary>Called on match/room end. Destroys every trail we spawned.</summary>
        public static void OnMatchEnd()
        {
            try
            {
                foreach (var kv in attached)
                    if (kv.Value != null) UnityEngine.Object.Destroy(kv.Value);
                attached.Clear();
                Plugin.Log.LogInfo("[TRAIL] All detached");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[TRAIL] OnMatchEnd error: {ex.Message}"); }
        }

        private static IEnumerator DelayedAttachAll()
        {
            for (int i = 0; i < 30; i++) yield return null;

            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null) yield break;

            foreach (var p in pm.players)
            {
                if (p == null) continue;
                var pv = p.GetComponent<PhotonView>();
                if (pv == null) continue;
                int actor = pv.OwnerActorNr;

                // Find Photon player to read properties off. Fully-qualified
                // because ROUNDS also has its own `Player` type in scope.
                Photon.Realtime.Player photonPlayer = null;
                foreach (var pp in PhotonNetwork.PlayerList)
                    if (pp != null && pp.ActorNumber == actor) { photonPlayer = pp; break; }

                string sku = "";
                string color = "";
                int price = 0;
                if (pv.IsMine)
                {
                    // Use our own cached stats (faster, and the Photon roundtrip may not have landed yet).
                    var s = ApiClient.CachedPlayerStats;
                    sku = s?.active_trail_sku ?? "";
                    color = s?.active_trail_color ?? "";
                    price = s?.active_trail_price ?? 0;
                }
                else if (photonPlayer != null && photonPlayer.CustomProperties != null)
                {
                    var cp = photonPlayer.CustomProperties;
                    if (cp.ContainsKey(PROP_SKU))   sku   = cp[PROP_SKU]?.ToString() ?? "";
                    if (cp.ContainsKey(PROP_COLOR)) color = cp[PROP_COLOR]?.ToString() ?? "";
                    if (cp.ContainsKey(PROP_PRICE))
                    {
                        try { price = Convert.ToInt32(cp[PROP_PRICE]); } catch { price = 0; }
                    }
                }

                if (string.IsNullOrEmpty(sku)) continue;
                AttachTrail(p.transform, actor, sku, color, price);
            }
        }

        private static void AttachTrail(Transform playerT, int actor, string sku, string hexColor, int price)
        {
            if (playerT == null) return;
            if (attached.TryGetValue(actor, out var existing) && existing != null)
                UnityEngine.Object.Destroy(existing);

            var go = new GameObject($"CR_Trail_{actor}_{sku}");
            go.transform.SetParent(playerT, false);
            go.transform.localPosition = Vector3.zero;

            var tr = go.AddComponent<TrailRenderer>();
            // Length scales with price: 3k tier = short, 5k = medium, 10k = long.
            // Interpolate linearly; falls back sensibly for any future price tier.
            float len = 0.35f;
            if (price >= 10000)     len = 0.90f;
            else if (price >= 5000) len = 0.60f;
            else if (price >= 3000) len = 0.35f;
            tr.time = len;
            tr.startWidth = 0.50f;
            tr.endWidth = 0.0f;
            tr.minVertexDistance = 0.05f;
            tr.autodestruct = false;
            tr.emitting = true;

            var mat = new Material(Shader.Find("Sprites/Default"));
            Color c = Color.white;
            if (!string.IsNullOrEmpty(hexColor))
                ColorUtility.TryParseHtmlString(hexColor, out c);
            mat.color = c;
            tr.material = mat;
            tr.startColor = c;
            tr.endColor = new Color(c.r, c.g, c.b, 0f);

            attached[actor] = go;

            // Prismatic cycles hue over time — screenshot showed a static trail because
            // the shop preview color is a single hue, but this SKU is supposed to shift.
            if (sku == "trail_prism")
                go.AddComponent<PrismaticHueCycle>().Target = tr;

            Plugin.Log.LogInfo($"[TRAIL] Attached actor={actor} sku={sku} color={hexColor} len={len:F2}s");
        }
    }

    /// <summary>Rotates a TrailRenderer's color through HSV hues every frame. Only
    /// used for trail_prism — costs nothing when not attached.</summary>
    internal class PrismaticHueCycle : MonoBehaviour
    {
        public TrailRenderer Target;
        private float t;

        void Update()
        {
            if (Target == null) return;
            t += Time.deltaTime * 0.6f;  // one full hue cycle every ~1.7s
            if (t > 1f) t -= 1f;
            var col = Color.HSVToRGB(t, 0.85f, 1.0f);
            Target.startColor = col;
            Target.endColor = new Color(col.r, col.g, col.b, 0f);
        }
    }
}
