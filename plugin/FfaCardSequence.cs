using System;
using System.Collections.Generic;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Same-card rule engine (ffa-configurable-lobbies §1a/§4c/§7e).
    ///
    /// THE SHARED UNIT IS THE PLAYER'S OWN DRAW INDEX, not the game's pick
    /// cycle: one global sequence S1,S2,S3,…; a player's k-th draw offers Sk
    /// WHENEVER it happens. The leader lags in the sequence (picks go to
    /// non-winners), trailing players run ahead. If you find yourself
    /// publishing a card list per pick CYCLE, you are building the wrong
    /// thing (the rejected per-cycle design).
    ///
    /// The generation constraint is OFFER-based, not ownership-based:
    /// "Phoenix appears at most once in the SEQUENCE", never "you can't be
    /// offered a card you own". Ownership depends on pick OUTCOMES, which are
    /// unknown at generation time — an ownership rule would destroy the
    /// pre-generation property entirely. DO NOT "improve" this.
    ///
    /// Determinism inputs that must agree on every client: the server-issued
    /// room name + master-published game index (the seed), the pool contents
    /// and ARRAY ORDER (hash-checked), the integer weights, the candidate
    /// count, the no-repeat set, and the PRNG. On any mismatch the client
    /// falls back to its private per-player roll — a mixed modlist degrades
    /// to today's behaviour with zero symptoms beyond one log line.
    ///
    /// TWO STREAMS (the §7e ⚠ box): this seeded engine runs ONLY when the
    /// same-card rule is ON. Rule OFF keeps the fully private, per-client
    /// UnityEngine.Random path in FfaMode.PickRandomCard — reproducibility
    /// must never leak into that path or the rule can never be switched off.
    ///
    /// Foreknowledge is ACCEPTED (Sid, 2026-08-01): the sequence is a pure
    /// function of (room, game index) and draw indexes are derivable from the
    /// scoreboard, so a modified client can precompute every upcoming hand.
    /// The closer, if ever abused, is a server-issued per-game nonce mixed
    /// into the seed (one field on the lobby poll payload).
    /// </summary>
    internal static class FfaCardSequence
    {
        // Room prop: "{game}:{seed}:{poolHash}". Seed is DERIVED (fnv of
        // room+game), so a master migration republish is idempotent — any
        // master computes the identical value and the prop can never fork.
        public const string SeqProp = "cr_ffa_seq";
        // Player prop (pre-join, #79 pattern): integer feature level. The
        // engine only runs when EVERY room member advertises >= FeatureLevel
        // (#273 — a master-only or latch-time-subset check goes stale on
        // routine master handoffs). The server's mod_version floor at lobby
        // Start is the real authority; this is the in-room belt-and-suspenders.
        public const string CapabilityProp = "cr_ffacfg";
        public const int FeatureLevel = 1;

        // ── deterministic PRNG (xorshift128 — integer-only, no UnityEngine.Random) ──
        private struct XorShift128
        {
            private uint x, y, z, w;
            public XorShift128(uint seed)
            {
                x = seed == 0 ? 2463534242u : seed;
                y = x * 1812433253u + 1;
                z = y * 1812433253u + 1;
                w = z * 1812433253u + 1;
                // warm up so near-zero seeds decorrelate
                for (int i = 0; i < 8; i++) Next8();
            }
            private uint Next8()
            {
                uint t = x ^ (x << 11);
                x = y; y = z; z = w;
                w = w ^ (w >> 19) ^ (t ^ (t >> 8));
                return w;
            }
            public uint Next() { return Next8(); }
            public int NextInt(int maxExclusive)
            {
                return maxExclusive <= 0 ? 0 : (int)(Next() % (uint)maxExclusive);
            }
        }

        private static uint Fnv1a(string s)
        {
            uint h = 2166136261u;
            if (s != null)
                for (int i = 0; i < s.Length; i++) { h ^= s[i]; h *= 16777619u; }
            return h;
        }

        // ── per-game state (reset via OnGameStart / OnRoomLeft) ──
        private static bool _active;
        private static int _latchedGame = -1;
        private static uint _seed;
        private static readonly List<string[]> _seq = new List<string[]>();
        private static XorShift128 _genRng;
        private static readonly HashSet<string> _usedNoRepeat = new HashSet<string>();
        // Local-only no-repeat memory for SUBSTITUTES (round-2 find 6): must
        // never touch _usedNoRepeat, which is shared fold-generation state.
        private static readonly HashSet<string> _usedLocalSubstitutes = new HashSet<string>();
        private static readonly Dictionary<int, int> _drawIndex = new Dictionary<int, int>();
        // pool snapshot (array-index order — never a Dictionary enumeration,
        // whose order is not guaranteed stable across runtimes)
        private static CardInfo[] _pool;
        private static int[] _poolWeights;
        private static HashSet<string> _noRepeat;
        private static int _candCount = 5;

        public static bool ActiveThisGame => _active;

        public static void PublishCapability()
        {
            try
            {
                var h = new ExitGames.Client.Photon.Hashtable();
                h[CapabilityProp] = FeatureLevel;
                PhotonNetwork.LocalPlayer?.SetCustomProperties(h);
            }
            catch { }
        }

        /// <summary>In-room republish carrying "level:poolHash" (Codex client
        /// review find 3): the pre-join advert can only carry the level (the
        /// card pool may not exist at the menu), and a hash checked only by
        /// the MISMATCHING client degrades that one seat while the rest run
        /// the shared sequence — deck divergence, not a fairness skew. With
        /// every seat advertising its own hash, ANY mixed-pool room fails the
        /// gate on EVERY client and the whole room falls back to private
        /// rolls uniformly. Called from OnGameStart (post-join, pool loaded).</summary>
        public static void PublishCapabilityWithHash()
        {
            try
            {
                uint hash = ComputePoolHash();
                if (hash == 0) return;   // pool not ready; the pre-join level advert stands
                var h = new ExitGames.Client.Photon.Hashtable();
                // Room-key stamp (round-2 find 3 / learning #182): player
                // props PERSIST ACROSS ROOMS, so a hash published in a
                // previous lobby would otherwise read as a valid (or falsely
                // mismatched) advert here. A value whose room key differs is
                // treated as NOT YET PUBLISHED for this room.
                h[CapabilityProp] = FeatureLevel + ":" + hash + ":" + RoomKey();
                PhotonNetwork.LocalPlayer?.SetCustomProperties(h);
            }
            catch { }
        }

        private static string RoomKey()
        {
            try { return (Fnv1a(PhotonNetwork.CurrentRoom?.Name ?? "") % 1000000u).ToString(); }
            catch { return "0"; }
        }

        public static void OnGameStart()
        {
            _active = false;
            _latchedGame = -1;
            _latchPendingSince = -1f;
            _seq.Clear();
            _usedNoRepeat.Clear();
            _usedLocalSubstitutes.Clear();
            _drawIndex.Clear();
            _pool = null; _poolWeights = null; _noRepeat = null;
        }

        public static void OnRoomLeft() { OnGameStart(); }

        /// <summary>Master: publish the per-game seed prop. Idempotent across
        /// master migrations because the seed is derived, not rolled. Called
        /// from OnGameStart (master) and re-asserted at each pick phase.</summary>
        public static void MasterPublishSeed(int game)
        {
            try
            {
                if (!PhotonNetwork.IsMasterClient || PhotonNetwork.CurrentRoom == null) return;
                if (!FfaMode.SameCardRule) return;
                string room = PhotonNetwork.CurrentRoom.Name ?? "";
                uint poolHash = ComputePoolHash();
                if (poolHash == 0) return;
                uint seed = Fnv1a(room + ":" + game) ^ (poolHash * 2654435761u);
                var h = new ExitGames.Client.Photon.Hashtable();
                h[SeqProp] = game + ":" + seed + ":" + poolHash;
                PhotonNetwork.CurrentRoom.SetCustomProperties(h);
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[FFA-SEQ] publish: " + ex.Message); }
        }

        /// <summary>Latch ONCE per game, at the FIRST pick phase (the prop has
        /// had the whole first round to propagate — room props are eventually
        /// consistent, never an activation barrier, #280). Accepted failure,
        /// documented per §3a: a client that still cannot validate here runs
        /// PRIVATE rolls for this entire game, invisibly — no desync (picks
        /// travel by name through the manifest), only a fairness skew on that
        /// one screen, and the log line names it.</summary>
        private static float _latchPendingSince = -1f;

        /// <summary>True once a VERDICT (shared or fallback) latched for this
        /// game — false while the latch is still pending-retryable. Lets the
        /// pick coroutine poll to a verdict before consuming offers (round-3
        /// find N7).</summary>
        public static bool IsLatchedFor(int game) => _latchedGame == game;

        public static void LatchForGame(int game)
        {
            if (_latchedGame == game) return;
            _active = false;
            try
            {
                if (!FfaMode.SameCardRule) { _latchedGame = game; return; }
                // RETRYABLE latch (round-2 find 3, timer bugs fixed per the
                // wave-2 verification): ONE shared pending budget for the
                // whole latch attempt — stamped at the FIRST pending
                // observation, cleared only when a verdict LATCHES. The old
                // shape reset the stamp between the capability and seed
                // checks (absence could pend forever) and latched permanent
                // fallback on a previous game's seed (a fresh publish one
                // frame later could never activate).
                bool pending()
                {
                    if (_latchPendingSince < 0f) _latchPendingSince = Time.realtimeSinceStartup;
                    return Time.realtimeSinceStartup - _latchPendingSince < 8f;
                }
                void latchFallback(string why)
                {
                    _latchPendingSince = -1f;
                    _latchedGame = game;
                    Plugin.Log.LogWarning($"[FFA-SEQ] same-card rule OFF this game — {why}");
                }
                int cap = RoomCapabilityState();
                if (cap == 0)
                {
                    if (pending()) return;   // not latched — next draw retries
                    latchFallback("capability adverts still pending after 8s");
                    return;
                }
                if (cap < 0) { latchFallback("room capability/hash disagreement"); return; }
                var room = PhotonNetwork.CurrentRoom;
                var raw = room?.CustomProperties != null && room.CustomProperties.ContainsKey(SeqProp)
                    ? room.CustomProperties[SeqProp] as string : null;
                if (string.IsNullOrEmpty(raw))
                {
                    // Seed prop is master-published at game start — same
                    // eventual consistency, same (shared) pending budget.
                    if (pending()) return;
                    latchFallback("seed prop absent after 8s");
                    return;
                }
                var parts = raw.Split(':');
                int propGame; uint seed, propHash;
                if (parts.Length != 3
                    || !int.TryParse(parts[0], out propGame) || !uint.TryParse(parts[1], out seed)
                    || !uint.TryParse(parts[2], out propHash))
                { latchFallback("malformed seed prop: " + raw); return; }
                if (propGame != game)
                {
                    // A PREVIOUS game's seed is a stale cache, not a verdict
                    // (wave-2 verification): the master's publish for THIS
                    // game is en route — pend, don't latch.
                    if (pending()) return;
                    latchFallback($"seed prop stuck on game {propGame} (local {game}) after 8s");
                    return;
                }
                if (!SnapshotPool())
                {
                    // Pool not readable yet (CardChoice not initialised) —
                    // same transient class as prop propagation.
                    if (pending()) return;
                    latchFallback("card pool unavailable after 8s");
                    return;
                }
                uint localHash = ComputePoolHash();
                if (localHash != propHash)
                {
                    _pool = null;
                    latchFallback($"pool hash mismatch (mine {localHash}, master {propHash}) — mixed modlist?");
                    return;
                }
                _latchPendingSince = -1f;
                _latchedGame = game;
                _seed = seed;
                _genRng = new XorShift128(seed);
                _usedNoRepeat.Clear();
                _seq.Clear();
                _candCount = Mathf.Clamp(FfaMode.CardCandidates, 1, 5);
                int players = 5;
                try { players = Mathf.Max(2, PhotonNetwork.CurrentRoom.PlayerCount); } catch { }
                // K = 4·(P−1)+6, floored at 16, capped at 64 (§7e); the fold
                // can EXTEND from its stored state, never restart.
                int k = Mathf.Clamp(4 * (players - 1) + 6, 16, 64);
                for (int i = 0; i < k; i++) _seq.Add(GenerateNextSet());
                _active = true;
                Plugin.Log.LogInfo($"[FFA-SEQ] shared sequence ACTIVE for game {game}: seed {seed}, {k} sets × {_candCount}, pool {_pool.Length}, no-repeat {_noRepeat.Count}");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[FFA-SEQ] latch failed — private rolls this game: " + ex.Message);
                _active = false;
            }
        }

        /// <summary>Tri-state room agreement (round-2 find 3): 1 = every seat
        /// advertises this room's key with a MATCHING hash and level; -1 =
        /// definitive disagreement (mismatched hash, level too low, or a
        /// non-upgradable legacy value); 0 = PENDING (some seat has not yet
        /// published for THIS room — retry, don't decide).</summary>
        private static int RoomCapabilityState()
        {
            try
            {
                if (PhotonNetwork.OfflineMode) return 1;
                var players = PhotonNetwork.PlayerList;
                if (players == null || players.Length == 0) return 0;
                uint myHash = ComputePoolHash();
                if (myHash == 0) return 0;
                string myRoomKey = RoomKey();
                foreach (var p in players)
                {
                    if (p == null) return 0;
                    var props = p.CustomProperties;
                    if (props == null || !props.ContainsKey(CapabilityProp)) return 0;
                    var rawVal = props[CapabilityProp];
                    string s = rawVal as string;
                    if (s == null) return 0;   // pre-join bare-level advert = no hash yet
                    var parts = s.Split(':');
                    // 2-part = a pre-room-key build; 3-part with a FOREIGN
                    // room key = a previous lobby's advert (#182). Both are
                    // "not published for this room yet" — pending, so a slow
                    // republisher gets its 8s rather than an instant verdict.
                    if (parts.Length != 3 || parts[2] != myRoomKey) return 0;
                    int lvl; uint theirHash;
                    if (!int.TryParse(parts[0], out lvl)
                        || !uint.TryParse(parts[1], out theirHash)) return -1;
                    if (lvl < FeatureLevel) return -1;
                    if (theirHash != myHash) return -1;
                }
                return 1;
            }
            catch { return 0; }
        }

        private static bool SnapshotPool()
        {
            var cards = CardChoice.instance != null ? CardChoice.instance.cards : null;
            if (cards == null || cards.Length == 0)
            {
                Plugin.Log.LogWarning("[FFA-SEQ] no card pool available at latch");
                return false;
            }
            var pool = new List<CardInfo>();
            foreach (var c in cards) if (c != null) pool.Add(c);   // array order preserved
            _pool = pool.ToArray();
            _poolWeights = new int[_pool.Length];
            _noRepeat = new HashSet<string>();
            for (int i = 0; i < _pool.Length; i++)
            {
                _poolWeights[i] = IntWeight(_pool[i]);
                // Runtime-derived no-repeat set (§7e decided: the engine's own
                // allowMultiple==false cards ARE the complete list, no curated
                // additions). Built from the live asset so every client derives
                // an identical set — a hardcoded list diverges on version skew.
                try { if (!_pool[i].allowMultiple) _noRepeat.Add(_pool[i].gameObject.name); }
                catch { }
            }
            return true;
        }

        private static int IntWeight(CardInfo c)
        {
            // INTEGER weights (10/4/1 — same ratios as FfaMode.RarityWeight):
            // an int total + int roll is bit-exact across clients by
            // construction; the float accumulator never was.
            try
            {
                switch (c.rarity)
                {
                    case CardInfo.Rarity.Common: return 10;
                    case CardInfo.Rarity.Uncommon: return 4;
                    case CardInfo.Rarity.Rare: return 1;
                }
            }
            catch { }
            return 4;
        }

        private static string[] GenerateNextSet()
        {
            // Rejection-resample AT THE SLOT — literally "the next random card
            // that lands there", globally identical for everyone (§1b: a
            // no-repeat card appears at most once in the ENTIRE sequence and
            // its replacement is global; there is no per-player substitution
            // at this layer).
            var set = new List<string>(_candCount);
            int total = 0;
            for (int i = 0; i < _poolWeights.Length; i++) total += _poolWeights[i];
            int guard = 0;
            while (set.Count < _candCount && guard++ < 512)
            {
                int roll = _genRng.NextInt(total);
                int idx = 0;
                for (; idx < _poolWeights.Length; idx++)
                {
                    roll -= _poolWeights[idx];
                    if (roll < 0) break;
                }
                if (idx >= _pool.Length) idx = _pool.Length - 1;
                string name = _pool[idx].gameObject.name;
                if (set.Contains(name)) continue;                       // no dup WITHIN a set
                if (_noRepeat.Contains(name) && _usedNoRepeat.Contains(name)) continue; // no dup ACROSS the game
                set.Add(name);
                if (_noRepeat.Contains(name)) _usedNoRepeat.Add(name);
            }
            return set.ToArray();
        }

        /// <summary>Every client calls this when a pick cycle's manifest
        /// resolves — the manifest IS the agreed offer event, so the index
        /// advances for every listed picker INCLUDING a crashed seat whose
        /// pick prop never lands (§4c.3 decided: consume-on-offer; if the
        /// index did not advance, that player would re-see Sk later and their
        /// draw k would differ from everyone else's — the invariant the whole
        /// feature exists for, broken by an edge case).</summary>
        public static void ConsumeOffers(List<int> pickerIds)
        {
            if (pickerIds == null) return;
            foreach (var pid in pickerIds)
            {
                int cur;
                _drawIndex.TryGetValue(pid, out cur);
                _drawIndex[pid] = cur + 1;
            }
        }

        /// <summary>The local picker's candidates for the draw its index was
        /// just consumed for. Returns false when the shared sequence is not
        /// active (caller falls back to the private roll). Applies the
        /// per-player TAIL SUBSTITUTION for blacklist/lockGun clashes — it
        /// reads only the local deck and candidates are never computed for
        /// other players (picks travel by name), so it cannot desync.</summary>
        public static bool TryGetCandidates(Player localPlayer, int count, List<CardInfo> outCandidates)
        {
            if (!_active || localPlayer == null || outCandidates == null) return false;
            try
            {
                int consumed;
                if (!_drawIndex.TryGetValue(localPlayer.PlayerID, out consumed) || consumed <= 0)
                {
                    Plugin.Log.LogWarning("[FFA-SEQ] TryGetCandidates before any offer was consumed — private roll");
                    return false;
                }
                int idx = consumed - 1;
                while (idx >= _seq.Count && _seq.Count < 256)
                    _seq.Add(GenerateNextSet());   // extend the fold, never restart it
                if (idx >= _seq.Count) return false;

                var byName = new Dictionary<string, CardInfo>();
                for (int i = 0; i < _pool.Length; i++) byName[_pool[i].gameObject.name] = _pool[i];

                var names = _seq[idx];
                var subRng = new XorShift128(_seed ^ (uint)(localPlayer.PlayerID * 2654435761u) ^ ((uint)idx * 40503u));
                int total = 0;
                for (int i = 0; i < _poolWeights.Length; i++) total += _poolWeights[i];

                // §1c: OPENING draws are identical for the whole lobby, NO
                // exceptions — the tail substitution must not run there even
                // when a draw-1 pick (Buckshot) blacklists a draw-2 card for
                // one player (Codex client review find 5). A blacklisted
                // offer in an opening hand is simply offered; picking it
                // applies mechanically fine — the blacklist is a draft-
                // variety rule, not an engine constraint.
                bool openingDraw = consumed <= FfaMode.InitialPicks;

                foreach (var nm in names)
                {
                    CardInfo card;
                    if (!byName.TryGetValue(nm, out card)) continue;
                    if (!openingDraw && !LocallyLegal(localPlayer, card, outCandidates))
                    {
                        // Deterministic per-player substitution: roll from the
                        // per-(player, draw) stream until a legal, non-duplicate
                        // card lands. Residual class is small — one Buckshot
                        // blacklist relationship + lockGunToDefault (§7e).
                        int guard = 0;
                        CardInfo sub = null;
                        while (guard++ < 512)
                        {
                            int roll = subRng.NextInt(total);
                            int pi = 0;
                            for (; pi < _poolWeights.Length; pi++)
                            {
                                roll -= _poolWeights[pi];
                                if (roll < 0) break;
                            }
                            if (pi >= _pool.Length) pi = _pool.Length - 1;
                            var cand = _pool[pi];
                            string cn = cand.gameObject.name;
                            bool inSet = false;
                            foreach (var o in outCandidates) if (o == cand) { inSet = true; break; }
                            if (inSet) continue;
                            bool namedInSet = false;
                            foreach (var n2 in names) if (n2 == cn) { namedInSet = true; break; }
                            if (namedInSet) continue;
                            if (_noRepeat.Contains(cn)
                                && (_usedNoRepeat.Contains(cn) || _usedLocalSubstitutes.Contains(cn))) continue;
                            if (!LocallyLegal(localPlayer, cand, outCandidates)) continue;
                            sub = cand; break;
                        }
                        if (sub != null)
                        {
                            outCandidates.Add(sub);
                            // Round-2 find 6: a no-repeat substitute must be
                            // remembered so THIS client never re-offers it —
                            // but in a SEPARATE, LOCAL-ONLY set. _usedNoRepeat
                            // feeds the shared deterministic fold, and a
                            // substitution is a local event (the substitute
                            // RNG includes player identity): writing it there
                            // diverges the fold state across clients and the
                            // "same" sequences silently split.
                            string subName = sub.gameObject.name;
                            if (_noRepeat.Contains(subName)) _usedLocalSubstitutes.Add(subName);
                        }
                        continue;
                    }
                    outCandidates.Add(card);
                }
                // Top up if substitutions failed outright (degenerate decks).
                return outCandidates.Count > 0;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[FFA-SEQ] TryGetCandidates: " + ex.Message);
                outCandidates.Clear();
                return false;
            }
        }

        /// <summary>Local legality WITHOUT the allowMultiple-own-copy rule:
        /// under global no-repeat an allowMultiple=false card structurally
        /// cannot be offered twice, so only the blacklist and lockGun clashes
        /// remain per-player. `categories` entries can be NULL in shipped
        /// prefabs (Scavenger, Shields up, Tactical reload — §7e incidental
        /// find), so every iteration null-checks.</summary>
        private static bool LocallyLegal(Player player, CardInfo candidate, List<CardInfo> already)
        {
            try
            {
                foreach (var o in already) if (o == candidate) return false;
                if (player?.data == null) return true;
                var holding = player.data.GetComponent<Holding>();
                var holdable = holding != null ? holding.holdable : null;
                if (holdable != null)
                {
                    var heldGun = holdable.GetComponent<Gun>();
                    var cardGun = candidate.GetComponent<Gun>();
                    if (cardGun != null && heldGun != null && cardGun.lockGunToDefault && heldGun.lockGunToDefault)
                        return false;
                }
                var current = player.data.currentCards;
                if (current != null)
                {
                    foreach (var have in current)
                    {
                        if (have == null) continue;
                        if (have.blacklistedCategories != null && candidate.categories != null)
                        {
                            foreach (var black in have.blacklistedCategories)
                            {
                                if (black == null) continue;
                                foreach (var cat in candidate.categories)
                                {
                                    if (cat == null) continue;
                                    if (cat == black) return false;
                                }
                            }
                        }
                    }
                }
                return true;
            }
            catch { return true; }
        }

        private static uint ComputePoolHash()
        {
            try
            {
                var cards = CardChoice.instance != null ? CardChoice.instance.cards : null;
                if (cards == null || cards.Length == 0) return 0;
                uint h = 2166136261u;
                int n = 0;
                foreach (var c in cards)
                {
                    if (c == null) continue;
                    n++;
                    string nm = c.gameObject.name;
                    for (int i = 0; i < nm.Length; i++) { h ^= nm[i]; h *= 16777619u; }
                    h ^= c.allowMultiple ? 1u : 2u; h *= 16777619u;
                    // Rarity drives the deterministic WEIGHTS (Codex client
                    // review find 4): a balance mod flipping one rarity
                    // changed the roll ranges while name/order/allowMultiple
                    // all still hashed equal — silent sequence divergence
                    // with every client logging "shared sequence ACTIVE".
                    h ^= (uint)(IntWeight(c) + 7); h *= 16777619u;
                }
                h ^= (uint)n; h *= 16777619u;
                return h == 0 ? 1u : h;
            }
            catch { return 0; }
        }
    }
}
