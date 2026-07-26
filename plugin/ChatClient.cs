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
            string outbound =
                "{\"steam_id\":\"" + JsonEscape(steamId ?? "") + "\"," +
                "\"display_name\":\"" + JsonEscape(displayName ?? "") + "\"," +
                "\"client_msg_id\":\"" + nonce + "\"," +
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
