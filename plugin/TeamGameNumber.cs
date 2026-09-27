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
    /// The client's own count, in FFA's gameNumber shape (advanced at each
    /// game start, restarted when the series or the room changes, cleared
    /// when the room is left), is kept for two things only: the drift note
    /// logged at every game start, and the one case where a number is safe
    /// without any read: a series' FIRST game start in a room is named 1. No
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
    /// published for, by the host's own count of the room's game starts, and
    /// an EPOCH the host raises at each publish; a seat takes it only for the
    /// game its own count and its posts both name; a post or a DC report
    /// carries it only while this seat's reading of the score, made when the
    /// post or the report is built, still shows that game; and the server
    /// reads it only for the game it names. Each of those rules withholds a
    /// token; none grants one.
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
        // findings F27 and F28) ----------------------------------------------
        //
        // At each game start in a cr_ff room the room's host publishes a token
        // as the room property TokenRoomKey
        // (GameStateWatcher.TryPublishTeamToken). A token has three parts,
        // joined by ':' (MakeToken): a fresh NONCE (16 random lowercase hex
        // digits), the ORDINAL of the physical game it is published for, and
        // the host's EPOCH. The ordinal is the host's own count of the game
        // starts it saw in the room, anchored to the server's count at the
        // first of them (Tracker.PhysicalOrdinal); the epoch is one above the
        // highest the host has read in the room or published, so a later
        // publish carries a higher one. A post and a DC report sign all three.
        // Every seat, the host included, takes the value the room itself
        // holds: a client sees its own room-property write only when the
        // server's echo of it arrives (#428), so until then the host's posts
        // go without a token like every other seat's, and a send that never
        // reached the room is never used.
        //
        // A seat takes (adopts) a value it reads during a game only when
        //   - the value names the ordinal this seat holds for the game, by its
        //     own count and by the number its posts name (round 6, F27: a seat
        //     a game ahead of a lagging host no longer takes the host's token
        //     as its own game's);
        //   - its epoch is above the epoch of every value stale for this seat,
        //     so a value published before one this seat already holds as an
        //     earlier game's is refused even when this seat never read it;
        //   - its nonce is not stale. Stale are the first value read in the
        //     room (it may belong to a game this seat did not see start), every
        //     value read during an earlier game, and the value the room held
        //     at each game over.
        // A different value read while one is taken ends it for the rest of
        // the game (round 6, F28: the next game's publish, or a second
        // publisher). A post or a DC report carries the taken value only while
        // the room still holds it and while this seat's own reading of the
        // score, taken when the post or the report is built, still shows the
        // game the value was taken in (Tracker.TokenFor): a game over, a fall
        // of the rounds, a 0-0 with no points, or a gap in the readings that
        // could hide a game boundary each withhold it, whether or not a game
        // over or a game start reached this seat. The server settles a
        // lead-forfeit only from posts that carried the DC report's token,
        // when that token names the game being settled, is its record's own,
        // no post filed there carried another token or one naming another
        // game, and it is on no other record of the series (main.py,
        // _team_game_token_seats). A missing token only ever withholds that
        // settlement.

        /// <summary>The room property the host publishes the token in.</summary>
        internal const string TokenRoomKey = "cr_tg_token";

        /// <summary>Why a seat does not publish (Tracker.TokenToPublish).
        /// Only WhyNotHost can change inside the game's first round (a host
        /// handoff), so GameStateWatcher retries on it and on nothing else.</summary>
        internal const string WhyNoGame = "no game is in progress";
        internal const string WhyMissed = "this seat missed a game boundary";
        internal const string WhyNoOrdinal = "this seat holds no physical-game ordinal for this game";
        internal const string WhyTaken = "this game's token is already in the room";
        internal const string WhyPublished = "this seat already published this game's token";
        internal const string WhyLate = "the game's first round is over";
        internal const string WhyNotHost = "this seat is not the room's host";
        internal const string WhyEpoch = "the room's epoch is at its bound";

        /// <summary>The highest epoch a token carries (nine digits).</summary>
        internal const long MaxEpoch = 999999999;

        /// <summary>Round 6, finding F28: the longest (seconds) this seat may
        /// go without a fresh reading of its score inside a game before it can
        /// no longer rule out a game boundary in the gap. A reading is as fresh
        /// as the room's transport: the time it was taken less the time the
        /// transport had then been silent (Score.Silent). A longer gap ends the
        /// game's token and this seat's count of the room's games. The poll
        /// reads the score every 0.1 s of real time (ROUNDS holds
        /// Time.timeScale at 1, #332), and a boundary the score cannot show
        /// needs the rest of one game and the next game's play up to a score
        /// that follows the last reading (Follows): at least a game's rounds
        /// to win of play inside one gap (#771: no honest game is that short).
        /// It only ever withholds: no token is carried BECAUSE a gap was
        /// short.</summary>
        internal const double MaxSampleAge = 5.0;

        /// <summary>The scoreboard as a seat reads it (round 6, finding F28):
        /// both sides' rounds and points, the rounds a game is won at (0 = not
        /// known), and how long (seconds) the room's transport had received
        /// nothing when it was read (Silent): the reading shows the room as of
        /// that long before it was taken. Read false: it could not be read (the
        /// fields are not resolved, or the room's messages are held), and
        /// nothing that reads it carries a token.</summary>
        internal struct Score
        {
            public bool Read;
            public int R1, R2, P1, P2, RoundsToWin;
            public double Silent;

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

        /// <summary>A token as a log line names it: the nonce's first 8 digits,
        /// its game and its epoch.</summary>
        internal static string Describe(string token)
        {
            string n;
            int o;
            long e;
            if (!TryParseToken(token, out n, out o, out e)) return "(none)";
            return n.Substring(0, 8) + " (game " + Num(o) + ", epoch " + e.ToString(CultureInfo.InvariantCulture) + ")";
        }

        private static string Secs(double s)
        {
            return s.ToString("0.00", CultureInfo.InvariantCulture);
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
            // The own count: game starts seen for (countSeries, countRoom).
            private string countSeries = "", countRoom = "";
            private int countStarts;
            // Round 6, finding F27: the physical game's ordinal by this seat's
            // own count. `anchor` is the number frozen at the first game start
            // counted (0 = none, and then no ordinal in this room); `physical`
            // is the game in progress, anchor + countStarts - 1 (0 = none).
            // `countLost`: this seat saw a game boundary without its game start
            // (a game boundary inside its game, or play read after a reset with
            // no game start), so its count no longer names physical games until
            // the count restarts (the series or the room changes, or the room is
            // left).
            private int anchor, physical;
            private bool countLost;
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
            private bool overSeen;             // the score showed the game in progress over
            private bool boundaryMissed;       // a game boundary this seat did not see: no token until the next start
            private bool withdrawn;            // the game's token was withdrawn: none for the rest of the game
            private bool published;            // this seat's publish for the game in progress was sent
            private string noted = "";         // the last value logged (each is logged once)
            private long epochRead, epochStale, epochPublished;
            // Round 6, finding F28: this seat's readings of the score. The last
            // one and the time its information is from (`sampledAt`, seconds on
            // the caller's clock: when it was taken, less the transport's
            // silence then); `sampled`: one was taken in the game in progress
            // (from its start). Between games: `resetOut`, a reset was read since
            // this seat's game ended, and `playOut`, the readings of play in a
            // row since that reset with no game start.
            private bool sampled;
            private Score lastScore;
            private double sampledAt;
            private bool resetOut;
            private int playOut;

            /// <summary>A read of team/series/{id}/state for `seriesId`.
            /// `hasWins`: the answer carried both win counts (the canceled and
            /// dc_incomplete answers carry neither, and a missing field parses as
            /// 0, which is not a read). Never lowers what an earlier read showed.</summary>
            internal void ObserveRead(string seriesId, bool hasWins, int t1Wins, int t2Wins)
            {
                if (string.IsNullOrEmpty(seriesId) || !hasWins || t1Wins < 0 || t2Wins < 0) return;
                int n = t1Wins + t2Wins;
                int had;
                if (recorded.TryGetValue(seriesId, out had))
                {
                    if (n > had) recorded[seriesId] = n;
                    return;
                }
                if (recorded.Count >= MaxSeries) recorded.Clear();
                recorded[seriesId] = n;
            }

            /// <summary>A game starts in a cr_ff room: freeze the number its posts
            /// carry, and count the physical game (round 6, finding F27). `live`
            /// is the score this seat reads at the start and `now` the time on
            /// the clock ObserveScore and TokenFor are given (round 6, finding
            /// F28: the game's first reading; one that cannot be read means no
            /// token in this game). Returns the number, 0 = its posts go without
            /// the pair; `log` is the line to write.</summary>
            internal int OnGameStart(string seriesId, string room, Score live, double now, out string log)
            {
                BeginGameToken(live, now);
                seriesId = seriesId ?? "";
                room = room ?? "";
                string sid8 = seriesId.Length > 8 ? seriesId.Substring(0, 8) : seriesId;
                if (seriesId.Length == 0 || room.Length == 0)
                {
                    Freeze("", "", 0);
                    physical = 0;
                    log = LogTag + " game start with no " + (seriesId.Length == 0 ? "series" : "room")
                          + ": its posts go without the pair";
                    return 0;
                }
                string restarted = "";
                if (seriesId != countSeries || room != countRoom)
                {
                    if (countStarts > 0) restarted = " (the own count restarted: the series or the room changed)";
                    countSeries = seriesId;
                    countRoom = room;
                    countStarts = 0;
                    anchor = 0;
                    countLost = false;
                }
                countStarts++;
                int had;
                bool read = recorded.TryGetValue(seriesId, out had);
                int n = read ? had + 1 : (countStarts == 1 ? 1 : 0);
                if (n > MaxGameNumber || !RoomSendable(room))
                {
                    Freeze(seriesId, room, 0);
                    Count(0);
                    log = LogTag + " series=" + sid8 + " game number " + Num(n) + " or the room is outside what the"
                          + " server accepts: its posts go without the pair" + restarted + OrdinalNote();
                    return 0;
                }
                Freeze(seriesId, room, n);
                Count(n);
                if (read)
                {
                    log = LogTag + " series=" + sid8 + " game " + Num(n) + " (" + Num(had) + " recorded as last read;"
                          + " game start " + Num(countStarts) + " of this series in this room"
                          + (n != countStarts ? ", which differs: the server's count is the one named" : "") + ")"
                          + restarted;
                }
                else if (n == 1)
                {
                    log = LogTag + " series=" + sid8 + " game 1 (the series' first game start in this room, no read"
                          + " of its recorded games yet)" + restarted;
                }
                else
                {
                    log = LogTag + " series=" + sid8 + " no game number (game start " + Num(countStarts)
                          + " in this room and no read of the series' recorded games): its posts go without the pair"
                          + restarted;
                }
                log += OrdinalNote();
                return n;
            }

            private void Freeze(string seriesId, string room, int n)
            {
                gameSeries = seriesId;
                gameRoom = room;
                gameNumber = n;
            }

            // Round 6, finding F27: the physical game's ordinal at a game start.
            // The first start counted anchors it to the number frozen there (the
            // server's count plus one, or 1 for the series' first game start in
            // the room); every later start in the room adds one.
            private void Count(int n)
            {
                if (countStarts == 1) anchor = n;
                long p = anchor > 0 ? (long)anchor + countStarts - 1 : 0;
                physical = countLost || p <= 0 || p > MaxGameNumber ? 0 : (int)p;
            }

            private string OrdinalNote()
            {
                int p = PhysicalOrdinal();
                if (p > 0) return "; physical game " + Num(p) + " by this seat's own count";
                return "; " + WhyNoOrdinal + (countLost ? " (it missed a game start in this room)" : "");
            }

            /// <summary>Round 6, finding F27: the physical game this seat is in
            /// (or last was) by its own count of the room's games; 0 = it cannot
            /// say.</summary>
            internal int PhysicalOrdinal()
            {
                return countLost ? 0 : physical;
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

            /// <summary>The room was left: nothing frozen, the own count and the
            /// physical-game ordinal restart, and the token state is gone (the
            /// first value read in the next room, the same room rejoined
            /// included, is taken as an earlier game's). Reads are kept (the
            /// count they show belongs to the series, not the room, and a
            /// resumed sitting needs it).</summary>
            internal void Clear()
            {
                Freeze("", "", 0);
                countSeries = "";
                countRoom = "";
                countStarts = 0;
                anchor = 0;
                physical = 0;
                countLost = false;
                ResetToken("");
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
                published = false;
                withdrawn = false;
                noted = "";
            }

            // Round 6, finding F28: a game start seeds the readings with the
            // score read there. One that cannot be read, or that shows the room
            // as of more than MaxSampleAge ago, leaves the game without a token.
            private void BeginGameToken(Score live, double now)
            {
                EndGameToken();
                inGame = true;
                overSeen = false;
                boundaryMissed = !live.Read || live.Silent > MaxSampleAge;
                took = false;
                sampled = live.Read;
                lastScore = live;
                sampledAt = InformationTime(live, now);
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

            // A reading's information time: when it was taken, less the time the
            // room's transport had then been silent.
            private static double InformationTime(Score s, double now)
            {
                return s.Silent > 0 ? now - s.Silent : now;
            }

            /// <summary>Round 6, finding F28: the score as this seat reads it on
            /// a poll tick (`s`), at `now` seconds on the clock TokenFor is
            /// given. Inside this seat's game: the game over ends the game's
            /// token at once, before any game over from the watcher arrives, and
            /// a reading that cannot follow the one before it inside one game
            /// (Follows), or whose information is more than MaxSampleAge newer
            /// than the last reading's, is a game boundary this seat did not see
            /// (round 5's missed-boundary guard, now on the points too and seeded
            /// at the game start). A reading that cannot be read is skipped, so
            /// the gap runs on from the last one that could. Between games: play
            /// read twice in a row after a reset with no game start is a game
            /// this seat did not see start. Returns the line to log, or
            /// null.</summary>
            internal string ObserveScore(Score s, double now)
            {
                if (!s.Read) return null;
                string line = null;
                double at = InformationTime(s, now);
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
                        if (at - sampledAt > MaxSampleAge)
                            line = Missed("no fresh reading of the score for " + Secs(at - sampledAt) + " s inside this"
                                          + " seat's game (a game boundary could hide in the gap)");
                        else if (!follows)
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
                    if (resetOut && ++playOut >= 2 && countStarts > 0 && !countLost)
                    {
                        countLost = true;
                        line = LogTag + " play was read after a reset with no game start on this seat (" + s + "): its"
                               + " count of the room's games missed a game, so its posts and a DC report carry no"
                               + " token in this room again";
                    }
                }
                sampled = true;
                lastScore = s;
                sampledAt = at;
                return line;
            }

            // Round 6, finding F28 (round 5's missed-boundary guard, D10): a game
            // boundary inside this seat's game that it did not see. Its token is
            // dropped at once and it takes none until its next game start; and
            // since the watcher's next game start does not come without its game
            // over, its count of the room's games is no longer trusted.
            private string Missed(string why)
            {
                bool had = adopted.Length > 0;
                EndGameToken();
                boundaryMissed = true;
                bool wasLost = countLost;
                countLost = true;
                return LogTag + " " + why + ": " + (had ? "its game token is dropped, and " : "")
                       + "its posts and a DC report carry no token"
                       + (wasLost ? "" : ", in this room again: its count of the room's games missed that game start");
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
                if (!inGame || overSeen) return null;
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
                if (withdrawn || boundaryMissed || countLost) return null;
                int own = PhysicalOrdinal();
                if (own > 0 && ordinal > own)
                {
                    // Round 6, finding F28: a later game's token. The room's
                    // games are ahead of this seat's, which takes none for its own.
                    withdrawn = true;
                    noted = v;
                    return LogTag + " the room's game token " + Describe(v) + " names a game after this seat's (game "
                           + Num(own) + "): its posts and a DC report carry no token until its next game start";
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
                return LogTag + " game token " + Describe(v) + " taken for this game";
            }

            // Round 6, finding F27: why a token naming `ordinal` is not the token
            // of this seat's game, or null. It must name the physical game this
            // seat is in by its own count and the game its posts name: a seat a
            // game ahead of a lagging host holds a higher ordinal than the one
            // the host's token names, whatever number the two seats' posts name.
            private string OrdinalRefusal(int ordinal)
            {
                int own = PhysicalOrdinal();
                if (own <= 0) return WhyNoOrdinal;
                if (ordinal != own) return "it names game " + Num(ordinal) + " and this seat is in game " + Num(own) + " by its own count";
                if (ordinal != gameNumber)
                    return "it names game " + Num(ordinal) + " and this seat's posts name "
                           + (gameNumber > 0 ? "game " + Num(gameNumber) : "no game");
                return null;
            }

            // Round 6, finding F28: why this seat's reading of the score now
            // (`live`, at `now`) does not show the game its token was taken in,
            // or null. It fails closed: a score this seat cannot read, one that
            // shows the room as of more than MaxSampleAge ago, no reading in the
            // game, a last fresh reading older than MaxSampleAge, rounds to win
            // not known or one (a one-round game's score cannot be told from the
            // next game's), the game over, a 0-0 with no points (a game's reset:
            // no crossing of the game in progress exists before its first
            // point), and a score that cannot follow the last reading inside one
            // game. Time only ever withholds here (#771).
            private string ReadTimeRefusal(Score live, double now)
            {
                if (!live.Read) return "this seat cannot read the score";
                if (live.Silent > MaxSampleAge) return "the room's transport has been silent for " + Secs(live.Silent) + " s";
                if (!sampled) return "this seat has no reading of the score in this game";
                if (now - sampledAt > MaxSampleAge) return "this seat's last reading of the score is " + Secs(now - sampledAt) + " s old";
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
            /// (`v`: the room's value now), while it names the game this seat is
            /// in by its own count and by the number its posts name (round 6,
            /// F27), and while this seat's reading of the score now (`live`, at
            /// `now`) still shows that game (round 6, F28). Every check is made
            /// here, when the post or the report is built, so a game over or a
            /// game start that has not reached this seat withholds the token as
            /// surely as one that has.</summary>
            internal string TokenFor(string seriesId, string room, string v, Score live, double now, out string why)
            {
                why = TokenRefusal(seriesId, room, v, live, now);
                return why == null ? adopted : "";
            }

            internal string TokenFor(string seriesId, string room, string v, Score live, double now)
            {
                string why;
                return TokenFor(seriesId, room, v, live, now, out why);
            }

            private string TokenRefusal(string seriesId, string room, string v, Score live, double now)
            {
                if (!inGame || overSeen) return WhyNoGame;
                if (boundaryMissed || countLost) return WhyMissed;
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
                return ReadTimeRefusal(live, now);
            }

            /// <summary>The token this seat publishes now, or "" and why not
            /// (`why`, one of the Why constants). Only the room's host
            /// (`isHost`) publishes, once per game, while the game's first round
            /// is in progress (`firstRound`: the rounds are 0-0), only while this
            /// seat has taken no token in the game and holds the game's ordinal
            /// by its own count, which the token names. Its epoch is one above
            /// the highest this seat has read in the room or published. `current`
            /// is the room's value now; the fresh nonce is neither its nonce nor
            /// any stale for this seat or read in this game.</summary>
            internal string TokenToPublish(bool isHost, bool firstRound, string current, out string why)
            {
                why = null;
                long epoch = Math.Max(epochRead, epochPublished) + 1;
                if (!inGame || overSeen) why = WhyNoGame;
                else if (boundaryMissed || countLost) why = WhyMissed;
                else if (PhysicalOrdinal() <= 0) why = WhyNoOrdinal;
                else if (adopted.Length > 0 || withdrawn) why = WhyTaken;
                else if (published) why = WhyPublished;
                else if (!firstRound) why = WhyLate;
                else if (!isHost) why = WhyNotHost;
                else if (epoch > MaxEpoch) why = WhyEpoch;
                if (why != null) return "";
                string current16 = NonceOf(current);
                string n;
                do n = DrawNonce();
                while (n == current16 || stale.Contains(n) || SeenNonce(n));
                return MakeToken(n, PhysicalOrdinal(), epoch);
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
            internal override void Read(string series, int recordedGames) { t.ObserveRead(series, true, recordedGames, 0); }
            internal override void Start(string series, string room) { string line; t.OnGameStart(series, room, Played, 0.0, out line); }
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

        // Scores the model's seats read (rounds to win 5).
        private static readonly Score Reset = Score.Of(0, 0, 0, 0, 5);     // a game's 0-0, before its first point
        private static readonly Score Played = Score.Of(0, 0, 1, 0, 5);    // its first point
        private static readonly Score TwoEach = Score.Of(0, 0, 1, 1, 5);   // one point each: two points, a crossing
        private static readonly Score RoundUp = Score.Of(1, 0, 0, 0, 5);   // its first round won
        private static readonly Score Later = Score.Of(3, 2, 0, 0, 5);     // deep in a game
        private static readonly Score Continue = Score.Of(4, 2, 0, 0, 5);  // deeper in the same game
        private static readonly Score Final = Score.Of(5, 2, 0, 0, 5);     // its game over

        private sealed class TokenRec
        {
            public string Token = "";        // the nonce of the first token filed
            public bool Conflict;
            public int TokTeams, AllTeams;   // bit per team: a two-point post carrying Token / any two-point post
            public readonly List<int> TokGames = new List<int>();
            public readonly List<int> AllGames = new List<int>();
        }

        // main.py's rule. A post is filed only under the game it names while
        // the server is in that game. ReadsTokens: the first token filed in a
        // record is the record's (its nonce), another one marks the record as
        // holding two games, and a DC report settles only from two-point posts
        // of both teams that carried its token, when that token is the
        // record's, the record holds one game, and no other record carries it.
        // ReadsOrdinals (round 6, F27): a filed token naming a game other than
        // its record's marks the record the same way, and a DC report settles
        // only when its token names the game being settled.
        private sealed class TokenServer
        {
            public bool ReadsTokens, ReadsOrdinals;
            public int Recorded;
            private readonly Dictionary<int, TokenRec> recs = new Dictionary<int, TokenRec>();

            public void File(int named, string token, int team, bool two, int game)
            {
                if (named < 1 || named != Recorded + 1) return;
                TokenRec r;
                if (!recs.TryGetValue(named, out r)) { r = new TokenRec(); recs[named] = r; }
                if (two) { r.AllTeams |= 1 << team; r.AllGames.Add(game); }
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
            // `fromAnother`: from a post of a game other than `game`.
            public bool Settles(string token, int game, out bool fromAnother)
            {
                fromAnother = false;
                TokenRec r;
                if (!recs.TryGetValue(Recorded + 1, out r)) return false;
                List<int> from;
                if (ReadsTokens)
                {
                    string nonce;
                    int ordinal;
                    long epoch;
                    if (!TryParseToken(token, out nonce, out ordinal, out epoch)) return false;
                    if (ReadsOrdinals && ordinal != Recorded + 1) return false;
                    if (r.Conflict || r.Token != nonce || r.TokTeams != 3) return false;
                    foreach (var kv in recs)
                        if (kv.Key != Recorded + 1 && kv.Value.Token == nonce) return false;
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
        }

        private sealed class TokenSeat
        {
            public readonly Tracker T = new Tracker();
            public string View = "";     // the room's value as this seat holds it
            public int Team;
            public Score Live = Reset;   // this seat's scoreboard now
            public double Now;           // this seat's clock, seconds

            public void Read(string room, string v) { View = v; T.ObserveRoomToken(room, v); }

            // A poll tick `dt` s after the last: the score reads `s` (the room's
            // transport silent for `silent` s), then the room's value.
            public void Tick(string room, Score s, double dt = 0.1, double silent = 0.0)
            {
                Now += dt;
                s.Silent = silent;
                Live = s;
                T.ObserveScore(s, Now);
                T.ObserveRoomToken(room, View);
            }

            // The watcher's game start (at the game's first combat, or at its
            // first point), then its read of the room.
            public void Start(string series, string room)
            {
                string line;
                T.OnGameStart(series, room, Live, Now, out line);
                T.ObserveRoomToken(room, View);
            }

            // The watcher's game over: the tick that reads the final score, then
            // its game over.
            public void Over(string room)
            {
                Tick(room, Final);
                T.OnTokenGameOver(room, View);
            }

            public string Token(string series, string room) { return T.TokenFor(series, room, View, Live, Now); }

            public void Post(TokenServer srv, string series, string room, bool two, int game)
            {
                srv.File(T.For(series, room), Token(series, room), Team, two, game);
            }
        }

        private sealed class TokenTally
        {
            public int Timelines, Settled, FromAnother, Clean, CleanSettled;
        }

        private const int Rep2BeforeStart = 0, Rep2AfterPosts = 1, Rep2AfterDc = 2, Rep2Never = 3;
        private const int ReachesInGame2 = 0, ReachesBeforeStart = 1, ReachesAfterStart = 2, ReachesNever = 3;

        // A seat's game start: its poll reads the reset, then the watcher starts
        // the game at its first combat.
        private static void SeatStart(TokenSeat s, string series, string room)
        {
            s.Tick(room, Reset);
            s.Start(series, room);
        }

        // The host's game start: a seat's, then its publish when due. Returns
        // the room's value after it.
        private static string HostStart(TokenSeat h, string series, string room, string value, bool sent)
        {
            SeatStart(h, series, room);
            string why;
            string tok = h.T.TokenToPublish(true, true, h.View, out why);
            if (tok.Length == 0 || !sent) return value;
            h.T.ArmPublished(tok);
            return tok;
        }

        private static void SimulateToken(bool readsTokens, bool g1Sent, int rep2, bool sent, int reaches, bool echo,
                                          bool missed, int reached, bool hostReports, TokenTally tally)
        {
            const string S = "series-t", R = "room-t";
            var srv = new TokenServer { ReadsTokens = readsTokens, ReadsOrdinals = readsTokens };
            var h = new TokenSeat { Team = 0 };
            var p = new TokenSeat { Team = 1 };
            string value = "";
            tally.Timelines++;
            h.Read(R, value);
            p.Read(R, value);
            // Games 1 and 2: the value reaches both seats before their posts;
            // game 1's report lands, and both seats read the count, before game
            // 2 starts.
            for (int g = 1; g <= 2; g++)
            {
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
                h.T.ObserveRead(S, true, 1, 0);
                p.T.ObserveRead(S, true, 1, 0);
            }
            // Game 2 ends: the host's game over first.
            h.Over(R);
            if (rep2 == Rep2BeforeStart) srv.Recorded = 2;
            h.T.ObserveRead(S, true, srv.Recorded, 0);
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
                p.T.ObserveRead(S, true, srv.Recorded, 0);
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
            bool settled = srv.Settles(reporter.Token(S, R), 3, out fromAnother);
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
        // whether C's game 2 start comes 10 s after the host's, with C reading
        // game 2's token inside its own game 1 (#182: a late hook must still
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
            var srv = new TokenServer { ReadsTokens = true, ReadsOrdinals = true };
            var h = new TokenSeat { Team = 0 };
            var c = new TokenSeat { Team = 1 };
            var a = new TokenSeat { Team = 0 };
            var all = new[] { h, c, a };
            string value = "";
            foreach (var x in all) x.Read(R, value);
            // Game 1, seen by every seat, and recorded: team 1 leads 1-0.
            value = HostStart(h, S, R, value, true);
            SeatStart(c, S, R);
            SeatStart(a, S, R);
            foreach (var x in all) { x.Read(R, value); x.Tick(R, TwoEach); x.Post(srv, S, R, true, 1); x.Tick(R, Later); }
            h.Over(R);
            a.Over(R);
            if (!lateHook) c.Over(R);
            srv.Recorded = 1;
            h.T.ObserveRead(S, true, 1, 0);
            a.T.ObserveRead(S, true, 1, 0);
            if (!lateHook) c.T.ObserveRead(S, true, 1, 0);
            if (ahead)
            {
                SeatStart(a, S, R);
                a.Tick(R, TwoEach);
                a.Post(srv, S, R, true, 2);
                a.Tick(R, Later);
                a.Over(R);
                a.T.ObserveRead(S, true, srv.Recorded, 0);
                SeatStart(a, S, R);
            }
            // The host's game 2 start (a game behind A when A is ahead), its
            // publish and its echo.
            value = HostStart(h, S, R, value, true);
            h.Read(R, value);
            if (lateHook)
            {
                c.Read(R, value);
                c.Over(R);
                c.T.ObserveRead(S, true, 1, 0);
                c.Tick(R, Reset, 10.0);
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
                foreach (var x in all) x.T.ObserveRead(S, true, 2, 0);
            }
            if (catchUp)
            {
                h.Tick(R, Later);
                h.Over(R);
                h.T.ObserveRead(S, true, srv.Recorded, 0);
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
        // won; or NO boundary: game 2 is still going); how the time since R's
        // last reading passed (0.1 s; 6 s with R's main thread frozen; 6 s of
        // polls reading a game frozen by a silent transport); whether the host
        // published game 3's token first (R's read of the room then shows it);
        // which lifecycle events reached R first (none, the game over, the game
        // over and game 3's start); and whether a poll tick ran first. The
        // invariant: across a boundary R's report carries no token, except in
        // the shape the notes name as the residual (a score that follows R's
        // last reading inside one game, 0.1 s after it on a live transport,
        // with the room still holding the token and nothing else reaching R),
        // which the sweep counts apart. The liveness check: with no boundary,
        // 0.1 s, R's report carries game 2's token.

        private const int AtReset = 0, AtPoint = 1, AtRoundUp = 2, AtNoBoundary = 3;
        private const int GapPoll = 0, GapFreeze = 1, GapStall = 2;
        private const int LifeNone = 0, LifeOver = 1, LifeOverAndStart = 2;

        private sealed class F28Tally
        {
            public int Timelines, Across, Residual, Carry, Carried;
        }

        private static string SimulateF28(bool deep, int at, int gapKind, bool published, int life, bool pollFirst,
                                          out bool settled, out bool fromAnother, out bool residual)
        {
            const string S = "series-f28", R = "room-f28";
            var srv = new TokenServer { ReadsTokens = true, ReadsOrdinals = true };
            var h = new TokenSeat { Team = 0 };
            var p = new TokenSeat { Team = 1 };
            var r = new TokenSeat { Team = 0 };
            var all = new[] { h, p, r };
            string value = "";
            foreach (var x in all) x.Read(R, value);
            value = HostStart(h, S, R, value, true);
            SeatStart(p, S, R);
            SeatStart(r, S, R);
            foreach (var x in all) { x.Read(R, value); x.Tick(R, TwoEach); x.Post(srv, S, R, true, 1); x.Tick(R, Later); }
            foreach (var x in all) { x.Over(R); x.T.ObserveRead(S, true, 1, 0); }
            srv.Recorded = 1;
            value = HostStart(h, S, R, value, true);
            SeatStart(p, S, R);
            SeatStart(r, S, R);
            foreach (var x in all) { x.Read(R, value); x.Tick(R, TwoEach); x.Post(srv, S, R, true, 2); }
            Score last = deep ? Later : TwoEach;
            r.Tick(R, last);
            bool boundary = at != AtNoBoundary;
            Score callback = at == AtReset ? Reset : at == AtPoint ? Played : at == AtRoundUp ? RoundUp
                             : (deep ? Continue : RoundUp);
            if (gapKind == GapStall)
                for (int i = 1; i <= 60; i++) r.Tick(R, last, 0.1, 0.1 * i);
            else
                r.Now += gapKind == GapFreeze ? 6.0 : 0.1;
            if (boundary)
            {
                h.Tick(R, last);
                h.Over(R);
                h.T.ObserveRead(S, true, 1, 0);
                value = HostStart(h, S, R, value, published);
                r.View = value;
                if (life >= LifeOver) { r.Over(R); r.T.ObserveRead(S, true, 1, 0); }
                if (life == LifeOverAndStart) SeatStart(r, S, R);
            }
            if (pollFirst) r.Tick(R, callback, 0.0);
            r.Live = callback;
            string sent = r.Token(S, R);
            settled = srv.Settles(sent, boundary ? 3 : 2, out fromAnother);
            residual = boundary && Follows(last, callback) && gapKind == GapPoll && !published && life == LifeNone;
            return sent;
        }

        private static F28Tally SweepF28()
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
                bool settled, fromAnother, residual;
                string sent = SimulateF28(deep != 0, at, gap, pub != 0, life, poll != 0, out settled, out fromAnother,
                                          out residual);
                tally.Timelines++;
                if (at != AtNoBoundary)
                {
                    if (sent.Length > 0 && residual) tally.Residual++;
                    else if (sent.Length > 0 || settled) tally.Across++;
                }
                else if (gap == GapPoll)
                {
                    tally.Carry++;
                    if (sent.Length > 0 && settled && !fromAnother) tally.Carried++;
                }
            }
            return tally;
        }

        private static int Begin(Tracker t, string series, string room)
        {
            string line;
            return t.OnGameStart(series, room, Played, 0.0, out line);
        }

        private static string Tok(char c, int ordinal, long epoch)
        {
            return MakeToken(new string(c, 16), ordinal, epoch);
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
            t.ObserveRead("S", true, 1, 0);
            checks++;
            if (Begin(t, "S", "R") != 2) { pass = false; detail += " read:1-recorded"; }
            checks++;
            if (t.ReadShowsGameRecorded("S")) { pass = false; detail += " recorded:too-early"; }
            t.ObserveRead("S", true, 0, 0);
            checks++;
            if (Begin(t, "S", "R") != 2) { pass = false; detail += " read:a-lower-late-answer-lowered-it"; }
            t.ObserveRead("S", false, 5, 5);
            checks++;
            if (Begin(t, "S", "R") != 2) { pass = false; detail += " read:an-answer-without-wins-counted"; }
            t.ObserveRead("S", true, 1, 1);
            checks++;
            if (!t.ReadShowsGameRecorded("S") || t.ReadShowsGameRecorded("S2")) { pass = false; detail += " recorded:after"; }
            t.Clear();
            checks++;
            if (t.For("S", "R") != 0) { pass = false; detail += " clear"; }
            checks++;
            if (Begin(t, "S", "R") != 3) { pass = false; detail += " clear:reads-kept"; }
            t.ObserveRead("S", true, 99, 0);
            checks++;
            if (Begin(t, "S", "R") != 0) { pass = false; detail += " bound:game-100"; }
            var tr = new Tracker();
            tr.ObserveRead("S", true, 0, 0);
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
            bool st, res;
            string f28 = SimulateF28(true, AtReset, GapPoll, false, LifeNone, false, out st, out fa, out res);
            checks++;
            if (f28.Length != 0 || st) { pass = false; detail += " F28-REVIEWER:token-sent-or-settled"; }
            f28 = SimulateF28(true, AtReset, GapPoll, false, LifeOver, false, out st, out fa, out res);
            checks++;
            if (f28.Length != 0 || st) { pass = false; detail += " F28-GAME-OVER-FIRST-CONTROL:token-sent"; }
            f28 = SimulateF28(true, AtReset, GapPoll, false, LifeNone, true, out st, out fa, out res);
            checks++;
            if (f28.Length != 0 || st) { pass = false; detail += " F28-POLL-FIRST-CONTROL:token-sent"; }
            f28 = SimulateF28(true, AtReset, GapPoll, true, LifeNone, true, out st, out fa, out res);
            checks++;
            if (f28.Length != 0 || st) { pass = false; detail += " F28-LATER-TOKEN-FIRST-CONTROL:token-sent"; }
            f28 = SimulateF28(true, AtNoBoundary, GapPoll, false, LifeNone, false, out st, out fa, out res);
            checks++;
            if (f28.Length == 0 || !st || fa) { pass = false; detail += " F28-NO-BOUNDARY-CONTROL:not-carried"; }
            F28Tally f28t = SweepF28();
            checks++;
            if (f28t.Across != 0) { pass = false; detail += " F28-sweep:" + f28t.Across + "-tokens-across-a-boundary"; }
            checks++;
            if (f28t.Carry == 0 || f28t.Carried != f28t.Carry)
            { pass = false; detail += " F28-sweep:carried=" + f28t.Carried + "/" + f28t.Carry; }

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
            double kt = 0;
            var k = new Tracker();
            k.ObserveRoomToken("R", TA);
            k.OnGameStart("S", "R", Reset, kt, out line);
            k.ObserveRoomToken("R", TA);
            k.ObserveScore(Played, kt += 0.1);
            checks++;
            if (k.TokenFor("S", "R", TA, Played, kt) != "") { pass = false; detail += " token:first-read-in-a-room-taken"; }
            k.ObserveRoomToken("R", TB);
            checks++;
            if (k.TokenFor("S", "R", TB, Played, kt) != TB || k.TokenFor("S", "R", TA, Played, kt) != ""
                || k.TokenFor("S2", "R", TB, Played, kt) != "" || k.TokenFor("S", "R2", TB, Played, kt) != ""
                || k.TokenFor(null, "R", TB, Played, kt) != "" || k.TokenFor("S", null, TB, Played, kt) != "")
            { pass = false; detail += " token:for"; }
            k.ObserveRoomToken("R", TC);
            checks++;
            if (k.TokenFor("S", "R", TC, Played, kt) != "" || k.TokenFor("S", "R", TB, Played, kt) != "" || k.Adopted != "")
            { pass = false; detail += " token:second-value-in-a-game-not-withdrawn"; }
            k.OnTokenGameOver("R", TC);
            checks++;
            if (k.TokenFor("S", "R", TB, Played, kt) != "" || k.TokenFor("S", "R", TC, Played, kt) != "")
            { pass = false; detail += " token:after-game-over"; }
            k.ObserveRead("S", true, 1, 0);
            k.OnGameStart("S", "R", Reset, kt += 0.1, out line);
            k.ObserveRoomToken("R", TC);
            k.ObserveRoomToken("R", TB);
            k.ObserveScore(Played, kt += 0.1);
            checks++;
            if (k.TokenFor("S", "R", TC, Played, kt) != "" || k.TokenFor("S", "R", TB, Played, kt) != "" || k.Adopted != "")
            { pass = false; detail += " token:stale-taken"; }
            k.ObserveRoomToken("R", TD);
            checks++;
            if (k.TokenFor("S", "R", TD, Played, kt) != TD || k.PhysicalOrdinal() != 2) { pass = false; detail += " token:fresh-not-taken"; }
            k.ObserveRead("S", true, 2, 0);
            k.OnGameStart("S", "R", Reset, kt += 0.1, out line);
            k.ObserveRoomToken("R", TD);
            k.ObserveScore(Played, kt += 0.1);
            checks++;
            if (k.TokenFor("S", "R", TD, Played, kt) != "" || k.Adopted != "") { pass = false; detail += " token:reused-across-a-restart"; }
            k.ObserveRoomToken("R", TE);
            checks++;
            if (k.TokenFor("S", "R", TE, Played, kt) != TE) { pass = false; detail += " token:game-3-not-taken"; }
            string missedLine = k.ObserveScore(Reset, kt += 0.1);
            k.ObserveRoomToken("R", TF);
            checks++;
            if (k.Adopted != "" || k.TokenFor("S", "R", TE, Played, kt) != "" || k.TokenFor("S", "R", TF, Played, kt) != ""
                || missedLine == null || !missedLine.StartsWith(LogTag + " the score went down inside this seat's game (a game boundary it did not see", StringComparison.Ordinal))
            { pass = false; detail += " token:missed-boundary"; }
            // The missed boundary also ends this seat's count of the room's
            // games: no ordinal, no publish, no token at its next game start.
            k.OnTokenGameOver("R", TF);
            k.ObserveRead("S", true, 3, 0);
            k.OnGameStart("S", "R", Reset, kt += 0.1, out line);
            string whyK;
            checks++;
            if (k.PhysicalOrdinal() != 0 || k.TokenToPublish(true, true, TF, out whyK) != "" || whyK != WhyMissed)
            { pass = false; detail += " token:count-lost-after-a-missed-boundary"; }
            k.Clear();
            k.ObserveRoomToken("R", Tok('0', 4, 7));
            k.OnGameStart("S", "R", Reset, kt += 0.1, out line);
            k.ObserveRoomToken("R", Tok('0', 4, 7));
            k.ObserveScore(Played, kt += 0.1);
            checks++;
            if (k.TokenFor("S", "R", Tok('0', 4, 7), Played, kt) != "" || k.PhysicalOrdinal() != 4)
            { pass = false; detail += " token:clear"; }

            // Round 6, finding F27, on one Tracker: the ordinal, the epoch and
            // the nonce each refuse alone; a late hook takes its game's token.
            var o = new Tracker();
            double ot = 0;
            o.ObserveRoomToken("R", "");
            o.OnGameStart("S", "R", Reset, ot, out line);            // physical 1, game 1
            o.ObserveRoomToken("R", Tok('1', 1, 1));
            o.ObserveScore(Played, ot += 0.1);
            o.ObserveScore(Final, ot += 0.1);
            o.OnTokenGameOver("R", Tok('1', 1, 1));
            o.ObserveRead("S", true, 1, 0);
            o.OnGameStart("S", "R", Reset, ot += 0.1, out line);     // physical 2, game 2
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
            o.ObserveScore(Played, ot += 0.1);
            o.ObserveRoomToken("R", Tok('5', 3, 4));
            checks++;
            if (o.Adopted != "" || o.TokenFor("S", "R", Tok('4', 2, 3), Played, ot) != "")
            { pass = false; detail += " F28:a-later-games-token-did-not-withdraw"; }
            o.ObserveScore(Final, ot += 0.1);
            o.OnTokenGameOver("R", Tok('5', 3, 4));
            o.ObserveRead("S", true, 2, 0);
            o.ObserveScore(Reset, ot += 10.0);
            o.OnGameStart("S", "R", Reset, ot += 0.1, out line);     // physical 3, game 3
            o.ObserveRoomToken("R", Tok('5', 3, 4));
            o.ObserveScore(Played, ot += 0.1);
            checks++;
            if (o.TokenFor("S", "R", Tok('5', 3, 4), Played, ot) != Tok('5', 3, 4)) { pass = false; detail += " F27:a-late-hook-lost-its-games-token"; }
            // A seat whose posts name game 2 (game 2's result queued) while its
            // own count says game 3 takes no token naming either.
            var q = new Tracker();
            double qt = 0;
            q.ObserveRoomToken("R", "");
            q.ObserveRead("S", true, 1, 0);
            q.OnGameStart("S", "R", Reset, qt, out line);            // physical 2 (anchor 2), game 2
            q.ObserveScore(Played, qt += 0.1);
            q.ObserveScore(Final, qt += 0.1);
            q.OnTokenGameOver("R", "");
            q.OnGameStart("S", "R", Reset, qt += 0.1, out line);     // physical 3, game 2 (no new read)
            q.ObserveRoomToken("R", Tok('6', 2, 1));
            q.ObserveRoomToken("R", Tok('7', 3, 2));
            checks++;
            if (q.Adopted != "" || q.PhysicalOrdinal() != 3 || q.For("S", "R") != 2)
            { pass = false; detail += " F27:a-token-taken-while-the-count-and-the-number-differ"; }

            // Round 6, finding F28, on one Tracker: each of the four signals
            // clears the taken token at once, and the read-time check withholds
            // it whenever the score does not show the game it was taken in.
            var f = new Tracker();
            double ft = 0;
            string FT1 = Tok('8', 1, 1);
            f.ObserveRoomToken("R", "");
            f.OnGameStart("S", "R", Reset, ft, out line);
            f.ObserveRoomToken("R", FT1);
            f.ObserveScore(TwoEach, ft += 0.1);
            checks++;
            if (f.TokenFor("S", "R", FT1, TwoEach, ft) != FT1 || f.TokenFor("S", "R", FT1, RoundUp, ft + 0.1) != FT1)
            { pass = false; detail += " F28:the-games-token-not-carried"; }
            string whyF;
            checks++;
            if (f.TokenFor("S", "R", FT1, Reset, ft, out whyF) != "" || f.TokenFor("S", "R", FT1, Played, ft) != ""
                || f.TokenFor("S", "R", FT1, Final, ft) != "" || f.TokenFor("S", "R", FT1, default(Score), ft) != ""
                || f.TokenFor("S", "R", FT1, TwoEach, ft + MaxSampleAge + 0.1) != ""
                || f.TokenFor("S", "R", FT1, Score.Of(0, 0, 1, 1, 1), ft) != ""
                || f.TokenFor("S", "R", FT1, Score.Of(0, 0, 1, 1, 0), ft) != "")
            { pass = false; detail += " F28:read-time-check"; }
            Score silent = TwoEach;
            silent.Silent = MaxSampleAge + 0.1;
            checks++;
            if (f.TokenFor("S", "R", FT1, silent, ft) != "") { pass = false; detail += " F28:a-silent-transport-carried"; }
            f.ObserveScore(Final, ft += 0.1);
            checks++;
            if (f.Adopted != "" || f.TokenFor("S", "R", FT1, TwoEach, ft) != "") { pass = false; detail += " F28:game-over-by-the-score"; }
            f.OnTokenGameOver("R", FT1);
            string FT2 = Tok('9', 2, 2);
            f.ObserveRead("S", true, 1, 0);
            f.OnGameStart("S", "R", Reset, ft += 0.1, out line);
            f.ObserveRoomToken("R", FT2);
            f.ObserveScore(TwoEach, ft += 0.1);
            f.OnTokenGameOver("R", FT2);
            checks++;
            if (f.Adopted != "" || f.TokenFor("S", "R", FT2, TwoEach, ft) != "") { pass = false; detail += " F28:game-over-by-the-watcher"; }
            string FT3 = Tok('a', 3, 3);
            f.ObserveRead("S", true, 2, 0);
            f.OnGameStart("S", "R", Reset, ft += 0.1, out line);
            f.ObserveRoomToken("R", FT3);
            f.ObserveScore(TwoEach, ft += 0.1);
            string advanced = f.Adopted;
            f.ObserveRead("S", true, 3, 0);
            f.OnGameStart("S", "R", Reset, ft += 0.1, out line);
            checks++;
            if (advanced != FT3 || f.Adopted != "" || f.TokenFor("S", "R", FT3, TwoEach, ft) != "")
            { pass = false; detail += " F28:the-ordinal-advancing"; }
            string FT4 = Tok('b', 4, 4);
            f.ObserveRoomToken("R", FT4);
            f.ObserveScore(TwoEach, ft += 0.1);
            f.ObserveScore(Reset, ft += 0.1);
            checks++;
            if (f.Adopted != "" || f.TokenFor("S", "R", FT4, TwoEach, ft) != "") { pass = false; detail += " F28:a-reset-by-the-score"; }
            // A later game's token seen first: nothing is taken for this game
            // after it, this game's own token included.
            var lo = new Tracker();
            lo.ObserveRoomToken("R", "");
            lo.OnGameStart("S", "R", Reset, 0.0, out line);
            lo.ObserveRoomToken("R", Tok('1', 2, 2));
            lo.ObserveRoomToken("R", Tok('2', 1, 3));
            lo.ObserveScore(Played, 0.1);
            checks++;
            if (lo.Adopted != "" || lo.TokenFor("S", "R", Tok('2', 1, 3), Played, 0.1) != "")
            { pass = false; detail += " F28:taken-after-a-later-games-token"; }
            // A report at 0-0 with no points carries no token, even one taken
            // for its own game; the game's first point carries it.
            var z = new Tracker();
            z.ObserveRoomToken("R", "");
            z.OnGameStart("S", "R", Reset, 0.0, out line);
            z.ObserveRoomToken("R", Tok('3', 1, 1));
            checks++;
            if (z.Adopted != Tok('3', 1, 1) || z.TokenFor("S", "R", Tok('3', 1, 1), Reset, 0.1) != ""
                || z.TokenFor("S", "R", Tok('3', 1, 1), Played, 0.1) != Tok('3', 1, 1))
            { pass = false; detail += " F28:a-0-0-report-carried"; }
            // An unreadable score at the game start: no token in that game.
            var u = new Tracker();
            u.ObserveRoomToken("R", "");
            u.OnGameStart("S", "R", default(Score), 0.0, out line);
            u.ObserveRoomToken("R", Tok('c', 1, 1));
            u.ObserveScore(TwoEach, 0.1);
            checks++;
            if (u.TokenFor("S", "R", Tok('c', 1, 1), TwoEach, 0.1) != "") { pass = false; detail += " F28:an-unread-start-carried"; }
            // Play read after a reset with no game start ends the count.
            var pl = new Tracker();
            pl.ObserveRoomToken("R", "");
            pl.OnGameStart("S", "R", Reset, 0.0, out line);
            pl.ObserveScore(TwoEach, 0.1);
            pl.ObserveScore(Final, 0.2);
            pl.OnTokenGameOver("R", "");
            pl.ObserveScore(Reset, 0.3);
            pl.ObserveScore(Played, 0.4);
            int beforeSecond = pl.PhysicalOrdinal();
            pl.ObserveScore(TwoEach, 0.5);
            checks++;
            if (beforeSecond != 1 || pl.PhysicalOrdinal() != 0) { pass = false; detail += " F28:play-without-a-start"; }

            // The publish.
            var w = new Tracker();
            string why;
            w.ObserveRoomToken("R", TA);
            checks++;
            if (w.TokenToPublish(true, true, TA, out why) != "" || why != WhyNoGame) { pass = false; detail += " publish:outside-a-game"; }
            w.OnGameStart("S", "R", Reset, 0.0, out line);
            w.ObserveRoomToken("R", TA);
            string drawn = w.TokenToPublish(true, true, TA, out why);
            string dn;
            int dord;
            long dep;
            string whyGuest, whyLate;
            checks++;
            if (!TryParseToken(drawn, out dn, out dord, out dep) || dord != 1 || dep != 2 || dn == NonceOf(TA) || why != null
                || w.TokenToPublish(false, true, TA, out whyGuest) != "" || whyGuest != WhyNotHost
                || w.TokenToPublish(true, false, TA, out whyLate) != "" || whyLate != WhyLate)
            { pass = false; detail += " publish:draw"; }
            w.ArmPublished(drawn);
            checks++;
            if (w.TokenToPublish(true, true, TA, out why) != "" || why != WhyPublished) { pass = false; detail += " publish:twice-in-a-game"; }
            w.ObserveRoomToken("R", drawn);
            w.ObserveScore(Played, 0.1);
            checks++;
            if (w.TokenFor("S", "R", drawn, Played, 0.1) != drawn || w.TokenToPublish(true, true, drawn, out why) != "" || why != WhyTaken)
            { pass = false; detail += " publish:own-echo"; }
            var e = new Tracker();
            e.ObserveRoomToken("R", Tok('d', 5, 7));
            e.ObserveRead("S", true, 5, 0);
            e.OnGameStart("S", "R", Reset, 0.0, out line);
            string next = e.TokenToPublish(true, true, Tok('d', 5, 7), out why);
            var none = new Tracker();
            none.ObserveRoomToken("R", "");
            none.OnGameStart("S", "", Reset, 0.0, out line);
            string whyNone;
            checks++;
            if (!TryParseToken(next, out dn, out dord, out dep) || dord != 6 || dep != 8
                || none.TokenToPublish(true, true, "", out whyNone) != "" || whyNone != WhyNoOrdinal)
            { pass = false; detail += " publish:ordinal-and-epoch"; }

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
                + " timelines, " + f28t.Across + " tokens across a boundary, " + f28t.Residual + " in the residual shape, "
                + f28t.Carried + " of " + f28t.Carry + " no-boundary reports carried)";
            return SentinelTag + " " + (pass ? "PASS" : "FAIL") + ": " + checks + " checks" + sweep + detail;
        }
    }
}
