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

        /// <summary>Invoked for each received message (raw JSON text). Called
        /// from a background thread. The payload is the server's own JSON,
        /// untouched — live WS frames and each scrollback entry sliced out by
        /// ApiClient.FetchRecentChat go through here in the SAME shape, so any
        /// server field (id, channel, timestamp, ...) is available to the
        /// consumer. Local echoes from Send() are synthesized in that same
        /// shape.
        ///
        /// A property rather than a plain field so the server-clock sampler
        /// below can see SCROLLBACK: ApiClient.FetchRecentChat dispatches each
        /// history row straight through this member, and the getter is the only
        /// place inside this file that those rows pass. The getter hands back a
        /// wrapper that feeds the row to the sampler and then calls the real
        /// consumer — a consumer exception still propagates to the caller's own
        /// try/catch exactly as it did when this was a field, and the wrapper
        /// is a cached delegate so a get allocates nothing.</summary>
        public static Action<string> OnMessage
        {
            // Null when nothing is subscribed, so the existing `OnMessage?.Invoke`
            // call sites short-circuit exactly as they did against the field.
            get { return messageSink == null ? null : dispatchAgeUnknown; }
            set { messageSink = value; }
        }

        // The real consumer. volatile: assigned once on the main thread during
        // plugin init, invoked from the WS receive task.
        private static volatile Action<string> messageSink;

        // Kept as a wrapper rather than exposing messageSink directly so the
        // OnMessage property's null-when-unsubscribed getter still short-
        // circuits `?.Invoke` at the call sites exactly as a plain field did.
        // (This used to also feed a clock-skew sampler; that estimator was
        // removed — see the local-echo timestamp note further down.)
        private static readonly Action<string> dispatchAgeUnknown = json => Dispatch(json);

        /// <summary>Hand a received row to the consumer.</summary>
        private static void Dispatch(string json)
        {
            messageSink?.Invoke(json);
        }

        // ── §2.6 chat split ──────────────────────────────────────
        // Subscribe to EVERY allowed channel, always (AllChannels), and send
        // to ONE. The subscription is a CONSTANT — it is deliberately not
        // derived from the locale or from any display filter, because the
        // socket subscription is what decides which messages ever reach this
        // client at all (the server's broadcast() skips non-subscribed
        // channels). Hiding a channel is a pure render-side concern for the
        // UI; the pipe always carries everything.
        //
        // SendChannel is the TYPING target and is fully decoupled from the
        // display filter: it is an explicit persisted pick
        // (Plugin.ChatSendChannel) when there is one, else it follows the mod
        // language, else global. It can never be "all" — that is what makes
        // "typing into the merged view" structurally impossible.

        /// <summary>The language channel this locale is entitled to, or null
        /// (en/pseudo have only global).</summary>
        public static string LocaleChannel
        {
            get
            {
                string loc = I18n.Locale;
                return (loc == "ru" || loc == "es" || loc == "uk" || loc == "sv") ? loc : null;
            }
        }

        /// <summary>True for every channel the server accepts as a send target
        /// (CHAT_CHANNELS_ALLOWED). The server relays a send to any of these
        /// regardless of the sender's locale.</summary>
        private static bool IsAllowedChannel(string c)
            => c == "global" || c == "es" || c == "ru" || c == "uk" || c == "sv";

        /// <summary>Every channel this client subscribes to — a CONSTANT, and
        /// the whole server-allowed set (CHAT_CHANNELS_ALLOWED). Comma-joined
        /// because both consumers (the subscribe frame and the scrollback
        /// query string) want that form. Closed-set values, so it is safe
        /// verbatim in JSON and in a URL.
        /// A client AHEAD of the server degrades instead of breaking: both the
        /// subscribe handler and the scrollback query intersect this list with
        /// CHAT_CHANNELS_ALLOWED and drop the unknown names rather than
        /// rejecting the request, so a new channel simply carries nothing until
        /// the API ships it. Server-first deploy is still preferred.</summary>
        private const string AllChannels = "global,es,ru,uk,sv";

        /// <summary>The TYPING target's default: an explicit persisted pick
        /// wins (Plugin.ChatSendChannel), else the mod language's channel,
        /// else global. Never returns "all". Independent of the display
        /// filter — a player viewing the merged log still types somewhere
        /// concrete.</summary>
        public static string DefaultSendChannel()
            => PersistedSendDefault() ?? LocaleChannel ?? "global";

        /// <summary>The explicit persisted typing-channel override, or null
        /// when the player never picked one (default "" = follow the mod
        /// language). Honors "global" as a real pick, so a player on any
        /// language channel who deliberately types in Global keeps doing so
        /// across restarts and across language changes. Must list every
        /// IsAllowedChannel value: a channel missing here is silently demoted
        /// to "follow the mod language" on the next launch, discarding the
        /// player's pick. Null-guarded: the config may not be bound
        /// yet in some init orders.</summary>
        private static string PersistedSendDefault()
        {
            try
            {
                string v = Plugin.ChatSendChannel != null ? Plugin.ChatSendChannel.Value : null;
                return (v == "es" || v == "ru" || v == "uk" || v == "sv" || v == "global") ? v : null;
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
            // An assignment is an EXPLICIT pick and is persisted, so it
            // survives a restart AND a later language change (that is what
            // "explicit override" means). "all" / anything unknown can never
            // land here — it collapses to the default, which is always a
            // concrete channel. Use ResetSendChannelToLocale() for the
            // "go back to following the language" action; assigning
            // DefaultSendChannel() would freeze today's language as a pick.
            set
            {
                sendChannel = IsAllowedChannel(value) ? value : DefaultSendChannel();
                try
                {
                    if (Plugin.ChatSendChannel != null && IsAllowedChannel(value))
                        Plugin.ChatSendChannel.Value = value;
                }
                catch { }
            }
        }

        /// <summary>Drop the explicit typing-channel override and go back to
        /// following the mod language (config "" = auto). The counterpart of
        /// the SendChannel setter — assigning DefaultSendChannel() there
        /// would persist the CURRENT language as an explicit pick and stop
        /// following later language changes.</summary>
        public static void ResetSendChannelToLocale()
        {
            try { if (Plugin.ChatSendChannel != null) Plugin.ChatSendChannel.Value = ""; } catch { }
            sendChannel = LocaleChannel ?? "global";
        }

        /// <summary>The VIEW-channel set as a comma-joined string. CONSTANT:
        /// every allowed channel, always, regardless of locale or of any
        /// display filter. THE single source of truth for both the socket
        /// subscription (SubscribeJson) and the scrollback fetch
        /// (ApiClient.FetchRecentChat), so the two can never diverge.
        ///
        /// It used to be derived (global + locale + an extra viewed channel +
        /// the persisted display filter) — which meant an English client
        /// derived literally "global", the server's broadcast() skipped every
        /// non-subscribed channel, and the "All (merged)" view could never
        /// show es/ru because those messages never reached the client at all.
        /// Hiding a channel is now purely render-side; the pipe always
        /// carries the full set. Do NOT re-narrow this from UI state.</summary>
        public static string DerivedChannelSet() => AllChannels;

        private static string SubscribeJson()
        {
            // Closed-set values (see AllChannels), so rewriting the
            // comma-joined form into quoted JSON array items is safe.
            return "{\"type\":\"subscribe\",\"channels\":[\""
                + DerivedChannelSet().Replace(",", "\",\"") + "\"]}";
        }

        /// <summary>Locale changed mid-session. The socket's channel set is a
        /// constant so there is nothing to re-declare — only the TYPING
        /// target can move. Scrollback is refetched because the render side
        /// rebuilds its pane on a language change (the dedup is a seen-id
        /// SET, not a high-water mark, precisely so a refetch isn't
        /// swallowed).</summary>
        public static void ResubscribeAndRefresh()
        {
            // Follow the NEW language unless the player explicitly overrode
            // the typing channel — DefaultSendChannel() prefers the persisted
            // pick, so an override survives and everything else moves with
            // the language.
            sendChannel = DefaultSendChannel();
            if (!running) return;
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
            // §2c identity fence (broadcast-architecture.md): the broadcast
            // service account never speaks in chat. Single entry point — every
            // chat-send surface funnels through here.
            if (BroadcastMode.FenceBlocksFighterPath("chat-send")) return;
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
            // "timestamp" mirrors the server's own field (ISO-8601 UTC with a
            // +00:00 offset, from a TIMESTAMPTZ) so a merged, time-ordered
            // view can sort echoes against real rows without a special case.
            // InvariantCulture is load-bearing (#47) — a ru/es OS locale
            // would otherwise emit non-ASCII / reordered date parts.
            // The value comes from the SERVER's clock (NowUtc), not this
            // machine's: the time-ordered pane sorts on this field, so a
            // client clock minutes fast would file its own line minutes into
            // the future and one running slow would bury it above messages
            // that are genuinely older. Ordering hint only — the server still
            // owns the stored timestamp, and its canonical row supersedes this
            // one when it arrives.
            string echo =
                "{\"source\":\"ingame\"," +
                "\"steam_id\":\"" + JsonEscape(steamId ?? "") + "\"," +
                "\"display_name\":\"" + JsonEscape(displayName ?? "") + "\"," +
                "\"rating\":" + rating + "," +
                "\"title\":\"" + JsonEscape(title) + "\"," +
                "\"title_color\":\"" + JsonEscape(titleColor) + "\"," +
                "\"channel\":\"" + channel + "\"," +
                "\"message\":\"" + JsonEscape(message) + "\"," +
                "\"timestamp\":\"" + ServerNowIso8601() + "\"}";
            // DIRECT to the consumer, NEVER through the OnMessage property: that
            // getter feeds the clock sampler, and an echo carries OUR stamp, so
            // routing it there would let the offset confirm itself and drift.
            try { messageSink?.Invoke(echo); } catch { }
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

                    /* Codex r1 f2: bind this socket to our verified Steam
                     * session so censor strikes can only ever land on OUR OWN
                     * identity server-side. Same direct-send rationale as the
                     * subscribe frame above. Best-effort: no token yet (early
                     * launch) just means this socket stays unverified until
                     * the next reconnect — messages still relay either way.
                     *
                     * Codex r2 f1 (HIGH): NEVER on a plaintext socket. The
                     * 24h session bearer over ws:// hands an on-path attacker
                     * both a censor-strike primitive against us AND an
                     * X-Session-Token replay. A downgraded session simply
                     * stays unverified (censor-only, no strikes) — chat still
                     * works. wsUrl is the exact string this socket dialed. */
                    try
                    {
                        string sid = MatchTracker.LocalSteamId;
                        string tok = SteamAuth.SessionToken;
                        if (!string.IsNullOrEmpty(sid) && sid != "unknown" && !string.IsNullOrEmpty(tok)
                            && wsUrl.StartsWith("wss://", StringComparison.OrdinalIgnoreCase))
                        {
                            string authJson = "{\"type\":\"auth\",\"steam_id\":\"" + JsonEscape(sid)
                                            + "\",\"token\":\"" + JsonEscape(tok) + "\"}";
                            var authBytes = Encoding.UTF8.GetBytes(authJson);
                            await socket.SendAsync(new ArraySegment<byte>(authBytes),
                                WebSocketMessageType.Text, true, token);
                        }
                    }
                    catch (Exception authEx)
                    { Plugin.Log.LogWarning($"[CHAT] auth frame failed: {authEx.Message}"); }

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
                            try { Dispatch(text); } catch { }
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

                // No mid-session re-subscribe: the channel set is a constant
                // declared once per connection (see RunLoop). The old
                // dirty-flag path existed only to RE-NARROW the socket when
                // the locale or the display filter changed — the very thing
                // that made the merged view unreachable.

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

        /// <summary>Server-shaped send time for the local echo: ISO-8601 UTC
        /// with an explicit +00:00 offset, matching Python's
        /// datetime.isoformat() on a TIMESTAMPTZ. Invariant so an es/ru OS
        /// locale can't reorder or localize the digits. Reads the SERVER's
        /// clock (NowUtc), not this machine's — see the offset block below.</summary>
        private static string ServerNowIso8601()
            => NowUtc().ToString("yyyy-MM-ddTHH:mm:ss.ffffff",
                   System.Globalization.CultureInfo.InvariantCulture) + "+00:00";

        // ── local echo timestamp ─────────────────────────────────
        // The chat pane is ordered by each row's server timestamp, but a local
        // echo is drawn before its canonical row exists, so it has to be
        // stamped here — off this machine's clock.
        //
        // A previous revision learned the server/client skew from the
        // timestamps on received rows and corrected for it. That estimator is
        // GONE, deliberately. Adversarial review confirmed five independent
        // ways for it to go wrong — one absurd row could move it by up to the
        // 400-day cap, frames buffered across a process stall sampled as
        // "live" and dragged it negative, a sender had no guaranteed route to
        // receive its own canonical row, and echo markers expired on the very
        // clock being corrected — for a benefit that lasts only until the
        // server's own row arrives.
        //
        // That arrival is the real fix and it still happens: NativeUI pairs the
        // canonical row with its echo and RE-STAMPS the drawn line with the
        // authoritative created_at, then re-sorts it. So a skewed clock costs
        // one briefly mis-ordered line, not a permanently mis-ordered one —
        // and no session-wide estimate can be corrupted, because there is none
        // (learning #288: prefer under-correction to a recovery mechanism whose
        // own failure modes are worse than the thing it recovers from).

        /// <summary>UTC now. Named for the role it plays — "the time to stamp a
        /// message with" — so the call sites read the same whether or not any
        /// skew correction ever exists again. Session state only.</summary>
        public static DateTime NowUtc() => DateTime.UtcNow;


        /// <summary>Read a string value stored under <paramref name="key"/> at
        /// the TOP level of a chat row, or null.
        ///
        /// String-aware rather than an IndexOf for the same reason as the
        /// scrollback slicer and NativeUI's field reader (#156): chat messages
        /// and display names are user-authored, and a raw scan finds the first
        /// textual occurrence anywhere — including inside a value. A player
        /// typing a literal timestamp field would otherwise be feeding this
        /// machine's clock estimator, which is a whole-session corruption
        /// rather than one misplaced line. Only depth-1 keys (direct members of
        /// the row object) are accepted, and only in value position.</summary>
        private static string ExtractTopLevelString(string json, string key)
        {
            if (string.IsNullOrEmpty(json) || string.IsNullOrEmpty(key)) return null;

            int depth = 0;
            bool inString = false, escaped = false, expectValue = false;
            int start = -1;
            string pendingKey = null;

            for (int i = 0; i < json.Length; i++)
            {
                char c = json[i];
                if (inString)
                {
                    if (escaped) { escaped = false; continue; }
                    if (c == '\\') { escaped = true; continue; }
                    if (c != '"') continue;
                    inString = false;
                    string token = json.Substring(start, i - start);
                    if (expectValue)
                    {
                        if (depth == 1 && pendingKey == key) return token;
                        expectValue = false;
                        pendingKey = null;
                    }
                    else pendingKey = token;   // key position (or an array item)
                    continue;
                }

                switch (c)
                {
                    case '"': inString = true; start = i + 1; break;
                    // A nested object/array is not depth 1, and it also ends any
                    // pending key/value pairing at this level.
                    case '{': case '[': depth++; expectValue = false; pendingKey = null; break;
                    case '}': case ']': depth--; expectValue = false; pendingKey = null; break;
                    case ':': expectValue = true; break;
                    case ',': expectValue = false; pendingKey = null; break;
                }
            }
            return null;
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
