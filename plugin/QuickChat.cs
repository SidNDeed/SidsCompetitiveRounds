using System;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Quick-chat: canned phrases sent through the BASE GAME's chat pipeline
    /// (DevConsole's <c>RPCA_SendChat</c> -&gt; the PlayerChat speech bubble
    /// above the sender's head) — Sid's Sept 1 direction: quick chat is a
    /// shortcut for the text players would otherwise TYPE into the default
    /// Enter chat, usable in casual and ranked games, and UNMODDED opponents
    /// must see it too. So the phrase goes out as plain TEXT in the sender's
    /// locale (exactly what the wheel displayed to them), and every receiver
    /// runs vanilla's own VerifyString + ChatFilter before display, the same
    /// as for a typed message. Nothing renders in the SCR chat box and no
    /// toast fires: the bubble IS the rendering, with spatial attribution,
    /// which also retires the styled-NickName leak the old SCR-chat line had
    /// (bug: "[Q] (b)(i)(u)(size=130%)(col: Hi!").
    ///
    /// The pre-Sept-1 Photon event-48 key protocol (send the phrase ID,
    /// render from each receiver's locale catalogue) is fully retired — no
    /// shipped client ever sent event 48, so there is no legacy receiver to
    /// keep. Phrases[] stays append-only regardless: the strings are still
    /// i18n catalogue keys for the WHEEL's labels.
    /// </summary>
    internal static class QuickChat
    {
        // English canonical phrases — these strings are catalogue KEYS
        // (I18nCatalogues carries translations) for the wheel labels, and the
        // sender's locale rendering of one is what actually goes on the wire.
        // Order is the wheel's stable id space: NEVER reorder or remove
        // entries, only append (CompetitiveUI's QC_MAIN/QC_MORE index here).
        internal static readonly string[] Phrases =
        {
            "Good luck, have fun!",     // 0
            "GG",                       // 1  (was "Good game!")
            "Well played!",             // 2
            "Nice shot!",               // 3
            "So close!",                // 4
            "Thanks!",                  // 5
            "Sorry!",                   // 6
            "Be right back",            // 7  (no longer offered by the wheel)
            "I'm ready",                // 8  (ditto)
            "Hold on!",                 // 9
            "Rematch?",                 // 10
            "Last game for me",         // 11 (ditto)
            "Hi!",                      // 12 (was "Hello!")
            "Bye!",                     // 13 (ditto)
            "Yeah",                     // 14
            "Nah",                      // 15
            "Are you good at this game?",                                        // 16
            "You should join Competitive Rounds, it's a discord community",      // 17
            "discord.gg/comp-rounds",                                            // 18
            "I play with a competitive framework mod called Sid's Competitive Rounds", // 19
            "(/°□°)/ ~ [_T_]",          // 20 table flip — ASCII arms/table: the real ╯/︵/┻ glyphs degrade in the IMGUI font (screenshot-verified #47 class); ° and □ render fine
            ":D",                       // 21
            "o7",                       // 22
        };

        private static float _lastSendAt = -999f;
        // DevConsole singleton cache (it is scene-persistent; the typed-null
        // check below sees a destroyed one as null and re-finds it). Typed as
        // Component so this file never touches its TMP_InputField field
        // (learning #15 — no TMPro assembly reference).
        private static Component _devConsole;

        /// <summary>Why the last Send() returned false: "cooldown", "no_body"
        /// (no local player spawned yet — the bubble needs a head to sit
        /// above), or "" / "silent" (fence, spectator, error — say nothing).
        /// The wheel reads this to pick an honest toast instead of blaming
        /// every refusal on the cooldown.</summary>
        internal static string LastRefusal = "";

        /// <summary>Send phrase by id through the vanilla chat RPC. Returns
        /// false (with LastRefusal set) outside a room, before the local body
        /// spawns, on an out-of-range id, or inside the 2s send throttle.</summary>
        internal static bool Send(int phraseId)
        {
            LastRefusal = "silent";
            if (phraseId < 0 || phraseId >= Phrases.Length) return false;
            // §2c identity fence (Codex mod-r1 F7): the service account needs
            // its own gate here — a keypress during the async fence restart
            // out of an illegitimate room would otherwise reach peers.
            if (BroadcastMode.FenceBlocksFighterPath("quick-chat")) return false;
            if (RoomActors.LocalIsSpectator) return false;   // spectators cannot chat into the match
            // OfflineMode is allowed (sandbox testing renders the local
            // bubble); otherwise a live room is required for the RPC.
            if (!PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode)
            { LastRefusal = "no_body"; return false; }
            if (Time.unscaledTime - _lastSendAt < 2f)
            { LastRefusal = "cooldown"; return false; }
            try
            {
                // Vanilla's own send shape (decompile DevConsole.SendChat):
                // resolve the local Player's view id and RPC the DevConsole
                // GameObject's PhotonView. RpcTarget.All = vanilla's
                // per-player loop incl. self, in one op. VerifyString is a
                // sender-side nicety vanilla ALSO runs on every receiver
                // before display, so skipping it here loses nothing.
                var local = PlayerManager.instance == null ? null
                    : PlayerManager.instance.GetPlayerWithActorID(PhotonNetwork.LocalPlayer.ActorNumber);
                if (local == null || local.data == null || local.data.view == null)
                { LastRefusal = "no_body"; return false; }
                var dc = ResolveDevConsole();
                var pv = dc == null ? null : dc.GetComponent<PhotonView>();
                if (pv == null) { LastRefusal = "no_body"; return false; }
                string msg = I18n.Tr(Phrases[phraseId]);
                pv.RPC("RPCA_SendChat", RpcTarget.All, msg, local.data.view.ViewID);
                // Stamp AFTER the RPC call (r1 LOW): a throw above must not
                // charge the cooldown for a message nobody received.
                _lastSendAt = Time.unscaledTime;
                LastRefusal = "";
                return true;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[QUICKCHAT] send threw: {ex.Message}");
                return false;
            }
        }

        private static Component ResolveDevConsole()
        {
            var c = _devConsole;
            if (c != null) return c;   // Unity-aware null: a destroyed cache falls through
            try { _devConsole = UnityEngine.Object.FindObjectOfType<DevConsole>(); }
            catch { _devConsole = null; }
            return _devConsole;
        }
    }
}
