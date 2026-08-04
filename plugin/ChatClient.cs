using System;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Groundwork WebSocket client for the in-game / Discord chat bridge.
    /// Opens a long-lived connection to /api/v1/ws/chat, sends Send() payloads,
    /// and logs incoming messages. UI integration (chat overlay, input box) is
    /// deferred — this class just keeps the pipe alive and exposes the events.
    ///
    /// Design notes:
    ///   - Runs entirely on background tasks (ClientWebSocket is Task-based).
    ///     Received messages are marshaled to a thread-safe callback so UI code
    ///     can dispatch back to the main thread if needed.
    ///   - Honors DataConsent — Connect() is a no-op without consent.
    ///   - Auto-reconnects with exponential backoff up to 60 s.
    /// </summary>
    public static class ChatClient
    {
        private static ClientWebSocket socket;
        private static CancellationTokenSource cts;
        private static Task loopTask;
        private static volatile bool running;

        // Messages queued for send. Drained by a dedicated sender task so we never
        // have two SendAsync calls racing on the same socket (ClientWebSocket
        // throws InvalidOperationException on overlapping sends — the bug that was
        // dropping all but the first message in a session).
        private static readonly ConcurrentQueue<string> sendQueue = new ConcurrentQueue<string>();
        // Signal used to wake the sender when a message arrives OR the socket state changes.
        private static SemaphoreSlim sendSignal;

        public static bool IsConnected => socket != null && socket.State == WebSocketState.Open;

        /// <summary>Invoked for each received message (raw JSON text). Called from a background thread.</summary>
        public static Action<string> OnMessage;

        // ── §2.6 chat split ──────────────────────────────────────
        // Subscribe to a SET (global + the locale channel + one optional
        // extra viewed channel), send to ONE. SendChannel is UI-owned (Tab
        // cycles it in the chat box; the Home dropdown sets it directly) and
        // may be ANY allowed channel regardless of locale — the server
        // relays sends to any allowed channel. It follows the language by
        // default (DefaultSendChannel) until the player picks explicitly.

        /// <summary>The language channel this locale is entitled to, or null
        /// (en/pseudo have only global).</summary>
        public static string LocaleChannel
        {
            get
            {
                string loc = I18n.Locale;
                return (loc == "ru" || loc == "es") ? loc : null;
            }
        }

        /// <summary>True for every channel the server accepts as a send target
        /// (CHAT_CHANNELS_ALLOWED). The server relays a send to any of these
        /// regardless of the sender's locale.</summary>
        private static bool IsAllowedChannel(string c)
            => c == "global" || c == "es" || c == "ru";

        /// <summary>Restart-coherent send default (R2-4a): an explicitly
        /// persisted language pick (item 5) wins, so a player who chose a
        /// display channel both VIEWS and TYPES into it after a restart;
        /// else follow the language; else global. Safe with the picker's
        /// "all" branch: it persists "all" BEFORE re-deriving, so reverting
        /// to the merged view falls through to the locale default.</summary>
        public static string DefaultSendChannel()
            => PersistedSendDefault() ?? LocaleChannel ?? "global";

        /// <summary>Send-default variant of the persisted pick: unlike
        /// PersistedDisplayChannel it ALSO honors an explicit "global" pick,
        /// so an es/ru-locale player who chose Global keeps typing into
        /// Global after a restart (view and type stay coherent). "all" and
        /// unset fall through to the locale default.</summary>
        private static string PersistedSendDefault()
        {
            try
            {
                string v = Plugin.ChatDisplayChannel != null ? Plugin.ChatDisplayChannel.Value : null;
                return (v == "es" || v == "ru" || v == "global") ? v : null;
            }
            catch { return null; }
        }

        /// <summary>The persisted display-channel pick when it names a
        /// language channel ("es"/"ru"), else null ("all"/"global"/unset
        /// narrow nothing). Null-guarded: the config may not be bound yet
        /// in some init orders. Unlike ExtraViewChannel this survives
        /// restarts, so it is the term that carries an explicit item-5
        /// pick across sessions — for BOTH the subscription set and the
        /// send default.</summary>
        private static string PersistedDisplayChannel()
        {
            try
            {
                string v = Plugin.ChatDisplayChannel != null ? Plugin.ChatDisplayChannel.Value : null;
                return (v == "es" || v == "ru") ? v : null;
            }
            catch { return null; }
        }

        // Null-backed: resolved lazily from DefaultSendChannel() on first get,
        // so a Spanish-locale player types into "es" at session start with no
        // init-order dependency on when the locale is bound.
        private static string sendChannel;
        public static string SendChannel
        {
            get
            {
                // Self-collapse ONLY when the stored value is a language
                // channel that no longer exists in the allowed set (future
                // channel retirement); any currently-allowed channel is a
                // valid pick for any locale.
                if (sendChannel == null || !IsAllowedChannel(sendChannel))
                    sendChannel = DefaultSendChannel();
                return sendChannel;
            }
            set { sendChannel = IsAllowedChannel(value) ? value : DefaultSendChannel(); }
        }

        // One EXTRA viewed channel beyond global + the locale channel, so a
        // player who picks a channel outside their locale in the Home dropdown
        // still receives it live. Null/absent by default. Normalized to the
        // language channels only — "global" is always subscribed, so it
        // collapses to null. Changing it re-declares the socket's channel set.
        private static volatile string extraViewChannel;
        public static string ExtraViewChannel
        {
            get { return extraViewChannel; }
            set
            {
                string v = (value == "es" || value == "ru") ? value : null;
                if (v == extraViewChannel) return;
                extraViewChannel = v;
                subscribeDirty = true;
                try { sendSignal?.Release(); } catch { }
            }
        }

        /// <summary>The derived VIEW-channel set as a comma-joined string:
        /// global + the locale channel + the extra viewed channel + the
        /// persisted display channel, deduped, stable order. THE single
        /// source of truth for both the socket subscription (SubscribeJson)
        /// and the scrollback fetch (ApiClient.FetchRecentChat) — R2-4b:
        /// those two derivations had already drifted once (the fetch was
        /// missing the persisted term), so both consume this helper and can
        /// never diverge again. The persisted term matters because the
        /// config survives restarts while ExtraViewChannel does not —
        /// without it a player whose saved display filter is a language
        /// channel outside their locale restarts into a filtered-EMPTY pane
        /// (subscription never carries the channel their filter shows).
        /// Values come from a closed set ("global"/"es"/"ru"), so the string
        /// is safe verbatim in both a JSON frame and a URL query.</summary>
        public static string DerivedChannelSet()
        {
            string lc = LocaleChannel;
            string extra = extraViewChannel;
            string persisted = PersistedDisplayChannel();
            var sb = new StringBuilder("global");
            if (lc != null) sb.Append(',').Append(lc);
            if (extra != null && extra != lc)   // dedup vs the locale channel
                sb.Append(',').Append(extra);
            if (persisted != null && persisted != lc && persisted != extra)
                sb.Append(',').Append(persisted);
            return sb.ToString();
        }

        private static string SubscribeJson()
        {
            // Closed-set values (see DerivedChannelSet), so rewriting the
            // comma-joined form into quoted JSON array items is safe.
            return "{\"type\":\"subscribe\",\"channels\":[\""
                + DerivedChannelSet().Replace(",", "\",\"") + "\"]}";
        }

        // Subscribe state is a DIRTY FLAG, never queued content (round-3
        // find N12): a queued frame captures the locale at enqueue time, and
        // a failed send requeues at the TAIL — a stale RU frame could drain
        // after a fresh EN one and win the socket's final state. The sender
        // computes SubscribeJson() at SEND time, so a retry always carries
        // the current channel set.
        private static volatile bool subscribeDirty;

        /// <summary>Locale changed mid-session: narrow/widen this socket's
        /// channel set and refetch scrollback so the newly-subscribed
        /// channel's history appears (the render-side dedup is a seen-id SET,
        /// not a high-water mark, precisely so this refetch isn't swallowed).</summary>
        public static void ResubscribeAndRefresh()
        {
            // Every locale change re-derives the send channel. Since R2-4a
            // the derivation prefers a PERSISTED explicit language pick over
            // the new locale — deliberate: the display filter carrying that
            // pick also survives the locale change, so the player keeps
            // typing into the channel they see. Only without such a pick
            // does the send channel follow the language, and either way the
            // player never silently types into a channel they can't view.
            // ExtraViewChannel is deliberately left alone here: the persisted
            // display channel is covered by SubscribeJson's config-derived
            // term, so no transient state needs re-seeding on locale change.
            sendChannel = DefaultSendChannel();
            if (!running) return;
            subscribeDirty = true;
            try { sendSignal?.Release(); } catch { }
            try { ApiClient.FetchRecentChat(50); } catch { }
        }

        public static void Connect()
        {
            if (running) return;
            if (!Plugin.DataConsentGranted)
            {
                Plugin.Log.LogInfo("[CHAT] Connect skipped — no data consent");
                return;
            }
            running = true;
            cts = new CancellationTokenSource();
            sendSignal = new SemaphoreSlim(0);
            loopTask = Task.Run(() => RunLoop(cts.Token));
        }

        public static void Disconnect()
        {
            running = false;
            try { cts?.Cancel(); } catch { }
            try { sendSignal?.Release(); } catch { }
            try
            {
                if (socket != null && socket.State == WebSocketState.Open)
                    socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "bye", CancellationToken.None).Wait(1000);
            }
            catch { }
            socket = null;
        }

        /// <summary>Queue a chat message for send. Drained by the sender task.</summary>
        public static void Send(string steamId, string displayName, string message)
        {
            if (string.IsNullOrEmpty(message)) return;
            // client_msg_id: per-message nonce baked into the queued JSON. When a
            // send fails mid-flight the SAME string is re-queued, so a resend
            // carries the same nonce — if the first copy actually reached the
            // server before the socket died, the server drops the repeat instead
            // of double-relaying it to Discord + other players (bug #30/#34).
            string nonce = Guid.NewGuid().ToString("N");
            // §2.6: send to ONE channel. SendChannel is any allowed channel
            // (follows the language by default); the server additionally
            // collapses unknown values to global (never drops).
            string channel = SendChannel;
            string outbound =
                "{\"steam_id\":\"" + JsonEscape(steamId ?? "") + "\"," +
                "\"display_name\":\"" + JsonEscape(displayName ?? "") + "\"," +
                "\"client_msg_id\":\"" + nonce + "\"," +
                "\"channel\":\"" + channel + "\"," +
                "\"message\":\"" + JsonEscape(message) + "\"}";
            sendQueue.Enqueue(outbound);
            try { sendSignal?.Release(); } catch { }
            Plugin.Log.LogInfo($"[CHAT] queued: {message}");

            // Local echo so the UI updates instantly — the server broadcast now excludes the sender,
            // so without this we'd never see our own message. Attach our own rating + active title
            // from cached stats so the local echo matches what other players will see.
            var s = ApiClient.CachedPlayerStats;
            int rating = s != null ? (int)Math.Round(s.rating) : 0;
            string title = s?.active_title ?? "";
            string titleColor = s?.active_title_color ?? "";
            string echo =
                "{\"source\":\"ingame\"," +
                "\"steam_id\":\"" + JsonEscape(steamId ?? "") + "\"," +
                "\"display_name\":\"" + JsonEscape(displayName ?? "") + "\"," +
                "\"rating\":" + rating + "," +
                "\"title\":\"" + JsonEscape(title) + "\"," +
                "\"title_color\":\"" + JsonEscape(titleColor) + "\"," +
                "\"channel\":\"" + channel + "\"," +
                "\"message\":\"" + JsonEscape(message) + "\"}";
            try { OnMessage?.Invoke(echo); } catch { }
        }

        /// <summary>Set by ApiClient when its TLS probe fails and it falls back to
        /// the legacy plaintext endpoint. Read inside the reconnect loop rather than
        /// captured once, so an in-flight loop picks it up on its next iteration.
        /// Session-scoped; never persisted.</summary>
        private static volatile string overrideBase;

        /// <summary>Point chat at a different base URL for the rest of the session and
        /// drop the current socket so the loop re-derives its ws/wss URL immediately.
        /// Without this, a loop that started against a dead wss:// host would retry
        /// that same dead host forever — the URL used to be computed once at entry.</summary>
        public static void Retarget(string newBaseHttp)
        {
            if (string.IsNullOrWhiteSpace(newBaseHttp)) return;
            overrideBase = newBaseHttp;
            Plugin.Log.LogInfo($"[CHAT] retargeting to {newBaseHttp}");
            try { socket?.Abort(); } catch { }   // wakes the loop; it reconnects on backoff
        }

        private static string ResolveBaseHttp()
        {
            // Precedence: session override (TLS fallback) > configured value >
            // compiled default. IsNullOrWhiteSpace rather than `?? ` because a
            // player who "resets" the key by blanking the line leaves an empty
            // STRING, which Config.Bind treats as a valid value and will not
            // replace — that would make `new Uri()` throw on every reconnect.
            if (!string.IsNullOrWhiteSpace(overrideBase)) return overrideBase;
            string cfg = Plugin.ApiBaseUrl?.Value;
            return string.IsNullOrWhiteSpace(cfg) ? Plugin.DefaultApiUrl : cfg;
        }

        /// <summary>True while this session's chat runs on the plaintext ws://
        /// fallback (see the connect-failure counter in RunLoop). Diagnostic
        /// only — mirrors ApiClient.UsingLegacyFallback's style.</summary>
        public static bool UsingWsFallback { get; private set; }

        private static async Task RunLoop(CancellationToken token)
        {
            int backoffSec = 2;
            // Chat-specific TLS fallback (learning #194): UnityWebRequest and
            // Mono's ClientWebSocket use DIFFERENT trust stores and TLS stacks
            // (the WS one is hardcoded <= TLS 1.2 and ignores
            // ServicePointManager), so ApiClient's REST probe can succeed while
            // every wss handshake fails — and Send() local-echoes regardless,
            // so the player is told their message sent while nobody receives
            // it. After N consecutive failed wss CONNECTs, fall back to the
            // legacy plaintext endpoint for this session only (never
            // persisted; TLS is retried next launch). DELETE THIS along with
            // Plugin.LegacyApiUrl in the same release that drops the
            // plaintext 8443 port-forward.
            int wssConnectFailures = 0;

            while (running && !token.IsCancellationRequested)
            {
                // Re-derived every iteration so a mid-session Retarget takes effect.
                string baseHttp = ResolveBaseHttp().TrimEnd('/');
                string wsUrl = baseHttp.Replace("https://", "wss://").Replace("http://", "ws://") + "/api/v1/ws/chat";
                Task senderTask = null;
                bool connected = false;
                try
                {
                    socket = new ClientWebSocket();
                    socket.Options.SetRequestHeader("X-Mod-Version", Plugin.ModVersion ?? "0.0.0");
                    await socket.ConnectAsync(new Uri(wsUrl), token);
                    connected = true;
                    wssConnectFailures = 0;
                    Plugin.Log.LogInfo($"[CHAT] WS connected: {wsUrl}");
                    backoffSec = 2;

                    // §2.6: declare this socket's channel set on every
                    // (re)connect. DIRECT send, not the queue (wave-2 find
                    // 21): a reconnect with an offline message backlog would
                    // otherwise drain the backlog BEFORE the subscribe frame,
                    // leaving the server's all-channels default live for that
                    // window. Safe: SendLoop hasn't been started yet, so no
                    // concurrent SendAsync exists.
                    try
                    {
                        var subBytes = Encoding.UTF8.GetBytes(SubscribeJson());
                        await socket.SendAsync(new ArraySegment<byte>(subBytes),
                            WebSocketMessageType.Text, true, token);
                    }
                    catch (Exception subEx)
                    { Plugin.Log.LogWarning($"[CHAT] subscribe frame failed: {subEx.Message}"); }

                    // Populate scrollback the first time we connect in a session.
                    try { ApiClient.FetchRecentChat(50); } catch { }

                    // Spawn sender and keepalive on this connection's lifetime. Both exit
                    // when the socket transitions away from Open or the token cancels.
                    senderTask = Task.Run(() => SendLoop(socket, token));
                    _ = Task.Run(() => KeepAliveLoop(socket, token));

                    var buffer = new byte[8192];
                    var msg = new StringBuilder();
                    while (socket.State == WebSocketState.Open && !token.IsCancellationRequested)
                    {
                        var seg = new ArraySegment<byte>(buffer);
                        WebSocketReceiveResult result;
                        try { result = await socket.ReceiveAsync(seg, token); }
                        catch (WebSocketException wex)
                        {
                            Plugin.Log.LogWarning($"[CHAT] recv error: {wex.Message}");
                            break;
                        }
                        if (result.MessageType == WebSocketMessageType.Close)
                        {
                            Plugin.Log.LogWarning($"[CHAT] WS close from server: {result.CloseStatus} {result.CloseStatusDescription}");
                            try { await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "closing", CancellationToken.None); } catch { }
                            break;
                        }
                        msg.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
                        if (result.EndOfMessage)
                        {
                            string text = msg.ToString();
                            msg.Clear();
                            try { OnMessage?.Invoke(text); } catch { }
                            Plugin.Log.LogInfo($"[CHAT] <- {text}");
                        }
                    }
                }
                catch (Exception ex) when (!token.IsCancellationRequested)
                {
                    Plugin.Log.LogWarning($"[CHAT] WS error: {ex.Message} (reconnect in {backoffSec}s)");
                    // Count only failed CONNECTs (post-connect throws are a
                    // different failure class), only for wss, only while on the
                    // compiled default base (a custom/LAN BaseUrl was chosen
                    // deliberately — mirror ApiClient.Initialize's probe gate),
                    // and only if ApiClient's own REST fallback hasn't already
                    // retargeted us (overrideBase composes the two mechanisms).
                    if (!connected
                        && overrideBase == null
                        && wsUrl.StartsWith("wss://")
                        && string.Equals(baseHttp, Plugin.DefaultApiUrl.TrimEnd('/'), StringComparison.OrdinalIgnoreCase)
                        && ++wssConnectFailures >= 3)
                    {
                        overrideBase = Plugin.LegacyApiUrl;
                        UsingWsFallback = true;
                        Plugin.Log.LogWarning(
                            $"[CHAT] wss unreachable after {wssConnectFailures} attempts — session fallback to plaintext ws ({Plugin.LegacyApiUrl}). " +
                            "Config untouched; TLS is retried next launch.");
                    }
                }
                finally
                {
                    try { sendSignal?.Release(); } catch { }  // wake sender so it sees socket.State != Open
                    if (senderTask != null) { try { await senderTask; } catch { } }
                    try { socket?.Dispose(); } catch { }
                    socket = null;
                }

                if (!running || token.IsCancellationRequested) break;
                try { await Task.Delay(backoffSec * 1000, token); } catch { }
                backoffSec = Math.Min(backoffSec * 2, 60);
            }
            Plugin.Log.LogInfo("[CHAT] WS loop exited");
        }

        // Single writer — drains sendQueue one message at a time. Non-awaited concurrent
        // SendAsync on the same ClientWebSocket throws InvalidOperationException, which
        // is what caused the "only first message got through" behaviour.
        private static async Task SendLoop(ClientWebSocket ws, CancellationToken token)
        {
            while (!token.IsCancellationRequested && ws.State == WebSocketState.Open)
            {
                try { await sendSignal.WaitAsync(token); }
                catch { return; }

                // Subscribe-dirty first, computed FRESH at send time (N12) —
                // ahead of any queued data so a channel change is never
                // outrun by the backlog.
                if (subscribeDirty)
                {
                    subscribeDirty = false;
                    var subJson = SubscribeJson();
                    var subBytes = Encoding.UTF8.GetBytes(subJson);
                    try
                    {
                        await ws.SendAsync(new ArraySegment<byte>(subBytes), WebSocketMessageType.Text, true, token);
                    }
                    catch (Exception ex)
                    {
                        Plugin.Log.LogWarning($"[CHAT] subscribe send failed: {ex.Message}");
                        subscribeDirty = true;   // retried (fresh) after reconnect
                        return;
                    }
                }

                while (sendQueue.TryDequeue(out var json))
                {
                    if (ws.State != WebSocketState.Open) { sendQueue.Enqueue(json); return; }
                    var bytes = Encoding.UTF8.GetBytes(json);
                    try
                    {
                        await ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, token);
                        Plugin.Log.LogInfo($"[CHAT] -> sent ({bytes.Length}B)");
                    }
                    catch (Exception ex)
                    {
                        Plugin.Log.LogWarning($"[CHAT] send failed: {ex.Message} — requeueing");
                        sendQueue.Enqueue(json);
                        return;  // break out so reconnect loop takes over
                    }
                }
            }
        }

        // App-level ping every 25s. uvicorn closes idle WS after ~60s by default; a
        // short empty-payload keeps the TCP connection from being nuked mid-session.
        private static async Task KeepAliveLoop(ClientWebSocket ws, CancellationToken token)
        {
            while (!token.IsCancellationRequested && ws.State == WebSocketState.Open)
            {
                try { await Task.Delay(25_000, token); } catch { return; }
                if (ws.State != WebSocketState.Open) return;
                // Send a ping through the same send queue so we don't race the sender.
                sendQueue.Enqueue("{\"type\":\"ping\"}");
                try { sendSignal?.Release(); } catch { }
            }
        }

        private static string JsonEscape(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new StringBuilder(s.Length);
            foreach (char c in s)
            {
                switch (c)
                {
                    case '\\': sb.Append("\\\\"); break;
                    case '"':  sb.Append("\\\""); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20) sb.Append($"\\u{(int)c:x4}");
                        else sb.Append(c);
                        break;
                }
            }
            return sb.ToString();
        }
    }
}
