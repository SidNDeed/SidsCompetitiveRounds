using System;
using System.Collections.Generic;
using System.Globalization;

namespace CompetitiveRounds
{
    /// <summary>The game a 2v2 live-points post names (v1.41.0 beta review
    /// round 3, finding 1: the client half, round 4).
    ///
    /// The server files an ATTESTED post, one that carries game_number and
    /// photon_room_id signed with its pair, only under exactly the game it
    /// names, and it names a game by its own count: the games recorded on the
    /// series plus one, in the room the series row stores (main.py,
    /// _team_game_identity and _record_team_game_points). So a post naming the
    /// game the server is in is evidence for that game, and a post the server
    /// processes after it has moved on is filed nowhere, however late it
    /// lands. That holds only while the number a post carries is never AHEAD
    /// of the server's count: a post from game N naming N+1 is filed under
    /// N+1 as soon as the server gets there, which is review finding 1's false
    /// positive over again.
    ///
    /// So the number is the server's own count, never a free-running one. At
    /// every game start in a cr_ff room (GameStateWatcher.OnMatchStarted, the
    /// event that also resets the pair the post carries) it is frozen as the
    /// recorded games of THIS series, the highest any read of
    /// team/series/{id}/state has shown, plus one. Every read counted was
    /// answered before this game started, and the server only ever adds to
    /// that count (main.py's two writers of t1_series_wins/t2_series_wins each
    /// add one game), so the frozen number is at most the game the server was
    /// in when this game started, and a post naming it is filed only if the
    /// server is still in that game when the post is processed. A stale read
    /// names a LOWER number, and then this game's posts are filed nowhere,
    /// which after the first game of a sitting settles exactly as a post
    /// without the pair does (neither counts). After every 2v2 game over
    /// ApiClient.RefreshTeamGameRecord reads the count again, so the next
    /// game starts from a fresh one.
    ///
    /// The client's own count of game starts, in FFA's gameNumber shape
    /// (advanced at each game start, restarted when the series or the room
    /// changes, cleared when the room is left), is kept for one thing only:
    /// the one case where a number is safe without any read: a series' FIRST
    /// game start in a room is named 1. No
    /// game number is lower, so 1 is never ahead of the server; in a sitting
    /// resumed at a later game it is behind, and that game's posts are filed
    /// nowhere. With no read and a later game start the post goes without the
    /// pair. An unverified count is exactly the one that runs ahead of the
    /// server, after the first game the server does not record.
    ///
    /// The number is the server's count, and a count is not a physical game
    /// (v1.41.0 beta review round 4, finding F25; round 5): while a game's
    /// report is still on its way to the server, the next game freezes the
    /// same number and the two games' posts are filed in one record. So a post
    /// that names its game also carries the physical game's TOKEN, and so does
    /// the DC report. The room's host publishes a fresh token as a room
    /// property in the first round of each game, and every seat takes the
    /// value the room holds; see "The physical game's token" below.
    ///
    /// A token is one physical game's only while every seat that carries it
    /// is in that game (v1.41.0 beta review round 5, findings F27 and F28;
    /// round 6). So the token names the ORDINAL of the physical game it was
    /// published for and an EPOCH the host raises at each publish. The
    /// ordinal is never taken from a count (round 7, finding F29), and its
    /// origin never from this seat's own reading of the series (round 8,
    /// finding F31): a seat holds one only once a publish it took grounds it
    /// or, for the series' physical game 1, once the server issued that game
    /// to it as the series' reporter (AskFirstGame, OnFirstGame); it then adds
    /// one at every game start the game itself reports and loses it at any
    /// other, and at every join.
    /// A seat takes a token only for the physical game it holds and the game
    /// its posts name; the game's own game over and next game start on this
    /// seat end it (round 7, finding F30: GM_ArmsRace's lifecycle, which
    /// changes this seat's scoreboard in the same step, so no reading of
    /// another game comes first), and no time or score carries it past
    /// either; a post or a DC report carries it only while the game's
    /// lifecycle hooks are attached and this seat's reading of the score,
    /// made when the post or the report is built, still shows that game;
    /// and the server reads it only for the game its recorded games say is
    /// in progress, in the series' original sitting. Each of those rules
    /// withholds a token; none grants one.
    ///
    /// Nothing here touches Photon or Unity. The sentinel below runs the same
    /// Tracker class the game runs, in the game through the [Broadcast]
    /// TestTeamGameNumberSentinel lever and outside it from this file.</summary>
    internal static class TeamGameNumber
    {
        internal const string SentinelTag = "[TEAM-GAME-NUMBER-SENTINEL]";
        internal const string LogTag = "[2V2-GAME]";

        /// <summary>The server's bounds on the pair (update_team_live_points:
        /// game_number Query(ge=1, le=99), photon_room_id Query(max_length=128)).
        /// A value outside them would get the whole request refused, the points
        /// included, so such a post goes without the pair instead.</summary>
        internal const int MaxGameNumber = 99;
        internal const int MaxRoomLength = 128;

        /// <summary>The seat's own tracker, fed by GameStateWatcher and
        /// ApiClient. The sentinel builds its own and never touches this one.</summary>
        internal static readonly Tracker Live = new Tracker();

        private static string Num(int v) { return v.ToString(CultureInfo.InvariantCulture); }

        /// <summary>What a post WITHOUT the pair signs (update_team_live_points).</summary>
        internal static string LegacyCanonical(string seriesId, string reporterSteamId, int t1Points, int t2Points)
        {
            return "team-live-points:" + seriesId + ":" + reporterSteamId + ":" + Num(t1Points) + ":" + Num(t2Points);
        }

        /// <summary>What a post WITH the pair signs, exactly as the server builds
        /// it: series, reporter, t1, t2, game number, room, the room unescaped.</summary>
        internal static string AttestedCanonical(string seriesId, string reporterSteamId, int t1Points, int t2Points,
                                                 int gameNumber, string photonRoomId)
        {
            return "team-live-points-game:" + seriesId + ":" + reporterSteamId + ":" + Num(t1Points) + ":" + Num(t2Points)
                   + ":" + Num(gameNumber) + ":" + photonRoomId;
        }

        /// <summary>The two query parameters, both or neither: the caller passes
        /// the room already URL-escaped.</summary>
        internal static string QueryPair(int gameNumber, string escapedRoom)
        {
            return "&game_number=" + Num(gameNumber) + "&photon_room_id=" + escapedRoom;
        }

        /// <summary>A room this client names: non-empty, within the server's
        /// length bound, and without outer white space (the server signs the
        /// room as sent but compares it stripped).</summary>
        internal static bool RoomSendable(string photonRoomId)
        {
            if (string.IsNullOrEmpty(photonRoomId) || photonRoomId.Length > MaxRoomLength) return false;
            return photonRoomId.Trim().Length == photonRoomId.Length;
        }

        /// <summary>Whether a post can carry the pair: a number the server
        /// accepts and a room it accepts. Otherwise it goes without the pair.</summary>
        internal static bool Sendable(int gameNumber, string photonRoomId)
        {
            return gameNumber >= 1 && gameNumber <= MaxGameNumber && RoomSendable(photonRoomId);
        }

        // The contract pin. backend/tests/test_team_series_report_dc.py reads
        // these four literals, signs PinExpected and asks the server's own
        // signature check to accept it for these inputs (t1 2, t2 1, game 3);
        // the sentinel checks that AttestedCanonical builds PinExpected.
        internal const string PinSeries = "5b0c7e1a-2d3f-4a5b-8c6d-7e8f9a0b1c2d";
        internal const string PinReporter = "90000000000700009";
        internal const string PinRoom = "team_pin_room";
        internal const string PinExpected =
            "team-live-points-game:5b0c7e1a-2d3f-4a5b-8c6d-7e8f9a0b1c2d:90000000000700009:2:1:3:team_pin_room";

        // ---- The physical game's token (round 5, finding F25; round 6,
        // findings F27 and F28; round 7, finding F29) ------------------------
        //
        // At each game start in a cr_ff room the room's host publishes a token
        // as the room property TokenRoomKey
        // (GameStateWatcher.TryPublishTeamToken). A token has three parts,
        // joined by ':' (MakeToken): a fresh NONCE (16 random lowercase hex
        // digits), the ORDINAL of the physical game it is published for, and
        // the host's EPOCH. The epoch is one above the highest the host has
        // read in the room or published, so a later publish carries a higher
        // one. A post and a DC report sign all three. Every seat, the host
        // included, takes the value the room itself holds: a client sees its
        // own room-property write only when the server's echo of it arrives
        // (#428), so until then the host's posts go without a token like every
        // other seat's, and a send that never reached the room is never used.
        //
        // Which physical game (round 7, finding F29; round 8, finding F31).
        // The ordinal is never taken from a count: the series' recorded games
        // lag the physical game whenever a result is still on its way, and
        // every seat that read the same count would agree on the same wrong
        // game. Nor is its origin taken from absence: a read showing no
        // recorded game, no relock and no pair of two points on the series'
        // record does not rule out an earlier game whose posts all failed
        // while its result waits in the reporter's outbox (F31). A seat holds
        // an ordinal (Tracker.PhysicalOrdinal) only once one of two things
        // grounds it: a publish it took (ObserveRoomToken), or the server's
        // issue of the series' physical game 1 to this seat as the series'
        // reporter (Tracker.AskFirstGame and OnFirstGame; main.py,
        // team_series_first_game: once per series, only while nothing of the
        // series is recorded, only on a Steam session issued before the series
        // was created, so only to a process that was there when the series
        // began, and (round 9, finding M1) only while no other session of the
        // reporter's account was live since the series was created and nothing
        // is on the series' live-points record, so to ONE process of the
        // account, whose session the server keeps: a match report sent on
        // another session voids the issue, and a DC report the reporter's
        // account sends on another session reads no token; asked only while
        // this seat's client has sent and queued no report of the series).
        // Physical game 1's token
        // carries the issued nonce, and the seat it was issued to publishes it
        // in the game's first round whether or not it is the room's host;
        // every later game's host DERIVES its nonce from the whole issued
        // nonce (the ROOT, learned from the issue or from physical game 1's
        // token) and the token's own ordinal and epoch (round 9, finding M2:
        // ChainNonce; main.py, _team_game_chain_nonce), and the server reads a
        // token only when its nonce is exactly the one derived. Round 8 drew
        // it as the issued nonce's first 8 digits and 8 fresh ones and read a
        // token by those 8 digits alone. A later token does not reveal the
        // root, so a seat that saw neither the issue nor physical game 1's
        // token publishes nothing as the host (WhyNoAnchor).
        // It then adds one at every game start the game itself reported
        // (GM_ArmsRace.DoStartGame, exactly
        // one since its last game start: TeamGameLifecycle), and loses it at
        // any other game start, at a missed game boundary and at every join
        // (a rejoin of the same room included: Tracker.NoteRoomJoined). A seat
        // holding none publishes nothing and carries nothing until a publish
        // grounds it again. So a new host after a master change inside
        // the room continues from the ordinal it holds and the epochs the room
        // holds, and after a room change no seat holds one: the new room's
        // host publishes nothing for the rest of the series' sitting there.
        //
        // A seat takes (adopts) a value it reads during a game only when
        //   - the game itself reported this seat's game start (round 7, F29);
        //   - the value names the physical game this seat holds, when it holds
        //     one (round 6, F27: a seat a game ahead of a lagging host does not
        //     take the host's token as its own game's), and the number its
        //     posts name (For: the server's count, which only ever withholds
        //     here, so a queued result leaves the game tokenless);
        //   - its epoch is above the epoch of every value stale for this seat,
        //     so a value published before one this seat already holds as an
        //     earlier game's is refused even when this seat never read it;
        //   - its nonce is not stale. Stale are the first value read in the
        //     room (it may belong to a game this seat did not see start), every
        //     value read during an earlier game, the value the room held at
        //     each game over, and (round 7, F29) every value read outside this
        //     seat's game before the game itself started its next game.
        // A different value read while one is taken ends it for the rest of
        // the game (round 6, F28: the next game's publish, or a second
        // publisher). So does (round 7, finding F30) the game's own game over
        // or next game start on this seat (GM_ArmsRace.GameOverTransition and
        // DoStartGame, TeamGameLifecycle: Tracker.OnGmGameOver and OnGmStart),
        // whatever this seat's watcher saw of them: the game changes this
        // seat's scoreboard to another game's only in the same step that
        // calls them, so no reading of the next game precedes them. After
        // either, this seat carries nothing until its next game start takes
        // a fresh publish for that game. No time is read anywhere: no gap in
        // the readings, short or long, ends a token or keeps one. A post or a
        // DC report carries the taken value only while both hooks are
        // attached (TeamGameLifecycle.HooksLive: without them no seat carries
        // one), while the room still holds it, and while this seat's own
        // reading of the score, taken when the post or the report is built,
        // still shows the game the value was taken in (Tracker.TokenFor): a
        // game over, a fall of the rounds, or a 0-0 with no points each
        // withhold it, whether or not a game over or a game start reached
        // this seat's watcher. The server settles a
        // lead-forfeit only from posts that carried the DC report's token,
        // when that token names the game being settled (the series' recorded
        // games plus one: with the ordinal no longer taken from that count,
        // a token naming the physical game while a lower result is still on
        // its way names a later game, and nothing is read), is its record's
        // own, no post filed there carried another token or one naming another
        // game, it is on no other record of the series, and the series is in
        // its original sitting (main.py, _team_game_token_seats). A missing
        // token only ever withholds that settlement.

        /// <summary>The room property the host publishes the token in.</summary>
        internal const string TokenRoomKey = "cr_tg_token";

        /// <summary>Why a seat does not publish (Tracker.TokenToPublish).
        /// Only WhyNotHost (a host handoff) and WhyFirstGamePending (round 8,
        /// F31: the series' reporter waits for the server's answer on physical
        /// game 1) can change inside the game's first round, so
        /// GameStateWatcher retries on those two and on nothing else.</summary>
        internal const string WhyNoGame = "no game is in progress";
        internal const string WhyMissed = "this seat missed a game boundary";
        internal const string WhyNoOrdinal = "this seat holds no physical-game ordinal for this game";
        internal const string WhyFirstGamePending = "this seat waits for the server's answer on the series' physical game 1";
        internal const string WhyTaken = "this game's token is already in the room";
        internal const string WhyPublished = "this seat already published this game's token";
        internal const string WhyLate = "the game's first round is over";
        internal const string WhyNotHost = "this seat is not the room's host";
        internal const string WhyEpoch = "the room's epoch is at its bound";
        internal const string WhyNoAnchor = "this seat holds no issued physical game 1 to derive its nonce from";
        internal const string WhyChainTaken = "the nonce derived for this game is one this seat already read or holds as stale";

        /// <summary>The highest epoch a token carries (nine digits).</summary>
        internal const long MaxEpoch = 999999999;

        /// <summary>Round 7, finding F30: why a post or a DC report carries no
        /// token when the game's lifecycle hooks are not both attached
        /// (TokenFor's `hooksLive`, TeamGameLifecycle.HooksLive). Round 6's
        /// bound on the time between readings is gone: no time is read (#771:
        /// a time bound is only as good as the honest receipt bound).</summary>
        internal const string WhyNoHooks = "the game's lifecycle hooks are not attached";

        /// <summary>The scoreboard as a seat reads it (round 6, finding F28):
        /// both sides' rounds and points and the rounds a game is won at (0 =
        /// not known). Read false: it could not be read (the fields are not
        /// resolved, or the room's messages are held), and nothing that reads
        /// it carries a token. It carries no time (round 7, finding
        /// F30).</summary>
        internal struct Score
        {
            public bool Read;
            public int R1, R2, P1, P2, RoundsToWin;

            internal static Score Of(int r1, int r2, int p1, int p2, int roundsToWin)
            {
                return new Score { Read = true, R1 = r1, R2 = r2, P1 = p1, P2 = p2, RoundsToWin = roundsToWin };
            }

            internal bool AllZero { get { return R1 == 0 && R2 == 0 && P1 == 0 && P2 == 0; } }

            internal bool Over { get { return RoundsToWin > 0 && (R1 >= RoundsToWin || R2 >= RoundsToWin); } }

            public override string ToString()
            {
                return Read ? "rounds " + Num(R1) + "-" + Num(R2) + ", points " + Num(P1) + "-" + Num(P2) : "unread";
            }
        }

        /// <summary>A nonce: 16 lowercase hex digits, the part of a token the
        /// server keeps (main.py _TEAM_GAME_TOKEN_RE; migration 354's CHECK).</summary>
        internal static bool NonceValid(string nonce)
        {
            if (nonce == null || nonce.Length != 16) return false;
            foreach (char c in nonce)
                if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
            return true;
        }

        // A decimal without a sign or a leading zero, at most `digits` long.
        private static bool Decimal(string s, int digits, out long v)
        {
            v = 0;
            if (string.IsNullOrEmpty(s) || s.Length > digits || s[0] == '0') return false;
            foreach (char c in s)
            {
                if (c < '0' || c > '9') return false;
                v = v * 10 + (c - '0');
            }
            return true;
        }

        /// <summary>A token's three parts: "nonce:ordinal:epoch", the nonce 16
        /// lowercase hex digits, the ordinal 1..MaxGameNumber and the epoch
        /// 1..MaxEpoch, both without a sign or a leading zero. The server
        /// parses the same shape (main.py _TEAM_GAME_WIRE_TOKEN_RE).</summary>
        internal static bool TryParseToken(string token, out string nonce, out int ordinal, out long epoch)
        {
            nonce = "";
            ordinal = 0;
            epoch = 0;
            if (token == null) return false;
            string[] parts = token.Split(':');
            long o, e;
            if (parts.Length != 3 || !NonceValid(parts[0]) || !Decimal(parts[1], 2, out o) || !Decimal(parts[2], 9, out e))
                return false;
            nonce = parts[0];
            ordinal = (int)o;
            epoch = e;
            return true;
        }

        /// <summary>A token as the room holds it and a post or a DC report
        /// sends it (TryParseToken).</summary>
        internal static bool TokenValid(string token)
        {
            string n;
            int o;
            long e;
            return TryParseToken(token, out n, out o, out e);
        }

        /// <summary>The token for a nonce, a physical game's ordinal and an epoch.</summary>
        internal static string MakeToken(string nonce, int ordinal, long epoch)
        {
            return nonce + ":" + Num(ordinal) + ":" + epoch.ToString(CultureInfo.InvariantCulture);
        }

        /// <summary>A token's nonce, "" when it is not a token.</summary>
        internal static string NonceOf(string token)
        {
            string n;
            int o;
            long e;
            return TryParseToken(token, out n, out o, out e) ? n : "";
        }

        /// <summary>A fresh nonce: the first 8 bytes of a new Guid (60 random
        /// bits) as 16 lowercase hex digits. It names a physical game; it is
        /// not a secret (every seat in the room reads it).</summary>
        internal static string DrawNonce()
        {
            byte[] b = Guid.NewGuid().ToByteArray();
            var sb = new System.Text.StringBuilder(16);
            for (int i = 0; i < 8; i++) sb.Append(b[i].ToString("x2", CultureInfo.InvariantCulture));
            return sb.ToString();
        }

        /// <summary>Round 9, finding M2: the nonce physical game `ordinal`'s
        /// token carries when published with `epoch`, counted from the series'
        /// issued physical game 1 (`root`, its 16 lowercase hex digits): the
        /// root itself for game 1, else the first 16 hex digits of HMAC-SHA256
        /// keyed by the root's 16 ASCII digits over
        /// "team-game-chain:{ordinal}:{epoch}", both in decimal as the wire
        /// carries them (main.py, _team_game_chain_nonce, computes the same).
        /// "" when the root is not a nonce or the ordinal or the epoch is out
        /// of the token's range.</summary>
        internal static string ChainNonce(string root, int ordinal, long epoch)
        {
            if (!NonceValid(root) || ordinal < 1 || ordinal > MaxGameNumber || epoch < 1 || epoch > MaxEpoch) return "";
            if (ordinal == 1) return root;
            byte[] key = System.Text.Encoding.ASCII.GetBytes(root);
            byte[] msg = System.Text.Encoding.ASCII.GetBytes(ChainPrefix + ordinal.ToString(CultureInfo.InvariantCulture)
                                                             + ":" + epoch.ToString(CultureInfo.InvariantCulture));
            byte[] mac;
            using (var hm = new System.Security.Cryptography.HMACSHA256(key)) mac = hm.ComputeHash(msg);
            var sb = new System.Text.StringBuilder(16);
            for (int i = 0; i < 8; i++) sb.Append(mac[i].ToString("x2", CultureInfo.InvariantCulture));
            return sb.ToString();
        }

        /// <summary>Round 9, finding M2: the derivation's message prefix, and
        /// its pin vector: ChainNonce(PinChainRoot, PinChainOrdinal,
        /// PinChainEpoch) is PinChainExpected on this client and on the server
        /// (the sentinel checks it here, and
        /// backend/tests/test_team_series_report_dc.py checks the same four
        /// values against main._team_game_chain_nonce).</summary>
        internal const string ChainPrefix = "team-game-chain:";
        internal const string PinChainRoot = "0123456789abcdef";
        internal const int PinChainOrdinal = 2;
        internal const long PinChainEpoch = 7;
        internal const string PinChainExpected = "4f9833dd5e56800d";

        /// <summary>A nonce as a log line shows it: its first 8 digits (display
        /// only: nothing compares them).</summary>
        internal static string ShortNonce(string nonce)
        {
            if (nonce == null) return "";
            return nonce.Length > 8 ? nonce.Substring(0, 8) : nonce;
        }

        /// <summary>A token as a log line names it: the nonce's first 8 digits,
        /// its game and its epoch.</summary>
        internal static string Describe(string token)
        {
            string n;
            int o;
            long e;
            if (!TryParseToken(token, out n, out o, out e)) return "(none)";
            return ShortNonce(n) + " (game " + Num(o) + ", epoch " + e.ToString(CultureInfo.InvariantCulture) + ")";
        }

        /// <summary>What a post carrying a token signs for it, apart from the
        /// pair's own signature (update_team_live_points, token_sig): series,
        /// reporter, t1, t2, game number, room (unescaped), token. The token is
        /// all three of its parts, so its ordinal and its epoch are signed.</summary>
        internal static string TokenCanonical(string seriesId, string reporterSteamId, int t1Points, int t2Points,
                                              int gameNumber, string photonRoomId, string token)
        {
            return "team-live-points-token:" + seriesId + ":" + reporterSteamId + ":" + Num(t1Points) + ":"
                   + Num(t2Points) + ":" + Num(gameNumber) + ":" + photonRoomId + ":" + token;
        }

        /// <summary>What a DC report carrying a token signs for it
        /// (team_series_report_dc, token_sig), the token's three parts
        /// included. The report's own hmac_sig and its canonical are
        /// unchanged.</summary>
        internal static string DcTokenCanonical(string reporterSteamId, string seriesId, string dcPlayerSteamId,
                                                string token)
        {
            return "team-dc-token:" + reporterSteamId + ":" + seriesId + ":" + dcPlayerSteamId + ":" + token;
        }

        /// <summary>The two token parameters, both or neither.</summary>
        internal static string QueryToken(string token, string tokenSig)
        {
            return "&game_token=" + token + "&token_sig=" + tokenSig;
        }

        /// <summary>Round 8, finding F31: what the series' reporter signs when
        /// it asks the server for the series' physical game 1
        /// (team_series_first_game): series, requester, room (unescaped).</summary>
        internal static string FirstGameCanonical(string seriesId, string requesterSteamId, string photonRoomId)
        {
            return "team-first-game:" + seriesId + ":" + requesterSteamId + ":" + photonRoomId;
        }

        /// <summary>Round 8, finding F31: the ask's three query parameters, the
        /// room already URL-escaped by the caller.</summary>
        internal static string QueryFirstGame(string requesterSteamId, string escapedRoom, string sig)
        {
            return "?requester_steam_id=" + requesterSteamId + "&photon_room_id=" + escapedRoom + "&sig=" + sig;
        }

        /// <summary>Round 8, finding F31: a series id the client's report
        /// ledger (ApiClient.cs, CompetitiveRounds.team-reports-sent.txt) can
        /// hold on one line: the server's UUIDs, hex digits and dashes, at
        /// most 64 characters.</summary>
        internal static bool LedgerKey(string seriesId)
        {
            if (string.IsNullOrEmpty(seriesId) || seriesId.Length > 64) return false;
            foreach (char c in seriesId)
                if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F') || c == '-'))
                    return false;
            return true;
        }

        /// <summary>Round 8, finding F31: the ledger's line for a match report
        /// of the series handed to the network.</summary>
        internal static string LedgerSent(string seriesId)
        {
            return "sent " + seriesId;
        }

        /// <summary>Round 8, finding F31; round 9, finding M2: the ledger's
        /// line for the series' issued physical game 1, by its whole nonce
        /// (the anchor every match report of the series carries). Round 8
        /// wrote "anchor <series> <the first 8 digits>"; such a line no longer
        /// parses (ParseLedgerLine), so the series' reports carry no anchor and
        /// the server voids the issue.</summary>
        internal static string LedgerIssued(string seriesId, string nonce)
        {
            return "issued " + seriesId + " " + nonce;
        }

        /// <summary>Round 8, finding F31: reads one ledger line, "sent
        /// <series>" or (round 9, finding M2) "issued <series> <16 hex>"
        /// (`anchorLine` says which; `anchor` is "" for a sent line). False
        /// for anything else: a line an interrupted append tore, which the
        /// ledger skips, and a round-8 client's "anchor <series> <8 hex>".</summary>
        internal static bool ParseLedgerLine(string line, out bool anchorLine, out string seriesId, out string anchor)
        {
            anchorLine = false;
            seriesId = "";
            anchor = "";
            string[] f = (line ?? "").Trim().Split(' ');
            if (f.Length == 2 && f[0] == "sent" && LedgerKey(f[1]))
            {
                seriesId = f[1];
                return true;
            }
            if (f.Length == 3 && f[0] == "issued" && LedgerKey(f[1]) && NonceValid(f[2]))
            {
                anchorLine = true;
                seriesId = f[1];
                anchor = f[2];
                return true;
            }
            return false;
        }

        /// <summary>Round 8, finding F31: whether a report in the client's
        /// outbox (`url`, `json`) is a match report of `seriesId`: a team match
        /// report whose body names the series (ApiClient.ReportTeamMatch writes
        /// "series_id" first). A team report with no body counts as one of
        /// every series.</summary>
        internal static bool QueuedReportOf(string url, string json, string seriesId)
        {
            if (url == null || !url.EndsWith("/api/v1/team/matches", StringComparison.Ordinal)) return false;
            if (json == null) return true;
            return json.IndexOf("\"series_id\":\"" + (seriesId ?? "") + "\"", StringComparison.Ordinal) >= 0;
        }

        // The token's contract pin, read by the same backend test as the pin
        // above: it signs PinTokenExpected and PinDcTokenExpected and asks the
        // server's own token checks to accept PinToken for these inputs (the
        // post: t1 2, t2 1, game 3, PinRoom; the DC report: PinDcPlayer); the
        // sentinel checks that TokenCanonical and DcTokenCanonical build them.
        // PinToken names game 3, the post's own game, at epoch 7.
        internal const string PinToken = "0123456789abcdef:3:7";
        internal const string PinDcPlayer = "90000000000700008";
        internal const string PinTokenExpected =
            "team-live-points-token:5b0c7e1a-2d3f-4a5b-8c6d-7e8f9a0b1c2d:90000000000700009:2:1:3:team_pin_room:0123456789abcdef:3:7";
        internal const string PinDcTokenExpected =
            "team-dc-token:90000000000700009:5b0c7e1a-2d3f-4a5b-8c6d-7e8f9a0b1c2d:90000000000700008:0123456789abcdef:3:7";
        // Round 8, finding F31: the first-game ask's canonical for PinSeries,
        // PinReporter and PinRoom (the same backend test signs it and asks the
        // route's own signature check to accept it).
        internal const string PinFirstGameExpected =
            "team-first-game:5b0c7e1a-2d3f-4a5b-8c6d-7e8f9a0b1c2d:90000000000700009:team_pin_room";

        /// <summary>Round 6, finding F28: whether `s` can follow `last` inside
        /// one game. Inside a game the rounds only rise, and while neither
        /// side's rounds change the points only rise: a point's end sets the
        /// score in one RPC, raising one side's rounds and resetting both
        /// points together when it ends the round (vanilla RPCA_NextRound, as
        /// SpectatorPatches mirrors it). A game's reset takes the rounds and
        /// the points to 0-0, which follows nothing but 0-0.</summary>
        internal static bool Follows(Score last, Score s)
        {
            if (s.R1 < last.R1 || s.R2 < last.R2) return false;
            if (s.R1 == last.R1 && s.R2 == last.R2) return s.P1 >= last.P1 && s.P2 >= last.P2;
            return true;
        }

        internal sealed class Tracker
        {
            // Recorded games per series: the highest any read showed. A seat
            // plays one series at a time; a few entries cover a late answer for
            // the one before, and a full map is simply dropped (a lost read costs
            // a number, never a wrong one).
            private const int MaxSeries = 8;
            private readonly Dictionary<string, int> recorded = new Dictionary<string, int>(StringComparer.Ordinal);
            // Series whose server refused the attested form (ApiClient's 403
            // fallback): their posts go without the pair from then on.
            private readonly HashSet<string> refused = new HashSet<string>(StringComparer.Ordinal);
            // The game frozen at the last game start; 0 = no number.
            private string gameSeries = "", gameRoom = "";
            private int gameNumber;
            // Round 7, finding F29: the physical game's ordinal, from a host's
            // publish only ("Which physical game" above ObserveRoomToken).
            // `chainSeries` and `chainRoom` are the series and the room it is
            // held for; `roomStarts` counts this seat's game starts there.
            // `chain` is the ordinal of this seat's game in progress (or last
            // game), 0 = none: this seat was never grounded in this room, or it
            // lost the chain at a game boundary it did not see. `witnessed`:
            // this game start was matched by exactly one start of the game
            // itself (OnGmStart) since this seat's last game start in the room.
            private string chainSeries = "", chainRoom = "";
            private int roomStarts, chain;
            private bool witnessed;
            // Round 8, finding F31: physical game 1 is issued by the server to
            // the series' reporter (AskFirstGame, OnFirstGame). `gameGen`
            // counts this seat's game starts and room changes, so an answer is
            // applied only to the game it was asked from; `askGen` is the game
            // an ask is out for (0 = none) and `askedGen` the last game an ask
            // was made in (one per game). `firstNonce`: the issued nonce, while
            // this seat holds physical game 1 by the server's issue (its token
            // carries it, and this seat publishes it, host or not). Round 9,
            // finding M2: `root` is the whole issued nonce of series
            // `rootSeries`, from the issue or from physical game 1's token (a
            // later token does not reveal it, and one that is not the nonce
            // derived from a root held drops that root); a host derives every
            // later game's nonce from it (ChainNonce). A join keeps it: the
            // ordinal is still lost, and only a publish taken grounds it again.
            private int gameGen, askGen, askedGen;
            private string firstNonce = "", root = "", rootSeries = "";
            // Round 7, F29: the game's own starts on this seat
            // (GM_ArmsRace.DoStartGame, TeamGameLifecycle) in `gmRoom`, and how
            // many of them this seat's game starts have accounted for.
            private string gmRoom = "";
            private int gmStarts, gmSeen;
            // Round 7, F29: what reads showed of each series' sitting. `sitting`
            // holds flags, and a flag once read is never forgotten:
            // SittingKnown, a read carried the sitting; SittingRelocked, it
            // showed the series relocked; SittingPlayed, it showed a live-points
            // pair of two points or more on the series' record (any seat, any
            // sitting). Since round 8 (F31) they name no game: they only save
            // the series' reporter an ask the server would refuse
            // (AskFirstGame).
            private const int SittingKnown = 1, SittingRelocked = 2, SittingPlayed = 4;
            private readonly Dictionary<string, int> sitting = new Dictionary<string, int>(StringComparer.Ordinal);
            // The physical game's token (round 5, finding F25; round 6). The
            // stale NONCES, oldest first: the first value this seat read in the
            // room, every value it read during an earlier game, and the value
            // the room held at each of its game overs, but a value naming a
            // later game than the one that ended (#182: its host started
            // first). A published nonce is fresh (60 random bits, none its
            // publisher holds), so only the last few can still be in the room,
            // and the list is bounded. `epochStale` is the highest epoch of a
            // stale value, `epochRead` the highest read in the room, and
            // `epochPublished` the highest this seat published.
            private const int MaxTokens = 16;
            private readonly List<string> stale = new List<string>();
            // Values read during the game in progress (whole tokens).
            private readonly List<string> seen = new List<string>();
            private string tokenRoom = "";     // the room those values were read in
            private string adopted = "";       // the token of the game in progress, "" = none
            private int adoptedOrdinal;        // the game it names (this seat's own when taken)
            private bool took;                 // a token was taken in the game in progress
            private bool inGame;               // from a game start to its game over
            private bool overSeen;             // the game in progress ended: the game's own game over or start (F30), or the score
            private bool boundaryMissed;       // a game boundary this seat did not see: no token until the next start
            private bool withdrawn;            // the game's token was withdrawn: none for the rest of the game
            private bool published;            // this seat's publish for the game in progress was sent
            private string noted = "";         // the last value logged (each is logged once)
            private long epochRead, epochStale, epochPublished;
            // Round 6, finding F28: this seat's readings of the score. The last
            // one (`lastScore`; no time is kept, round 7, F30); `sampled`: one
            // was taken in the game in progress (from its start). Between
            // games: `resetOut`, a reset was read since this seat's game ended,
            // and `playOut`, the readings of play in a row since that reset
            // with no game start.
            private bool sampled;
            private Score lastScore;
            private bool resetOut;
            private int playOut;

            /// <summary>A read of team/series/{id}/state for `seriesId`.
            /// `hasWins`: the answer carried both win counts (the canceled and
            /// dc_incomplete answers carry neither, and a missing field parses as
            /// 0, which is not a read). Never lowers what an earlier read showed.
            /// Round 7, finding F29: `sittingKnown` says the answer carried
            /// `relocked` and `two_points_on_record` (an older server's does
            /// not, and then nothing is learned about the sitting); `played`:
            /// a live-points pair of two points or more is on the series'
            /// record. A relock or a played game, read once, is never
            /// forgotten. Since round 8 (F31) a read names no game: it only
            /// saves the series' reporter an ask the server would refuse
            /// (AskFirstGame). Returns the line to log, or null (nothing is
            /// logged here since round 8).</summary>
            internal string ObserveRead(string seriesId, bool hasWins, int t1Wins, int t2Wins, bool sittingKnown,
                                        bool relocked, bool played)
            {
                if (string.IsNullOrEmpty(seriesId)) return null;
                if (sittingKnown)
                {
                    int st;
                    if (!sitting.TryGetValue(seriesId, out st) && sitting.Count >= MaxSeries) sitting.Clear();
                    sitting[seriesId] = st | SittingKnown | (relocked ? SittingRelocked : 0) | (played ? SittingPlayed : 0);
                }
                if (hasWins && t1Wins >= 0 && t2Wins >= 0)
                {
                    int n = t1Wins + t2Wins;
                    int had;
                    if (recorded.TryGetValue(seriesId, out had))
                    {
                        if (n > had) recorded[seriesId] = n;
                    }
                    else
                    {
                        if (recorded.Count >= MaxSeries) recorded.Clear();
                        recorded[seriesId] = n;
                    }
                }
                return null;
            }

            /// <summary>A game starts in a cr_ff room (the watcher's game start):
            /// freeze the number its posts carry, and move the physical game's
            /// ordinal (round 7, finding F29). `live` is the score this seat
            /// reads at the start (round 6, finding F28: the game's first
            /// reading; one that cannot be read means no token in this game).
            /// Returns the number, 0 = its posts go without the pair; `log` is
            /// the line to write.
            ///
            /// The ordinal (PhysicalOrdinal) moves only here and only on a game
            /// start the game itself reported: exactly one start of the game
            /// (OnGmStart) since this seat's last game start in the room. It then
            /// adds one to an ordinal this seat holds; any other start (none of
            /// the game's own, or more than one: a game this seat's watcher did
            /// not see) loses it for the room. It is never taken from a count:
            /// it is grounded only on a publish this seat took
            /// (ObserveRoomToken) or, for the series' physical game 1, on the
            /// server's issue of that game to this seat (round 8, finding F31:
            /// AskFirstGame and OnFirstGame, asked after this start).</summary>
            internal int OnGameStart(string seriesId, string room, Score live, out string log)
            {
                BeginGameToken(live);
                gameGen = gameGen == int.MaxValue ? 1 : gameGen + 1;
                seriesId = seriesId ?? "";
                room = room ?? "";
                string sid8 = seriesId.Length > 8 ? seriesId.Substring(0, 8) : seriesId;
                // The game's own starts on this seat in this room since its last
                // game start here (OnGmStart).
                bool gmHere = room.Length > 0 && string.Equals(room, gmRoom, StringComparison.Ordinal);
                int gm = gmHere ? gmStarts - gmSeen : 0;
                if (gmHere) gmSeen = gmStarts;
                if (seriesId.Length == 0 || room.Length == 0)
                {
                    Freeze("", "", 0);
                    chain = 0;
                    witnessed = false;
                    log = LogTag + " game start with no " + (seriesId.Length == 0 ? "series" : "room")
                          + ": its posts go without the pair and carry no token";
                    return 0;
                }
                string restarted = "";
                if (seriesId != chainSeries || room != chainRoom)
                {
                    if (roomStarts > 0) restarted = " (the series or the room changed: this seat's physical-game ordinal starts over)";
                    chainSeries = seriesId;
                    chainRoom = room;
                    roomStarts = 0;
                    chain = 0;
                    // Round 9, finding M2: a root is one series' only.
                    if (!string.Equals(seriesId, rootSeries, StringComparison.Ordinal))
                    {
                        root = "";
                        rootSeries = "";
                    }
                }
                roomStarts++;
                witnessed = gm == 1;
                string chainNote = "";
                if (!witnessed)
                {
                    if (chain > 0)
                        chainNote = "; this seat's physical-game ordinal is lost for this room (" + Num(gm)
                                    + " starts of the game itself since its last game start)";
                    chain = 0;
                }
                else if (chain > 0)
                {
                    chain = chain >= MaxGameNumber ? 0 : chain + 1;
                }
                int had;
                bool read = recorded.TryGetValue(seriesId, out had);
                int n = read ? had + 1 : (roomStarts == 1 ? 1 : 0);
                if (n > MaxGameNumber || !RoomSendable(room))
                {
                    Freeze(seriesId, room, 0);
                    log = LogTag + " series=" + sid8 + " game number " + Num(n) + " or the room is outside what the"
                          + " server accepts: its posts go without the pair" + restarted + chainNote + OrdinalNote();
                    return 0;
                }
                Freeze(seriesId, room, n);
                if (read)
                {
                    log = LogTag + " series=" + sid8 + " game " + Num(n) + " (" + Num(had) + " recorded as last read;"
                          + " game start " + Num(roomStarts) + " of this series in this room)" + restarted;
                }
                else if (n == 1)
                {
                    log = LogTag + " series=" + sid8 + " game 1 (the series' first game start in this room, no read"
                          + " of its recorded games yet)" + restarted;
                }
                else
                {
                    log = LogTag + " series=" + sid8 + " no game number (game start " + Num(roomStarts)
                          + " in this room and no read of the series' recorded games): its posts go without the pair"
                          + restarted;
                }
                log += chainNote + OrdinalNote();
                return n;
            }

            private void Freeze(string seriesId, string room, int n)
            {
                gameSeries = seriesId;
                gameRoom = room;
                gameNumber = n;
            }

            /// <summary>Round 8, finding F31: whether this seat asks the server
            /// for the series' physical game 1 now, and the game the ask is for
            /// (`gen`, handed back with the answer to OnFirstGame); false and
            /// why not otherwise. Only the series' reporter asks (`reporter`:
            /// this seat holds the lowest Steam ID of the room's four fighters,
            /// the seat whose client sends the series' match reports), once per
            /// game, in a game in progress whose start the game itself reported,
            /// in which this seat holds no ordinal, and only while its client
            /// has sent no report of the series and queued none
            /// (`reportsClean`: an earlier game's result may otherwise still be
            /// on its way). A read showing the series with a recorded game,
            /// relocked or with a pair of two points or more on its record saves
            /// an ask the server would refuse. The server decides
            /// (team_series_first_game), and also refuses an ask whose Steam
            /// session was issued after the series was created, as a restarted
            /// client's is, or one's on another machine or profile, whose
            /// ledger cannot show that game's reports, and (round 9, finding
            /// M1) any ask while another session of this account was live
            /// since the series was created, as a second process's is, or while
            /// anything is on the series' live-points record; nothing here
            /// names a game.</summary>
            internal bool AskFirstGame(string seriesId, string room, bool reporter, bool reportsClean, out int gen,
                                       out string why)
            {
                gen = 0;
                seriesId = seriesId ?? "";
                room = room ?? "";
                int rec, st;
                bool recKnown = recorded.TryGetValue(seriesId, out rec);
                bool stKnown = sitting.TryGetValue(seriesId, out st);
                if (!inGame || overSeen) why = WhyNoGame;
                else if (boundaryMissed) why = WhyMissed;
                else if (!witnessed) why = "the game itself did not report this game start";
                else if (chain > 0) why = "this seat already holds this game's physical-game ordinal";
                else if (askedGen == gameGen) why = "this seat already asked in this game";
                else if (seriesId.Length == 0 || room.Length == 0
                         || !string.Equals(seriesId, chainSeries, StringComparison.Ordinal)
                         || !string.Equals(room, chainRoom, StringComparison.Ordinal))
                    why = "the series or the room is not this game's";
                else if (!reporter) why = "this seat is not the series' reporter";
                else if (!reportsClean)
                    why = "this seat's client has sent or queued a report of the series: an earlier game's result may"
                          + " still be on its way";
                else if (recKnown && rec > 0) why = "a read shows " + Num(rec) + " recorded game(s)";
                else if (stKnown && (st & SittingRelocked) != 0) why = "a read shows the series relocked";
                else if (stKnown && (st & SittingPlayed) != 0)
                    why = "a read shows a pair of two points or more on the series' record";
                else why = null;
                if (why != null) return false;
                askedGen = gameGen;
                askGen = gameGen;
                gen = gameGen;
                return true;
            }

            /// <summary>Round 8, finding F31: the server's answer to the ask made
            /// for game `gen` (AskFirstGame). `issued`: that game is the series'
            /// physical game 1 and `nonce` its issued nonce; `reason` says why
            /// not otherwise. It is taken only while this seat is still in the
            /// game it asked from, holds no ordinal, and its client has still
            /// sent and queued no report of the series (`reportsClean`, read
            /// again now). This seat then holds physical game 1 and publishes its
            /// token in the game's first round (TokenToPublish). Any other
            /// answer, or one too late, leaves the game tokenless. Returns the
            /// line to log.</summary>
            internal string OnFirstGame(string seriesId, string room, int gen, bool issued, string nonce, string reason,
                                        bool reportsClean)
            {
                bool current = gen > 0 && gen == askGen && gen == gameGen;
                if (gen > 0 && gen == askGen) askGen = 0;
                if (!issued)
                    return LogTag + " physical game 1 not issued (" + (string.IsNullOrEmpty(reason) ? "no reason given" : reason)
                           + "): this game is tokenless unless a publish grounds this seat";
                string why = null;
                if (!current || !inGame || overSeen || boundaryMissed) why = "this seat is no longer in the game it asked from";
                else if (chain > 0) why = "this seat already holds a physical-game ordinal";
                else if (!string.Equals(seriesId ?? "", chainSeries, StringComparison.Ordinal)
                         || !string.Equals(room ?? "", chainRoom, StringComparison.Ordinal))
                    why = "the series or the room changed";
                else if (!NonceValid(nonce)) why = "the answer carries no nonce";
                else if (!reportsClean) why = "this seat's client has since sent or queued a report of the series";
                if (why != null)
                    return LogTag + " physical game 1 issued, but not taken: " + why + "; the server issues it once per"
                           + " series, so no later game of the series is named game 1 either";
                chain = 1;
                firstNonce = nonce;
                root = nonce;
                rootSeries = chainSeries;
                return LogTag + " physical game 1 issued by the server (" + ShortNonce(nonce) + "): this seat holds it and"
                       + " publishes its token";
            }

            /// <summary>Round 8, finding F31: the answer to the ask made for
            /// game `gen` is dropped, not taken, because the client cannot keep
            /// what taking it needs (`why`). Settles the ask; returns the line
            /// to log.</summary>
            internal string DropFirstGame(int gen, string why)
            {
                if (gen > 0 && gen == askGen) askGen = 0;
                return LogTag + " physical game 1 issued, but not taken: " + why + "; the server issues it once per"
                       + " series, so no later game of the series is named game 1 either";
            }

            // Round 8, finding F31: this seat's ask for physical game 1 is out
            // for the game in progress.
            private bool FirstGamePending()
            {
                return chain == 0 && askGen > 0 && askGen == gameGen;
            }

            private string OrdinalNote()
            {
                int p = PhysicalOrdinal();
                if (p > 0) return "; physical game " + Num(p);
                return "; " + WhyNoOrdinal + (witnessed ? "" : " (the game itself did not report this game start)");
            }

            /// <summary>Round 7, finding F29: the physical game this seat is in
            /// (or last was), grounded on a publish it took or (round 8, F31) on
            /// the server's issue of the series' physical game 1, and counted at
            /// every game start the game itself reported since; 0 = it cannot
            /// say.</summary>
            internal int PhysicalOrdinal()
            {
                return chain;
            }

            /// <summary>The number a post sent now carries: the frozen one while
            /// the series and the room are the ones it was frozen for, else 0.</summary>
            internal int For(string seriesId, string room)
            {
                if (gameNumber <= 0) return 0;
                if (!string.Equals(seriesId ?? "", gameSeries, StringComparison.Ordinal)) return 0;
                if (!string.Equals(room ?? "", gameRoom, StringComparison.Ordinal)) return 0;
                return gameNumber;
            }

            /// <summary>Whether a read has shown the frozen game recorded: the
            /// after-game refresh has what the next game start needs.</summary>
            internal bool ReadShowsGameRecorded(string seriesId)
            {
                int had;
                return gameNumber > 0
                       && string.Equals(seriesId ?? "", gameSeries, StringComparison.Ordinal)
                       && recorded.TryGetValue(gameSeries, out had) && had >= gameNumber;
            }

            /// <summary>The room was left (the watcher's polled exit): nothing
            /// frozen, the physical-game ordinal is gone, and so is the token
            /// state (the first value read in the next room, the same room
            /// rejoined included, is taken as an earlier game's). Reads are kept
            /// (they belong to the series, not the room).</summary>
            internal void Clear()
            {
                ResetRoom("");
            }

            // Round 7, F29: everything this seat holds for the room it is in.
            private void ResetRoom(string gm)
            {
                Freeze("", "", 0);
                chainSeries = "";
                chainRoom = "";
                roomStarts = 0;
                chain = 0;
                witnessed = false;
                // Round 8, F31: an answer to an ask from the room left behind
                // names no game here, and the issued game is dropped with the
                // ordinal.
                gameGen = gameGen == int.MaxValue ? 1 : gameGen + 1;
                askGen = 0;
                firstNonce = "";
                gmRoom = gm ?? "";
                gmStarts = 0;
                gmSeen = 0;
                ResetToken("");
            }

            /// <summary>Round 7, finding F29: Photon's OnJoinedRoom, for every
            /// join (a rejoin of the same room included): a join breaks this
            /// seat's physical-game ordinal, so everything it held for a room is
            /// dropped. Round 8, finding F31: which seat created the room names
            /// nothing. Returns the line to log, or null.</summary>
            internal string NoteRoomJoined(string room)
            {
                room = room ?? "";
                bool had = chain > 0 || adopted.Length > 0;
                ResetRoom(room);
                return had
                    ? LogTag + " joined a room: this seat's physical-game ordinal and game token are dropped (a join"
                      + " breaks them; only a publish grounds them again)"
                    : null;
            }

            /// <summary>Round 7, finding F29: the game itself started a game on
            /// this seat (GM_ArmsRace.DoStartGame, TeamGameLifecycle), in `room`
            /// (the Photon room this seat is in). The next watcher game start
            /// counts these (OnGameStart). Round 7, finding F30: a game this
            /// seat is still in by its tracker ends here (its watcher missed
            /// the game over, and the game-over hook did not end it): the game
            /// resets this seat's scoreboard in the same step (IDoRematch's
            /// ResetMatch), so no reading of the new game comes first, and the
            /// token is not carried into it. Returns the line to log, or
            /// null.</summary>
            internal string OnGmStart(string room)
            {
                room = room ?? "";
                string line = GmVoid("the game itself started its next game on this seat");
                if (!string.Equals(room, gmRoom, StringComparison.Ordinal))
                {
                    gmRoom = room;
                    gmStarts = 0;
                    gmSeen = 0;
                }
                if (gmStarts < int.MaxValue) gmStarts++;
                return line;
            }

            /// <summary>Round 7, finding F30: the game itself ended this seat's
            /// game (GM_ArmsRace.GameOverTransition, TeamGameLifecycle), called
            /// in the same step that sets this seat's scoreboard to the game
            /// over (RPCA_NextRound), before any reading of it, whatever the
            /// watcher saw. The game's token ends at once, and none is taken
            /// until this seat's next game start. Returns the line to log, or
            /// null.</summary>
            internal string OnGmGameOver()
            {
                return GmVoid("the game itself ended this seat's game");
            }

            // Round 7, finding F30: the game in progress ended by the game's own
            // lifecycle. Its token ends and nothing is taken or carried until
            // the next game start; the watcher's game over, if it comes, finds
            // nothing left (OnTokenGameOver).
            private string GmVoid(string why)
            {
                if (!inGame || overSeen) return null;
                bool had = adopted.Length > 0;
                EndGameToken();
                overSeen = true;
                return had ? LogTag + " " + why + ": its game token is dropped" : null;
            }

            internal void NoteAttestationRefused(string seriesId)
            {
                if (string.IsNullOrEmpty(seriesId)) return;
                if (refused.Count >= MaxSeries) refused.Clear();
                refused.Add(seriesId);
            }

            internal bool AttestationRefused(string seriesId)
            {
                return !string.IsNullOrEmpty(seriesId) && refused.Contains(seriesId);
            }

            // ---- The physical game's token (round 5, finding F25; round 6) ----

            /// <summary>The token this seat holds for the game in progress, ""
            /// = none (for the log and the sentinel; a post or a DC report
            /// takes TokenFor).</summary>
            internal string Adopted { get { return adopted; } }

            private static void Remember(List<string> list, string v)
            {
                if (!TokenValid(v) || list.Contains(v)) return;
                if (list.Count >= MaxTokens) list.RemoveAt(0);
                list.Add(v);
            }

            // A value stale for every later game in the room: its nonce is not
            // taken again, and no value whose epoch is not above its is taken.
            private void Stale(string v)
            {
                string nonce;
                int o;
                long e;
                if (!TryParseToken(v, out nonce, out o, out e)) return;
                NoteEpoch(e);
                if (e > epochStale) epochStale = e;
                if (stale.Contains(nonce)) return;
                if (stale.Count >= MaxTokens) stale.RemoveAt(0);
                stale.Add(nonce);
            }

            private void NoteEpoch(long e)
            {
                if (e > epochRead) epochRead = e;
            }

            // Round 6 (#182): a value naming a later game than `ending`, the
            // game of this seat's that ends, was published for a game this seat
            // has not started yet (its host started first), so it is not stale
            // for that game. 0 = this seat cannot say which game ended: every
            // value is stale.
            private static bool NamesLaterGame(string v, int ending)
            {
                string n;
                int o;
                long e;
                return ending > 0 && TryParseToken(v, out n, out o, out e) && o > ending;
            }

            private bool SeenNonce(string nonce)
            {
                foreach (string v in seen)
                    if (NonceOf(v) == nonce) return true;
                return false;
            }

            private void ResetToken(string room)
            {
                stale.Clear();
                seen.Clear();
                tokenRoom = room ?? "";
                adopted = "";
                adoptedOrdinal = 0;
                firstNonce = "";
                took = false;
                inGame = false;
                overSeen = false;
                boundaryMissed = false;
                withdrawn = false;
                published = false;
                noted = "";
                epochRead = 0;
                epochStale = 0;
                epochPublished = 0;
                sampled = false;
                resetOut = false;
                playOut = 0;
            }

            // The game in progress ends (a game over, a game start without one,
            // a missed boundary): everything read or taken in it is stale for
            // every later game, but a value naming a later game.
            private void EndGameToken()
            {
                int ending = PhysicalOrdinal();
                foreach (string v in seen)
                    if (!NamesLaterGame(v, ending)) Stale(v);
                seen.Clear();
                Stale(adopted);
                adopted = "";   // a token is never carried into another game
                adoptedOrdinal = 0;
                firstNonce = "";   // round 8, F31: the issued game's token is published in that game only
                published = false;
                withdrawn = false;
                noted = "";
            }

            // Round 6, finding F28: a game start seeds the readings with the
            // score read there. One that cannot be read leaves the game without
            // a token.
            private void BeginGameToken(Score live)
            {
                EndGameToken();
                inGame = true;
                overSeen = false;
                boundaryMissed = !live.Read;
                took = false;
                sampled = live.Read;
                lastScore = live;
                resetOut = false;
                playOut = 0;
            }

            // Round 6, finding F28: the game's token ends at once, and none is
            // taken for the rest of the game.
            private void Withdraw()
            {
                Stale(adopted);
                adopted = "";
                adoptedOrdinal = 0;
                withdrawn = true;
            }

            /// <summary>Round 6, finding F28: the score as this seat reads it on
            /// a poll tick (`s`). Inside this seat's game: the game over ends
            /// the game's token at once, before any game over from the watcher
            /// arrives, and a reading that cannot follow the one before it
            /// inside one game (Follows) is a game boundary this seat did not
            /// see (round 5's missed-boundary guard, now on the points too and
            /// seeded at the game start). A reading that cannot be read is
            /// skipped. No time is read (round 7, finding F30): a gap between
            /// readings is neither a boundary nor proof of none; the game's own
            /// game over and game start end the token (OnGmGameOver,
            /// OnGmStart). Between games: play read twice in a row after a
            /// reset with no game start is a game this seat did not see start.
            /// Returns the line to log, or null.</summary>
            internal string ObserveScore(Score s)
            {
                if (!s.Read) return null;
                string line = null;
                bool follows = sampled && Follows(lastScore, s);
                if (inGame && overSeen)
                {
                    // The score showed this game over; its reset ends the game
                    // here when the watcher's game over did not.
                    if (sampled && !follows)
                    {
                        EndGameToken();
                        inGame = false;
                        overSeen = false;
                        resetOut = true;
                        playOut = 0;
                    }
                }
                else if (inGame)
                {
                    if (sampled && !boundaryMissed)
                    {
                        if (!follows)
                            line = Missed("the score went down inside this seat's game (a game boundary it did not see;"
                                          + " " + lastScore + " then " + s + ")");
                        else if (s.Over)
                        {
                            bool had = adopted.Length > 0;
                            EndGameToken();
                            overSeen = true;
                            if (had) line = LogTag + " the score shows the game over (" + s + "): its game token is dropped";
                        }
                    }
                }
                else if (s.AllZero)
                {
                    resetOut = true;
                    playOut = 0;
                }
                else
                {
                    if (sampled && !follows)
                    {
                        resetOut = true;
                        playOut = 0;
                    }
                    if (resetOut && ++playOut >= 2 && chain > 0)
                    {
                        chain = 0;
                        line = LogTag + " play was read after a reset with no game start on this seat (" + s + "): it"
                               + " missed a game start, so its physical-game ordinal is lost for this room (only a"
                               + " host's publish grounds it again)";
                    }
                }
                sampled = true;
                lastScore = s;
                return line;
            }

            // Round 6, finding F28 (round 5's missed-boundary guard, D10): a game
            // boundary inside this seat's game that it did not see. Its token is
            // dropped at once and it takes none until its next game start; and
            // (round 7, F29) its physical-game ordinal is lost for the room: only
            // a host's publish grounds it again.
            private string Missed(string why)
            {
                bool had = adopted.Length > 0;
                EndGameToken();
                boundaryMissed = true;
                bool grounded = chain > 0;
                chain = 0;
                return LogTag + " " + why + ": " + (had ? "its game token is dropped, and " : "")
                       + "its posts and a DC report carry no token"
                       + (grounded ? "; its physical-game ordinal is lost for this room" : "");
            }

            /// <summary>The room's TokenRoomKey value as this seat reads it now
            /// (`v`; "" = none, or not a token), read on every poll tick in a
            /// cr_ff room and right after every game start. Returns the line to
            /// log, or null (most reads change nothing).</summary>
            internal string ObserveRoomToken(string room, string v)
            {
                room = room ?? "";
                string nonce;
                int ordinal;
                long epoch;
                if (!TryParseToken(v, out nonce, out ordinal, out epoch)) v = "";
                if (room.Length == 0) return null;
                if (!string.Equals(room, tokenRoom, StringComparison.Ordinal))
                {
                    // The first value read in a room may be the token of a game
                    // this seat did not see start (a join or a rejoin in the
                    // middle of one), so it is stale. This seat's posts go
                    // without a token until the host publishes a fresh one at a
                    // game start this seat sees.
                    ResetToken(room);
                    if (v.Length == 0) return LogTag + " first read of the room's game token: none yet";
                    Stale(v);
                    return LogTag + " first read of the room's game token " + Describe(v) + ": taken as an earlier"
                           + " game's (this seat did not see that game start)";
                }
                if (v.Length == 0) return null;
                NoteEpoch(epoch);
                if (!inGame || overSeen)
                {
                    // Round 7, finding F29: outside this seat's game, a value
                    // read before the game itself started this seat's next game
                    // (OnGmStart) was published for a game this seat's game did
                    // not start (it joined in the middle of one) or for an
                    // earlier game, so it is stale for every later game. A value
                    // read after that start is left to this seat's game start:
                    // the host publishes after its game's first point, and a
                    // watcher that starts later still takes its game's token
                    // (#182).
                    if (!(string.Equals(room, gmRoom, StringComparison.Ordinal) && gmStarts > gmSeen)) Stale(v);
                    return null;
                }
                Remember(seen, v);
                if (adopted.Length > 0)
                {
                    if (v == adopted) return null;
                    // Round 6, finding F28: another value inside this seat's game
                    // (the next game's publish, a later game's, a second
                    // publisher's) ends the game's token at once.
                    Withdraw();
                    noted = v;
                    return LogTag + " the room's game token changed to " + Describe(v) + " inside this seat's game: its"
                           + " token is withdrawn, and its posts and a DC report carry none until its next game start";
                }
                if (withdrawn || boundaryMissed) return null;
                if (!witnessed)
                {
                    // Round 7, finding F29: a game start the game itself did not
                    // report (a join or a rejoin in the middle of a game, or a
                    // watcher that missed a game): which physical game this is
                    // cannot be told, so nothing is taken until the next game
                    // start that the game reports.
                    if (v == noted) return null;
                    noted = v;
                    return LogTag + " game token " + Describe(v) + " not taken: the game itself did not report this"
                           + " seat's game start; its posts and a DC report carry none until its next game start";
                }
                int own = PhysicalOrdinal();
                // Round 7, finding F29: a seat holding no ordinal measures a
                // later game by the number its posts name (For), the only one
                // it has; this only ever withholds.
                int mine = own > 0 ? own : gameNumber;
                if (mine > 0 && ordinal > mine)
                {
                    // Round 6, finding F28: a later game's token. The room's
                    // games are ahead of this seat's, which takes none for its own.
                    withdrawn = true;
                    noted = v;
                    return LogTag + " the room's game token " + Describe(v) + " names a game after this seat's (game "
                           + Num(mine) + "): its posts and a DC report carry no token until its next game start";
                }
                if (stale.Contains(nonce)) return null;
                string why = epoch <= epochStale
                    ? "its epoch is not above " + epochStale.ToString(CultureInfo.InvariantCulture)
                      + ", the highest of a value this seat holds as an earlier game's"
                    : OrdinalRefusal(ordinal);
                if (why != null)
                {
                    if (v == noted) return null;
                    noted = v;
                    return LogTag + " game token " + Describe(v) + " not taken: " + why + "; its posts and a DC report"
                           + " carry none unless this game's own token arrives";
                }
                adopted = v;
                adoptedOrdinal = ordinal;
                took = true;
                if (chain > 0) return LogTag + " game token " + Describe(v) + " taken for this game";
                // Round 7, finding F29: a seat holding no ordinal is grounded on
                // the publish it takes, and only on that (or on the server's
                // issue of physical game 1: OnFirstGame). Round 9, finding M2:
                // physical game 1's token carries the root every nonce this
                // seat later publishes as the host is derived from; a later
                // token keeps a root this seat holds for the series only when
                // it is the nonce derived from that root, and never reveals one.
                chain = ordinal;
                if (ordinal == 1)
                {
                    root = nonce;
                    rootSeries = chainSeries;
                }
                else if (ChainNonce(RootFor(chainSeries), ordinal, epoch) != nonce)
                {
                    root = "";
                    rootSeries = "";
                }
                return LogTag + " game token " + Describe(v) + " taken for this game: this seat's physical-game"
                       + " ordinal is grounded on it (game " + Num(ordinal) + ")";
            }

            // Round 6, finding F27; round 7, finding F29: why a token naming
            // `ordinal` is not the token of this seat's game, or null. When this
            // seat holds the physical game's ordinal (PhysicalOrdinal: grounded
            // on a publish or on the server's issue of physical game 1, never on
            // a count)
            // the token must name it: a seat a game ahead of a lagging host
            // holds a higher ordinal than the one the host's token names. It
            // must also name the game this seat's posts name (the server's
            // count, For): that number only ever withholds here, and it never
            // grounds or moves the ordinal, so a queued result (the count
            // behind the physical game) leaves the game tokenless.
            private string OrdinalRefusal(int ordinal)
            {
                int own = PhysicalOrdinal();
                if (own > 0 && ordinal != own)
                    return "it names game " + Num(ordinal) + " and this seat is in physical game " + Num(own);
                if (ordinal != gameNumber)
                    return "it names game " + Num(ordinal) + " and this seat's posts name "
                           + (gameNumber > 0 ? "game " + Num(gameNumber) : "no game");
                return null;
            }

            // Round 6, finding F28: why this seat's reading of the score now
            // (`live`) does not show the game its token was taken in, or null.
            // It fails closed: a score this seat cannot read, no reading in the
            // game, rounds to win not known or one (a one-round game's score
            // cannot be told from the next game's), the game over, a 0-0 with
            // no points (a game's reset: no crossing of the game in progress
            // exists before its first point), and a score that cannot follow
            // the last reading inside one game. It compares values only, and
            // only ever withholds (round 7, finding F30: a score that follows
            // is no proof of the same game; the game's own lifecycle ends a
            // token, OnGmGameOver and OnGmStart).
            private string ScoreRefusal(Score live)
            {
                if (!live.Read) return "this seat cannot read the score";
                if (!sampled) return "this seat has no reading of the score in this game";
                if (live.RoundsToWin <= 1) return "the rounds a game is won at are not known or one: a game's score cannot be told from the next game's";
                if (live.Over) return "the score shows the game over (" + live + ")";
                if (live.AllZero) return "the score reads 0-0 with no points (a game's reset)";
                if (!Follows(lastScore, live)) return "the score went down (" + lastScore + " then " + live + ")";
                return null;
            }

            /// <summary>This seat's game is over. The value the room holds now
            /// (`v`) and everything read or taken in the game are stale for
            /// every later game, but a value naming a later game. Returns the
            /// line to log, or null.</summary>
            internal string OnTokenGameOver(string room, string v)
            {
                string line = inGame && !took
                    ? LogTag + " no game token was taken in this game: its posts carried none"
                    : null;
                int ending = PhysicalOrdinal();
                if (string.Equals(room ?? "", tokenRoom, StringComparison.Ordinal) && !NamesLaterGame(v, ending)) Stale(v);
                EndGameToken();
                inGame = false;
                overSeen = false;
                boundaryMissed = false;
                resetOut = false;
                playOut = 0;
                return line;
            }

            /// <summary>The token a post or a DC report sent now carries, "" =
            /// none (`why`: the reason, for the log). The one taken in this
            /// seat's game, while that game is in progress, in the series and
            /// the room its number was frozen for, while the room still holds it
            /// (`v`: the room's value now), while it names this seat's physical
            /// game (round 7, F29: PhysicalOrdinal, grounded on a publish or on
            /// the server's issue of physical game 1, never on a count) and the
            /// number its posts name (round 6, F27),
            /// and while this seat's reading of the score now (`live`) still
            /// shows that game (round 6, F28), and only while both of the game's
            /// lifecycle hooks are attached (`hooksLive`, round 7, finding F30:
            /// without them a game over or a game start this seat's watcher
            /// missed cannot end the token, so none is carried). Every check is
            /// made here, when the post or the report is built. A game over or
            /// a game start the game itself ran on this seat has already ended
            /// the token (OnGmGameOver, OnGmStart), whether or not it reached
            /// the watcher.</summary>
            internal string TokenFor(string seriesId, string room, string v, Score live, bool hooksLive, out string why)
            {
                why = TokenRefusal(seriesId, room, v, live, hooksLive);
                return why == null ? adopted : "";
            }

            internal string TokenFor(string seriesId, string room, string v, Score live, bool hooksLive)
            {
                string why;
                return TokenFor(seriesId, room, v, live, hooksLive, out why);
            }

            private string TokenRefusal(string seriesId, string room, string v, Score live, bool hooksLive)
            {
                if (!hooksLive) return WhyNoHooks;
                if (!inGame || overSeen) return WhyNoGame;
                if (boundaryMissed) return WhyMissed;
                if (PhysicalOrdinal() <= 0) return WhyNoOrdinal;
                if (withdrawn) return "this game's token was withdrawn";
                if (adopted.Length == 0) return "no game token was taken in this game";
                if (string.IsNullOrEmpty(seriesId)) return "no series";
                room = room ?? "";
                if (!string.Equals(seriesId, gameSeries, StringComparison.Ordinal)
                    || !string.Equals(room, gameRoom, StringComparison.Ordinal)
                    || !string.Equals(room, tokenRoom, StringComparison.Ordinal))
                    return "the series or the room is not the one the token was taken for";
                if (!string.Equals(v ?? "", adopted, StringComparison.Ordinal)) return "the room no longer holds this game's token";
                string ordinalWhy = OrdinalRefusal(adoptedOrdinal);
                if (ordinalWhy != null) return ordinalWhy;
                return ScoreRefusal(live);
            }

            /// <summary>The token this seat publishes now, or "" and why not
            /// (`why`, one of the Why constants). Once per game, while the
            /// game's first round is in progress (`firstRound`: the rounds are
            /// 0-0), only while this seat has taken no token in the game and
            /// holds the physical game's ordinal (round 7, F29: PhysicalOrdinal,
            /// grounded on a publish this seat took or on the server's issue of
            /// physical game 1, and counted at every game start the game itself
            /// reported since), which the token names. A seat holding none
            /// publishes nothing. Round 8, finding F31: the seat the server
            /// issued physical game 1 to publishes that game's token, its nonce
            /// the issued one, whether or not it is the room's host; every other
            /// token is the host's (`isHost`). Its epoch is one above the highest
            /// this seat has read in the room or published (a new host after a
            /// master change continues the room's epochs from the value the room
            /// holds). Round 9, finding M2: its nonce is derived from the root
            /// this seat holds for the series and the token's ordinal and epoch
            /// (ChainNonce; none held: WhyNoAnchor). `current` is the room's
            /// value now; a derived nonce equal to its nonce, to one stale for
            /// this seat or to one read in this game is not published
            /// (WhyChainTaken).</summary>
            internal string TokenToPublish(bool isHost, bool firstRound, string current, out string why)
            {
                why = null;
                long epoch = Math.Max(epochRead, epochPublished) + 1;
                bool issued = firstNonce.Length > 0 && PhysicalOrdinal() == 1;
                if (!inGame || overSeen) why = WhyNoGame;
                else if (boundaryMissed) why = WhyMissed;
                else if (PhysicalOrdinal() <= 0) why = FirstGamePending() && firstRound ? WhyFirstGamePending : WhyNoOrdinal;
                else if (adopted.Length > 0 || withdrawn) why = WhyTaken;
                else if (published) why = WhyPublished;
                else if (!firstRound) why = WhyLate;
                else if (!isHost && !issued) why = WhyNotHost;
                else if (epoch > MaxEpoch) why = WhyEpoch;
                else if (!issued && RootFor(chainSeries).Length == 0) why = WhyNoAnchor;
                if (why != null) return "";
                if (issued) return MakeToken(firstNonce, 1, epoch);
                string n = ChainNonce(RootFor(chainSeries), PhysicalOrdinal(), epoch);
                if (n.Length == 0 || n == NonceOf(current) || stale.Contains(n) || SeenNonce(n))
                {
                    why = WhyChainTaken;
                    return "";
                }
                return MakeToken(n, PhysicalOrdinal(), epoch);
            }

            // Round 9, finding M2: the root this seat holds for `seriesId`, or "".
            private string RootFor(string seriesId)
            {
                if (rootSeries.Length == 0 || !string.Equals(seriesId ?? "", rootSeries, StringComparison.Ordinal)) return "";
                return root;
            }

            /// <summary>The publish of `token` was sent (SetCustomProperties
            /// returned true): no second one this game, and a later publish
            /// takes a higher epoch. Nothing else changes; this seat's posts
            /// carry the token once the room shows it.</summary>
            internal void ArmPublished(string token)
            {
                string n;
                int o;
                long e;
                if (!inGame || !TryParseToken(token, out n, out o, out e)) return;
                published = true;
                if (e > epochPublished) epochPublished = e;
            }
        }

        // ---- The sentinel ----------------------------------------------------
        //
        // A model of one series, three real games, and the server's filing
        // rule, run under four numbering rules: the Tracker above, and three
        // kept copies of rules this round did not build. The invariant: an
        // attested post the server files is filed under the game the server
        // was in when the post's own game started, in that game's sitting
        // (never under a later game: finding 1's false positive). The
        // liveness check: when every game is recorded before the next one
        // starts, every after-game read sees it and no game start fires twice,
        // every post a game sends at its start is filed.

        private abstract class Rule
        {
            internal abstract void Read(string series, int recordedGames);
            internal abstract void Start(string series, string room);
            internal abstract void Leave();
            internal abstract int Name(string series, string room);
        }

        private sealed class TrackerRule : Rule
        {
            private readonly Tracker t = new Tracker();
            internal override void Read(string series, int recordedGames) { t.ObserveRead(series, true, recordedGames, 0, false, false, false); }
            internal override void Start(string series, string room) { string line; t.OnGameStart(series, room, Played, out line); }
            internal override void Leave() { t.Clear(); }
            internal override int Name(string series, string room) { return t.For(series, room); }
        }

        // Kept copy: a free-running count of game starts, restarted when the
        // room changes: FFA's shape without its correction from the server.
        private sealed class OwnCountRule : Rule
        {
            private string room = "";
            private int starts;
            internal override void Read(string series, int recordedGames) { }
            internal override void Start(string series, string r) { if (r != room) { room = r; starts = 0; } starts++; }
            internal override void Leave() { room = ""; starts = 0; }
            internal override int Name(string series, string r) { return r == room ? starts : 0; }
        }

        // Kept copy: the server's count read when a post is SENT, not frozen at
        // its game's start.
        private sealed class SendTimeRule : Rule
        {
            private string room = "";
            private int last = -1;
            internal override void Read(string series, int recordedGames) { if (recordedGames > last) last = recordedGames; }
            internal override void Start(string series, string r) { room = r; }
            internal override void Leave() { room = ""; }
            internal override int Name(string series, string r) { return (r == room && last >= 0) ? last + 1 : 0; }
        }

        // Kept copy: never name a game (every post goes without the pair).
        private sealed class NeverRule : Rule
        {
            internal override void Read(string series, int recordedGames) { }
            internal override void Start(string series, string r) { }
            internal override void Leave() { }
            internal override int Name(string series, string r) { return 0; }
        }

        private sealed class Tally
        {
            public int Timelines, Posts, Filed, Wrong, CleanFirst, CleanFirstFiled;
        }

        private struct SentPost
        {
            public int Named;
            public string Room;
            public int GameAtStart;       // the server's game when this post's own game started
            public string SittingAtStart; // and the room it had stored then
            public bool First;            // sent at its game's start, processed at once
        }

        private const int RecBefore = 0, RecLate = 1, RecNever = 2;

        private sealed class Sim
        {
            public int Recorded;          // the server's recorded games
            public string Stored;         // the server's sitting room
            public bool Clean;
            public Tally Tally;

            public void Process(SentPost p)
            {
                Tally.Posts++;
                // _record_team_game_points: filed only under exactly the game in
                // progress, in the stored sitting.
                bool filed = p.Named >= 1 && p.Named == Recorded + 1 && p.Room == Stored;
                if (filed)
                {
                    Tally.Filed++;
                    if (Recorded + 1 != p.GameAtStart || Stored != p.SittingAtStart) Tally.Wrong++;
                }
                if (p.First && Clean)
                {
                    Tally.CleanFirst++;
                    if (filed) Tally.CleanFirstFiled++;
                }
            }
        }

        // One timeline. rec[k]: game k+1 is recorded before the next game
        // starts, during it (late), or never. fresh[k]: a read after game k+1's
        // end sees what the server has then. initRead: a read before game 1.
        // doubleAt: that game's start fires twice. relockAfter: after that game
        // the series moves to a new sitting in a new room. midRead: a read in
        // the middle of every game. lagRead: a read after a game's record that
        // a seat still in that game takes before its last post.
        private static void Simulate(Rule rule, int[] rec, bool[] fresh, bool initRead, int doubleAt,
                                     int relockAfter, bool midRead, bool lagRead, Tally tally)
        {
            const string S = "series-a", R1 = "room-a", R2 = "room-b";
            var sim = new Sim { Recorded = 0, Stored = R1, Tally = tally };
            sim.Clean = doubleAt == 0;
            for (int k = 0; k < 3; k++) sim.Clean &= rec[k] == RecBefore && fresh[k];
            tally.Timelines++;
            string room = R1;
            var carried = new List<SentPost>();
            if (initRead) rule.Read(S, sim.Recorded);
            for (int k = 0; k < 3; k++)
            {
                rule.Start(S, room);
                if (doubleAt == k + 1) rule.Start(S, room);
                int gameAtStart = sim.Recorded + 1;
                string sittingAtStart = sim.Stored;
                // The first post of the game, processed at once.
                sim.Process(new SentPost { Named = rule.Name(S, room), Room = room, GameAtStart = gameAtStart,
                                           SittingAtStart = sittingAtStart, First = true });
                // The previous game's posts still in flight.
                foreach (var p in carried) sim.Process(p);
                carried.Clear();
                // The previous game's record, landing late.
                if (k > 0 && rec[k - 1] == RecLate) sim.Recorded++;
                if (midRead) rule.Read(S, sim.Recorded);
                sim.Process(new SentPost { Named = rule.Name(S, room), Room = room, GameAtStart = gameAtStart,
                                           SittingAtStart = sittingAtStart });
                var afterItsRecord = new SentPost { Named = rule.Name(S, room), Room = room, GameAtStart = gameAtStart,
                                                    SittingAtStart = sittingAtStart };
                var intoNextGame = new SentPost { Named = rule.Name(S, room), Room = room, GameAtStart = gameAtStart,
                                                  SittingAtStart = sittingAtStart };
                // Game over, and its report.
                if (rec[k] == RecBefore) sim.Recorded++;
                sim.Process(afterItsRecord);
                // A seat whose own game over has not fired yet reads, then posts.
                if (lagRead) rule.Read(S, sim.Recorded);
                var lagging = new SentPost { Named = rule.Name(S, room), Room = room, GameAtStart = gameAtStart,
                                             SittingAtStart = sittingAtStart };
                carried.Add(intoNextGame);
                carried.Add(lagging);
                if (fresh[k]) rule.Read(S, sim.Recorded);
                if (relockAfter == k + 1)
                {
                    sim.Stored = R2;
                    room = R2;
                    rule.Leave();
                }
            }
            if (rec[2] == RecLate) sim.Recorded++;
            foreach (var p in carried) sim.Process(p);
        }

        private static Tally Sweep(Func<Rule> make)
        {
            var tally = new Tally();
            var rec = new int[3];
            var fresh = new bool[3];
            for (int r = 0; r < 27; r++)
            for (int f = 0; f < 8; f++)
            for (int init = 0; init < 2; init++)
            for (int dbl = 0; dbl < 4; dbl++)
            for (int relock = 0; relock < 3; relock++)
            for (int mid = 0; mid < 2; mid++)
            for (int lag = 0; lag < 2; lag++)
            {
                int rr = r;
                for (int k = 0; k < 3; k++) { rec[k] = rr % 3; rr /= 3; fresh[k] = ((f >> k) & 1) != 0; }
                Simulate(make(), rec, fresh, init != 0, dbl, relock, mid != 0, lag != 0, tally);
            }
            return tally;
        }

        // ---- The token sentinel (round 5, finding F25; round 6, F27 and F28) --
        //
        // The reviewer's scenario and its neighbours, run on two real Trackers:
        // the room's host H (team 1) and a peer P (team 2). Game 1 is recorded
        // before game 2 starts (its host's publish sent or not); game 2 crosses
        // two points for both teams. What varies after that: when game 2's
        // report lands (before game 3 starts, after game 3's posts, after the
        // DC report, never), whether the host's publish for game 3 is sent,
        // when the room's new value reaches P (inside P's game 2 because the
        // host started first, before P's game 3 start, after it, never),
        // whether the host's echo arrives before the DC report, whether P
        // missed the boundary between the games (its polls read game 3's reset
        // inside its game 2), how far game 3 got (0-0, one point, two points
        // each), and which seat reports the DC. Every seat reads its own score
        // on its own clock (TokenSeat.Tick) and starts a game at its first
        // combat, the score 0-0. The lead rule is outside the model: every DC
        // report comes from the team a game up. The server is main.py's rule
        // (TokenServer). The invariant: nothing settles from a post of a
        // physical game other than the one the DC is in. The liveness check:
        // with game 2 recorded before game 3 starts, the publish sent, the
        // value reaching P at all, the host's echo in time and no boundary
        // missed, a DC after two points each settles (round 6: a value that
        // reaches P inside its game 2 names game 3 and is taken at P's game 3
        // start, #182). The same sweep against the rule before round 5 (no
        // token read) must settle from another game, or it could not see F25.
        //
        // Round 6 adds two models on three real Trackers each, F27's seats a
        // game apart and F28's reporter that did not see a game boundary; each
        // is described above its own code below.
        //
        // Round 7 (finding F29): a seat holds a physical game only through a
        // publish it takes or the server's issue of physical game 1, and the
        // game itself starts each game on a seat (Rematch: DoStartGame,
        // TeamGameLifecycle) before that seat's watcher does. F29's own model
        // follows F28's. Round 8 (finding F31): in every model but F31's the
        // room's host is also the series' reporter, and physical game 1 is the
        // server's issue to it at its first game start (TokenSeat.Ask,
        // TokenServer.GrantFirst), never a read of the series; the server reads
        // a DC report's token only when it is counted from that issue
        // (ReadsAnchor). F31's own model follows F29's.

        // Scores the model's seats read (rounds to win 5).
        private static readonly Score Reset = Score.Of(0, 0, 0, 0, 5);     // a game's 0-0, before its first point
        private static readonly Score Played = Score.Of(0, 0, 1, 0, 5);    // its first point
        private static readonly Score TwoEach = Score.Of(0, 0, 1, 1, 5);   // one point each: two points, a crossing
        private static readonly Score RoundUp = Score.Of(1, 0, 0, 0, 5);   // its first round won
        private static readonly Score Later = Score.Of(3, 2, 0, 0, 5);     // deep in a game
        private static readonly Score Continue = Score.Of(4, 2, 0, 0, 5);  // deeper in the same game
        private static readonly Score Final = Score.Of(5, 2, 0, 0, 5);     // its game over

        // Round 9, finding M1: a fresh name for a harness seat's account or
        // Steam session.
        private static int harnessNames;

        private static string NewHarnessName(string kind)
        {
            harnessNames++;
            return kind + "-" + harnessNames.ToString(CultureInfo.InvariantCulture);
        }

        private sealed class TokenRec
        {
            public string Room = "";         // the sitting it was filed in
            public string Token = "";        // the nonce of the first token filed
            public bool Conflict;
            public int TokTeams, AllTeams;   // bit per team: a two-point post carrying Token / any two-point post
            public readonly List<int> TokGames = new List<int>();
            public readonly List<int> AllGames = new List<int>();
        }

        // main.py's rule. A post is filed only under the game it names while
        // the server is in that game, in the room the series stores (Stored).
        // ReadsTokens: the first token filed in a record is the record's (its
        // nonce), another one marks the record as holding two games, and a DC
        // report settles only from two-point posts of both teams that carried
        // its token, when that token is the record's, the record holds one
        // game, and no other record carries it. ReadsOrdinals (round 6, F27):
        // a filed token naming a game other than its record's marks the record
        // the same way, and a DC report settles only when its token names the
        // game being settled. ReadsSitting (round 7, F29; main.py,
        // _team_game_sitting_refusal): a DC report's token settles nothing once
        // the series was relocked or has a record in another room. ReadsAnchor
        // (round 8, F31; main.py, _team_game_first_game_refusal): nor unless
        // the series was issued a physical game 1 (GrantFirst), not voided
        // (Land), and (round 9, M2) the token's nonce is the one derived from
        // the issued nonce for its ordinal and epoch (ChainNonce; ReadsPrefix
        // is round 8's rule, the kept copy: its first 8 digits alone); nor
        // (round 9, M1, ReadsIssued) when the series' reporter's account
        // reports on another session than the one the issue went to.
        // Unreachable: the seats' requests fail (a post is not filed, an ask
        // is not answered).
        private sealed class TokenServer
        {
            public bool ReadsTokens, ReadsOrdinals, ReadsSitting, ReadsAnchor;
            public int Recorded;
            public string Stored = "";
            public bool Relocked;
            // Round 7, F29: a post of two points or more was filed (main.py,
            // team_series_state's two_points_on_record).
            public bool AnyTwo;
            // Round 8, F31 (main.py, team_series_first_game and
            // _team_first_game_void; migration 359): physical game 1 was issued
            // (`FirstNonce`), and a recorded report without its anchor voided it.
            public bool Unreachable, Granted, Voided;
            public string FirstNonce = "";
            // Round 8, F31: team_series_first_game issues only to an ask whose
            // own Steam session was issued before the series was created (the
            // asking process was there when the series began); false is a
            // server without that rule.
            public bool ReadsSession = true;
            // Round 9, M1 (main.py, team_series_first_game and
            // _team_first_game_void; migration 362): the issue goes to ONE
            // process of the reporter's account. ReadsOthers: no issue while
            // another session of the requester's account was live after the
            // series was created (Issue). ReadsAnyPost: none while anything is
            // on the series' live-points record (`AnyPost`: a post reached the
            // server; false is round 8's AnyTwo). ReadsIssued: the session the
            // issue went to is kept (`FirstSession`); a match report sent on
            // another session voids the issue (Land), and a DC report the
            // reporter's account sends on another session reads no token
            // (Settles). All three false is round 8's issuance.
            public bool ReadsOthers = true, ReadsAnyPost = true, ReadsIssued = true;
            public bool AnyPost;
            // Round 9, M2: the kept copies of round 8's comparisons: a token
            // read by the issued nonce's first 8 digits alone (ReadsPrefix),
            // and a match report's anchor held to those 8 digits alone
            // (ReadsPrefixAnchor).
            public bool ReadsPrefix, ReadsPrefixAnchor;
            public string FirstSession = "";
            private readonly Dictionary<string, HashSet<string>> sessions =
                new Dictionary<string, HashSet<string>>(StringComparer.Ordinal);
            private readonly Dictionary<string, TokenRec> recs = new Dictionary<string, TokenRec>(StringComparer.Ordinal);

            private static string Key(int game, string room) { return Num(game) + "@" + room; }

            // Round 7, F29: a relock; the series' next sitting is `room`.
            public void Relock(string room)
            {
                Stored = room ?? "";
                Relocked = true;
            }

            // Round 9, M1: a Steam session of `account` live after the series
            // was created (issued before it and not expired by then, or issued
            // since). steam_sessions holds its row whether or not its process
            // ever sends a request of the series; "" is no session.
            public void Issue(string account, string session)
            {
                if (string.IsNullOrEmpty(session)) return;
                HashSet<string> held;
                if (!sessions.TryGetValue(account ?? "", out held))
                {
                    held = new HashSet<string>(StringComparer.Ordinal);
                    sessions[account ?? ""] = held;
                }
                held.Add(session);
            }

            private bool OtherSession(string account, string session)
            {
                HashSet<string> held;
                if (!sessions.TryGetValue(account ?? "", out held)) return false;
                foreach (string o in held) if (o != session) return true;
                return false;
            }

            // Round 8, F31: main.py's team_series_first_game. Issued once per
            // series, to the series' reporter, on a session issued before the
            // series was created (`born`: the asking process was there when the
            // series began), only while the series has no recorded game, was
            // never relocked, has no game on record in another room and no pair
            // of two points or more on its record, and only in its stored room;
            // `reason` says why not. Round 9, M1: an ask needs a verified
            // session (`session`; "" is none: a 401, no answer), and is refused
            // while another session of the requester's `account` was live after
            // the series was created (ReadsOthers) and while anything is on the
            // series' live-points record (ReadsAnyPost); the session it went to
            // is kept.
            public bool GrantFirst(string room, bool reporter, bool born, string account, string session,
                                   out string nonce, out string reason)
            {
                nonce = "";
                reason = null;
                if (Unreachable) reason = "no answer: the server cannot be reached";
                else if (string.IsNullOrEmpty(session)) reason = "no answer: the ask carries no verified session";
                else if (!reporter) reason = "the requester is not the series' reporter";
                else if (Recorded > 0) reason = "a game of the series is recorded";
                else if (Relocked) reason = "the series was relocked";
                else if (room != Stored) reason = "the requester's room is not the series' stored room";
                else if (Granted) reason = "physical game 1 was already issued for this series";
                else if (ReadsSession && !born) reason = "the requester's session was not issued before the series was created";
                else if (ReadsOthers && OtherSession(account, session))
                    reason = "another session of the requester's account was live after the series was created";
                else if (OtherRoom()) reason = "the series has a game on record in another room";
                else if (ReadsAnyPost && AnyPost) reason = "a live-points post is on the series' record";
                else if (!ReadsAnyPost && AnyTwo) reason = "a pair of two points or more is on the series' record";
                if (reason != null) return false;
                Granted = true;
                FirstNonce = DrawNonce();
                FirstSession = session;
                nonce = FirstNonce;
                return true;
            }

            // Round 8, F31: main.py's submit_team_match. A match report is
            // recorded; `anchor` is what the reporter's client held for the
            // series when it built the report ("" = none). One without the
            // issued anchor voids physical game 1 for good. Round 9, M1: so
            // does one sent on another session than the issued one (`session`:
            // the session of the process that sends it, "" none; ReadsIssued).
            public void Land(string anchor, string session)
            {
                Recorded++;
                if (!Granted || Voided) return;
                if (!AnchorHolds(anchor)) Voided = true;
                else if (ReadsIssued && (session ?? "") != FirstSession) Voided = true;
            }

            // Round 9, M2: whether a match report's anchor is the issued nonce,
            // the whole of it (ReadsPrefixAnchor: round 8's first 8 digits
            // alone, which an 8-digit anchor and any nonce sharing those
            // digits pass).
            private bool AnchorHolds(string anchor)
            {
                if (ReadsPrefixAnchor) return (anchor ?? "").Length >= 8 && anchor.Substring(0, 8) == FirstNonce.Substring(0, 8);
                return (anchor ?? "") == FirstNonce;
            }

            // Round 9, M2: whether a token's nonce is counted from the issued
            // physical game 1: the nonce derived for its ordinal and epoch
            // (ReadsPrefix: round 8's first 8 digits alone).
            private bool ChainHolds(string nonce, int ordinal, long epoch)
            {
                if (ReadsPrefix) return nonce.Substring(0, 8) == FirstNonce.Substring(0, 8);
                return nonce == ChainNonce(FirstNonce, ordinal, epoch);
            }

            public void File(int named, string room, string token, int team, bool two, int game)
            {
                if (Unreachable) return;
                // Round 9, M1: every post that reaches the server is on the
                // series' live-points record from then on, whatever game it
                // names (main.py, _TEAM_FIRST_GAME_ANY_POST_SQL: a row filed
                // under any game, or a point in its live totals, which are
                // raised by GREATEST and never reset).
                AnyPost = true;
                if (named < 1 || named != Recorded + 1 || room != Stored) return;
                TokenRec r;
                string key = Key(named, room);
                if (!recs.TryGetValue(key, out r)) { r = new TokenRec { Room = room }; recs[key] = r; }
                if (two) { r.AllTeams |= 1 << team; r.AllGames.Add(game); AnyTwo = true; }
                string nonce;
                int ordinal;
                long epoch;
                if (!TryParseToken(token, out nonce, out ordinal, out epoch)) return;
                if (ReadsOrdinals && ordinal != named) { r.Conflict = true; return; }
                if (r.Token.Length == 0) r.Token = nonce;
                if (nonce != r.Token) { r.Conflict = true; return; }
                if (two) { r.TokTeams |= 1 << team; r.TokGames.Add(game); }
            }

            // Whether a DC report naming `token`, processed now, settles;
            // `fromAnother`: from a post of a game other than `game`. The
            // report comes from a member other than the series' reporter.
            public bool Settles(string token, int game, out bool fromAnother)
            {
                return Settles(token, game, false, "", out fromAnother);
            }

            // Round 9, M1: the same, `byReporter` saying whether the report
            // comes from the series' reporter's account, sent on `session`.
            public bool Settles(string token, int game, bool byReporter, string session, out bool fromAnother)
            {
                fromAnother = false;
                // main.py's lead-forfeit reads the record only when the
                // remaining team already won a game of the series (the model
                // takes any recorded game as its win): none recorded, nothing
                // settles.
                if (Recorded < 1) return false;
                TokenRec r;
                string key = Key(Recorded + 1, Stored);
                if (!recs.TryGetValue(key, out r)) return false;
                List<int> from;
                if (ReadsTokens)
                {
                    string nonce;
                    int ordinal;
                    long epoch;
                    if (!TryParseToken(token, out nonce, out ordinal, out epoch)) return false;
                    if (ReadsOrdinals && ordinal != Recorded + 1) return false;
                    if (ReadsSitting && (Relocked || OtherRoom())) return false;
                    if (ReadsAnchor && (!Granted || Voided || !ChainHolds(nonce, ordinal, epoch))) return false;
                    if (ReadsAnchor && ReadsIssued && byReporter && (session ?? "") != FirstSession) return false;
                    if (r.Conflict || r.Token != nonce || r.TokTeams != 3) return false;
                    foreach (var kv in recs)
                        if (kv.Key != key && kv.Value.Token == nonce) return false;
                    from = r.TokGames;
                }
                else
                {
                    if (r.AllTeams != 3) return false;
                    from = r.AllGames;
                }
                foreach (int g in from) if (g != game) fromAnother = true;
                return true;
            }

            private bool OtherRoom()
            {
                foreach (var kv in recs)
                    if (kv.Value.Room != Stored) return true;
                return false;
            }
        }

        private sealed class TokenSeat
        {
            public Tracker T = new Tracker();
            public string View = "";     // the room's value as this seat holds it
            public int Team;
            public Score Live = Reset;   // this seat's scoreboard now
            // Round 7, F30: whether the game's own lifecycle ends this seat's
            // game (`Hooks`; false is a kept copy: a seat whose game over and
            // game start end nothing, round 6's Tracker without its time
            // bridge), and whether both hooks are attached (`HooksLive`,
            // TokenFor's gate).
            public bool Hooks = true, HooksLive = true;
            // Round 8, F31: this seat is the series' reporter (`Reporter`: the
            // lowest Steam ID of the four; its client sends the series' match
            // reports and asks for physical game 1), and the server it asks
            // (`Srv`; null: it never asks). The reporter client's durable
            // state, kept across a restart: the ledger's series it sent or
            // queued a report of (`Sent`) and the anchors of the issues it took
            // (`Anchors`), and the reports still in its outbox, oldest first
            // (`Outbox`, each the anchor it was built with).
            public bool Reporter;
            public TokenServer Srv;
            public readonly HashSet<string> Sent = new HashSet<string>(StringComparer.Ordinal);
            public readonly Dictionary<string, string> Anchors = new Dictionary<string, string>(StringComparer.Ordinal);
            public readonly List<string> Outbox = new List<string>();
            private string series = "";
            // Round 8, F31: this seat's process was there when the series was
            // created (its Steam session was issued before the series); a
            // restart is a new process, on a session issued after it.
            public bool Born = true;
            // Round 9, M1: the account this seat plays on (two seats of one
            // account would be two processes of it) and the Steam session its
            // process holds ("" = none was ever issued to it); a restart is a
            // new process on a new session, which the server then holds.
            public string Account = NewHarnessName("account"), Session = NewHarnessName("session");

            public void Read(string room, string v) { View = v; T.ObserveRoomToken(room, v); }

            // Round 7, F29: Photon's OnJoinedRoom, then this seat's first read
            // of the room's value `v`. Round 8, F31: which seat created the
            // room names nothing.
            public void Enter(string room, string v)
            {
                T.NoteRoomJoined(room);
                Read(room, v);
            }

            // Round 7, F29: a read of the series' state: its recorded games,
            // whether it was relocked, and whether a pair of two points or more
            // is on its record (`played`).
            public void Fetch(string series, int recorded, bool relocked, bool played)
            {
                T.ObserveRead(series, true, recorded, 0, true, relocked, played);
            }

            // Round 7, F29: the game restarted as a new process; nothing the
            // old one held survives but its durable files (round 8, F31: the
            // reporter's ledger and outbox), and its Steam session is a new
            // one, issued after the series was created.
            public void Restart()
            {
                T = new Tracker();
                View = "";
                series = "";
                Born = false;
                Session = NewHarnessName("session");
                if (Srv != null) Srv.Issue(Account, Session);
            }

            // Round 9, M1: this seat's account plays on in another process
            // that has held its own session (`session`) since before the series
            // was created, while the first one may live on elsewhere: nothing
            // the first one held here survives, and its ledger and outbox stay
            // with it.
            public void Twin(string session)
            {
                T = new Tracker();
                View = "";
                series = "";
                Born = true;
                Session = session ?? "";
            }

            // Round 7, F29: the game itself starts a game on this seat
            // (DoStartGame; round 7, F30: it ends a game this seat's tracker
            // is still in).
            public void GmStart(string room) { if (Hooks) T.OnGmStart(room); }

            // Round 7, F30: the game itself ends this seat's game
            // (GameOverTransition), in the step that shows the game over on its
            // scoreboard, whatever its watcher sees.
            public void GmOver() { if (Hooks) T.OnGmGameOver(); }

            // A poll tick: the score reads `s`, then the room's value. No time
            // passes for the Tracker (round 7, F30).
            public void Tick(string room, Score s)
            {
                Live = s;
                T.ObserveScore(s);
                T.ObserveRoomToken(room, View);
            }

            // The watcher's game start (at the game's first combat, or at its
            // first point), then its read of the room, then (round 8, F31) the
            // reporter's ask for physical game 1, answered at once
            // (GameStateWatcher.TryAskTeamFirstGame).
            public void Start(string series, string room)
            {
                string line;
                this.series = series ?? "";
                T.OnGameStart(series, room, Live, out line);
                T.ObserveRoomToken(room, View);
                Ask(series, room);
            }

            // Round 8, F31: the ask, and the answer taken (its anchor written
            // to the ledger first, as ApiClient.NoteTeamAnchor does).
            public void Ask(string series, string room)
            {
                if (Srv == null) return;
                int gen;
                string why;
                if (!T.AskFirstGame(series, room, Reporter, Clean(series), out gen, out why)) return;
                string nonce, reason;
                bool issued = Srv.GrantFirst(room, Reporter, Born, Account, Session, out nonce, out reason);
                if (issued && Clean(series)) Anchors[series ?? ""] = nonce;
                T.OnFirstGame(series, room, gen, issued, nonce, reason, Clean(series));
            }

            // Round 8, F31: the reporter client's ledger and outbox hold no
            // report of the series (ApiClient.TeamReportsClean: no team report
            // of any series in the outbox).
            public bool Clean(string series) { return !Sent.Contains(series ?? "") && Outbox.Count == 0; }

            // The game's own game over on this seat, then the watcher's: the
            // tick that reads the final score, then its game over. Round 8,
            // F31: the reporter's client then sends the game's report, written
            // to its ledger first and built with the anchor its ledger holds for
            // the series; returns that anchor ("" = none), or null when this
            // seat sends no report. The model lands it (TokenServer.Land) or
            // queues it (Outbox).
            public string Over(string room)
            {
                GmOver();
                Tick(room, Final);
                T.OnTokenGameOver(room, View);
                if (!Reporter || series.Length == 0) return null;
                Sent.Add(series);
                string a;
                return Anchors.TryGetValue(series, out a) ? a : "";
            }

            public string Token(string series, string room) { return T.TokenFor(series, room, View, Live, HooksLive); }

            public void Post(TokenServer srv, string series, string room, bool two, int game)
            {
                srv.File(T.For(series, room), room, Token(series, room), Team, two, game);
            }
        }

        private sealed class TokenTally
        {
            public int Timelines, Settled, FromAnother, Clean, CleanSettled;
        }

        private const int Rep2BeforeStart = 0, Rep2AfterPosts = 1, Rep2AfterDc = 2, Rep2Never = 3;
        private const int ReachesInGame2 = 0, ReachesBeforeStart = 1, ReachesAfterStart = 2, ReachesNever = 3;

        // Round 7, F29: the game itself starts a game on each of `seats`
        // (DoStartGame), before their watchers do.
        private static void Rematch(string room, params TokenSeat[] seats)
        {
            foreach (var s in seats) s.GmStart(room);
        }

        // A seat's game start: its poll reads the reset, then the watcher starts
        // the game at its first combat.
        private static void SeatStart(TokenSeat s, string series, string room)
        {
            s.Tick(room, Reset);
            s.Start(series, room);
        }

        // The host's game start: a seat's, then its publish when due. Returns
        // the room's value after it. `countSeed` is a kept copy of the rule
        // round 7 removed (F29): a host holding no physical game publishes the
        // game its posts name, the server's count.
        private static string HostStart(TokenSeat h, string series, string room, string value, bool sent,
                                        bool countSeed = false)
        {
            SeatStart(h, series, room);
            string why;
            string tok = h.T.TokenToPublish(true, true, h.View, out why);
            if (tok.Length == 0 && countSeed && why == WhyNoOrdinal && h.T.For(series, room) > 0)
            {
                string n;
                int o;
                long e;
                long above = TryParseToken(h.View, out n, out o, out e) ? e : 0;
                tok = MakeToken(DrawNonce(), h.T.For(series, room), above + 1);
            }
            if (tok.Length == 0 || !sent) return value;
            h.T.ArmPublished(tok);
            return tok;
        }

        // Round 8, F31: the reporter's publish when it is not the room's host:
        // the token of the physical game 1 the server issued it (TokenToPublish
        // publishes that one host or not; every other token is the host's).
        // Returns the room's value after it.
        private static string ReporterPublish(TokenSeat s, string value, bool sent)
        {
            string why;
            string tok = s.T.TokenToPublish(false, true, s.View, out why);
            if (tok.Length == 0 || !sent) return value;
            s.T.ArmPublished(tok);
            return tok;
        }

        // Round 8, F31: the kept copy of round 7's creator boot. The room's
        // creator and host, holding no physical game at its game start in a
        // room it created, names that game physical game 1 because a read
        // shows the series with no recorded game, never relocked and no pair of
        // two points on its record (the caller calls it only then), and
        // publishes it with a fresh nonce (round 7's TryBoot and draw).
        // Returns the room's value after it.
        private static string KeptBoot(TokenSeat h, string value)
        {
            string why;
            if (h.T.PhysicalOrdinal() != 0 || h.T.TokenToPublish(true, true, h.View, out why) != "" || why != WhyNoOrdinal)
                return value;
            string n;
            int o;
            long e;
            long above = TryParseToken(h.View, out n, out o, out e) ? e : 0;
            string tok = MakeToken(DrawNonce(), 1, above + 1);
            h.T.ArmPublished(tok);
            return tok;
        }

        private static void SimulateToken(bool readsTokens, bool g1Sent, int rep2, bool sent, int reaches, bool echo,
                                          bool missed, int reached, bool hostReports, TokenTally tally)
        {
            const string S = "series-t", R = "room-t";
            var srv = new TokenServer { ReadsTokens = readsTokens, ReadsOrdinals = readsTokens, ReadsSitting = readsTokens,
                                        ReadsAnchor = readsTokens,
                                        Stored = R };
            var h = new TokenSeat { Team = 0, Reporter = true, Srv = srv };
            var p = new TokenSeat { Team = 1 };
            string value = "";
            tally.Timelines++;
            h.Enter(R, value);
            p.Enter(R, value);
            h.Fetch(S, 0, false, srv.AnyTwo);
            p.Fetch(S, 0, false, srv.AnyTwo);
            // Games 1 and 2: the value reaches both seats before their posts;
            // game 1's report lands, and both seats read the count, before game
            // 2 starts.
            for (int g = 1; g <= 2; g++)
            {
                Rematch(R, h, p);
                value = HostStart(h, S, R, value, g == 2 || g1Sent);
                SeatStart(p, S, R);
                h.Read(R, value);
                p.Read(R, value);
                h.Tick(R, TwoEach);
                p.Tick(R, TwoEach);
                h.Post(srv, S, R, true, g);
                p.Post(srv, S, R, true, g);
                h.Tick(R, Later);
                p.Tick(R, Later);
                if (g == 2) break;
                h.Over(R);
                p.Over(R);
                srv.Recorded = 1;
                h.Fetch(S, 1, false, srv.AnyTwo);
                p.Fetch(S, 1, false, srv.AnyTwo);
            }
            // Game 2 ends: the host's game over first, and the game ends it on
            // P too (round 7, F30: GameOverTransition, whatever P's watcher
            // sees). Game 3 starts on both seats (P's watcher may still be in
            // its game 2).
            h.Over(R);
            p.GmOver();
            if (rep2 == Rep2BeforeStart) srv.Recorded = 2;
            h.Fetch(S, srv.Recorded, false, srv.AnyTwo);
            Rematch(R, h, p);
            bool hostStarted = false;
            if (reaches == ReachesInGame2)
            {
                value = HostStart(h, S, R, value, sent);
                hostStarted = true;
                if (echo) h.Read(R, value);
                p.Read(R, value);
            }
            if (!missed)
            {
                p.Over(R);
                p.Fetch(S, srv.Recorded, false, srv.AnyTwo);
            }
            if (!hostStarted)
            {
                value = HostStart(h, S, R, value, sent);
                if (echo) h.Read(R, value);
            }
            if (reaches == ReachesBeforeStart) p.Read(R, value);
            // P's game 3: its start, or (it missed the boundary) only its poll,
            // which reads game 3's reset inside its game 2.
            if (missed) p.Tick(R, Reset);
            else SeatStart(p, S, R);
            if (reaches == ReachesAfterStart) p.Read(R, value);
            if (reached > 0)
            {
                Score g3 = reached == 2 ? TwoEach : Played;
                h.Tick(R, g3);
                p.Tick(R, g3);
                h.Post(srv, S, R, reached == 2, 3);
                p.Post(srv, S, R, reached == 2, 3);
            }
            if (rep2 == Rep2AfterPosts) srv.Recorded = 2;
            TokenSeat reporter = hostReports ? h : p;
            bool fromAnother;
            bool settled = srv.Settles(reporter.Token(S, R), 3, reporter.Reporter, reporter.Session, out fromAnother);
            if (settled) tally.Settled++;
            if (settled && (fromAnother || reached < 2)) tally.FromAnother++;
            bool clean = rep2 == Rep2BeforeStart && sent && echo && !missed && reached == 2 && reaches != ReachesNever;
            if (clean)
            {
                tally.Clean++;
                if (settled) tally.CleanSettled++;
            }
        }

        private static TokenTally SweepToken(bool readsTokens)
        {
            var tally = new TokenTally();
            for (int g1 = 0; g1 < 2; g1++)
            for (int rep2 = 0; rep2 < 4; rep2++)
            for (int sent = 0; sent < 2; sent++)
            for (int reaches = 0; reaches < 4; reaches++)
            for (int echo = 0; echo < 2; echo++)
            for (int missed = 0; missed < 2; missed++)
            for (int reached = 0; reached < 3; reached++)
            for (int hostReports = 0; hostReports < 2; hostReports++)
                SimulateToken(readsTokens, g1 != 0, rep2, sent != 0, reaches, echo != 0, missed != 0, reached,
                              hostReports != 0, tally);
            return tally;
        }

        // ---- Round 6, finding F27: seats a game apart ------------------------
        //
        // The reviewer's scenario on three real Trackers: the room's host H
        // (team 1) and the opposite team's contributor C (team 2), a game
        // behind, and the reporter A (team 1). Team 1 leads 1-0, and game 2's
        // result stays queued, so the server is in game 2 and every seat's
        // posts name game 2. When A is AHEAD, A plays its game 2 before the
        // host starts game 2 (the room still holds game 1's token, stale for
        // A) and starts game 3; H then publishes game 2's token at its own game
        // 2 start, H and C file game 2's crossing under it, and A reads it
        // inside its game 3. A team-2 player leaves in A's game and A reports.
        // What varies: A ahead or LEVEL (A plays game 2 with H and C: the
        // control), A's score at the DC (0-0 as the report has it, its first
        // point, two points), whether game 2's result lands before the DC,
        // whether H catches up and publishes game 3's token before the DC, and
        // whether C's watcher starts game 2 late, well after the host's, with
        // C reading game 2's token inside its own game 1 (#182: a late hook must still
        // take its game's token). The invariant: nothing settles from a post of
        // a physical game other than the one A's DC is in. The liveness check:
        // level, two points each in the DC's game, nothing else moved: it
        // settles, late hook or not.

        private const int DcAtReset = 0, DcAtPoint = 1, DcAtTwo = 2;

        private sealed class F27Tally
        {
            public int Timelines, Settled, FromAnother, Live, LiveSettled;
        }

        private static bool SimulateF27(bool ahead, int dcAt, bool rep2Lands, bool catchUp, bool lateHook,
                                        out bool fromAnother, out string sent)
        {
            const string S = "series-f27", R = "room-f27";
            var srv = new TokenServer { ReadsTokens = true, ReadsOrdinals = true, ReadsSitting = true, ReadsAnchor = true, Stored = R };
            var h = new TokenSeat { Team = 0, Reporter = true, Srv = srv };
            var c = new TokenSeat { Team = 1 };
            var a = new TokenSeat { Team = 0 };
            var all = new[] { h, c, a };
            string value = "";
            h.Enter(R, value);
            c.Enter(R, value);
            a.Enter(R, value);
            foreach (var x in all) x.Fetch(S, 0, false, srv.AnyTwo);
            // Game 1, seen by every seat, and recorded: team 1 leads 1-0.
            Rematch(R, all);
            value = HostStart(h, S, R, value, true);
            SeatStart(c, S, R);
            SeatStart(a, S, R);
            foreach (var x in all) { x.Read(R, value); x.Tick(R, TwoEach); x.Post(srv, S, R, true, 1); x.Tick(R, Later); }
            h.Over(R);
            a.Over(R);
            if (!lateHook) c.Over(R);
            else c.GmOver();   // round 7, F30: the game ends game 1 on C; its watcher is late
            srv.Recorded = 1;
            h.Fetch(S, 1, false, srv.AnyTwo);
            a.Fetch(S, 1, false, srv.AnyTwo);
            if (!lateHook) c.Fetch(S, 1, false, srv.AnyTwo);
            if (ahead)
            {
                Rematch(R, a);
                SeatStart(a, S, R);
                a.Tick(R, TwoEach);
                a.Post(srv, S, R, true, 2);
                a.Tick(R, Later);
                a.Over(R);
                a.Fetch(S, srv.Recorded, false, srv.AnyTwo);
                Rematch(R, a);
                SeatStart(a, S, R);
            }
            // The host's game 2 start (a game behind A when A is ahead), its
            // publish and its echo. The game itself starts game 2 on H and C
            // (C's watcher, with a late hook, still in its game 1).
            Rematch(R, h, c);
            if (!ahead) Rematch(R, a);
            value = HostStart(h, S, R, value, true);
            h.Read(R, value);
            if (lateHook)
            {
                c.Read(R, value);
                c.Over(R);
                c.Fetch(S, 1, false, srv.AnyTwo);
                c.Tick(R, Reset);
            }
            SeatStart(c, S, R);
            c.Read(R, value);
            if (!ahead) SeatStart(a, S, R);
            a.Read(R, value);
            // Game 2's crossing under the host's token.
            h.Tick(R, TwoEach);
            h.Post(srv, S, R, true, 2);
            c.Tick(R, TwoEach);
            c.Post(srv, S, R, true, 2);
            int aGame = ahead ? 3 : 2;
            Score dc = !ahead ? TwoEach : dcAt == DcAtReset ? Reset : dcAt == DcAtPoint ? Played : TwoEach;
            a.Tick(R, dc);
            if (!dc.AllZero) a.Post(srv, S, R, dc.P1 + dc.P2 >= 2, aGame);
            if (rep2Lands)
            {
                srv.Recorded = 2;
                foreach (var x in all) x.Fetch(S, 2, false, srv.AnyTwo);
            }
            if (catchUp)
            {
                h.Tick(R, Later);
                h.Over(R);
                h.Fetch(S, srv.Recorded, false, srv.AnyTwo);
                Rematch(R, h);
                value = HostStart(h, S, R, value, true);
                h.Read(R, value);
                c.Read(R, value);
                a.Read(R, value);
            }
            a.Tick(R, dc);
            sent = a.Token(S, R);
            return srv.Settles(sent, aGame, out fromAnother);
        }

        private static F27Tally SweepF27()
        {
            var tally = new F27Tally();
            for (int ahead = 0; ahead < 2; ahead++)
            for (int dcAt = ahead == 0 ? DcAtTwo : DcAtReset; dcAt <= DcAtTwo; dcAt++)
            for (int rep2 = 0; rep2 < 2; rep2++)
            for (int catchUp = 0; catchUp < 2; catchUp++)
            for (int late = 0; late < 2; late++)
            {
                bool fromAnother;
                string sent;
                bool settled = SimulateF27(ahead != 0, dcAt, rep2 != 0, catchUp != 0, late != 0, out fromAnother, out sent);
                tally.Timelines++;
                if (settled) tally.Settled++;
                // A's game has two points from team 1 only when A is ahead: any
                // settlement there is read from game 2's posts.
                if (settled && (fromAnother || ahead != 0)) tally.FromAnother++;
                if (ahead == 0 && rep2 == 0 && catchUp == 0)
                {
                    tally.Live++;
                    if (settled && !fromAnother) tally.LiveSettled++;
                }
            }
            return tally;
        }

        // ---- Round 6, finding F28: a boundary the reporter did not see --------
        //
        // The reviewer's scenario on three real Trackers: the room's host H
        // (team 1), P (team 2) and the reporter R (team 1). Team 1 leads 1-0;
        // game 2 crosses two points each under the host's token, and its
        // result stays queued. R's last reading of the score is in game 2 (two
        // points in its first round, or deep in it). Game 2 ends and game 3
        // starts in the room; R sees none of it (no game over, no game start,
        // no poll tick); a team-2 player leaves and R's DC report is built at
        // once. What varies: R's last reading; the score R reads when the
        // report is built (game 3's reset, its first point, its first round
        // won; or NO boundary: game 2 is still going); how the gap since R's
        // last reading passed (a short one; R's main thread frozen; R's polls
        // reading a game frozen by a silent transport: round 7, finding F30,
        // reads no time, so a gap's length is nothing to the Tracker); whether
        // the host published game 3's token first (R's read of the room then
        // shows it); which of R's watcher's lifecycle events reached it first
        // (none, the game over, the game over and game 3's start); and whether
        // a poll tick ran first. The game itself ends game 2 and starts game 3
        // on every seat, R included, whatever its watcher saw (R's scoreboard
        // cannot show game 3 otherwise: TeamGameLifecycle). The invariant
        // (round 7, F30): across a boundary R's report carries no token and
        // nothing settles, in every shape; round 6's residual shape (a score
        // that follows R's last reading inside one game, with the room still
        // holding the token and nothing else reaching R's watcher) is counted
        // with the rest. `hooks` false is the kept copy: R's own game over and
        // game start end nothing at the boundary, and the residual shape must
        // come back, or the sweep proves nothing. The liveness checks: with no
        // boundary R's report carries game 2's token, after a short gap and
        // after a long one.

        private const int AtReset = 0, AtPoint = 1, AtRoundUp = 2, AtNoBoundary = 3;
        private const int GapPoll = 0, GapFreeze = 1, GapStall = 2;
        private const int LifeNone = 0, LifeOver = 1, LifeOverAndStart = 2;

        private sealed class F28Tally
        {
            public int Timelines, Across, SettledAcross, Carry, Carried, CarryGap, CarriedGap;
        }

        private static string SimulateF28(bool deep, int at, int gapKind, bool published, int life, bool pollFirst,
                                          bool hooks, out bool settled, out bool fromAnother)
        {
            const string S = "series-f28", R = "room-f28";
            var srv = new TokenServer { ReadsTokens = true, ReadsOrdinals = true, ReadsSitting = true, ReadsAnchor = true, Stored = R };
            var h = new TokenSeat { Team = 0, Reporter = true, Srv = srv };
            var p = new TokenSeat { Team = 1 };
            var r = new TokenSeat { Team = 0 };
            var all = new[] { h, p, r };
            string value = "";
            h.Enter(R, value);
            p.Enter(R, value);
            r.Enter(R, value);
            foreach (var x in all) x.Fetch(S, 0, false, srv.AnyTwo);
            Rematch(R, all);
            value = HostStart(h, S, R, value, true);
            SeatStart(p, S, R);
            SeatStart(r, S, R);
            foreach (var x in all) { x.Read(R, value); x.Tick(R, TwoEach); x.Post(srv, S, R, true, 1); x.Tick(R, Later); }
            foreach (var x in all) { x.Over(R); x.Fetch(S, 1, false, srv.AnyTwo); }
            srv.Recorded = 1;
            Rematch(R, all);
            value = HostStart(h, S, R, value, true);
            SeatStart(p, S, R);
            SeatStart(r, S, R);
            foreach (var x in all) { x.Read(R, value); x.Tick(R, TwoEach); x.Post(srv, S, R, true, 2); }
            Score last = deep ? Later : TwoEach;
            r.Tick(R, last);
            bool boundary = at != AtNoBoundary;
            Score callback = at == AtReset ? Reset : at == AtPoint ? Played : at == AtRoundUp ? RoundUp
                             : (deep ? Continue : RoundUp);
            // The gap: no reading of R's (a short gap, or R's main thread
            // frozen: the two are one to a Tracker that reads no time), or R's
            // polls reading game 2's last score again and again (a game frozen
            // by a silent transport).
            if (gapKind == GapStall)
                for (int i = 1; i <= 60; i++) r.Tick(R, last);
            if (boundary)
            {
                // Game 2 ends on every seat (the game's own game over, on P and
                // R too, whatever their watchers see) and the host starts game
                // 3; the game starts it on R before R reads its score.
                r.Hooks = hooks;
                h.Tick(R, last);
                h.Over(R);
                p.GmOver();
                r.GmOver();
                h.Fetch(S, 1, false, srv.AnyTwo);
                Rematch(R, h, p);
                value = HostStart(h, S, R, value, published);
                r.View = value;
                if (life >= LifeOver) { r.Over(R); r.Fetch(S, 1, false, srv.AnyTwo); }
                Rematch(R, r);
                if (life == LifeOverAndStart) SeatStart(r, S, R);
            }
            if (pollFirst) r.Tick(R, callback);
            r.Live = callback;
            string sent = r.Token(S, R);
            settled = srv.Settles(sent, boundary ? 3 : 2, out fromAnother);
            return sent;
        }

        private static F28Tally SweepF28(bool hooks)
        {
            var tally = new F28Tally();
            for (int deep = 0; deep < 2; deep++)
            for (int at = 0; at < 4; at++)
            for (int gap = 0; gap < 3; gap++)
            for (int pub = 0; pub < 2; pub++)
            for (int life = 0; life < 3; life++)
            for (int poll = 0; poll < 2; poll++)
            {
                // With no boundary nothing was published and nothing happened.
                if (at == AtNoBoundary && (pub != 0 || life != LifeNone)) continue;
                bool settled, fromAnother;
                string sent = SimulateF28(deep != 0, at, gap, pub != 0, life, poll != 0, hooks, out settled,
                                          out fromAnother);
                tally.Timelines++;
                if (at != AtNoBoundary)
                {
                    // Round 7, F30: every token sent across a boundary counts,
                    // in every shape, and so does every settlement.
                    if (sent.Length > 0 || settled) tally.Across++;
                    if (settled) tally.SettledAcross++;
                }
                else if (gap == GapPoll)
                {
                    tally.Carry++;
                    if (sent.Length > 0 && settled && !fromAnother) tally.Carried++;
                }
                else
                {
                    // Round 7, F30: no gap withholds a token either.
                    tally.CarryGap++;
                    if (sent.Length > 0 && settled && !fromAnother) tally.CarriedGap++;
                }
            }
            return tally;
        }

        // ---- Round 7, finding F30: no time or score bridges a boundary --------
        //
        // The reviewer's scenario, round 6's residual shape, on three real
        // Trackers: the room's host H (team 1), P (team 2) and the reporter R
        // (team 1). Team 1 leads 1-0; game 2 crosses one point each under the
        // host's token T2, and its result stays queued; R's last reading is
        // that crossing. Game 2 ends and game 3 starts: no game over, game
        // start or poll tick of R's watcher runs, and the host publishes
        // nothing, so the room still holds T2. R reads game 3's first round won
        // (a score that follows its last reading inside one game) when a
        // team-2 player leaves, and builds its report at once. The game itself
        // ended game 2 and started game 3 on R (its scoreboard cannot show game
        // 3 otherwise), and that ends R's token: none is sent and nothing
        // settles. `hooks` false is the kept copy, a seat whose game over and
        // game start end nothing (round 6's Tracker without its time bridge):
        // it must send T2 and settle game 3's leave from game 2's posts, or the
        // scenario proves nothing; with `hooksLive` false as well (the hooks
        // not attached) nothing is sent at all. `fresh` is the control: game
        // 2's result lands, R's watcher sees game 2 end and game 3 start, the
        // host publishes game 3's token, every seat takes it and game 3
        // crosses under it: R's report carries game 3's token and settles game
        // 3 from game 3's posts. `heldT2`: R carried T2 before the boundary.

        private static string SimulateF30(bool hooks, bool hooksLive, bool fresh, out bool settled,
                                          out bool fromAnother, out bool heldT2)
        {
            const string S = "series-f30", R = "room-f30";
            var srv = new TokenServer { ReadsTokens = true, ReadsOrdinals = true, ReadsSitting = true, ReadsAnchor = true, Stored = R };
            var h = new TokenSeat { Team = 0, Reporter = true, Srv = srv };
            var p = new TokenSeat { Team = 1 };
            var r = new TokenSeat { Team = 0 };
            var all = new[] { h, p, r };
            string value = "";
            h.Enter(R, value);
            p.Enter(R, value);
            r.Enter(R, value);
            foreach (var x in all) x.Fetch(S, 0, false, srv.AnyTwo);
            for (int g = 1; g <= 2; g++)
            {
                Rematch(R, all);
                value = HostStart(h, S, R, value, true);
                SeatStart(p, S, R);
                SeatStart(r, S, R);
                foreach (var x in all) { x.Read(R, value); x.Tick(R, TwoEach); x.Post(srv, S, R, true, g); }
                if (g == 2) break;
                foreach (var x in all) { x.Tick(R, Later); x.Over(R); x.Fetch(S, 1, false, srv.AnyTwo); }
                srv.Recorded = 1;
            }
            heldT2 = value.Length > 0 && r.Token(S, R) == value;
            r.Hooks = hooks;
            r.HooksLive = hooksLive;
            if (fresh)
            {
                foreach (var x in all) { x.Tick(R, Later); x.Over(R); }
                srv.Recorded = 2;
                foreach (var x in all) x.Fetch(S, 2, false, srv.AnyTwo);
                Rematch(R, all);
                value = HostStart(h, S, R, value, true);
                SeatStart(p, S, R);
                SeatStart(r, S, R);
                foreach (var x in all) { x.Read(R, value); x.Tick(R, TwoEach); x.Post(srv, S, R, true, 3); }
            }
            else
            {
                h.Tick(R, Later);
                h.Over(R);
                p.GmOver();
                r.GmOver();
                h.Fetch(S, 1, false, srv.AnyTwo);
                Rematch(R, h, p, r);
                value = HostStart(h, S, R, value, false);
                r.View = value;
            }
            r.Live = RoundUp;
            string sent = r.Token(S, R);
            settled = srv.Settles(sent, 3, out fromAnother);
            return sent;
        }

        // ---- Round 7, finding F30: the sweep of missed signals --------------
        //
        // The reviewer's scenario generalized, on the same three Trackers and
        // the same game 2 (its crossing under the host's token T2 posted, R's
        // last reading that crossing). At the boundary every signal that can
        // reach R varies: which of the game's own lifecycle calls runs on R
        // (both; the game over only; game 3's start only: each alone must end
        // the token, so neither void rests on the other); which of R's
        // watcher's events arrive (none, the game over, game 3's start, both);
        // the room's value as R reads it (the host published nothing, so the
        // room still holds T2; the host published game 3's token and R read
        // it; the host published it and R's read still shows T2, a new-token
        // signal that has not reached R); whether a poll tick runs before the
        // report; R's scoreboard when the report is built (game 3's one point
        // each, identical to R's last reading in game 2; its first round won;
        // deep in it: all three follow that reading inside one game; its
        // reset; its first point); and whether game 2's result landed before
        // game 3 started. The invariant: in every timeline, no token but game
        // 3's own publish is sent in game 3, and nothing settles (game 3's
        // posts are never filed here, so any settlement is game 3's leave
        // settled from game 2's posts). Liveness: game 3's own token is
        // carried exactly where it is due (the game reported R's game 3
        // start, R's watcher saw it, R read the host's publish, game 2's
        // result landed so R's posts name game 3, and R's scoreboard shows a
        // point of game 3), and nowhere else. `hooks` false is the kept copy
        // (R's game over and game start end nothing): tokens of game 2 must
        // be sent and settled in game 3, or the sweep proves nothing. With
        // `hooksLive` false as well (a hook not attached: nothing ends R's
        // game and TokenFor's gate is shut) nothing is sent at all.

        private const int F30GmBoth = 0, F30GmOverOnly = 1, F30GmStartOnly = 2;
        private const int F30WatchNone = 0, F30WatchOver = 1, F30WatchStart = 2, F30WatchBoth = 3;
        private const int F30RoomStill = 0, F30RoomRead = 1, F30RoomLagging = 2;
        private const int F30AtCount = 5, F30AtReset = 3;

        private sealed class F30Tally
        {
            public int Timelines, Sent, Across, Settled, FromAnother, Fresh, FreshDue, FreshMissed;
        }

        // R's scoreboard when the report is built.
        private static Score F30Now(int at)
        {
            return at == 0 ? TwoEach : at == 1 ? RoundUp : at == 2 ? Later : at == F30AtReset ? Reset : Played;
        }

        private static string SimulateF30Sweep(int gm, int watch, int roomKind, bool pollFirst, int at, bool landed,
                                               bool hooks, bool hooksLive, out string t2, out string t3,
                                               out bool settled, out bool fromAnother)
        {
            const string S = "series-f30s", R = "room-f30s";
            var srv = new TokenServer { ReadsTokens = true, ReadsOrdinals = true, ReadsSitting = true, ReadsAnchor = true, Stored = R };
            var h = new TokenSeat { Team = 0, Reporter = true, Srv = srv };
            var p = new TokenSeat { Team = 1 };
            var r = new TokenSeat { Team = 0 };
            var all = new[] { h, p, r };
            string value = "";
            h.Enter(R, value);
            p.Enter(R, value);
            r.Enter(R, value);
            foreach (var x in all) x.Fetch(S, 0, false, srv.AnyTwo);
            for (int g = 1; g <= 2; g++)
            {
                Rematch(R, all);
                value = HostStart(h, S, R, value, true);
                SeatStart(p, S, R);
                SeatStart(r, S, R);
                foreach (var x in all) { x.Read(R, value); x.Tick(R, TwoEach); x.Post(srv, S, R, true, g); }
                if (g == 2) break;
                foreach (var x in all) { x.Tick(R, Later); x.Over(R); x.Fetch(S, 1, false, srv.AnyTwo); }
                srv.Recorded = 1;
            }
            t2 = value;
            r.Hooks = hooks;
            r.HooksLive = hooksLive;
            // Game 2 ends. The game ends it on the host and P; on R its own game
            // over runs unless this timeline has only its start, and R's
            // watcher sees the game over (its poll reads the final score, then
            // its game over) only when this timeline says so.
            h.Tick(R, Later);
            h.Over(R);
            p.GmOver();
            if (gm != F30GmStartOnly) r.GmOver();
            if (watch == F30WatchOver || watch == F30WatchBoth)
            {
                r.Tick(R, Final);
                r.T.OnTokenGameOver(R, r.View);
            }
            if (landed)
            {
                srv.Recorded = 2;
                foreach (var x in all) x.Fetch(S, 2, false, srv.AnyTwo);
            }
            else h.Fetch(S, 1, false, srv.AnyTwo);
            // Game 3 starts. The game starts it on the host and P, and on R
            // unless this timeline has only its game over; the host publishes
            // game 3's token unless the room still holds T2; R's read of the
            // room shows it, or still shows T2.
            Rematch(R, h, p);
            if (gm != F30GmOverOnly) r.GmStart(R);
            value = HostStart(h, S, R, value, roomKind != F30RoomStill);
            t3 = value != t2 ? value : "";
            r.View = roomKind == F30RoomRead ? value : t2;
            if (watch == F30WatchStart || watch == F30WatchBoth) SeatStart(r, S, R);
            Score now = F30Now(at);
            if (pollFirst) r.Tick(R, now);
            r.Live = now;
            string sent = r.Token(S, R);
            settled = srv.Settles(sent, 3, out fromAnother);
            return sent;
        }

        private static F30Tally SweepF30(bool hooks, bool hooksLive)
        {
            var tally = new F30Tally();
            for (int gm = 0; gm < 3; gm++)
            for (int watch = 0; watch < 4; watch++)
            for (int room = 0; room < 3; room++)
            for (int poll = 0; poll < 2; poll++)
            for (int at = 0; at < F30AtCount; at++)
            for (int landed = 0; landed < 2; landed++)
            {
                string t2, t3;
                bool settled, fromAnother;
                string sent = SimulateF30Sweep(gm, watch, room, poll != 0, at, landed != 0, hooks, hooksLive, out t2,
                                               out t3, out settled, out fromAnother);
                tally.Timelines++;
                if (sent.Length > 0) tally.Sent++;
                // Every token sent in game 3 but game 3's own publish crossed
                // the boundary, and so did every settlement.
                bool fresh = t3.Length > 0 && sent == t3;
                if ((sent.Length > 0 && !fresh) || settled) tally.Across++;
                if (settled) tally.Settled++;
                if (settled && fromAnother) tally.FromAnother++;
                if (fresh) tally.Fresh++;
                bool due = hooks && hooksLive && gm != F30GmOverOnly
                           && (watch == F30WatchStart || watch == F30WatchBoth)
                           && room == F30RoomRead && landed != 0 && at != F30AtReset;
                if (!due) continue;
                tally.FreshDue++;
                if (!fresh) tally.FreshMissed++;
            }
            return tally;
        }

        // ---- Round 7, finding F29: seats re-anchored while a result is queued -
        //
        // The reviewer's scenario on three real Trackers: the room's host H
        // (team 1, the room's creator and master, and the series' reporter,
        // which the server issued physical game 1) and team 2's C and R (R
        // reports the leave). Games 1 and 2 are played and
        // recorded (1-1). Game 3 crosses, under the host's token or with its
        // publish not sent, and team 1 wins it; its result is QUEUED (the
        // server still counts two games) or, in the in-step control, recorded,
        // and every seat reads the series. Before game 4 seats re-anchor: a
        // rejoin of the same room by any nonempty set of the three (a
        // rejoining host hands the master to the first seat that stayed, C
        // when none did); the whole series moved to a new room the host
        // creates (a relock); or every seat gone and the host creating the
        // same room again (its properties gone with it). Each re-anchored seat
        // is the same process or a restarted one, and reads the series again.
        // The game itself starts game 4 on every seat, its master publishes
        // when TokenToPublish lets it, both teams' seats post two points each,
        // a team-1 player leaves, and R reports it. The invariant: nothing
        // settles while game 3's result is queued (the server would settle
        // game 3 from game 4's posts), and no seat carries a token then. The
        // liveness check: nothing queued and a rejoin that left a seat in
        // place, which holds the room's physical game and publishes as the
        // master: the report settles, the re-anchored seats taking the
        // master's publish. The same sweep with round 6's host seed restored as
        // a kept copy (a master holding no physical game publishes the game its
        // posts name) must settle while queued, or it could not see F29; with
        // the server's sitting rule off as well, the room change settles too.
        // Both kept copies run against a server without round 8's anchor rule
        // (`readsAnchor` false), which alone refuses every token the kept seed
        // draws (a fresh nonce, not counted from the issued game 1); with the
        // anchor rule the kept copy settles nothing while queued.

        private const int KindRejoin = 0, KindRoomChange = 1, KindRecreate = 2;

        private sealed class F29Tally
        {
            public int Timelines, Settled, Wrong, Carrying, ReanchoredCarrying, Live, LiveSettled;
        }

        private static bool SimulateF29(int kind, int mask, bool queued, bool restart, bool g3Sent, bool countSeed,
                                        bool readsSitting, bool readsAnchor, out bool wrong, out int carrying,
                                        out int reanchoredCarrying)
        {
            const string S = "series-f29", R1 = "room-f29", R2 = "room-f29-next";
            var srv = new TokenServer { ReadsTokens = true, ReadsOrdinals = true, ReadsSitting = readsSitting,
                                        ReadsAnchor = readsAnchor, Stored = R1 };
            var h = new TokenSeat { Team = 0, Reporter = true, Srv = srv };
            var c = new TokenSeat { Team = 1 };
            var r = new TokenSeat { Team = 1 };
            var all = new[] { h, c, r };
            string room = R1, value = "";
            h.Enter(room, value);
            c.Enter(room, value);
            r.Enter(room, value);
            foreach (var x in all) x.Fetch(S, 0, false, srv.AnyTwo);
            // Games 1 to 3, seen by every seat, each under the host's token
            // (game 3's when its publish is sent).
            for (int g = 1; g <= 3; g++)
            {
                Rematch(room, all);
                value = HostStart(h, S, room, value, g < 3 || g3Sent);
                SeatStart(c, S, room);
                SeatStart(r, S, room);
                foreach (var x in all) { x.Read(room, value); x.Tick(room, TwoEach); x.Post(srv, S, room, true, g); x.Tick(room, Later); }
                foreach (var x in all) x.Over(room);
                if (g < 3 || !queued) srv.Recorded = g;
                foreach (var x in all) x.Fetch(S, srv.Recorded, false, srv.AnyTwo);
            }
            // The re-anchor.
            var re = new bool[3];
            int master = 0;
            if (kind == KindRejoin)
            {
                for (int k = 0; k < 3; k++) re[k] = ((mask >> k) & 1) != 0;
                master = !re[0] ? 0 : !re[1] ? 1 : !re[2] ? 2 : 1;
            }
            else
            {
                // Every seat left. The host creates the room the seats join
                // (the new sitting's, or the same name again) and is its master;
                // the room holds no value yet.
                if (kind == KindRoomChange)
                {
                    srv.Relock(R2);
                    room = R2;
                }
                value = "";
                for (int k = 0; k < 3; k++) re[k] = true;
            }
            for (int k = 0; k < 3; k++)
            {
                if (!re[k]) continue;
                if (restart) all[k].Restart();
                all[k].Enter(room, value);
                all[k].Fetch(S, srv.Recorded, kind == KindRoomChange, srv.AnyTwo);
            }
            // Game 4.
            Rematch(room, all);
            TokenSeat m = all[master];
            value = HostStart(m, S, room, value, true, countSeed);
            foreach (var x in all) if (x != m) SeatStart(x, S, room);
            foreach (var x in all) { x.Read(room, value); x.Tick(room, TwoEach); x.Post(srv, S, room, true, 4); }
            carrying = 0;
            reanchoredCarrying = 0;
            for (int k = 0; k < 3; k++)
            {
                if (all[k].Token(S, room).Length == 0) continue;
                carrying++;
                if (re[k]) reanchoredCarrying++;
            }
            bool fromAnother;
            bool settled = srv.Settles(r.Token(S, room), 4, out fromAnother);
            wrong = settled && (srv.Recorded + 1 != 4 || fromAnother);
            return settled;
        }

        private static F29Tally SweepF29(bool countSeed, bool readsSitting, bool readsAnchor)
        {
            var tally = new F29Tally();
            for (int kind = KindRejoin; kind <= KindRecreate; kind++)
            for (int mask = kind == KindRejoin ? 1 : 7; mask <= 7; mask++)
            for (int q = 0; q < 2; q++)
            for (int rs = 0; rs < 2; rs++)
            for (int g3 = 0; g3 < 2; g3++)
            {
                bool wrong;
                int carrying, reCarrying;
                bool settled = SimulateF29(kind, mask, q != 0, rs != 0, g3 != 0, countSeed, readsSitting, readsAnchor,
                                           out wrong, out carrying, out reCarrying);
                tally.Timelines++;
                if (settled) tally.Settled++;
                if (wrong) tally.Wrong++;
                if (q != 0)
                {
                    tally.Carrying += carrying;
                    tally.ReanchoredCarrying += reCarrying;
                }
                if (q == 0 && kind == KindRejoin && mask != 7)
                {
                    tally.Live++;
                    if (settled && !wrong) tally.LiveSettled++;
                }
            }
            return tally;
        }

        // ---- Round 8, finding F31: the room created again over queued results -
        //
        // The reviewer's scenario on three real Trackers: team 1's H (the
        // room's creator and master) and R, and team 2's C. The series'
        // reporter M (the lowest Steam ID of the four: its client sends the
        // series' match reports and is the only one that asks for physical
        // game 1) is H, R or C. Games 1 and 2 are played in the room while the
        // server cannot be reached: every live-points post fails, and so does
        // M's ask unless game 1's went through first (`g1Issued`); both games'
        // results wait in M's durable outbox (its ledger holds the series).
        // Every seat leaves; H, restarted, creates the same room again (its
        // properties gone with it), and every other seat joins it, restarted
        // (`restartAll`) or the same process; the server answers again, and
        // every seat reads the series: no recorded game, never relocked, no
        // pair of two points on its record. Game 3 is played; game 1's result
        // lands after it (`land`), game 2's stays queued. Game 4 crosses two
        // points each, a team-2 player leaves and R reports it (`dcIn` 3: the
        // leave is in game 3). Any settlement is wrong: the server then
        // settles game 2 at most (game 1 recorded), while game 2's result is
        // still on its way. The fixed path: no seat names a physical game and
        // none carries a token (M's ledger shows the series' reports, so M
        // does not ask; had game 1's ask been answered, the server would issue
        // nothing again), and nothing settles. `keptBoot` is the kept copy of
        // round 7's creator boot (H names game 3 physical game 1 from the
        // reads' absence alone, and publishes it): against a server without
        // round 8's anchor rule (`readsAnchor` false) it must settle wrongly,
        // with the restarted and joined seats carrying its token, or the
        // scenario proves nothing; against the anchor rule nothing settles
        // (the server half alone). `ledgerLost`: M plays on from another
        // machine or profile, a new process whose ledger and outbox hold
        // nothing, so M asks at game 3; the server refuses it, the session it
        // asks on having been issued after the series was created
        // (`readsSession`), and nothing settles. The queued results land, if
        // at all (`land`), from where they were sent; with `ownLands` M's own
        // reports of the games it plays there land as it plays them. Against
        // a server without the session rule that never answered game 1's ask,
        // M is issued physical game 3 as game 1: with game 1's result landing
        // and M's own delayed, that report, built without the issued anchor,
        // voids the issue (the void alone: nothing settles; without the anchor
        // rule, which reads the void, it settles wrongly); with game 1's
        // result never landing and M's own landing, nothing is voided and a
        // leave in game 4 settles wrongly (the session rule alone closes it).
        //
        // Round 9, finding M1: the server's rules beyond round 8's (`m1`:
        // TokenServer.ReadsOthers, ReadsAnyPost and ReadsIssued), and the
        // reporter's account running a second process (`twin`, which implies
        // `ledgerLost`): B, on its own session issued before the series was
        // created, takes M's seat from game 3 (its Tracker and ledger empty,
        // not a restart: round 8's session rule passes it), while the first
        // process A, whose outbox holds games 1 and 2, lives on elsewhere and
        // sends them from there if at all. TwinLive: A held a session since
        // before the series (the other-session rule refuses B). TwinPosted: A
        // held none, and its first post of game 1 (one point) reached the
        // server before the server became unreachable (the any-post rule
        // refuses B; round 8's pair-of-two-points rule does not). TwinUnseen:
        // A held none and nothing of it reached the server: no rule this
        // server can apply sees A, B is issued game 3 as physical game 1, and
        // with A's results never landing and B's own landing a leave in game 4
        // settles wrongly (the residual, stated with its integrity class in
        // the notes, section 20).

        private const int M1Others = 1, M1AnyPost = 2, M1Issued = 4, M1All = 7;
        private const int TwinNone = 0, TwinLive = 1, TwinPosted = 2, TwinUnseen = 3;

        private sealed class F31Tally
        {
            public int Timelines, Settled, Wrong, Carrying, Named;
        }

        private static bool SimulateF31(int reporter, bool g1Issued, bool restartAll, bool land, int dcIn,
                                        bool keptBoot, bool readsAnchor, bool ledgerLost, bool ownLands,
                                        bool readsSession, int m1, int twin,
                                        out bool wrong, out int carrying, out int ordinals)
        {
            const string S = "series-f31", R = "room-f31";
            var srv = new TokenServer { ReadsTokens = true, ReadsOrdinals = true, ReadsSitting = true,
                                        ReadsAnchor = readsAnchor, ReadsSession = readsSession,
                                        ReadsOthers = (m1 & M1Others) != 0, ReadsAnyPost = (m1 & M1AnyPost) != 0,
                                        ReadsIssued = (m1 & M1Issued) != 0, Stored = R };
            var h = new TokenSeat { Team = 0, Srv = srv };
            var r = new TokenSeat { Team = 0, Srv = srv };
            var c = new TokenSeat { Team = 1, Srv = srv };
            var all = new[] { h, r, c };
            TokenSeat m = all[reporter];
            m.Reporter = true;
            // Round 9, M1: every process there when the series was created
            // holds a session the server keeps, and so does B (`twin`, which
            // hands M's seat to B with the ledger and outbox left behind).
            if (twin != TwinNone) ledgerLost = true;
            if (twin == TwinPosted || twin == TwinUnseen) m.Session = "";
            string twinSession = twin != TwinNone ? NewHarnessName("session") : "";
            foreach (var x in all) srv.Issue(x.Account, x.Session);
            srv.Issue(m.Account, twinSession);
            string value = "";
            foreach (var x in all) x.Enter(R, value);
            foreach (var x in all) x.Fetch(S, 0, false, srv.AnyTwo);
            for (int g = 1; g <= 2; g++)
            {
                srv.Unreachable = !(g == 1 && g1Issued);
                Rematch(R, all);
                value = HostStart(h, S, R, value, true);
                foreach (var x in all) if (x != h) SeatStart(x, S, R);
                value = ReporterPublish(m, value, true);
                if (twin == TwinPosted && g == 1)
                {
                    srv.Unreachable = false;
                    m.Read(R, value);
                    m.Tick(R, Played);
                    m.Post(srv, S, R, false, g);
                }
                srv.Unreachable = true;
                foreach (var x in all) { x.Read(R, value); x.Tick(R, TwoEach); x.Post(srv, S, R, true, g); x.Tick(R, Later); }
                foreach (var x in all) { string rep = x.Over(R); if (rep != null) m.Outbox.Add(rep); }
            }
            List<string> queued = m.Outbox;
            string sentFrom = m.Session;
            if (ledgerLost)
            {
                queued = new List<string>(m.Outbox);
                m.Outbox.Clear();
                m.Sent.Clear();
                m.Anchors.Clear();
            }
            srv.Unreachable = false;
            value = "";
            foreach (var x in all)
            {
                if (twin != TwinNone && x == m) x.Twin(twinSession);
                else if (x == h || restartAll || (ledgerLost && x == m)) x.Restart();
                x.Enter(R, value);
                x.Fetch(S, srv.Recorded, false, srv.AnyTwo);
            }
            for (int g = 3; g <= dcIn; g++)
            {
                Rematch(R, all);
                value = HostStart(h, S, R, value, true);
                if (keptBoot && g == 3) value = KeptBoot(h, value);
                foreach (var x in all) if (x != h) SeatStart(x, S, R);
                value = ReporterPublish(m, value, true);
                foreach (var x in all) { x.Read(R, value); x.Tick(R, TwoEach); x.Post(srv, S, R, true, g); }
                if (g == dcIn) break;
                foreach (var x in all) { x.Tick(R, Later); string rep = x.Over(R); if (rep != null) m.Outbox.Add(rep); }
                if (ledgerLost && ownLands && m.Outbox.Count > 0) { srv.Land(m.Outbox[0], m.Session); m.Outbox.RemoveAt(0); }
                if (land && queued.Count > 0) { srv.Land(queued[0], ledgerLost ? sentFrom : m.Session); queued.RemoveAt(0); }
                foreach (var x in all) x.Fetch(S, srv.Recorded, false, srv.AnyTwo);
            }
            carrying = 0;
            ordinals = 0;
            foreach (var x in all)
            {
                if (x.Token(S, R).Length != 0) carrying++;
                if (x.T.PhysicalOrdinal() != 0) ordinals++;
            }
            bool fromAnother;
            bool settled = srv.Settles(r.Token(S, R), dcIn, r.Reporter, r.Session, out fromAnother);
            wrong = settled && (srv.Recorded + 1 != dcIn || fromAnother);
            return settled;
        }

        // `lost`: 0 the reporter's ledger kept, 1 lost with its own reports
        // landing as it plays, 2 lost with its own reports delayed (with a
        // `twin` the ledger is always lost, so 0 is 2 again).
        private static F31Tally SweepF31(bool keptBoot, bool readsAnchor, bool readsSession, int m1, int twin)
        {
            var tally = new F31Tally();
            for (int rep = 0; rep < 3; rep++)
            for (int g1 = 0; g1 < 2; g1++)
            for (int ra = 0; ra < 2; ra++)
            for (int land = 0; land < 2; land++)
            for (int dc = 3; dc <= 4; dc++)
            for (int lost = 0; lost < 3; lost++)
            {
                bool wrong;
                int carrying, ordinals;
                bool settled = SimulateF31(rep, g1 != 0, ra != 0, land != 0, dc, keptBoot, readsAnchor, lost != 0,
                                           lost == 1, readsSession, m1, twin, out wrong, out carrying, out ordinals);
                tally.Timelines++;
                if (settled) tally.Settled++;
                if (wrong) tally.Wrong++;
                tally.Carrying += carrying;
                tally.Named += ordinals;
            }
            return tally;
        }

        // Round 9: how game 1's report lands in the fresh room (SimulateF31Fresh).
        private const int LandOwn = 0, LandShort = 1, LandTwin = 2;

        // Round 8, finding F31: the genuinely fresh room, the control. The same
        // seats and reporter, the server answering throughout. Game 1: M asks
        // at its game start and the server issues physical game 1; M publishes
        // its token (host or not) and every seat takes it; game 1 crosses and
        // team 1 wins it, and its report lands carrying the issued anchor. With
        // `restartBetween` R and C restart and join the room again before game
        // 2. Game 2 crosses under the host's token (round 9, M2: its nonce
        // derived from the issued one), a team-2 player leaves and R reports
        // it: it settles, from game 2's posts, every seat carrying game 2's
        // token. Round 9, M1: except where R is the reporter and restarted,
        // reporting the leave on a session the issue did not go to: nothing
        // settles (the cost of the issued-session rule, counted apart by the
        // sentinel). Round 9, M2: with `prefixOnly` the host publishes for game
        // 2, in place of the derived token, one whose nonce shares only the
        // issued nonce's first 8 digits (PrefixPublish): every seat takes it,
        // and it settles nothing, unless the server is round 8's copy that
        // reads a token by those 8 digits (`readsPrefix`). Round 9, M2,
        // `landMode`: game 1's report lands carrying, in place of the issued
        // nonce, an anchor sharing only its first 8 digits (LandShort: a
        // round-8 client's 8-digit anchor; LandTwin: 16 digits): the issue is
        // void and nothing settles, unless the server is round 8's copy that
        // holds an anchor to those 8 digits (`readsPrefixAnchor`).
        private static bool SimulateF31Fresh(int reporter, bool restartBetween, bool prefixOnly, bool readsPrefix,
                                             int landMode, bool readsPrefixAnchor,
                                             out bool fromAnother, out int carrying)
        {
            const string S = "series-f31f", R = "room-f31f";
            var srv = new TokenServer { ReadsTokens = true, ReadsOrdinals = true, ReadsSitting = true, ReadsAnchor = true,
                                        ReadsPrefix = readsPrefix, ReadsPrefixAnchor = readsPrefixAnchor, Stored = R };
            var h = new TokenSeat { Team = 0, Srv = srv };
            var r = new TokenSeat { Team = 0, Srv = srv };
            var c = new TokenSeat { Team = 1, Srv = srv };
            var all = new[] { h, r, c };
            TokenSeat m = all[reporter];
            m.Reporter = true;
            foreach (var x in all) srv.Issue(x.Account, x.Session);
            string value = "";
            foreach (var x in all) x.Enter(R, value);
            foreach (var x in all) x.Fetch(S, 0, false, srv.AnyTwo);
            for (int g = 1; g <= 2; g++)
            {
                Rematch(R, all);
                bool prefix = prefixOnly && g == 2;
                value = HostStart(h, S, R, value, !prefix);
                if (prefix) value = PrefixPublish(h, srv.FirstNonce, value);
                foreach (var x in all) if (x != h) SeatStart(x, S, R);
                value = ReporterPublish(m, value, true);
                foreach (var x in all) { x.Read(R, value); x.Tick(R, TwoEach); x.Post(srv, S, R, true, g); }
                if (g == 2) break;
                foreach (var x in all)
                {
                    x.Tick(R, Later);
                    string rep = x.Over(R);
                    if (rep == null) continue;
                    srv.Land(landMode == LandShort ? ShortNonce(srv.FirstNonce)
                             : landMode == LandTwin ? PrefixTwin(srv.FirstNonce) : rep, x.Session);
                }
                if (restartBetween)
                {
                    r.Restart();
                    c.Restart();
                    r.Enter(R, value);
                    c.Enter(R, value);
                }
                foreach (var x in all) x.Fetch(S, srv.Recorded, false, srv.AnyTwo);
            }
            carrying = 0;
            foreach (var x in all) if (x.Token(S, R).Length != 0) carrying++;
            return srv.Settles(r.Token(S, R), 2, r.Reporter, r.Session, out fromAnother) && srv.Recorded == 1
                   && !srv.Voided;
        }

        // Round 9, finding M2: the host publishes, in place of its derived
        // token, one whose nonce shares only the issued nonce's first 8 digits
        // (`issued`), for the ordinal it holds and the room's next epoch.
        // Returns the room's value after it (unchanged when nothing was
        // issued: PrefixTwin).
        private static string PrefixPublish(TokenSeat h, string issued, string value)
        {
            string twin = PrefixTwin(issued);
            if (twin.Length == 0) return value;
            string n;
            int o;
            long e;
            long above = TryParseToken(value, out n, out o, out e) ? e : 0;
            string tok = MakeToken(twin, h.T.PhysicalOrdinal(), above + 1);
            h.T.ArmPublished(tok);
            return tok;
        }

        // Round 9, finding M2: a nonce sharing only the issued nonce's first 8
        // digits (`issued`): those 8, then 8 that differ from its last 8; ""
        // when nothing was issued (a control that loses the issue then
        // publishes or lands nothing in its place, and fails the checks that
        // need the issue).
        private static string PrefixTwin(string issued)
        {
            if (!NonceValid(issued)) return "";
            return ShortNonce(issued) + (issued.EndsWith("e3e3e3e3", StringComparison.Ordinal) ? "3e3e3e3e" : "e3e3e3e3");
        }

        private static int Begin(Tracker t, string series, string room)
        {
            string line;
            return t.OnGameStart(series, room, Played, out line);
        }

        private static string Tok(char c, int ordinal, long epoch)
        {
            return MakeToken(new string(c, 16), ordinal, epoch);
        }

        // Round 9, finding M2: a Tracker grounded on physical game 1's token
        // (`issued`), then a join of the room, then grounded again on
        // `later`, a game-2 token, at a game start the game itself reported;
        // returns what it publishes as the host at the next game start ("" and
        // why not in `why`).
        private static string RootAfterJoin(string issued, string later, out string why)
        {
            string line;
            var t = new Tracker();
            t.NoteRoomJoined("R");
            t.ObserveRoomToken("R", "");
            t.ObserveRead("S", true, 0, 0, true, false, false);
            t.OnGmStart("R");
            t.OnGameStart("S", "R", Reset, out line);
            t.ObserveRoomToken("R", MakeToken(issued, 1, 1));
            t.NoteRoomJoined("R");
            t.ObserveRoomToken("R", "");
            t.ObserveRead("S", true, 1, 0, true, false, false);
            t.OnGmStart("R");
            t.OnGameStart("S", "R", Reset, out line);
            t.ObserveRoomToken("R", later);
            t.ObserveScore(Played);
            t.ObserveScore(Final);
            t.OnTokenGameOver("R", later);
            t.ObserveRead("S", true, 2, 0, true, false, false);
            t.OnGmStart("R");
            t.OnGameStart("S", "R", Reset, out line);
            return t.TokenToPublish(true, true, later, out why);
        }

        // Round 8, finding F31: whether a fresh Tracker asks for physical game 1
        // at its first game start in room R, series S: a read of the series
        // (`recorded`, relocked or not, a pair of two points or more on its
        // record or not), the game's own start reported or not (`gm`), this
        // seat the series' reporter or not, its client's reports clean or not.
        private static bool AskOutcome(bool gm, int recorded, bool relocked, bool played, bool reporter, bool clean)
        {
            var t = new Tracker();
            string line, why;
            int gen;
            t.NoteRoomJoined("R");
            t.ObserveRoomToken("R", "");
            t.ObserveRead("S", true, recorded, 0, true, relocked, played);
            if (gm) t.OnGmStart("R");
            t.OnGameStart("S", "R", Reset, out line);
            return t.AskFirstGame("S", "R", reporter, clean, out gen, out why);
        }

        // Round 8, finding F31: the physical game a fresh Tracker holds after
        // it asked at its first game start (a read showing the series unplayed)
        // and the answer came back: issued or not, with `nonce`, after
        // `startsBetween` more game starts and a join or not (`joinBetween`),
        // its client's reports clean or not (`clean`). -1: it did not ask.
        private static int IssueOrdinal(bool issued, string nonce, int startsBetween, bool joinBetween, bool clean)
        {
            var t = new Tracker();
            string line, why;
            int gen;
            t.NoteRoomJoined("R");
            t.ObserveRoomToken("R", "");
            t.ObserveRead("S", true, 0, 0, true, false, false);
            t.OnGmStart("R");
            t.OnGameStart("S", "R", Reset, out line);
            if (!t.AskFirstGame("S", "R", true, true, out gen, out why)) return -1;
            for (int i = 0; i < startsBetween; i++)
            {
                t.OnGmStart("R");
                t.OnGameStart("S", "R", Reset, out line);
            }
            if (joinBetween) t.NoteRoomJoined("R");
            t.OnFirstGame("S", "R", gen, issued, nonce, issued ? null : "refused", clean);
            return t.PhysicalOrdinal();
        }

        /// <summary>Returns the log line; `pass` is its verdict.</summary>
        internal static string RunSentinel(out bool pass)
        {
            pass = true;
            int checks = 0;
            string detail = "";

            // The sweep: the Tracker files nothing under another game and loses
            // nothing in a clean series; each kept copy fails where it should,
            // or the sweep could not tell them apart.
            Tally cur = Sweep(() => new TrackerRule());
            Tally own = Sweep(() => new OwnCountRule());
            Tally send = Sweep(() => new SendTimeRule());
            Tally never = Sweep(() => new NeverRule());
            checks++;
            if (cur.Wrong != 0) { pass = false; detail += " tracker:" + cur.Wrong + "-filed-under-another-game"; }
            checks++;
            if (cur.CleanFirst == 0 || cur.CleanFirstFiled != cur.CleanFirst)
            { pass = false; detail += " tracker:clean-first-posts-filed=" + cur.CleanFirstFiled + "/" + cur.CleanFirst; }
            checks++;
            if (own.Wrong == 0) { pass = false; detail += " own-count:none-filed-under-another-game(the-sweep-proves-nothing)"; }
            checks++;
            if (send.Wrong == 0) { pass = false; detail += " send-time:none-filed-under-another-game(the-sweep-proves-nothing)"; }
            checks++;
            if (never.CleanFirstFiled == never.CleanFirst) { pass = false; detail += " never:liveness-check-proves-nothing"; }

            // Direct checks on one Tracker.
            var t = new Tracker();
            checks++;
            if (Begin(t, "S", "R") != 1 || t.For("S", "R") != 1) { pass = false; detail += " first-start-no-read"; }
            checks++;
            if (t.For("S2", "R") != 0 || t.For("S", "R2") != 0 || t.For(null, null) != 0) { pass = false; detail += " for:mismatch"; }
            checks++;
            if (Begin(t, "S", "R") != 0 || t.For("S", "R") != 0) { pass = false; detail += " second-start-no-read"; }
            t.ObserveRead("S", true, 1, 0, false, false, false);
            checks++;
            if (Begin(t, "S", "R") != 2) { pass = false; detail += " read:1-recorded"; }
            checks++;
            if (t.ReadShowsGameRecorded("S")) { pass = false; detail += " recorded:too-early"; }
            t.ObserveRead("S", true, 0, 0, false, false, false);
            checks++;
            if (Begin(t, "S", "R") != 2) { pass = false; detail += " read:a-lower-late-answer-lowered-it"; }
            t.ObserveRead("S", false, 5, 5, false, false, false);
            checks++;
            if (Begin(t, "S", "R") != 2) { pass = false; detail += " read:an-answer-without-wins-counted"; }
            t.ObserveRead("S", true, 1, 1, false, false, false);
            checks++;
            if (!t.ReadShowsGameRecorded("S") || t.ReadShowsGameRecorded("S2")) { pass = false; detail += " recorded:after"; }
            t.Clear();
            checks++;
            if (t.For("S", "R") != 0) { pass = false; detail += " clear"; }
            checks++;
            if (Begin(t, "S", "R") != 3) { pass = false; detail += " clear:reads-kept"; }
            t.ObserveRead("S", true, 99, 0, false, false, false);
            checks++;
            if (Begin(t, "S", "R") != 0) { pass = false; detail += " bound:game-100"; }
            var tr = new Tracker();
            tr.ObserveRead("S", true, 0, 0, false, false, false);
            checks++;
            if (Begin(tr, "S", new string('r', MaxRoomLength + 1)) != 0
                || Begin(tr, "S", " r") != 0
                || Begin(tr, "S", new string('r', MaxRoomLength)) != 1)
            { pass = false; detail += " bound:room"; }
            checks++;
            if (Begin(tr, "", "R") != 0 || Begin(tr, "S", "") != 0) { pass = false; detail += " empty"; }
            tr.NoteAttestationRefused("S");
            checks++;
            if (!tr.AttestationRefused("S") || tr.AttestationRefused("S2") || tr.AttestationRefused(null)) { pass = false; detail += " refused"; }

            // The wire: bounds, both canonicals, the query pair, the pin.
            checks++;
            if (Sendable(0, "r") || Sendable(MaxGameNumber + 1, "r") || Sendable(1, "") || Sendable(1, null)
                || !Sendable(1, "r") || !Sendable(MaxGameNumber, "r"))
            { pass = false; detail += " sendable"; }
            checks++;
            if (LegacyCanonical("S", "P", 1, 2) != "team-live-points:S:P:1:2") { pass = false; detail += " legacy-canonical"; }
            checks++;
            if (AttestedCanonical("S", "P", 1, 2, 3, "room_x") != "team-live-points-game:S:P:1:2:3:room_x")
            { pass = false; detail += " attested-canonical"; }
            checks++;
            if (QueryPair(3, "room_x") != "&game_number=3&photon_room_id=room_x") { pass = false; detail += " query-pair"; }
            checks++;
            if (AttestedCanonical(PinSeries, PinReporter, 2, 1, 3, PinRoom) != PinExpected) { pass = false; detail += " pin"; }

            // Round 5, finding F25: the token sweep. Nothing settles from a
            // post of another physical game, a clean game 3 settles, and the
            // rule without the token settles from another game.
            TokenTally tok = SweepToken(true);
            TokenTally untok = SweepToken(false);
            checks++;
            if (tok.FromAnother != 0) { pass = false; detail += " token:" + tok.FromAnother + "-settled-from-another-game"; }
            checks++;
            if (tok.Clean == 0 || tok.CleanSettled != tok.Clean)
            { pass = false; detail += " token:clean-dc-settled=" + tok.CleanSettled + "/" + tok.Clean; }
            checks++;
            if (untok.FromAnother == 0) { pass = false; detail += " no-token-rule:none-settled-from-another-game(the-sweep-proves-nothing)"; }

            // Round 6, finding F27: the reviewer's scenario, named, and its
            // controls; then the sweep around it.
            bool fa;
            string sentToken;
            checks++;
            if (SimulateF27(true, DcAtReset, false, false, false, out fa, out sentToken) || sentToken.Length != 0)
            { pass = false; detail += " F27-REVIEWER-0-0:settled-or-token-sent"; }
            checks++;
            if (SimulateF27(true, DcAtPoint, false, false, false, out fa, out sentToken) || sentToken.Length != 0)
            { pass = false; detail += " F27-REVIEWER-AFTER-A-POINT:settled-or-token-sent"; }
            checks++;
            if (!SimulateF27(false, DcAtTwo, false, false, false, out fa, out sentToken) || fa)
            { pass = false; detail += " F27-LEVEL-CONTROL:not-settled"; }
            checks++;
            if (!SimulateF27(false, DcAtTwo, false, false, true, out fa, out sentToken) || fa)
            { pass = false; detail += " F27-LATE-HOOK-CONTROL:not-settled"; }
            F27Tally f27 = SweepF27();
            checks++;
            if (f27.FromAnother != 0) { pass = false; detail += " F27-sweep:" + f27.FromAnother + "-settled-from-another-game"; }
            checks++;
            if (f27.Live == 0 || f27.LiveSettled != f27.Live)
            { pass = false; detail += " F27-sweep:level-dc-settled=" + f27.LiveSettled + "/" + f27.Live; }

            // Round 6, finding F28: the reviewer's scenario, named, and its
            // controls; then the sweep around it.
            bool st;
            string f28 = SimulateF28(true, AtReset, GapPoll, false, LifeNone, false, true, out st, out fa);
            checks++;
            if (f28.Length != 0 || st) { pass = false; detail += " F28-REVIEWER:token-sent-or-settled"; }
            f28 = SimulateF28(true, AtReset, GapPoll, false, LifeOver, false, true, out st, out fa);
            checks++;
            if (f28.Length != 0 || st) { pass = false; detail += " F28-GAME-OVER-FIRST-CONTROL:token-sent"; }
            f28 = SimulateF28(true, AtReset, GapPoll, false, LifeNone, true, true, out st, out fa);
            checks++;
            if (f28.Length != 0 || st) { pass = false; detail += " F28-POLL-FIRST-CONTROL:token-sent"; }
            f28 = SimulateF28(true, AtReset, GapPoll, true, LifeNone, true, true, out st, out fa);
            checks++;
            if (f28.Length != 0 || st) { pass = false; detail += " F28-LATER-TOKEN-FIRST-CONTROL:token-sent"; }
            f28 = SimulateF28(true, AtNoBoundary, GapPoll, false, LifeNone, false, true, out st, out fa);
            checks++;
            if (f28.Length == 0 || !st || fa) { pass = false; detail += " F28-NO-BOUNDARY-CONTROL:not-carried"; }
            F28Tally f28t = SweepF28(true);
            F28Tally f28kept = SweepF28(false);
            checks++;
            if (f28t.Across != 0) { pass = false; detail += " F28-sweep:" + f28t.Across + "-tokens-across-a-boundary"; }
            checks++;
            if (f28t.SettledAcross != 0)
            { pass = false; detail += " F28-sweep:" + f28t.SettledAcross + "-settled-across-a-boundary"; }
            checks++;
            if (f28t.Carry == 0 || f28t.Carried != f28t.Carry)
            { pass = false; detail += " F28-sweep:carried=" + f28t.Carried + "/" + f28t.Carry; }
            checks++;
            if (f28t.CarryGap == 0 || f28t.CarriedGap != f28t.CarryGap)
            { pass = false; detail += " F28-sweep:carried-after-a-gap=" + f28t.CarriedGap + "/" + f28t.CarryGap; }
            checks++;
            if (f28kept.Across == 0 || f28kept.SettledAcross == 0)
            { pass = false; detail += " F28-kept-copy:none-across-a-boundary(the-sweep-proves-nothing)"; }

            // Round 7, finding F30: the reviewer's scenario, named, its kept
            // copy, the hooks not attached, and the fresh publish's control.
            // SimulateF30(hooks, hooksLive, fresh, ...).
            bool st30, fa30, held30;
            string f30 = SimulateF30(true, true, false, out st30, out fa30, out held30);
            checks++;
            if (!held30) { pass = false; detail += " F30-REVIEWER:no-token-held-before-the-boundary(the-scenario-proves-nothing)"; }
            checks++;
            if (f30.Length != 0 || st30) { pass = false; detail += " F30-REVIEWER:token-sent-or-settled"; }
            f30 = SimulateF30(false, true, false, out st30, out fa30, out held30);
            checks++;
            if (f30.Length == 0 || !st30 || !fa30)
            { pass = false; detail += " F30-KEPT-COPY:not-settled-from-another-game(the-scenario-proves-nothing)"; }
            f30 = SimulateF30(false, false, false, out st30, out fa30, out held30);
            checks++;
            if (f30.Length != 0 || st30) { pass = false; detail += " F30-HOOKS-NOT-ATTACHED:token-sent-or-settled"; }
            f30 = SimulateF30(true, true, true, out st30, out fa30, out held30);
            string f30n;
            int f30o;
            long f30e;
            checks++;
            if (!TryParseToken(f30, out f30n, out f30o, out f30e) || f30o != 3 || !st30 || fa30)
            { pass = false; detail += " F30-FRESH-PUBLISH-CONTROL:the-next-games-token-not-carried-or-not-settled"; }

            // Round 7, finding F30: the sweep of missed signals, its kept copy
            // and a hook not attached. SweepF30(hooks, hooksLive).
            F30Tally f30s = SweepF30(true, true);
            F30Tally f30kept = SweepF30(false, true);
            F30Tally f30nh = SweepF30(false, false);
            checks++;
            if (f30s.Across != 0) { pass = false; detail += " F30-sweep:" + f30s.Across + "-tokens-sent-across-the-boundary"; }
            checks++;
            if (f30s.Settled != 0) { pass = false; detail += " F30-sweep:" + f30s.Settled + "-settled-across-the-boundary"; }
            checks++;
            if (f30s.FreshDue == 0 || f30s.FreshMissed != 0 || f30s.Fresh != f30s.FreshDue)
            {
                pass = false;
                detail += " F30-sweep:fresh=" + f30s.Fresh + "/" + f30s.FreshDue + ",missed=" + f30s.FreshMissed;
            }
            checks++;
            if (f30kept.Across == 0 || f30kept.FromAnother == 0)
            { pass = false; detail += " F30-kept-copy-sweep:none-settled-from-another-game(the-sweep-proves-nothing)"; }
            checks++;
            if (f30nh.Sent != 0) { pass = false; detail += " F30-hooks-not-attached-sweep:" + f30nh.Sent + "-sent"; }

            // Round 7, finding F29: the reviewer's scenario, named (every seat
            // re-anchored by a rejoin, and by a room change), and its controls;
            // then the sweep around it, the kept copy of round 6's host seed,
            // and the server's sitting rule on and off (the kept copy and the
            // sitting rule off both against a server without round 8's anchor
            // rule; with it, the kept copy settles nothing while queued).
            // SimulateF29(kind, mask, queued, restart, g3Sent, countSeed,
            // readsSitting, readsAnchor, ...).
            bool w29;
            int carry29, reCarry29;
            checks++;
            if (SimulateF29(KindRejoin, 7, true, false, false, false, true, true, out w29, out carry29, out reCarry29)
                || carry29 != 0 || reCarry29 != 0)
            { pass = false; detail += " F29-REVIEWER-REJOIN:settled-or-token-carried"; }
            checks++;
            if (SimulateF29(KindRoomChange, 7, true, false, true, false, true, true, out w29, out carry29, out reCarry29)
                || carry29 != 0 || reCarry29 != 0)
            { pass = false; detail += " F29-REVIEWER-ROOM-CHANGE:settled-or-token-carried"; }
            checks++;
            if (SimulateF29(KindRecreate, 7, true, true, false, false, true, true, out w29, out carry29, out reCarry29)
                || carry29 != 0)
            { pass = false; detail += " F29-RECREATED-ROOM-RESTARTED:settled-or-token-carried"; }
            checks++;
            if (SimulateF29(KindRoomChange, 7, true, true, true, false, false, false, out w29, out carry29, out reCarry29)
                || carry29 != 0)
            { pass = false; detail += " F29-ROOM-CHANGE-RESTARTED-WITHOUT-THE-SITTING-RULE:settled-or-token-carried"; }
            checks++;
            if (SimulateF29(KindRejoin, 6, true, false, true, false, true, true, out w29, out carry29, out reCarry29)
                || carry29 != 0)
            { pass = false; detail += " F29-HOST-STAYED-QUEUED:settled-or-token-carried"; }
            checks++;
            if (!SimulateF29(KindRejoin, 6, false, false, true, false, true, true, out w29, out carry29, out reCarry29) || w29
                || reCarry29 != 2)
            { pass = false; detail += " F29-IN-STEP-CONTROL:not-settled-or-the-re-anchored-seats-took-nothing"; }
            checks++;
            if (!SimulateF29(KindRejoin, 7, true, false, false, true, true, false, out w29, out carry29, out reCarry29) || !w29)
            { pass = false; detail += " F29-KEPT-COPY-CONTROL:not-settled-while-queued(the-scenario-proves-nothing)"; }
            F29Tally f29 = SweepF29(false, true, true);
            F29Tally f29bare = SweepF29(false, false, false);
            F29Tally f29kept = SweepF29(true, true, false);
            F29Tally f29open = SweepF29(true, false, false);
            F29Tally f29anchored = SweepF29(true, true, true);
            checks++;
            if (f29.Wrong != 0 || f29bare.Wrong != 0)
            { pass = false; detail += " F29-sweep:" + f29.Wrong + "+" + f29bare.Wrong + "-settled-while-a-result-was-queued"; }
            checks++;
            if (f29.Carrying != 0 || f29.ReanchoredCarrying != 0 || f29bare.Carrying != 0)
            { pass = false; detail += " F29-sweep:" + f29.Carrying + "-tokens-carried-while-a-result-was-queued"; }
            checks++;
            if (f29.Live == 0 || f29.LiveSettled != f29.Live)
            { pass = false; detail += " F29-sweep:in-step-dc-settled=" + f29.LiveSettled + "/" + f29.Live; }
            checks++;
            if (f29kept.Wrong == 0) { pass = false; detail += " F29-kept-copy:none-settled-while-queued(the-sweep-proves-nothing)"; }
            checks++;
            if (f29open.Wrong <= f29kept.Wrong)
            { pass = false; detail += " F29-sitting-rule:the-room-change-settles-no-less-without-it(the-sweep-proves-nothing)"; }
            checks++;
            if (f29anchored.Wrong != 0)
            { pass = false; detail += " F29-anchor-rule:" + f29anchored.Wrong + "-of-round-6's-seeded-tokens-settled-while-queued"; }

            // Round 8, finding F31: the reviewer's scenario, named, for every
            // reporter, with game 1's ask answered or not, the other seats
            // restarted or only joined again; the client half alone (a server
            // without the anchor rule); the kept copy of round 7's creator boot
            // against a server without the anchor rule (it must settle wrongly
            // with every seat carrying its token, restarted and joined ones
            // included, or the scenario proves nothing) and against the anchor
            // rule (the server half alone: nothing settles); the reporter's
            // ledger and outbox lost, M playing on from another
            // machine or profile (the session rule: nothing settles, with its
            // own reports landing or delayed and with game 1's result never
            // landing; without the session rule the last settles wrongly, and
            // the void alone catches the case where game 1's result lands
            // first, which without the anchor rule settles wrongly); then the
            // sweep and the genuinely fresh room's control. Round 9, finding
            // M1: every server below applies round 9's rules (M1All) unless a
            // check says otherwise. The client half runs against none of them.
            // Round 8's session-rule controls run without the other-session
            // rule, which alone also closes a restarted reporter
            // (M1-OTHERS-ALONE: the first process's session stays live on the
            // server).
            // SimulateF31(reporter, g1Issued, restartAll, land, dcIn,
            // keptBoot, readsAnchor, ledgerLost, ownLands, readsSession, m1,
            // twin, ...).
            const int NoOthers = M1All & ~M1Others, NoAnyPost = M1All & ~M1AnyPost;
            int f31Named = 0, f31Client = 0, f31Kept = 0, f31Server = 0, f31Lost = 0, f31Unlanded = 0;
            int f31UnlandedOpen = 0, f31Void = 0, f31VoidOpen = 0, f31OthersAlone = 0;
            for (int rep = 0; rep < 3; rep++)
            for (int g1 = 0; g1 < 2; g1++)
            for (int ra = 0; ra < 2; ra++)
            {
                bool w31;
                int carry31, ord31;
                bool st31 = SimulateF31(rep, g1 != 0, ra != 0, true, 4, false, true, false, false, true, M1All, TwinNone,
                                        out w31, out carry31, out ord31);
                if (st31 || carry31 != 0 || ord31 != 0) f31Named++;
                st31 = SimulateF31(rep, g1 != 0, ra != 0, true, 4, false, false, false, false, true, 0, TwinNone,
                                   out w31, out carry31, out ord31);
                if (st31 || carry31 != 0 || ord31 != 0) f31Client++;
                st31 = SimulateF31(rep, g1 != 0, ra != 0, true, 4, true, false, false, false, true, M1All, TwinNone,
                                   out w31, out carry31, out ord31);
                if (w31 && carry31 == 3) f31Kept++;
                st31 = SimulateF31(rep, g1 != 0, ra != 0, true, 4, true, true, false, false, true, M1All, TwinNone,
                                   out w31, out carry31, out ord31);
                if (st31) f31Server++;
                for (int landsOwn = 0; landsOwn < 2; landsOwn++)
                {
                    st31 = SimulateF31(rep, g1 != 0, ra != 0, true, 4, false, true, true, landsOwn != 0, true, M1All,
                                       TwinNone, out w31, out carry31, out ord31);
                    if (st31 || carry31 != 0 || ord31 != 0) f31Lost++;
                }
                st31 = SimulateF31(rep, g1 != 0, ra != 0, false, 4, false, true, true, true, true, M1All, TwinNone,
                                   out w31, out carry31, out ord31);
                if (st31 || carry31 != 0 || ord31 != 0) f31Unlanded++;
                st31 = SimulateF31(rep, g1 != 0, ra != 0, false, 4, false, true, true, true, false, NoOthers, TwinNone,
                                   out w31, out carry31, out ord31);
                if (w31) f31UnlandedOpen++;
                st31 = SimulateF31(rep, g1 != 0, ra != 0, false, 4, false, true, true, true, false, M1All, TwinNone,
                                   out w31, out carry31, out ord31);
                if (st31 || carry31 != 0 || ord31 != 0) f31OthersAlone++;
                st31 = SimulateF31(rep, g1 != 0, ra != 0, true, 4, false, true, true, false, false, NoOthers, TwinNone,
                                   out w31, out carry31, out ord31);
                if (st31) f31Void++;
                st31 = SimulateF31(rep, g1 != 0, ra != 0, true, 4, false, false, true, false, false, NoOthers, TwinNone,
                                   out w31, out carry31, out ord31);
                if (w31) f31VoidOpen++;
            }
            checks++;
            if (f31Named != 0)
            { pass = false; detail += " F31-REVIEWER:" + f31Named + "-of-12-named-a-game-carried-a-token-or-settled"; }
            checks++;
            if (f31Client != 0)
            { pass = false; detail += " F31-CLIENT-HALF:" + f31Client + "-of-12-named-a-game-carried-a-token-or-settled"; }
            checks++;
            if (f31Kept != 12)
            { pass = false; detail += " F31-KEPT-COPY:" + f31Kept + "-of-12-settled-wrongly-with-every-seat-carrying(the-scenario-proves-nothing)"; }
            checks++;
            if (f31Server != 0) { pass = false; detail += " F31-SERVER-HALF:" + f31Server + "-of-12-settled"; }
            checks++;
            if (f31Lost != 0)
            { pass = false; detail += " F31-LEDGER-LOST:" + f31Lost + "-of-24-named-a-game-carried-a-token-or-settled"; }
            checks++;
            if (f31Unlanded != 0)
            { pass = false; detail += " F31-LEDGER-LOST-UNLANDED:" + f31Unlanded + "-of-12-named-a-game-carried-a-token-or-settled"; }
            checks++;
            if (f31UnlandedOpen == 0)
            { pass = false; detail += " F31-LEDGER-LOST-WITHOUT-THE-SESSION-RULES:none-settled-wrongly(the-scenario-proves-nothing)"; }
            checks++;
            if (f31OthersAlone != 0)
            { pass = false; detail += " M1-OTHERS-ALONE:" + f31OthersAlone + "-of-12-named-a-game-carried-a-token-or-settled"; }
            checks++;
            if (f31Void != 0) { pass = false; detail += " F31-VOID-ALONE:" + f31Void + "-of-12-settled"; }
            checks++;
            if (f31VoidOpen == 0)
            { pass = false; detail += " F31-VOID-UNREAD:none-settled-wrongly(the-scenario-proves-nothing)"; }
            F31Tally f31 = SweepF31(false, true, true, M1All, TwinNone);
            F31Tally f31boot = SweepF31(true, false, true, M1All, TwinNone);
            F31Tally f31open = SweepF31(false, true, false, NoOthers, TwinNone);
            checks++;
            if (f31.Settled != 0 || f31.Wrong != 0)
            { pass = false; detail += " F31-sweep:" + f31.Settled + "-settled," + f31.Wrong + "-wrongly"; }
            checks++;
            if (f31.Carrying != 0 || f31.Named != 0)
            { pass = false; detail += " F31-sweep:" + f31.Carrying + "-tokens-carried," + f31.Named + "-games-named"; }
            checks++;
            if (f31boot.Wrong == 0) { pass = false; detail += " F31-kept-copy-sweep:none-settled-wrongly(the-sweep-proves-nothing)"; }
            checks++;
            if (f31open.Wrong == 0)
            { pass = false; detail += " F31-no-session-sweep:none-settled-wrongly(the-sweep-proves-nothing)"; }

            // Round 9, finding M1: the reporter's account runs a second process
            // B from game 3, the required control's shape. Where A held a
            // session (TwinLive) or a post of game 1 reached the server
            // (TwinPosted), nothing is named, carried or settled on round 9's
            // server; with round 8's issuance (none of round 9's rules), or
            // without the one rule that sees A, B is issued game 3 as physical
            // game 1 and a leave in game 4 settles wrongly, or the scenario
            // proves nothing. TwinUnseen, A leaving nothing the server can see,
            // is the residual: it settles, wrongly, exactly where A's results
            // never land and B's own do (12 of 48), and nowhere else.
            int m1Live = 0, m1LiveR8 = 0, m1LiveNoOthers = 0, m1Posted = 0, m1PostedR8 = 0, m1PostedNoAny = 0;
            int m1Unseen = 0, m1UnseenWrong = 0, m1UnseenOutside = 0;
            for (int rep = 0; rep < 3; rep++)
            for (int g1 = 0; g1 < 2; g1++)
            for (int ra = 0; ra < 2; ra++)
            for (int lm = 0; lm < 4; lm++)
            {
                bool landsM1 = lm < 2, ownM1 = (lm & 1) != 0;
                bool wM1, sM1;
                int carryM1, ordM1;
                sM1 = SimulateF31(rep, g1 != 0, ra != 0, landsM1, 4, false, true, true, ownM1, true, M1All, TwinLive,
                                  out wM1, out carryM1, out ordM1);
                if (sM1 || carryM1 != 0 || ordM1 != 0) m1Live++;
                SimulateF31(rep, g1 != 0, ra != 0, landsM1, 4, false, true, true, ownM1, true, 0, TwinLive,
                            out wM1, out carryM1, out ordM1);
                if (wM1) m1LiveR8++;
                SimulateF31(rep, g1 != 0, ra != 0, landsM1, 4, false, true, true, ownM1, true, NoOthers, TwinLive,
                            out wM1, out carryM1, out ordM1);
                if (wM1) m1LiveNoOthers++;
                sM1 = SimulateF31(rep, g1 != 0, ra != 0, landsM1, 4, false, true, true, ownM1, true, M1All, TwinPosted,
                                  out wM1, out carryM1, out ordM1);
                if (sM1 || carryM1 != 0 || ordM1 != 0) m1Posted++;
                SimulateF31(rep, g1 != 0, ra != 0, landsM1, 4, false, true, true, ownM1, true, 0, TwinPosted,
                            out wM1, out carryM1, out ordM1);
                if (wM1) m1PostedR8++;
                SimulateF31(rep, g1 != 0, ra != 0, landsM1, 4, false, true, true, ownM1, true, NoAnyPost, TwinPosted,
                            out wM1, out carryM1, out ordM1);
                if (wM1) m1PostedNoAny++;
                sM1 = SimulateF31(rep, g1 != 0, ra != 0, landsM1, 4, false, true, true, ownM1, true, M1All, TwinUnseen,
                                  out wM1, out carryM1, out ordM1);
                if (sM1) m1Unseen++;
                if (wM1) m1UnseenWrong++;
                if (sM1 && (landsM1 || !ownM1)) m1UnseenOutside++;
            }
            checks++;
            if (m1Live != 0)
            { pass = false; detail += " M1-TWIN-LIVE:" + m1Live + "-of-48-named-a-game-carried-a-token-or-settled"; }
            checks++;
            if (m1LiveR8 == 0)
            { pass = false; detail += " M1-TWIN-LIVE-ROUND-8-ISSUANCE:none-settled-wrongly(the-scenario-proves-nothing)"; }
            checks++;
            if (m1LiveNoOthers == 0)
            { pass = false; detail += " M1-TWIN-LIVE-WITHOUT-THE-OTHER-SESSION-RULE:none-settled-wrongly(the-scenario-proves-nothing)"; }
            checks++;
            if (m1Posted != 0)
            { pass = false; detail += " M1-TWIN-POSTED:" + m1Posted + "-of-48-named-a-game-carried-a-token-or-settled"; }
            checks++;
            if (m1PostedR8 == 0)
            { pass = false; detail += " M1-TWIN-POSTED-ROUND-8-ISSUANCE:none-settled-wrongly(the-scenario-proves-nothing)"; }
            checks++;
            if (m1PostedNoAny == 0)
            { pass = false; detail += " M1-TWIN-POSTED-WITHOUT-THE-ANY-POST-RULE:none-settled-wrongly(the-scenario-proves-nothing)"; }
            checks++;
            if (m1Unseen != 12 || m1UnseenWrong != 12 || m1UnseenOutside != 0)
            {
                pass = false;
                detail += " M1-RESIDUAL-UNSEEN:" + m1Unseen + "-settled," + m1UnseenWrong + "-wrongly," + m1UnseenOutside
                          + "-outside-its-class(expected-12,12,0)";
            }
            F31Tally m1LiveSweep = SweepF31(false, true, true, M1All, TwinLive);
            F31Tally m1PostedSweep = SweepF31(false, true, true, M1All, TwinPosted);
            F31Tally m1UnseenSweep = SweepF31(false, true, true, M1All, TwinUnseen);
            checks++;
            if (m1LiveSweep.Settled + m1LiveSweep.Carrying + m1LiveSweep.Named != 0
                || m1PostedSweep.Settled + m1PostedSweep.Carrying + m1PostedSweep.Named != 0)
            {
                pass = false;
                detail += " M1-twin-sweep:" + m1LiveSweep.Settled + "/" + m1LiveSweep.Carrying + "/" + m1LiveSweep.Named
                          + "-live," + m1PostedSweep.Settled + "/" + m1PostedSweep.Carrying + "/" + m1PostedSweep.Named
                          + "-posted(settled/carried/named)";
            }
            checks++;
            if (m1UnseenSweep.Settled != m1UnseenSweep.Wrong)
            { pass = false; detail += " M1-unseen-sweep:" + m1UnseenSweep.Settled + "-settled," + m1UnseenSweep.Wrong + "-wrongly"; }
            // Round 9, finding M2: the fresh room with game 2's token replaced
            // by one sharing only the issued nonce's first 8 digits, which
            // every seat takes: round 9's server reads it nowhere; round 8's
            // comparison, the kept copy, reads it (or the scenario proves
            // nothing). The same for game 1's report landing with an anchor
            // sharing only those 8 digits (8 of them, or 16): round 9's server
            // voids the issue; round 8's comparison keeps it, and the five
            // timelines the control settles settle (or the scenario proves
            // nothing).
            int f31Fresh = 0, f31FreshRestarted = 0, m2Prefix = 0, m2PrefixRead = 0, m2Anchor = 0, m2AnchorRead = 0;
            for (int rep = 0; rep < 3; rep++)
            for (int rb = 0; rb < 2; rb++)
            {
                bool fa31, faP;
                int carryF31, carryP;
                bool stF31 = SimulateF31Fresh(rep, rb != 0, false, false, LandOwn, false, out fa31, out carryF31);
                if (SimulateF31Fresh(rep, rb != 0, true, false, LandOwn, false, out faP, out carryP)) m2Prefix++;
                if (SimulateF31Fresh(rep, rb != 0, true, true, LandOwn, false, out faP, out carryP) && carryP == 3)
                    m2PrefixRead++;
                for (int form = LandShort; form <= LandTwin; form++)
                {
                    if (SimulateF31Fresh(rep, rb != 0, false, false, form, false, out faP, out carryP)) m2Anchor++;
                    if (!(rep == 1 && rb != 0)
                        && SimulateF31Fresh(rep, rb != 0, false, false, form, true, out faP, out carryP)
                        && !faP && carryP == 3)
                        m2AnchorRead++;
                }
                if (rep == 1 && rb != 0) { if (stF31) f31FreshRestarted++; continue; }
                if (stF31 && !fa31 && carryF31 == 3) f31Fresh++;
            }
            checks++;
            if (f31Fresh != 5)
            { pass = false; detail += " F31-FRESH-ROOM-CONTROL:" + f31Fresh + "-of-5-settled-from-its-own-game-with-every-seat-carrying"; }
            checks++;
            if (f31FreshRestarted != 0)
            { pass = false; detail += " M1-RESTARTED-REPORTER:the-leave-reported-on-a-session-the-issue-did-not-go-to-settled"; }
            checks++;
            if (m2Prefix != 0) { pass = false; detail += " M2-PREFIX-ONLY:" + m2Prefix + "-of-6-settled"; }
            checks++;
            if (m2PrefixRead != 5)
            { pass = false; detail += " M2-PREFIX-ONLY-ROUND-8-COMPARE:" + m2PrefixRead + "-of-5-settled-with-every-seat-carrying(the-scenario-proves-nothing)"; }
            checks++;
            if (m2Anchor != 0) { pass = false; detail += " M2-PREFIX-ANCHOR:" + m2Anchor + "-of-12-settled"; }
            checks++;
            if (m2AnchorRead != 10)
            { pass = false; detail += " M2-PREFIX-ANCHOR-ROUND-8-COMPARE:" + m2AnchorRead + "-of-10-settled-with-every-seat-carrying(the-scenario-proves-nothing)"; }
            // Round 9, finding M2: the derivation's pin vector (the four values
            // the server's test checks against main._team_game_chain_nonce);
            // game 1's nonce is the root itself, and another ordinal or epoch
            // gives another nonce.
            checks++;
            if (ChainNonce(PinChainRoot, PinChainOrdinal, PinChainEpoch) != PinChainExpected
                || ChainNonce(PinChainRoot, 1, PinChainEpoch) != PinChainRoot
                || ChainNonce(PinChainRoot, PinChainOrdinal, PinChainEpoch + 1) == PinChainExpected
                || ChainNonce(PinChainRoot, PinChainOrdinal + 1, PinChainEpoch) == PinChainExpected
                || ChainNonce("0123456789ABCDEF", PinChainOrdinal, PinChainEpoch) != ""
                || ChainNonce(PinChainRoot, 0, PinChainEpoch) != "" || ChainNonce(PinChainRoot, PinChainOrdinal, 0) != "")
            { pass = false; detail += " M2-PIN:the-derivation-does-not-give-the-pinned-nonce"; }

            // The score's successor rule (F28).
            checks++;
            if (!Follows(Reset, Reset) || !Follows(Reset, Played) || !Follows(Played, TwoEach) || !Follows(TwoEach, RoundUp)
                || !Follows(Later, Continue) || !Follows(Continue, Final) || Follows(Played, Reset)
                || Follows(TwoEach, Played) || Follows(Later, Reset) || Follows(Later, RoundUp) || Follows(Final, Reset))
            { pass = false; detail += " follows"; }

            // The token on one Tracker (k): taken only fresh, for this seat's
            // game, and never carried past a signal that its game ended.
            string TA = Tok('a', 1, 1), TB = Tok('b', 1, 2), TC = Tok('c', 1, 3), TD = Tok('d', 2, 4);
            string TE = Tok('e', 3, 5), TF = Tok('f', 3, 6);
            string line;
            var k = new Tracker();
            k.ObserveRoomToken("R", TA);
            k.OnGmStart("R");
            k.OnGameStart("S", "R", Reset, out line);
            k.ObserveRoomToken("R", TA);
            k.ObserveScore(Played);
            checks++;
            if (k.TokenFor("S", "R", TA, Played, true) != "") { pass = false; detail += " token:first-read-in-a-room-taken"; }
            k.ObserveRoomToken("R", TB);
            checks++;
            if (k.TokenFor("S", "R", TB, Played, true) != TB || k.TokenFor("S", "R", TA, Played, true) != ""
                || k.TokenFor("S2", "R", TB, Played, true) != "" || k.TokenFor("S", "R2", TB, Played, true) != ""
                || k.TokenFor(null, "R", TB, Played, true) != "" || k.TokenFor("S", null, TB, Played, true) != "")
            { pass = false; detail += " token:for"; }
            k.ObserveRoomToken("R", TC);
            checks++;
            if (k.TokenFor("S", "R", TC, Played, true) != "" || k.TokenFor("S", "R", TB, Played, true) != "" || k.Adopted != "")
            { pass = false; detail += " token:second-value-in-a-game-not-withdrawn"; }
            k.OnTokenGameOver("R", TC);
            checks++;
            if (k.TokenFor("S", "R", TB, Played, true) != "" || k.TokenFor("S", "R", TC, Played, true) != "")
            { pass = false; detail += " token:after-game-over"; }
            k.ObserveRead("S", true, 1, 0, false, false, false);
            k.OnGmStart("R");
            k.OnGameStart("S", "R", Reset, out line);
            k.ObserveRoomToken("R", TC);
            k.ObserveRoomToken("R", TB);
            k.ObserveScore(Played);
            checks++;
            if (k.TokenFor("S", "R", TC, Played, true) != "" || k.TokenFor("S", "R", TB, Played, true) != "" || k.Adopted != "")
            { pass = false; detail += " token:stale-taken"; }
            k.ObserveRoomToken("R", TD);
            checks++;
            if (k.TokenFor("S", "R", TD, Played, true) != TD || k.PhysicalOrdinal() != 2) { pass = false; detail += " token:fresh-not-taken"; }
            k.ObserveRead("S", true, 2, 0, false, false, false);
            k.OnGmStart("R");
            k.OnGameStart("S", "R", Reset, out line);
            k.ObserveRoomToken("R", TD);
            k.ObserveScore(Played);
            checks++;
            if (k.TokenFor("S", "R", TD, Played, true) != "" || k.Adopted != "") { pass = false; detail += " token:reused-across-a-restart"; }
            k.ObserveRoomToken("R", TE);
            checks++;
            if (k.TokenFor("S", "R", TE, Played, true) != TE) { pass = false; detail += " token:game-3-not-taken"; }
            string missedLine = k.ObserveScore(Reset);
            k.ObserveRoomToken("R", TF);
            checks++;
            if (k.Adopted != "" || k.TokenFor("S", "R", TE, Played, true) != "" || k.TokenFor("S", "R", TF, Played, true) != ""
                || missedLine == null || !missedLine.StartsWith(LogTag + " the score went down inside this seat's game (a game boundary it did not see", StringComparison.Ordinal))
            { pass = false; detail += " token:missed-boundary"; }
            // The missed boundary also ends this seat's physical game (round 7,
            // F29): no ordinal and no publish at its next game start, whatever
            // a read of the series shows.
            k.OnTokenGameOver("R", TF);
            k.ObserveRead("S", true, 3, 0, false, false, false);
            k.OnGmStart("R");
            k.OnGameStart("S", "R", Reset, out line);
            string whyK;
            checks++;
            if (k.PhysicalOrdinal() != 0 || k.TokenToPublish(true, true, TF, out whyK) != "" || whyK != WhyNoOrdinal)
            { pass = false; detail += " token:ordinal-lost-after-a-missed-boundary"; }
            // Round 7, finding F29: leaving and joining the room again grounds
            // nothing from the count (four games' worth of reads here); a
            // host's publish this seat takes does.
            k.Clear();
            k.NoteRoomJoined("R");
            k.ObserveRoomToken("R", Tok('0', 4, 7));
            k.OnGmStart("R");
            k.OnGameStart("S", "R", Reset, out line);
            k.ObserveRoomToken("R", Tok('0', 4, 7));
            k.ObserveScore(Played);
            string whyC;
            checks++;
            if (k.TokenFor("S", "R", Tok('0', 4, 7), Played, true) != "" || k.PhysicalOrdinal() != 0
                || k.TokenToPublish(true, true, Tok('0', 4, 7), out whyC) != "" || whyC != WhyNoOrdinal)
            { pass = false; detail += " F29:a-rejoin-grounded-on-the-count"; }
            k.ObserveRoomToken("R", Tok('1', 4, 8));
            checks++;
            if (k.Adopted != Tok('1', 4, 8) || k.PhysicalOrdinal() != 4 || k.TokenFor("S", "R", Tok('1', 4, 8), Played, true) != Tok('1', 4, 8))
            { pass = false; detail += " F29:a-hosts-publish-did-not-ground-it"; }

            // Round 6, finding F27, on one Tracker: the ordinal, the epoch and
            // the nonce each refuse alone; a late hook takes its game's token.
            var o = new Tracker();
            o.ObserveRoomToken("R", "");
            o.OnGmStart("R");
            o.OnGameStart("S", "R", Reset, out line);            // physical 1, game 1
            o.ObserveRoomToken("R", Tok('1', 1, 1));
            o.ObserveScore(Played);
            o.ObserveScore(Final);
            o.OnTokenGameOver("R", Tok('1', 1, 1));
            o.ObserveRead("S", true, 1, 0, false, false, false);
            o.OnGmStart("R");
            o.OnGameStart("S", "R", Reset, out line);     // physical 2, game 2
            o.ObserveRoomToken("R", Tok('2', 1, 2));
            checks++;
            if (o.Adopted != "" || o.PhysicalOrdinal() != 2) { pass = false; detail += " F27:an-earlier-games-ordinal-taken"; }
            o.ObserveRoomToken("R", Tok('1', 2, 3));
            checks++;
            if (o.Adopted != "") { pass = false; detail += " F27:a-stale-nonce-with-a-higher-epoch-taken"; }
            o.ObserveRoomToken("R", Tok('3', 2, 1));
            checks++;
            if (o.Adopted != "") { pass = false; detail += " F27:an-epoch-not-above-a-stale-one-taken"; }
            o.ObserveRoomToken("R", Tok('4', 2, 3));
            checks++;
            if (o.Adopted != Tok('4', 2, 3)) { pass = false; detail += " F27:its-games-token-not-taken"; }
            // A value naming the next game, read inside this game, withdraws
            // this game's token (F28) and is taken at the next game start (#182).
            o.ObserveScore(Played);
            o.ObserveRoomToken("R", Tok('5', 3, 4));
            checks++;
            if (o.Adopted != "" || o.TokenFor("S", "R", Tok('4', 2, 3), Played, true) != "")
            { pass = false; detail += " F28:a-later-games-token-did-not-withdraw"; }
            o.ObserveScore(Final);
            o.OnTokenGameOver("R", Tok('5', 3, 4));
            o.ObserveRead("S", true, 2, 0, false, false, false);
            o.ObserveScore(Reset);
            o.OnGmStart("R");
            o.OnGameStart("S", "R", Reset, out line);     // physical 3, game 3
            o.ObserveRoomToken("R", Tok('5', 3, 4));
            o.ObserveScore(Played);
            checks++;
            if (o.TokenFor("S", "R", Tok('5', 3, 4), Played, true) != Tok('5', 3, 4)) { pass = false; detail += " F27:a-late-hook-lost-its-games-token"; }
            // A seat in physical game 3 (grounded on game 2's publish) whose
            // posts name game 2 (game 2's result queued) takes no token naming
            // either.
            var q = new Tracker();
            q.ObserveRoomToken("R", "");
            q.ObserveRead("S", true, 1, 0, false, false, false);
            q.OnGmStart("R");
            q.OnGameStart("S", "R", Reset, out line);            // game 2
            q.ObserveRoomToken("R", Tok('5', 2, 1));                  // physical 2, from the host's publish
            q.ObserveScore(Played);
            q.ObserveScore(Final);
            q.OnTokenGameOver("R", Tok('5', 2, 1));
            q.OnGmStart("R");
            q.OnGameStart("S", "R", Reset, out line);     // physical 3, game 2 (no new read)
            q.ObserveRoomToken("R", Tok('6', 2, 2));
            q.ObserveRoomToken("R", Tok('7', 3, 3));
            checks++;
            if (q.Adopted != "" || q.PhysicalOrdinal() != 3 || q.For("S", "R") != 2)
            { pass = false; detail += " F27:a-token-taken-while-the-physical-game-and-the-number-differ"; }

            // Round 6, finding F28, on one Tracker: each of the four signals
            // clears the taken token at once, and the read-time check withholds
            // it whenever the score does not show the game it was taken in.
            var f = new Tracker();
            string FT1 = Tok('8', 1, 1);
            f.ObserveRoomToken("R", "");
            f.OnGmStart("R");
            f.OnGameStart("S", "R", Reset, out line);
            f.ObserveRoomToken("R", FT1);
            f.ObserveScore(TwoEach);
            checks++;
            if (f.TokenFor("S", "R", FT1, TwoEach, true) != FT1 || f.TokenFor("S", "R", FT1, RoundUp, true) != FT1)
            { pass = false; detail += " F28:the-games-token-not-carried"; }
            string whyF;
            checks++;
            if (f.TokenFor("S", "R", FT1, Reset, true, out whyF) != "" || f.TokenFor("S", "R", FT1, Played, true) != ""
                || f.TokenFor("S", "R", FT1, Final, true) != "" || f.TokenFor("S", "R", FT1, default(Score), true) != ""
                || f.TokenFor("S", "R", FT1, Score.Of(0, 0, 1, 1, 1), true) != ""
                || f.TokenFor("S", "R", FT1, Score.Of(0, 0, 1, 1, 0), true) != "")
            { pass = false; detail += " F28:read-time-check"; }
            string whyNh;
            checks++;
            if (f.TokenFor("S", "R", FT1, TwoEach, false, out whyNh) != "" || whyNh != WhyNoHooks)
            { pass = false; detail += " F30:a-token-carried-without-the-lifecycle-hooks"; }
            f.ObserveScore(Final);
            checks++;
            if (f.Adopted != "" || f.TokenFor("S", "R", FT1, TwoEach, true) != "") { pass = false; detail += " F28:game-over-by-the-score"; }
            f.OnTokenGameOver("R", FT1);
            string FT2 = Tok('9', 2, 2);
            f.ObserveRead("S", true, 1, 0, false, false, false);
            f.OnGmStart("R");
            f.OnGameStart("S", "R", Reset, out line);
            f.ObserveRoomToken("R", FT2);
            f.ObserveScore(TwoEach);
            f.OnTokenGameOver("R", FT2);
            checks++;
            if (f.Adopted != "" || f.TokenFor("S", "R", FT2, TwoEach, true) != "") { pass = false; detail += " F28:game-over-by-the-watcher"; }
            string FT3 = Tok('a', 3, 3);
            f.ObserveRead("S", true, 2, 0, false, false, false);
            f.OnGmStart("R");
            f.OnGameStart("S", "R", Reset, out line);
            f.ObserveRoomToken("R", FT3);
            f.ObserveScore(TwoEach);
            string advanced = f.Adopted;
            f.ObserveRead("S", true, 3, 0, false, false, false);
            f.OnGmStart("R");
            f.OnGameStart("S", "R", Reset, out line);
            checks++;
            if (advanced != FT3 || f.Adopted != "" || f.TokenFor("S", "R", FT3, TwoEach, true) != "")
            { pass = false; detail += " F28:the-ordinal-advancing"; }
            string FT4 = Tok('b', 4, 4);
            f.ObserveRoomToken("R", FT4);
            f.ObserveScore(TwoEach);
            f.ObserveScore(Reset);
            checks++;
            if (f.Adopted != "" || f.TokenFor("S", "R", FT4, TwoEach, true) != "") { pass = false; detail += " F28:a-reset-by-the-score"; }
            // A later game's token seen first: nothing is taken for this game
            // after it, this game's own token included (a seat holding no
            // physical game measures by the number its posts name, round 7).
            var lo = new Tracker();
            lo.ObserveRoomToken("R", "");
            lo.OnGmStart("R");
            lo.OnGameStart("S", "R", Reset, out line);
            lo.ObserveRoomToken("R", Tok('1', 2, 2));
            lo.ObserveRoomToken("R", Tok('2', 1, 3));
            lo.ObserveScore(Played);
            checks++;
            if (lo.Adopted != "" || lo.TokenFor("S", "R", Tok('2', 1, 3), Played, true) != "")
            { pass = false; detail += " F28:taken-after-a-later-games-token"; }
            // A report at 0-0 with no points carries no token, even one taken
            // for its own game; the game's first point carries it.
            var z = new Tracker();
            z.ObserveRoomToken("R", "");
            z.OnGmStart("R");
            z.OnGameStart("S", "R", Reset, out line);
            z.ObserveRoomToken("R", Tok('3', 1, 1));
            checks++;
            if (z.Adopted != Tok('3', 1, 1) || z.TokenFor("S", "R", Tok('3', 1, 1), Reset, true) != ""
                || z.TokenFor("S", "R", Tok('3', 1, 1), Played, true) != Tok('3', 1, 1))
            { pass = false; detail += " F28:a-0-0-report-carried"; }
            // An unreadable score at the game start: no token in that game.
            var u = new Tracker();
            u.ObserveRoomToken("R", "");
            u.OnGmStart("R");
            u.OnGameStart("S", "R", default(Score), out line);
            u.ObserveRoomToken("R", Tok('c', 1, 1));
            u.ObserveScore(TwoEach);
            checks++;
            if (u.TokenFor("S", "R", Tok('c', 1, 1), TwoEach, true) != "") { pass = false; detail += " F28:an-unread-start-carried"; }
            // Play read after a reset with no game start ends this seat's
            // physical game.
            var pl = new Tracker();
            pl.ObserveRoomToken("R", "");
            pl.OnGmStart("R");
            pl.OnGameStart("S", "R", Reset, out line);
            pl.ObserveRoomToken("R", Tok('e', 1, 1));
            pl.ObserveScore(TwoEach);
            pl.ObserveScore(Final);
            pl.OnTokenGameOver("R", Tok('e', 1, 1));
            pl.ObserveScore(Reset);
            pl.ObserveScore(Played);
            int beforeSecond = pl.PhysicalOrdinal();
            pl.ObserveScore(TwoEach);
            checks++;
            if (beforeSecond != 1 || pl.PhysicalOrdinal() != 0) { pass = false; detail += " F28:play-without-a-start"; }

            // Round 7, finding F30, on one Tracker: the game's own game over and
            // its next start each end the taken token at once, and a reading of
            // the next game that follows the last one does not bring it back;
            // the value is not taken again. The genuine-game control: a seat
            // that sees every signal carries its game's token through a whole
            // game's readings, and one whose readings are far apart carries it
            // too (no gap withholds it); its game over ends it.
            string GV = Tok('7', 1, 1);
            var gv = new Tracker();
            gv.ObserveRoomToken("R", "");
            gv.OnGmStart("R");
            gv.OnGameStart("S", "R", Reset, out line);
            gv.ObserveRoomToken("R", GV);
            gv.ObserveScore(TwoEach);
            bool gvHeld = gv.TokenFor("S", "R", GV, RoundUp, true) == GV;
            string gvLine = gv.OnGmGameOver();
            gv.ObserveScore(RoundUp);
            gv.ObserveRoomToken("R", GV);
            checks++;
            if (!gvHeld || gvLine == null || gv.Adopted != "" || gv.TokenFor("S", "R", GV, RoundUp, true) != "")
            { pass = false; detail += " F30:the-games-own-game-over-kept-the-token"; }
            var gs = new Tracker();
            gs.ObserveRoomToken("R", "");
            gs.OnGmStart("R");
            gs.OnGameStart("S", "R", Reset, out line);
            gs.ObserveRoomToken("R", GV);
            gs.ObserveScore(TwoEach);
            bool gsHeld = gs.TokenFor("S", "R", GV, RoundUp, true) == GV;
            string gsLine = gs.OnGmStart("R");
            gs.ObserveScore(RoundUp);
            gs.ObserveRoomToken("R", GV);
            bool gsDropped = gs.Adopted == "" && gs.TokenFor("S", "R", GV, RoundUp, true) == "";
            gs.OnGameStart("S", "R", Reset, out line);
            gs.ObserveRoomToken("R", GV);
            checks++;
            if (!gsHeld || gsLine == null || !gsDropped || gs.Adopted != "")
            { pass = false; detail += " F30:the-games-own-start-kept-the-token"; }
            var lg = new Tracker();
            lg.ObserveRoomToken("R", "");
            lg.OnGmStart("R");
            lg.OnGameStart("S", "R", Reset, out line);
            lg.ObserveRoomToken("R", GV);
            int lgReadings = 0, lgCarried = 0;
            for (int rs = 0; rs <= 8; rs++)
            {
                // Rounds 0-0, 1-0, 1-1, 2-1, ... 4-4: each round's reset, then a
                // point, then one point each (the first round starts at 0-0).
                int r1 = (rs + 1) / 2, r2 = rs / 2;
                for (int pt = rs == 0 ? 1 : 0; pt <= 2; pt++)
                {
                    Score s = Score.Of(r1, r2, pt >= 1 ? 1 : 0, pt >= 2 ? 1 : 0, 5);
                    lg.ObserveScore(s);
                    lgReadings++;
                    if (lg.TokenFor("S", "R", GV, s, true) == GV) lgCarried++;
                }
            }
            lg.ObserveScore(Score.Of(5, 4, 0, 0, 5));
            bool lgEnded = lg.Adopted == "" && lg.TokenFor("S", "R", GV, Score.Of(5, 4, 0, 0, 5), true) == "";
            var lj = new Tracker();
            lj.ObserveRoomToken("R", "");
            lj.OnGmStart("R");
            lj.OnGameStart("S", "R", Reset, out line);
            lj.ObserveRoomToken("R", GV);
            lj.ObserveScore(TwoEach);
            Score nearEnd = Score.Of(4, 4, 1, 1, 5);
            bool ljCarried = lj.TokenFor("S", "R", GV, nearEnd, true) == GV;
            lj.ObserveScore(nearEnd);
            ljCarried = ljCarried && lj.TokenFor("S", "R", GV, nearEnd, true) == GV;
            checks++;
            if (lgReadings != 26 || lgCarried != lgReadings || !lgEnded || !ljCarried)
            {
                pass = false;
                detail += " F30-LONG-GAME-CONTROL:carried=" + lgCarried + "/" + lgReadings
                          + (lgEnded ? "" : ",not-ended-at-its-game-over")
                          + (ljCarried ? "" : ",far-apart-readings-not-carried");
            }

            // Round 8, finding F31, on one Tracker: a read showing the series
            // with no recorded game, never relocked and no pair of two points or
            // more on its record names no game (round 7's creator boot is gone);
            // only the series' reporter asks, once per game, at a game start
            // the game itself reported, holding no ordinal, with its client's
            // reports clean and no read showing the series recorded, relocked
            // or played; while the ask is out it waits (WhyFirstGamePending); a
            // refusal leaves it holding none; the issue makes it hold physical
            // game 1 and publish that game's token, host or not; its next
            // game's host derives its nonce from the issued one (round 9, M2);
            // an answer for
            // another game, after a join, after its client sent or queued a
            // report, or without a nonce is not taken; a join drops the issue.
            var b = new Tracker();
            string whyB, whyX;
            int genB = 0, genX;
            b.NoteRoomJoined("R");
            b.ObserveRoomToken("R", "");
            b.ObserveRead("S", true, 0, 0, true, false, false);
            b.OnGmStart("R");
            b.OnGameStart("S", "R", Reset, out line);
            checks++;
            if (b.PhysicalOrdinal() != 0 || b.TokenToPublish(true, true, "", out whyB) != "" || whyB != WhyNoOrdinal)
            { pass = false; detail += " F31:absence-named-a-game"; }
            checks++;
            if (!AskOutcome(true, 0, false, false, true, true)
                || AskOutcome(false, 0, false, false, true, true)
                || AskOutcome(true, 1, false, false, true, true)
                || AskOutcome(true, 0, true, false, true, true)
                || AskOutcome(true, 0, false, true, true, true)
                || AskOutcome(true, 0, false, false, false, true)
                || AskOutcome(true, 0, false, false, true, false))
            { pass = false; detail += " F31:who-asks"; }
            checks++;
            if (b.AskFirstGame("S2", "R", true, true, out genX, out whyX) || b.AskFirstGame("S", "R2", true, true, out genX, out whyX)
                || b.AskFirstGame("", "R", true, true, out genX, out whyX) || b.AskFirstGame("S", "", true, true, out genX, out whyX)
                || !b.AskFirstGame("S", "R", true, true, out genB, out whyX) || genB <= 0
                || b.AskFirstGame("S", "R", true, true, out genX, out whyX)
                || b.TokenToPublish(true, true, "", out whyB) != "" || whyB != WhyFirstGamePending
                || b.TokenToPublish(true, false, "", out whyB) != "" || whyB != WhyNoOrdinal)
            { pass = false; detail += " F31:the-ask"; }
            string refusedLine = b.OnFirstGame("S", "R", genB, false, "", "a game of the series is recorded", true);
            checks++;
            if (b.PhysicalOrdinal() != 0 || refusedLine == null || b.TokenToPublish(true, true, "", out whyB) != ""
                || whyB != WhyNoOrdinal || b.AskFirstGame("S", "R", true, true, out genX, out whyX))
            { pass = false; detail += " F31:a-refusal"; }
            // An issue the client cannot keep (its report ledger took no
            // anchor, GameStateWatcher.TryAskTeamFirstGame) is dropped: the ask
            // is settled, nothing is held, and the same answer offered again is
            // not taken.
            var bd = new Tracker();
            int genD;
            string whyD;
            bd.NoteRoomJoined("R");
            bd.ObserveRoomToken("R", "");
            bd.OnGmStart("R");
            bd.OnGameStart("S", "R", Reset, out line);
            bool askedD = bd.AskFirstGame("S", "R", true, true, out genD, out whyD);
            string droppedLine = bd.DropFirstGame(genD, "the report ledger cannot be written");
            checks++;
            if (!askedD || droppedLine == null || bd.PhysicalOrdinal() != 0
                || bd.TokenToPublish(true, true, "", out whyD) != "" || whyD != WhyNoOrdinal
                || bd.OnFirstGame("S", "R", genD, true, "0123456789abcdef", null, true)
                       .IndexOf("not taken", StringComparison.Ordinal) < 0
                || bd.PhysicalOrdinal() != 0)
            { pass = false; detail += " F31:a-dropped-answer"; }
            const string Issued = "0123456789abcdef";
            var bi = new Tracker();
            int genI;
            string whyI, whyH;
            bi.NoteRoomJoined("R");
            bi.ObserveRoomToken("R", "");
            bi.ObserveRead("S", true, 0, 0, true, false, false);
            bi.OnGmStart("R");
            bi.OnGameStart("S", "R", Reset, out line);
            bi.AskFirstGame("S", "R", true, true, out genI, out whyI);
            string issuedLine = bi.OnFirstGame("S", "R", genI, true, Issued, null, true);
            string guestTok = bi.TokenToPublish(false, true, "", out whyI);
            string hostTok = bi.TokenToPublish(true, true, "", out whyH);
            checks++;
            if (bi.PhysicalOrdinal() != 1 || issuedLine == null || guestTok != MakeToken(Issued, 1, 1) || hostTok != guestTok)
            { pass = false; detail += " F31:the-issue"; }
            bi.ArmPublished(guestTok);
            bi.ObserveRoomToken("R", guestTok);
            bi.ObserveScore(Played);
            checks++;
            if (bi.Adopted != guestTok || bi.TokenFor("S", "R", guestTok, Played, true) != guestTok
                || bi.TokenToPublish(false, true, guestTok, out whyI) != "" || whyI != WhyTaken)
            { pass = false; detail += " F31:the-issued-games-own-echo"; }
            bi.ObserveScore(Final);
            bi.OnTokenGameOver("R", guestTok);
            bi.ObserveRead("S", true, 1, 0, true, false, false);
            bi.OnGmStart("R");
            bi.OnGameStart("S", "R", Reset, out line);
            string nextI = bi.TokenToPublish(true, true, guestTok, out whyI);
            string ni;
            int oi;
            long ei;
            checks++;
            if (!TryParseToken(nextI, out ni, out oi, out ei) || oi != 2 || ei != 2 || ni == Issued
                || ni != ChainNonce(Issued, 2, 2)
                || bi.TokenToPublish(false, true, guestTok, out whyH) != "" || whyH != WhyNotHost)
            { pass = false; detail += " M2:the-next-games-derived-nonce"; }
            checks++;
            if (IssueOrdinal(true, Issued, 0, false, true) != 1
                || IssueOrdinal(false, "", 0, false, true) != 0
                || IssueOrdinal(true, Issued, 1, false, true) != 0
                || IssueOrdinal(true, Issued, 0, true, true) != 0
                || IssueOrdinal(true, Issued, 0, false, false) != 0
                || IssueOrdinal(true, "", 0, false, true) != 0
                || IssueOrdinal(true, "0123456789ABCDEF", 0, false, true) != 0)
            { pass = false; detail += " F31:an-answer-taken-when-it-may-not"; }
            string joinedI = bi.NoteRoomJoined("R");
            bi.ObserveRoomToken("R", "");
            bi.OnGmStart("R");
            bi.OnGameStart("S", "R", Reset, out line);
            checks++;
            if (joinedI == null || bi.PhysicalOrdinal() != 0 || bi.TokenToPublish(true, true, "", out whyI) != ""
                || whyI != WhyNoOrdinal)
            { pass = false; detail += " F31:a-join-kept-the-issue"; }
            // A join drops the physical game; a game start the game itself did
            // not report (a rejoin in the middle of a game) takes nothing.
            var bj = new Tracker();
            bj.NoteRoomJoined("R");
            bj.ObserveRoomToken("R", "");
            bj.ObserveRead("S", true, 0, 0, true, false, false);
            bj.OnGmStart("R");
            bj.OnGameStart("S", "R", Reset, out line);
            bj.ObserveRoomToken("R", Tok('8', 1, 1));
            string joinLine = bj.NoteRoomJoined("R");
            checks++;
            if (bj.PhysicalOrdinal() != 0 || joinLine == null) { pass = false; detail += " F29:a-join-kept-the-ordinal"; }
            bj.ObserveRoomToken("R", "");
            bj.ObserveRead("S", true, 1, 0, true, false, false);
            bj.OnGameStart("S", "R", Played, out line);
            bj.ObserveRoomToken("R", Tok('9', 2, 3));
            checks++;
            if (bj.Adopted != "" || bj.PhysicalOrdinal() != 0) { pass = false; detail += " F29:an-unreported-start-took-a-token"; }
            // Two starts of the game itself before one of this seat's (its
            // watcher missed a game): the physical game is lost.
            var g2 = new Tracker();
            g2.ObserveRoomToken("R", "");
            g2.OnGmStart("R");
            g2.OnGameStart("S", "R", Reset, out line);
            g2.ObserveRoomToken("R", Tok('5', 1, 1));
            g2.ObserveScore(Final);
            g2.OnTokenGameOver("R", Tok('5', 1, 1));
            int g2Before = g2.PhysicalOrdinal();
            g2.OnGmStart("R");
            g2.OnGmStart("R");
            g2.OnGameStart("S", "R", Reset, out line);
            checks++;
            if (g2Before != 1 || g2.PhysicalOrdinal() != 0) { pass = false; detail += " F29:a-missed-game-kept-the-ordinal"; }
            // A value read outside this seat's game before the game itself
            // started its next game is stale; one read after that start is
            // left to the game start (#182).
            var sv = new Tracker();
            sv.NoteRoomJoined("R");
            sv.ObserveRoomToken("R", "");
            sv.ObserveRead("S", true, 1, 0, true, false, false);
            sv.ObserveRoomToken("R", Tok('6', 2, 2));
            sv.OnGmStart("R");
            sv.ObserveRoomToken("R", Tok('7', 2, 3));
            sv.OnGameStart("S", "R", Reset, out line);
            sv.ObserveRoomToken("R", Tok('6', 2, 2));
            checks++;
            if (sv.Adopted != "") { pass = false; detail += " F29:a-value-read-before-the-games-own-start-taken"; }
            sv.ObserveRoomToken("R", Tok('7', 2, 3));
            checks++;
            if (sv.Adopted != Tok('7', 2, 3) || sv.PhysicalOrdinal() != 2) { pass = false; detail += " F29:a-value-read-after-the-games-own-start-lost"; }

            // The publish: physical game 1's token, issued, the issued nonce
            // itself, published by the seat it was issued to, host or not, once,
            // in the game's first round, its epoch above the room's.
            var w = new Tracker();
            string why;
            int wGen;
            w.NoteRoomJoined("R");
            w.ObserveRoomToken("R", TA);
            w.ObserveRead("S", true, 0, 0, true, false, false);
            checks++;
            if (w.TokenToPublish(true, true, TA, out why) != "" || why != WhyNoGame) { pass = false; detail += " publish:outside-a-game"; }
            w.OnGmStart("R");
            w.OnGameStart("S", "R", Reset, out line);
            w.ObserveRoomToken("R", TA);
            w.AskFirstGame("S", "R", true, true, out wGen, out why);
            w.OnFirstGame("S", "R", wGen, true, "5555555555555555", null, true);
            string drawn = w.TokenToPublish(false, true, TA, out why);
            string dn;
            int dord;
            long dep;
            string whyHost, whyLate;
            checks++;
            if (!TryParseToken(drawn, out dn, out dord, out dep) || dn != "5555555555555555" || dord != 1 || dep != 2 || why != null
                || w.TokenToPublish(true, true, TA, out whyHost) != drawn
                || w.TokenToPublish(false, false, TA, out whyLate) != "" || whyLate != WhyLate)
            { pass = false; detail += " publish:the-issued-game"; }
            w.ArmPublished(drawn);
            checks++;
            if (w.TokenToPublish(true, true, TA, out why) != "" || why != WhyPublished) { pass = false; detail += " publish:twice-in-a-game"; }
            w.ObserveRoomToken("R", drawn);
            w.ObserveScore(Played);
            checks++;
            if (w.TokenFor("S", "R", drawn, Played, true) != drawn || w.TokenToPublish(true, true, drawn, out why) != "" || why != WhyTaken)
            { pass = false; detail += " publish:own-echo"; }
            // Round 7, finding F29: a host that joined the room holds no
            // physical game, however many games a read shows recorded, and
            // publishes nothing (round 6 seeded it from the count); a publish
            // it takes grounds it, and at its next game start the game itself
            // reported it would publish the next game (round 9, M2: grounded on
            // a later game's token it holds no root and publishes nothing,
            // WhyNoAnchor; one grounded on physical game 1's token names the
            // next game, continues the room's epochs, and derives its nonce
            // from that root); a seat that is not the host publishes nothing.
            var e = new Tracker();
            e.NoteRoomJoined("R");
            e.ObserveRoomToken("R", Tok('d', 5, 7));
            e.ObserveRead("S", true, 5, 0, true, false, false);
            e.OnGmStart("R");
            e.OnGameStart("S", "R", Reset, out line);
            string whySeed;
            string seeded = e.TokenToPublish(true, true, Tok('d', 5, 7), out whySeed);
            checks++;
            if (seeded != "" || whySeed != WhyNoOrdinal) { pass = false; detail += " F29:a-joined-host-published-from-the-count"; }
            e.ObserveRoomToken("R", Tok('4', 6, 8));
            e.ObserveScore(Played);
            e.ObserveScore(Final);
            e.OnTokenGameOver("R", Tok('4', 6, 8));
            e.ObserveRead("S", true, 6, 0, true, false, false);
            e.OnGmStart("R");
            e.OnGameStart("S", "R", Reset, out line);
            string next = e.TokenToPublish(true, true, Tok('4', 6, 8), out why);
            string whyGuest;
            bool guestNone = e.TokenToPublish(false, true, Tok('4', 6, 8), out whyGuest) == "" && whyGuest == WhyNotHost;
            var none = new Tracker();
            none.ObserveRoomToken("R", "");
            none.OnGameStart("S", "", Reset, out line);
            string whyNone;
            checks++;
            if (next != "" || why != WhyNoAnchor || !guestNone
                || none.TokenToPublish(true, true, "", out whyNone) != "" || whyNone != WhyNoOrdinal)
            { pass = false; detail += " M2:a-later-token-gave-a-root"; }
            var e1 = new Tracker();
            e1.NoteRoomJoined("R");
            e1.ObserveRoomToken("R", "");
            e1.ObserveRead("S", true, 0, 0, true, false, false);
            e1.OnGmStart("R");
            e1.OnGameStart("S", "R", Reset, out line);
            e1.ObserveRoomToken("R", Tok('4', 1, 8));
            e1.ObserveScore(Played);
            e1.ObserveScore(Final);
            e1.OnTokenGameOver("R", Tok('4', 1, 8));
            e1.ObserveRead("S", true, 1, 0, true, false, false);
            e1.OnGmStart("R");
            e1.OnGameStart("S", "R", Reset, out line);
            string next1 = e1.TokenToPublish(true, true, Tok('4', 1, 8), out why);
            checks++;
            if (!TryParseToken(next1, out dn, out dord, out dep) || dord != 2 || dep != 9
                || dn != ChainNonce("4444444444444444", 2, 9) || dn == "4444444444444444")
            { pass = false; detail += " publish:ordinal-epoch-and-derived-nonce"; }
            // Round 9, finding M2: a root survives a join of the room while
            // the later token the seat is grounded on again is the one derived
            // from it (the next game's publish derives from it); a later token
            // that is not drops it.
            string g2Tok = MakeToken(ChainNonce(Issued, 2, 2), 2, 2);
            string rootKept = RootAfterJoin(Issued, g2Tok, out whyH);
            string rootDropped = RootAfterJoin(Issued, MakeToken("5eed1ab00f1e2d3c", 2, 2), out whyI);
            checks++;
            if (rootKept != MakeToken(ChainNonce(Issued, 3, 3), 3, 3) || rootDropped != "" || whyI != WhyNoAnchor)
            { pass = false; detail += " M2:the-root-across-a-join"; }

            // The token's wire: its shape, both canonicals, the query, the pin.
            string pn;
            int po;
            long pe;
            checks++;
            if (!TokenValid(PinToken) || !TokenValid(MakeToken(DrawNonce(), 1, 1)) || !TokenValid(MakeToken(DrawNonce(), MaxGameNumber, MaxEpoch))
                || TokenValid("0123456789abcdef") || TokenValid("0123456789ABCDEF:3:7") || TokenValid("0123456789abcde:3:7")
                || TokenValid("0123456789abcdef:0:7") || TokenValid("0123456789abcdef:100:7") || TokenValid("0123456789abcdef:03:7")
                || TokenValid("0123456789abcdef:3:0") || TokenValid("0123456789abcdef:3:1000000000") || TokenValid("0123456789abcdef:3:-7")
                || TokenValid("0123456789abcdef:3:7:1") || TokenValid("0123456789abcdef::7") || TokenValid("") || TokenValid(null)
                || !TryParseToken(PinToken, out pn, out po, out pe) || pn != "0123456789abcdef" || po != 3 || pe != 7
                || Describe(PinToken) != "01234567 (game 3, epoch 7)")
            { pass = false; detail += " token-valid"; }
            checks++;
            if (TokenCanonical("S", "P", 1, 2, 3, "room_x", TB) != "team-live-points-token:S:P:1:2:3:room_x:" + TB
                || DcTokenCanonical("P", "S", "Q", TB) != "team-dc-token:P:S:Q:" + TB
                || TokenCanonical("S", "P", 1, 2, 3, "room_x", Tok('b', 2, 2)) == TokenCanonical("S", "P", 1, 2, 3, "room_x", TB)
                || DcTokenCanonical("P", "S", "Q", Tok('b', 1, 3)) == DcTokenCanonical("P", "S", "Q", TB))
            { pass = false; detail += " token-canonicals"; }
            checks++;
            if (QueryToken(TB, "sig") != "&game_token=" + TB + "&token_sig=sig") { pass = false; detail += " query-token"; }
            checks++;
            if (TokenCanonical(PinSeries, PinReporter, 2, 1, 3, PinRoom, PinToken) != PinTokenExpected
                || DcTokenCanonical(PinReporter, PinSeries, PinDcPlayer, PinToken) != PinDcTokenExpected)
            { pass = false; detail += " token-pin"; }
            checks++;
            if (FirstGameCanonical(PinSeries, PinReporter, PinRoom) != PinFirstGameExpected
                || QueryFirstGame(PinReporter, "r", "sig") != "?requester_steam_id=" + PinReporter + "&photon_room_id=r&sig=sig")
            { pass = false; detail += " first-game-pin"; }
            // Round 8, finding F31: the report ledger's lines and the outbox
            // rule (ApiClient.cs reads and writes the ledger through these).
            // Round 9, finding M2: the issue's line holds the whole nonce, and
            // a round-8 client's 8-digit anchor line no longer parses.
            {
                bool al;
                string ls, la;
                checks++;
                if (!ParseLedgerLine(LedgerSent(PinSeries), out al, out ls, out la) || al || ls != PinSeries || la != ""
                    || !ParseLedgerLine(LedgerIssued(PinSeries, PinChainRoot) + "\r", out al, out ls, out la) || !al
                    || ls != PinSeries || la != PinChainRoot
                    || ParseLedgerLine("sent " + PinSeries.Substring(0, 12) + " x", out al, out ls, out la)
                    || ParseLedgerLine("issued " + PinSeries + " 0123456789abcde", out al, out ls, out la)
                    || ParseLedgerLine("issued " + PinSeries + " 0123456789ABCDEF", out al, out ls, out la)
                    || ParseLedgerLine("anchor " + PinSeries + " 0123abcd", out al, out ls, out la)
                    || ParseLedgerLine("sen", out al, out ls, out la)
                    || ParseLedgerLine("", out al, out ls, out la)
                    || ParseLedgerLine("sent " + PinSeries + "\nsent x", out al, out ls, out la)
                    || LedgerKey("") || LedgerKey("a b") || LedgerKey(new string('a', 65)) || !LedgerKey(PinSeries))
                { pass = false; detail += " F31:ledger-lines"; }
                string rep = "{\"series_id\":\"" + PinSeries + "\",\"t1a\":{}}";
                checks++;
                if (!QueuedReportOf("http://h:1/api/v1/team/matches", rep, PinSeries)
                    || QueuedReportOf("http://h:1/api/v1/team/matches", rep, "5b0c7e1a")
                    || QueuedReportOf("http://h:1/api/v1/matches", rep, PinSeries)
                    || QueuedReportOf(null, rep, PinSeries)
                    || !QueuedReportOf("http://h:1/api/v1/team/matches", null, PinSeries))
                { pass = false; detail += " F31:queued-report"; }
            }

            string sweep = " (sweep: " + cur.Timelines + " timelines per rule; tracker: " + cur.Posts + " posts, "
                + cur.Filed + " filed, " + cur.Wrong + " under another game, " + cur.CleanFirstFiled + " of "
                + cur.CleanFirst + " clean first posts filed; own count: " + own.Wrong + " under another game; "
                + "send-time read: " + send.Wrong + "; never naming: " + never.CleanFirstFiled + " of "
                + never.CleanFirst + " clean first posts filed; token sweep: " + tok.Timelines + " timelines per rule,"
                + " token rule: " + tok.Settled + " settled, " + tok.FromAnother + " from another game, "
                + tok.CleanSettled + " of " + tok.Clean + " clean DC reports settled; without the token: "
                + untok.Settled + " settled, " + untok.FromAnother + " from another game; F27 sweep: " + f27.Timelines
                + " timelines, " + f27.Settled + " settled, " + f27.FromAnother + " from another game, "
                + f27.LiveSettled + " of " + f27.Live + " level DC reports settled; F28 sweep: " + f28t.Timelines
                + " timelines, " + f28t.Across + " tokens across a boundary, " + f28t.SettledAcross + " settled across a"
                + " boundary, " + f28t.Carried + " of " + f28t.Carry + " no-boundary reports carried, " + f28t.CarriedGap
                + " of " + f28t.CarryGap + " after a gap; without the game's own game over and start: " + f28kept.Across
                + " across a boundary, " + f28kept.SettledAcross + " settled; F30 sweep: " + f30s.Timelines
                + " timelines, " + f30s.Across + " tokens sent across the boundary, " + f30s.Settled + " settled, "
                + f30s.Fresh + " of " + f30s.FreshDue + " fresh game-3 tokens carried where due; without the game's own"
                + " game over and start: " + f30kept.Across + " across, " + f30kept.FromAnother + " settled from"
                + " another game; a hook not attached: " + f30nh.Sent + " sent; F29 sweep: " + f29.Timelines
                + " timelines per rule, " + f29.Settled + " settled, " + f29.Wrong + " while a result was queued, "
                + f29.Carrying + " tokens carried while queued (" + f29.ReanchoredCarrying + " by re-anchored seats), "
                + f29.LiveSettled + " of " + f29.Live + " in-step DC reports settled; without the sitting rule: "
                + f29bare.Wrong + " while queued, " + f29bare.Carrying + " tokens carried; round 6's host seed: "
                + f29kept.Wrong + " while queued, " + f29open.Wrong + " without the sitting rule, and "
                + f29anchored.Wrong + " against the anchor rule; F31 sweep: " + f31.Timelines + " timelines per rule, "
                + f31.Settled + " settled, " + f31.Wrong + " wrongly, " + f31.Carrying + " tokens carried and "
                + f31.Named + " games named; without the session rules: " + f31open.Settled + " settled, "
                + f31open.Wrong + " wrongly; round 7's creator boot against a server without the anchor rule: "
                + f31boot.Settled + " settled, " + f31boot.Wrong + " wrongly; named: " + f31Kept
                + " of 12 kept-copy timelines settled wrongly, " + f31Server + " against the anchor rule; the"
                + " reporter's ledger lost: " + f31Lost + " of 24 timelines named a game, carried a token or settled, "
                + f31Unlanded + " of 12 with game 1's result never landing, and " + f31UnlandedOpen + " of those 12"
                + " settled wrongly without the session rules, " + f31OthersAlone + " of 12 named a game, carried a token"
                + " or settled against the other-session rule alone; the void alone: " + f31Void + " of 12 settled, "
                + f31VoidOpen + " of 12 wrongly with the void unread; " + f31Fresh + " of 5 fresh-room DC reports"
                + " settled, " + f31FreshRestarted + " where the reporter restarted and reported the leave; M2: " + m2Prefix
                + " of 6 fresh rooms settled from game-2 tokens sharing only the issued nonce's first 8 digits, "
                + m2PrefixRead + " of 5 with round 8's comparison; " + m2Anchor + " of 12 settled where game 1's report"
                + " carried an anchor sharing only those 8 digits, " + m2AnchorRead + " of 10 with round 8's comparison;"
                + " M1, the"
                + " reporter's account in a second process: " + m1Live + " of 48 timelines named a game, carried a token"
                + " or settled where the first process held a session (" + m1LiveR8 + " settled wrongly with round 8's"
                + " issuance, " + m1LiveNoOthers + " without the other-session rule), " + m1Posted + " of 48 where its"
                + " post reached the server (" + m1PostedR8 + " with round 8's issuance, " + m1PostedNoAny
                + " without the any-post rule), " + m1Unseen + " of 48 settled where nothing of it reached the server"
                + " (the residual, " + m1UnseenWrong + " wrongly); twin sweeps: " + m1LiveSweep.Timelines
                + " timelines each, " + m1LiveSweep.Settled + " and " + m1PostedSweep.Settled + " settled, "
                + m1UnseenSweep.Settled + " unseen)";
            return SentinelTag + " " + (pass ? "PASS" : "FAIL") + ": " + checks + " checks" + sweep + detail;
        }
    }
}
