using System;
using System.Collections.Generic;
using ExitGames.Client.Photon;
using Photon.Pun;
using Photon.Realtime;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>The region list <see cref="RegionPingSweep"/> needs, fetched
    /// directly from Photon's NameServer when PUN has not built one.
    ///
    /// WHY THIS EXISTS. The sweep can only ping regions PUN has told it about:
    /// it needs each region's Code and HostAndPort, and those exist nowhere but
    /// the OpGetRegions response. PUN issues that operation from exactly one
    /// place — LoadBalancingClient's EncryptionEstablished case, and only while
    /// Server is NameServer AND CloudRegion is empty — and assigns the resulting
    /// RegionHandler at exactly one place, the case-220 handler. A ranked join
    /// force-connects (Plugin sets RegionSelector.region and m_ForceRegion, so
    /// NetworkConnectionHandler calls ConnectToRegion), which SETS CloudRegion
    /// on the way through the NameServer, so that gate never fires. A player who
    /// launches ROUNDS and only ever queues ranked therefore has no region list
    /// for the whole process, and rung 0 can never fire for them — the ladder
    /// decides every room they play, which is the defect this closes.
    ///
    /// WHAT IT DOES. Opens a PRIVATE LoadBalancingClient to the NameServer and
    /// reads the region list off its own RegionHandler. ConnectToNameServer sets
    /// connectToBestRegion = false, so the fetch stops after SetRegions and PUN's
    /// own all-region ping never runs. The handshake breaks before authenticate,
    /// so there is no CCU and no session. The game's own client is never touched:
    /// this is a separate object with a separate socket.
    ///
    /// THE ONE THING THAT COULD REACH THE GAME, and the bound on it.
    /// RegionHandler's constructor writes the PROCESS-WIDE static
    /// PortToPingOverride (RegionHandler.cs:109-111), and that static is what
    /// SetRegions bakes into every address and what the sweep reads when it
    /// builds targets. A probe constructing its own RegionHandler therefore
    /// writes a static the real sweep depends on. Two things bound it rather
    /// than guard it: the probe is given the GAME's own ServerPortOverrides, so
    /// in the ordinary case it writes exactly the value that was already there;
    /// and <see cref="RestorePortOverride"/> holds the invariant that the static
    /// ends up carrying the GAME's port. Note what that is NOT: it is not
    /// "whoever wrote last wins", because nothing here can identify the writer.
    /// PUN builds its RegionHandler with the same port this probe was handed, so
    /// the value cannot say who put it there — see RestorePortOverride for why
    /// undoing our write on that evidence is what breaks PUN. The catalog also
    /// carries the port its OWN addresses were built for, so a catalog-sourced
    /// target never depends on the static at all.
    ///
    /// FAILURE DIRECTION. Every refusal, timeout, error and abort leaves
    /// Entries as it was — usually null. A null catalog is exactly today's
    /// behaviour: the sweep finds no region list, publishes no map, and the
    /// server's ladder decides the room.
    ///
    /// What that does NOT buy is freshness, and the first draft of this comment
    /// claimed it did. A published list is kept until a LATER fetch succeeds,
    /// and FetchedAt gates only whether to re-fetch, never whether to use what
    /// is held — so a long-running client whose refreshes keep failing goes on
    /// measuring the roster Photon served hours ago. What IS bounded is that the
    /// entries were Photon's own words when they arrived: a region retired since
    /// then simply fails to answer and drops out of the map, and the cost of one
    /// ADDED since then is that it cannot be measured until a refresh lands.
    /// PUN's own list wins wherever PUN has one, so this staleness is confined
    /// to the sessions that have no other list at all.</summary>
    internal static class RegionCatalog
    {
        internal sealed class Entry
        {
            public string Code;
            public string HostAndPort;
        }

        /// <summary>The published list, or null until a fetch succeeds. Main
        /// thread only, like the sweep's own publication.</summary>
        public static Entry[] Entries;
        public static float FetchedAt = -1f;      // Time.realtimeSinceStartup
        /// <summary>The master-server port override the published addresses
        /// were built for. The sweep uses THIS for catalog-sourced targets
        /// rather than the process-wide static, which anyone may rewrite.</summary>
        public static ushort PortOverride;
        public static int Revision;

        const float TTL_S = 21600f;        // 6 h: a region roster changes on the order of years
        const float DEADLINE_S = 10f;      // NameServer connect + OpGetRegions round trip
        const float TEARDOWN_S = 3f;       // then the socket is dropped regardless
        const float POLL_S = 0.25f;
        const float GATE_LOG_S = 60f;
        const int MAX_ATTEMPTS = 6;
        const int MAX_ATTEMPTS_CEILING = 12;
        static readonly float[] BACKOFF_S = { 30f, 120f, 600f, 1800f, 1800f, 1800f };

        static Probe probe;
        static float startedRt = -1f;
        static float teardownRt = -1f;
        static float nextAttemptRt = -1f;
        static float nextPollRt;
        static float gateLoggedRt = -1f;
        static string gateLoggedWhy;
        static int attempts;
        static int granted = MAX_ATTEMPTS;
        static bool wanted;
        static ushort savedPortOverride;
        static ushort probeWrotePortOverride;
        static bool portOverrideSaved;

        /// <summary>Our own LoadBalancingClient. The DebugReturn override is the
        /// point of the subclass: the base implementation routes Photon's
        /// diagnostics through UnityEngine.Debug, which this mod's card-name
        /// capture reads — keep the probe's chatter in the BepInEx log only.</summary>
        sealed class Probe : LoadBalancingClient
        {
            public override void DebugReturn(DebugLevel level, string message)
            {
                if (level == DebugLevel.ERROR || level == DebugLevel.WARNING)
                    Plugin.Log?.LogInfo($"[REGION-CATALOG] photon {level}: {message}");
            }
        }

        /// <summary>The sweep found no region list and wants one. A demand edge
        /// grants one extra attempt past the idle ceiling, so a player who
        /// actually queues is not left starved by a backoff that a quiet launch
        /// consumed.</summary>
        public static void NoteWanted()
        {
            wanted = true;
            if (attempts >= granted && granted < MAX_ATTEMPTS_CEILING) granted++;
        }

        static BepInEx.Configuration.ConfigEntry<bool> lever;
        static bool leverBound;

        /// <summary>The kill switch. This is the only feature in the mod that
        /// opens a Photon connection of its own, so it gets a lever that can be
        /// flipped without a rebuild: turning it off restores exactly the
        /// pre-D2 behaviour (no catalog, so a ranked-only session sweeps
        /// nothing and the server's ladder decides the room).</summary>
        static bool Enabled()
        {
            if (!leverBound)
            {
                leverBound = true;
                try
                {
                    var cf = Plugin.ConfigFileForLevers;
                    if (cf != null)
                        lever = cf.Bind(
                            "Network", "RegionCatalogFetch", true,
                            "Fetch Photon's region list directly from its name server when the game has not built one, so ranked matchmaking can measure your latency to each region. Turn this off to stop the mod opening any connection of its own; ranked rooms are then placed by the server's fallback rules.");
                }
                catch (Exception ex) { Plugin.Log?.LogWarning("[REGION-CATALOG] lever bind failed: " + ex.Message); }
            }
            try { return lever == null || lever.Value; } catch { return true; }
        }

        /// <summary>Main-thread poll from the persistent tick. Services a live
        /// probe every call (a Photon client that is not serviced never
        /// progresses); the start policy is self-throttled.</summary>
        public static void Tick()
        {
            float rt = Time.realtimeSinceStartup;
            // A live probe is always serviced and torn down, even if the lever
            // went false mid-fetch: dropping an unserviced client would leak the
            // socket rather than close it.
            if (probe != null) { ServiceProbe(rt); return; }
            if (rt < nextPollRt) return;
            nextPollRt = rt + POLL_S;
            if (!Enabled()) return;
            TryStart(rt);
        }

        // ── policy ──

        static void TryStart(float rt)
        {
            try
            {
                // g1: a fresh catalog needs no fetch.
                if (Entries != null && FetchedAt >= 0f && rt - FetchedAt < TTL_S) return;
                // g3/g4: backoff and the attempt ceiling.
                if (nextAttemptRt >= 0f && rt < nextAttemptRt) return;
                if (attempts >= granted) return;
                // g6: never start into a quitting application.
                if (ConnectionHandler.AppQuits) return;
                // g7: not while the player is in a real game.
                if (PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode) return;

                var settings = PhotonNetwork.PhotonServerSettings;
                var app = settings != null ? settings.AppSettings : null;
                if (app == null || string.IsNullOrEmpty(app.AppIdRealtime)) { Gate(rt, "no-appid"); return; }

                var client = PhotonNetwork.NetworkingClient;
                // g8: PUN has a list of its own — the catalog is not needed.
                var rh = client != null ? client.RegionHandler : null;
                if (rh != null && rh.EnabledRegions != null && rh.EnabledRegions.Count > 0) return;

                // g9: PhotonNetwork.ServerPortOverrides reads back `default` while
                // NetworkingClient is null, and the real value is installed by
                // NetworkConnectionHandler.Awake. Fetching in that window would
                // bake Photon's stock 5055 into every address instead of the
                // alternative ports ROUNDS uses, and a catalog of wrong ports
                // measures nothing. Waiting costs one poll.
                if (client == null || PhotonNetwork.ServerPortOverrides.MasterServerPort == 0)
                { Gate(rt, "no-port-override"); return; }

                // g10: never overlap the game's own NameServer phase. That window
                // is the only one in which PUN itself builds a RegionHandler or
                // rewrites its port overrides, so staying out of it removes the
                // interleaving rather than reasoning about it.
                if (GameIsOnNameServer(client)) { Gate(rt, "game-on-nameserver"); return; }

                // g11: demand, or one eager fetch per launch from the menu — the
                // eager one is for LATENCY, not reachability: it means the first
                // ranked queue of a session already has a list to sweep.
                if (!wanted && !RegionPingSweep.AtMainMenu()) return;

                Start(rt, app);
            }
            catch (Exception ex)
            {
                // Same reason as the refusal above: an exception thrown before
                // Start charged its attempt would otherwise retry at the shortest
                // backoff for the life of the process. Charging twice when the
                // throw came AFTER the charge only backs off sooner, which is the
                // safe direction for a fetch nothing is waiting on.
                attempts++;
                Plugin.Log?.LogWarning($"[REGION-CATALOG] start failed: {ex.GetType().Name}: {ex.Message}");
                Consume(rt);
            }
        }

        static void Start(float rt, AppSettings app)
        {
            var p = new Probe();
            p.LoadBalancingPeer.TransportProtocol = app.Protocol;
            p.AppId = app.AppIdRealtime;
            // FORCED, not mirrored. AuthOnce/AuthOnceWss take a different branch
            // out of EncryptionEstablished and land in paths that reset
            // ServerPortOverrides; forcing plain Auth removes those branches
            // rather than surviving them.
            p.AuthMode = AuthModeOption.Auth;
            p.EnableProtocolFallback = false;
            p.ProxyServerAddress = app.ProxyServer;
            if (!app.IsDefaultNameServer) p.NameServerHost = app.Server;
            p.NameServerPortInAppSettings = app.Port;
            // The game's own overrides, so the RegionHandler this probe builds
            // writes the value that was already in the static.
            p.ServerPortOverrides = PhotonNetwork.ServerPortOverrides;
            p.LoadBalancingPeer.CrcEnabled = PhotonNetwork.CrcCheckEnabled;

            savedPortOverride = RegionHandler.PortToPingOverride;
            probeWrotePortOverride = p.ServerPortOverrides.MasterServerPort;
            portOverrideSaved = true;

            // Charged BEFORE the connect, not after it. A refusal here is a real
            // attempt and has to age the backoff: Consume() reads its interval from
            // attempts, so an uncharged refusal retried at the SHORTEST interval,
            // forever, and never reached the ceiling that exists to stop exactly
            // that. The old message also named the one cause this call cannot
            // have — the probe is a fresh client, so its peer IS disconnected;
            // a false return here is an app id, an address or a transport.
            attempts++;
            if (!p.ConnectToNameServer())
            {
                portOverrideSaved = false;
                Plugin.Log?.LogInfo($"[REGION-CATALOG] fetch refused by PUN attempt={attempts}/{granted}");
                Consume(rt);
                return;
            }
            probe = p;
            startedRt = rt;
            teardownRt = -1f;
            Plugin.Log?.LogInfo($"[REGION-CATALOG] fetch started attempt={attempts}/{granted}");
        }

        // ── the live probe ──

        static void ServiceProbe(float rt)
        {
            var p = probe;
            try { p.Service(); } catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[REGION-CATALOG] service failed: {ex.GetType().Name}: {ex.Message}");
                Finish(rt, null, "service-error");
                return;
            }

            if (teardownRt >= 0f)
            {
                if (rt >= teardownRt || p.LoadBalancingPeer.PeerState == PeerStateValue.Disconnected) Release();
                return;
            }

            // The game entered its own NameServer phase after we started: get out
            // rather than interleave two RegionHandler constructions.
            var client = PhotonNetwork.NetworkingClient;
            if (client != null && GameIsOnNameServer(client)) { Finish(rt, null, "game-on-nameserver"); return; }
            if (ConnectionHandler.AppQuits) { Finish(rt, null, "quitting"); return; }

            var rh = p.RegionHandler;
            if (rh != null && rh.EnabledRegions != null && rh.EnabledRegions.Count > 0)
            { Finish(rt, rh, null); return; }

            if (rt - startedRt >= DEADLINE_S) Finish(rt, null, "deadline");
        }

        /// <summary>Publishes when <paramref name="rh"/> is non-null, then begins
        /// teardown. Every path through here restores the port-override static.</summary>
        static void Finish(float rt, RegionHandler rh, string why)
        {
            bool published = false;
            if (rh != null)
            {
                var list = new List<Entry>(rh.EnabledRegions.Count);
                foreach (var region in rh.EnabledRegions)
                {
                    if (region == null) continue;
                    if (string.IsNullOrEmpty(region.Code) || string.IsNullOrEmpty(region.HostAndPort)) continue;
                    list.Add(new Entry { Code = region.Code, HostAndPort = region.HostAndPort });
                }
                if (list.Count > 0)
                {
                    Entries = list.ToArray();
                    FetchedAt = rt;
                    PortOverride = probeWrotePortOverride;
                    Revision++;
                    attempts = 0;
                    nextAttemptRt = -1f;
                    wanted = false;
                    Plugin.Log?.LogInfo($"[REGION-CATALOG] fetched n={Entries.Length} rev={Revision} port={PortOverride}");
                    published = true;
                }
                else
                {
                    Plugin.Log?.LogInfo("[REGION-CATALOG] fetch returned an empty region list");
                    Consume(rt);
                }
            }
            else
            {
                Plugin.Log?.LogInfo($"[REGION-CATALOG] fetch ended why={why}");
                Consume(rt);
            }

            // BEFORE the sweep is woken, and before anything else can run: that
            // wake-up re-enters RegionPingSweep.TryStart synchronously, and if PUN
            // acquired a list of its own while we were fetching, that sweep reads
            // the process-wide static — which must already be the game's value,
            // not ours. Restoring after the callback would hand the one reader
            // this whole bound exists for exactly the value it must not see.
            RestorePortOverride();
            try { probe.Disconnect(); } catch { }
            teardownRt = rt + TEARDOWN_S;
            if (published) { try { RegionPingSweep.NoteCatalogReady(); } catch { } }
        }

        /// <summary>Put the process-wide static back — but only where leaving
        /// it alone would be worse, because value equality is NOT writer
        /// ownership.
        ///
        /// PUN builds its own RegionHandler with the same port this probe was
        /// handed (LoadBalancingClient.cs:1527 passes
        /// ServerPortOverrides.MasterServerPort, which is exactly what Start
        /// gave us), so "the static still holds our value" cannot tell "nobody
        /// wrote after us" from "PUN wrote the identical value". In the second
        /// case the saved value is usually 0 — a ranked-only session never built
        /// a RegionHandler at all, which is the whole reason this catalog
        /// exists — and restoring it drops the port replacement out of PUN's
        /// NEXT SetRegions, since RegionHandler.cs:95 rewrites the address only
        /// while the static is non-zero. PUN would then ping Photon's stock
        /// port: the exact breakage this class was added to prevent.
        ///
        /// So the invariant to hold is not "our write is undone" but "the static
        /// carries the GAME's port" — which is what every reader of it wants. If
        /// it already does, leave it, whoever put it there; undo only a value
        /// that is no longer the game's.</summary>
        static void RestorePortOverride()
        {
            if (!portOverrideSaved) return;
            portOverrideSaved = false;
            try
            {
                ushort want = 0;
                try { want = PhotonNetwork.ServerPortOverrides.MasterServerPort; } catch { }
                if (want != 0 && RegionHandler.PortToPingOverride == want) return;
                if (RegionHandler.PortToPingOverride == probeWrotePortOverride)
                    RegionHandler.PortToPingOverride = savedPortOverride;
            }
            catch { }
        }

        static void Release()
        {
            var p = probe;
            probe = null;
            startedRt = -1f;
            teardownRt = -1f;
            RestorePortOverride();   // belt: Finish already ran, this is a no-op then
            try { p.LoadBalancingPeer.StopThread(); } catch { }
        }

        // ── helpers ──

        static bool GameIsOnNameServer(LoadBalancingClient c)
        {
            if (c.Server == ServerConnection.NameServer) return true;
            var s = c.State;
            return s == ClientState.ConnectingToNameServer
                || s == ClientState.ConnectedToNameServer
                || s == ClientState.Authenticating
                || s == ClientState.ConnectWithFallbackProtocol;
        }

        /// <summary>An attempt that produced nothing: arm the backoff.</summary>
        static void Consume(float rt)
        {
            int i = attempts - 1;
            if (i < 0) i = 0;
            if (i >= BACKOFF_S.Length) i = BACKOFF_S.Length - 1;
            nextAttemptRt = rt + BACKOFF_S[i];
        }

        static void Gate(float rt, string why)
        {
            if (why == gateLoggedWhy && gateLoggedRt >= 0f && rt - gateLoggedRt < GATE_LOG_S) return;
            gateLoggedWhy = why; gateLoggedRt = rt;
            Plugin.Log?.LogInfo($"[REGION-CATALOG] gated why={why}");
        }
    }
}
