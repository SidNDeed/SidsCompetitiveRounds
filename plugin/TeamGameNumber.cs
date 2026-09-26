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

        // ---- The physical game's token (round 5, finding F25) ---------------
        //
        // At each game start in a cr_ff room the room's host draws a fresh
        // token and publishes it as the room property TokenRoomKey
        // (GameStateWatcher.TryPublishTeamToken). Every seat, the host
        // included, takes the value the room itself holds: a client sees its
        // own room-property write only when the server's echo of it arrives
        // (#428), so until then the host's posts go without a token like every
        // other seat's, and a send that never reached the room is never used.
        // A seat takes (adopts) the first value it reads during a game that is
        // not stale for it. Stale are the first value it read in the room (it
        // may belong to a game this seat did not see start), every value it
        // read during an earlier game, and the value the room held at each of
        // its game overs. A post or a DC report carries the taken value only
        // while the room still holds it. The server settles a
        // lead-forfeit only from posts that carried the DC report's token,
        // when that token is its record's own and on no other record of the
        // series (main.py, _team_game_token_seats). A missing token only ever
        // withholds that settlement.

        /// <summary>The room property the host publishes the token in.</summary>
        internal const string TokenRoomKey = "cr_tg_token";

        /// <summary>Why a seat does not publish (Tracker.TokenToPublish).
        /// Only WhyNotHost can change inside the game's first round (a host
        /// handoff), so GameStateWatcher retries on it and on nothing else.</summary>
        internal const string WhyNoGame = "no game is in progress";
        internal const string WhyMissed = "this seat missed a game boundary";
        internal const string WhyTaken = "this game's token is already in the room";
        internal const string WhyPublished = "this seat already published this game's token";
        internal const string WhyLate = "the game's first round is over";
        internal const string WhyNotHost = "this seat is not the room's host";

        /// <summary>A token: 16 lowercase hex digits, the shape the server
        /// accepts (main.py _TEAM_GAME_TOKEN_RE; migration 354's CHECK).</summary>
        internal static bool TokenValid(string token)
        {
            if (token == null || token.Length != 16) return false;
            foreach (char c in token)
                if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
            return true;
        }

        /// <summary>A fresh token: the first 8 bytes of a new Guid (60 random
        /// bits) as 16 lowercase hex digits. It names a physical game; it is
        /// not a secret (every seat in the room reads it).</summary>
        internal static string DrawToken()
        {
            byte[] b = Guid.NewGuid().ToByteArray();
            var sb = new System.Text.StringBuilder(16);
            for (int i = 0; i < 8; i++) sb.Append(b[i].ToString("x2", CultureInfo.InvariantCulture));
            return sb.ToString();
        }

        private static string Short(string token)
        {
            return token == null ? "" : (token.Length > 8 ? token.Substring(0, 8) : token);
        }

        /// <summary>What a post carrying a token signs for it, apart from the
        /// pair's own signature (update_team_live_points, token_sig): series,
        /// reporter, t1, t2, game number, room (unescaped), token.</summary>
        internal static string TokenCanonical(string seriesId, string reporterSteamId, int t1Points, int t2Points,
                                              int gameNumber, string photonRoomId, string token)
        {
            return "team-live-points-token:" + seriesId + ":" + reporterSteamId + ":" + Num(t1Points) + ":"
                   + Num(t2Points) + ":" + Num(gameNumber) + ":" + photonRoomId + ":" + token;
        }

        /// <summary>What a DC report carrying a token signs for it
        /// (team_series_report_dc, token_sig). The report's own hmac_sig and
        /// its canonical are unchanged.</summary>
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
        internal const string PinToken = "0123456789abcdef";
        internal const string PinDcPlayer = "90000000000700008";
        internal const string PinTokenExpected =
            "team-live-points-token:5b0c7e1a-2d3f-4a5b-8c6d-7e8f9a0b1c2d:90000000000700009:2:1:3:team_pin_room:0123456789abcdef";
        internal const string PinDcTokenExpected =
            "team-dc-token:90000000000700009:5b0c7e1a-2d3f-4a5b-8c6d-7e8f9a0b1c2d:90000000000700008:0123456789abcdef";

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
            // The physical game's token (round 5, finding F25). The stale
            // values, oldest first: the first value this seat read in the room,
            // every value it read during an earlier game, and the value the
            // room held at each of its game overs. A published token is fresh
            // (60 random bits, none its publisher holds), so only the last few
            // can still be in the room, and the list is bounded.
            private const int MaxTokens = 16;
            private readonly List<string> stale = new List<string>();
            // Values read during the game in progress: stale for every later game.
            private readonly List<string> seen = new List<string>();
            private string tokenRoom = "";     // the room those values were read in
            private string adopted = "";       // the token of the game in progress, "" = none
            private bool inGame;               // from a game start to its game over
            private bool boundaryMissed;       // the score went down inside the game: no token until the next start
            private bool published;            // this seat's publish for the game in progress was sent
            private string noted = "";         // the last changed value logged (each is logged once)

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
            /// carry. Returns it, 0 = its posts go without the pair; `log` is
            /// the line to write.</summary>
            internal int OnGameStart(string seriesId, string room, out string log)
            {
                BeginGameToken();
                seriesId = seriesId ?? "";
                room = room ?? "";
                string sid8 = seriesId.Length > 8 ? seriesId.Substring(0, 8) : seriesId;
                if (seriesId.Length == 0 || room.Length == 0)
                {
                    Freeze("", "", 0);
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
                }
                countStarts++;
                int had;
                bool read = recorded.TryGetValue(seriesId, out had);
                int n = read ? had + 1 : (countStarts == 1 ? 1 : 0);
                if (n > MaxGameNumber || !RoomSendable(room))
                {
                    Freeze(seriesId, room, 0);
                    log = LogTag + " series=" + sid8 + " game number " + Num(n) + " or the room is outside what the"
                          + " server accepts: its posts go without the pair" + restarted;
                    return 0;
                }
                Freeze(seriesId, room, n);
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
                return n;
            }

            private void Freeze(string seriesId, string room, int n)
            {
                gameSeries = seriesId;
                gameRoom = room;
                gameNumber = n;
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

            /// <summary>The room was left: nothing frozen, the own count restarts,
            /// and the token state is gone (the first value read in the next
            /// room, the same room rejoined included, is taken as an earlier
            /// game's). Reads are kept (the count they show belongs to the
            /// series, not the room, and a resumed sitting needs it).</summary>
            internal void Clear()
            {
                Freeze("", "", 0);
                countSeries = "";
                countRoom = "";
                countStarts = 0;
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

            // ---- The physical game's token (round 5, finding F25) ----

            private static void Remember(List<string> list, string v)
            {
                if (!TokenValid(v) || list.Contains(v)) return;
                if (list.Count >= MaxTokens) list.RemoveAt(0);
                list.Add(v);
            }

            private void ResetToken(string room)
            {
                stale.Clear();
                seen.Clear();
                tokenRoom = room ?? "";
                adopted = "";
                inGame = false;
                boundaryMissed = false;
                published = false;
                noted = "";
            }

            // The game in progress ends (a game over, a game start without one,
            // a missed boundary): everything read or taken in it is stale for
            // every later game.
            private void EndGameToken()
            {
                foreach (string v in seen) Remember(stale, v);
                seen.Clear();
                Remember(stale, adopted);
                adopted = "";   // a token is never carried into another game
                published = false;
                noted = "";
            }

            private void BeginGameToken()
            {
                EndGameToken();
                inGame = true;
                boundaryMissed = false;
            }

            /// <summary>The room's TokenRoomKey value as this seat reads it now
            /// (`v`; "" = none, or not a token), read on every poll tick in a
            /// cr_ff room and right after every game start. Returns the line to
            /// log, or null (most reads change nothing).</summary>
            internal string ObserveRoomToken(string room, string v)
            {
                room = room ?? "";
                if (!TokenValid(v)) v = "";
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
                    stale.Add(v);
                    return LogTag + " first read of the room's game token " + Short(v) + ": taken as an earlier"
                           + " game's (this seat did not see that game start)";
                }
                if (v.Length == 0 || !inGame) return null;
                Remember(seen, v);
                if (adopted.Length > 0)
                {
                    if (v == adopted || v == noted) return null;
                    noted = v;
                    return LogTag + " the room's game token changed to " + Short(v) + " inside this seat's game: its"
                           + " posts and a DC report carry no token until its next game start";
                }
                if (boundaryMissed || stale.Contains(v)) return null;
                adopted = v;
                return LogTag + " game token " + Short(v) + " taken for this game";
            }

            /// <summary>This seat's game is over. The value the room holds now
            /// (`v`) and everything read or taken in the game are stale for
            /// every later game. Returns the line to log, or null.</summary>
            internal string OnTokenGameOver(string room, string v)
            {
                string line = inGame && adopted.Length == 0
                    ? LogTag + " no game token was taken in this game: its posts carried none"
                    : null;
                if (string.Equals(room ?? "", tokenRoom, StringComparison.Ordinal)) Remember(stale, v);
                EndGameToken();
                inGame = false;
                boundaryMissed = false;
                return line;
            }

            /// <summary>The score went down inside this seat's game: a game
            /// ended and another started without this seat's game over. The
            /// token it took is stale, and it takes none until its next game
            /// start.</summary>
            internal void OnMissedBoundary(out string log)
            {
                bool had = adopted.Length > 0;
                EndGameToken();
                boundaryMissed = true;
                log = LogTag + " the score went down inside this seat's game (a game boundary it did not see): "
                      + (had ? "its game token is dropped, and " : "")
                      + "its posts and a DC report carry no token until its next game start";
            }

            /// <summary>The token a post or a DC report sent now carries: the
            /// one taken in this seat's game, while that game is in progress,
            /// in the series and the room its number was frozen for, and while
            /// the room still holds it (`v`: the room's value now). "" = none.</summary>
            internal string TokenFor(string seriesId, string room, string v)
            {
                if (!inGame || boundaryMissed || adopted.Length == 0 || string.IsNullOrEmpty(seriesId)) return "";
                room = room ?? "";
                if (!string.Equals(seriesId, gameSeries, StringComparison.Ordinal)
                    || !string.Equals(room, gameRoom, StringComparison.Ordinal)
                    || !string.Equals(room, tokenRoom, StringComparison.Ordinal)) return "";
                return string.Equals(v ?? "", adopted, StringComparison.Ordinal) ? adopted : "";
            }

            /// <summary>The token this seat publishes now, or "" and why not
            /// (`why`, one of the Why constants). Only the room's host
            /// (`isHost`) publishes, once per game, while the game's first round
            /// is in progress (`firstRound`: the rounds are 0-0), and only while
            /// this seat has taken no token in the game. `current` is the room's
            /// value now; the fresh token is neither it nor any value stale for
            /// this seat or read in this game.</summary>
            internal string TokenToPublish(bool isHost, bool firstRound, string current, out string why)
            {
                why = null;
                if (!inGame) why = WhyNoGame;
                else if (boundaryMissed) why = WhyMissed;
                else if (adopted.Length > 0) why = WhyTaken;
                else if (published) why = WhyPublished;
                else if (!firstRound) why = WhyLate;
                else if (!isHost) why = WhyNotHost;
                if (why != null) return "";
                string t;
                do t = DrawToken();
                while (t == current || stale.Contains(t) || seen.Contains(t));
                return t;
            }

            /// <summary>The publish of `token` was sent (SetCustomProperties
            /// returned true): no second one this game. Nothing else changes;
            /// this seat's posts carry the token once the room shows it.</summary>
            internal void ArmPublished(string token)
            {
                if (inGame && TokenValid(token)) published = true;
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
            internal override void Start(string series, string room) { string line; t.OnGameStart(series, room, out line); }
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

        // ---- The token sentinel (round 5, finding F25) ----------------------
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
        // missed the boundary between the games (its score went down inside a
        // game), how far game 3 got (0-0, one point each, two points each), and
        // which seat reports the DC. The lead rule is outside the model: every
        // DC report comes from the team a game up. The server is main.py's
        // rule: a post is filed only under the game it names while the server
        // is in that game; the first token filed in a record is the record's,
        // and another one marks the record as holding two games; a DC report
        // settles only from two-point posts of both teams that carried its
        // token, when that token is the record's, the record holds one game,
        // and no other record carries it. The invariant: nothing settles from
        // a post of a physical game other than the one the DC is in. The
        // liveness check: with game 2 recorded before game 3 starts, the
        // publish sent, the value reaching P before game 3's posts, the host's
        // echo in time and no boundary missed, a DC after two points each
        // settles. The same sweep against the rule before round 5 (no token
        // read) must settle from another game, or it could not see F25.

        private sealed class TokenRec
        {
            public string Token = "";
            public bool Conflict;
            public int TokTeams, AllTeams;   // bit per team: a two-point post carrying Token / any two-point post
            public readonly List<int> TokGames = new List<int>();
            public readonly List<int> AllGames = new List<int>();
        }

        private sealed class TokenServer
        {
            public bool ReadsTokens;
            public int Recorded;
            private readonly Dictionary<int, TokenRec> recs = new Dictionary<int, TokenRec>();

            public void File(int named, string token, int team, bool two, int game)
            {
                if (named < 1 || named != Recorded + 1) return;
                TokenRec r;
                if (!recs.TryGetValue(named, out r)) { r = new TokenRec(); recs[named] = r; }
                if (two) { r.AllTeams |= 1 << team; r.AllGames.Add(game); }
                if (!TokenValid(token)) return;
                if (r.Token.Length == 0) r.Token = token;
                if (token != r.Token) { r.Conflict = true; return; }
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
                    if (!TokenValid(token) || r.Conflict || r.Token != token || r.TokTeams != 3) return false;
                    foreach (var kv in recs)
                        if (kv.Key != Recorded + 1 && kv.Value.Token == token) return false;
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
            public string View = "";   // the room's value as this seat holds it
            public int Team;

            public void Read(string room, string v) { View = v; T.ObserveRoomToken(room, v); }

            public void Post(TokenServer srv, string series, string room, bool two, int game)
            {
                srv.File(T.For(series, room), T.TokenFor(series, room, View), Team, two, game);
            }
        }

        private sealed class TokenTally
        {
            public int Timelines, Settled, FromAnother, Clean, CleanSettled;
        }

        private const int Rep2BeforeStart = 0, Rep2AfterPosts = 1, Rep2AfterDc = 2, Rep2Never = 3;
        private const int ReachesInGame2 = 0, ReachesBeforeStart = 1, ReachesAfterStart = 2, ReachesNever = 3;

        // The host's game start: freeze, read the room, publish when due.
        // Returns the room's value after it.
        private static string HostStart(TokenSeat h, string series, string room, string value, bool sent)
        {
            string line, why;
            h.T.OnGameStart(series, room, out line);
            h.Read(room, h.View);
            string tok = h.T.TokenToPublish(true, true, h.View, out why);
            if (tok.Length == 0 || !sent) return value;
            h.T.ArmPublished(tok);
            return tok;
        }

        private static void SimulateToken(bool readsTokens, bool g1Sent, int rep2, bool sent, int reaches, bool echo,
                                          bool missed, int reached, bool hostReports, TokenTally tally)
        {
            const string S = "series-t", R = "room-t";
            var srv = new TokenServer { ReadsTokens = readsTokens };
            var h = new TokenSeat { Team = 0 };
            var p = new TokenSeat { Team = 1 };
            string value = "", line;
            tally.Timelines++;
            h.Read(R, value);
            p.Read(R, value);
            // Games 1 and 2: the value reaches both seats before their posts;
            // game 1's report lands, and both seats read the count, before game
            // 2 starts.
            for (int g = 1; g <= 2; g++)
            {
                value = HostStart(h, S, R, value, g == 2 || g1Sent);
                p.T.OnGameStart(S, R, out line);
                p.Read(R, p.View);
                h.Read(R, value);
                p.Read(R, value);
                h.Post(srv, S, R, true, g);
                p.Post(srv, S, R, true, g);
                if (g == 2) break;
                h.T.OnTokenGameOver(R, h.View);
                p.T.OnTokenGameOver(R, p.View);
                srv.Recorded = 1;
                h.T.ObserveRead(S, true, 1, 0);
                p.T.ObserveRead(S, true, 1, 0);
            }
            // Game 2 ends: the host's game over first.
            h.T.OnTokenGameOver(R, h.View);
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
                p.T.OnTokenGameOver(R, p.View);
                p.T.ObserveRead(S, true, srv.Recorded, 0);
            }
            if (!hostStarted)
            {
                value = HostStart(h, S, R, value, sent);
                if (echo) h.Read(R, value);
            }
            if (reaches == ReachesBeforeStart) p.Read(R, value);
            if (missed) p.T.OnMissedBoundary(out line);
            else { p.T.OnGameStart(S, R, out line); p.Read(R, p.View); }
            if (reaches == ReachesAfterStart) p.Read(R, value);
            if (reached > 0)
            {
                h.Post(srv, S, R, reached == 2, 3);
                p.Post(srv, S, R, reached == 2, 3);
            }
            if (rep2 == Rep2AfterPosts) srv.Recorded = 2;
            TokenSeat reporter = hostReports ? h : p;
            bool fromAnother;
            bool settled = srv.Settles(reporter.T.TokenFor(S, R, reporter.View), 3, out fromAnother);
            if (settled) tally.Settled++;
            if (settled && (fromAnother || reached < 2)) tally.FromAnother++;
            bool clean = rep2 == Rep2BeforeStart && sent && echo && !missed && reached == 2
                         && (reaches == ReachesBeforeStart || reaches == ReachesAfterStart);
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
            string line;
            checks++;
            if (t.OnGameStart("S", "R", out line) != 1 || t.For("S", "R") != 1) { pass = false; detail += " first-start-no-read"; }
            checks++;
            if (t.For("S2", "R") != 0 || t.For("S", "R2") != 0 || t.For(null, null) != 0) { pass = false; detail += " for:mismatch"; }
            checks++;
            if (t.OnGameStart("S", "R", out line) != 0 || t.For("S", "R") != 0) { pass = false; detail += " second-start-no-read"; }
            t.ObserveRead("S", true, 1, 0);
            checks++;
            if (t.OnGameStart("S", "R", out line) != 2) { pass = false; detail += " read:1-recorded"; }
            checks++;
            if (t.ReadShowsGameRecorded("S")) { pass = false; detail += " recorded:too-early"; }
            t.ObserveRead("S", true, 0, 0);
            checks++;
            if (t.OnGameStart("S", "R", out line) != 2) { pass = false; detail += " read:a-lower-late-answer-lowered-it"; }
            t.ObserveRead("S", false, 5, 5);
            checks++;
            if (t.OnGameStart("S", "R", out line) != 2) { pass = false; detail += " read:an-answer-without-wins-counted"; }
            t.ObserveRead("S", true, 1, 1);
            checks++;
            if (!t.ReadShowsGameRecorded("S") || t.ReadShowsGameRecorded("S2")) { pass = false; detail += " recorded:after"; }
            t.Clear();
            checks++;
            if (t.For("S", "R") != 0) { pass = false; detail += " clear"; }
            checks++;
            if (t.OnGameStart("S", "R", out line) != 3) { pass = false; detail += " clear:reads-kept"; }
            t.ObserveRead("S", true, 99, 0);
            checks++;
            if (t.OnGameStart("S", "R", out line) != 0) { pass = false; detail += " bound:game-100"; }
            var tr = new Tracker();
            tr.ObserveRead("S", true, 0, 0);
            checks++;
            if (tr.OnGameStart("S", new string('r', MaxRoomLength + 1), out line) != 0
                || tr.OnGameStart("S", " r", out line) != 0
                || tr.OnGameStart("S", new string('r', MaxRoomLength), out line) != 1)
            { pass = false; detail += " bound:room"; }
            checks++;
            if (tr.OnGameStart("", "R", out line) != 0 || tr.OnGameStart("S", "", out line) != 0) { pass = false; detail += " empty"; }
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

            // The token on one Tracker.
            const string TA = "aaaaaaaaaaaaaaaa", TB = "bbbbbbbbbbbbbbbb", TC = "cccccccccccccccc";
            const string TD = "dddddddddddddddd", TE = "eeeeeeeeeeeeeeee";
            var k = new Tracker();
            k.ObserveRoomToken("R", TA);
            k.OnGameStart("S", "R", out line);
            k.ObserveRoomToken("R", TA);
            checks++;
            if (k.TokenFor("S", "R", TA) != "") { pass = false; detail += " token:first-read-in-a-room-taken"; }
            k.ObserveRoomToken("R", TB);
            checks++;
            if (k.TokenFor("S", "R", TB) != TB || k.TokenFor("S", "R", TA) != "" || k.TokenFor("S2", "R", TB) != ""
                || k.TokenFor("S", "R2", TB) != "" || k.TokenFor(null, "R", TB) != "" || k.TokenFor("S", null, TB) != "")
            { pass = false; detail += " token:for"; }
            k.ObserveRoomToken("R", TC);
            checks++;
            if (k.TokenFor("S", "R", TC) != "" || k.TokenFor("S", "R", TB) != TB) { pass = false; detail += " token:second-value-in-a-game"; }
            k.OnTokenGameOver("R", TC);
            checks++;
            if (k.TokenFor("S", "R", TB) != "" || k.TokenFor("S", "R", TC) != "") { pass = false; detail += " token:after-game-over"; }
            k.OnGameStart("S", "R", out line);
            k.ObserveRoomToken("R", TC);
            k.ObserveRoomToken("R", TB);
            checks++;
            if (k.TokenFor("S", "R", TC) != "" || k.TokenFor("S", "R", TB) != "") { pass = false; detail += " token:stale-taken"; }
            k.ObserveRoomToken("R", TD);
            checks++;
            if (k.TokenFor("S", "R", TD) != TD) { pass = false; detail += " token:fresh-not-taken"; }
            k.OnGameStart("S", "R", out line);
            k.ObserveRoomToken("R", TD);
            checks++;
            if (k.TokenFor("S", "R", TD) != "") { pass = false; detail += " token:reused-across-a-restart"; }
            k.ObserveRoomToken("R", TE);
            string missedLine;
            k.OnMissedBoundary(out missedLine);
            k.ObserveRoomToken("R", "ffffffffffffffff");
            checks++;
            if (k.TokenFor("S", "R", TE) != "" || k.TokenFor("S", "R", "ffffffffffffffff") != "")
            { pass = false; detail += " token:missed-boundary"; }
            k.Clear();
            k.ObserveRoomToken("R", "0000000000000001");
            k.OnGameStart("S", "R", out line);
            k.ObserveRoomToken("R", "0000000000000001");
            checks++;
            if (k.TokenFor("S", "R", "0000000000000001") != "") { pass = false; detail += " token:clear"; }
            var w = new Tracker();
            string why;
            w.ObserveRoomToken("R", TA);
            checks++;
            if (w.TokenToPublish(true, true, TA, out why) != "" || why != WhyNoGame) { pass = false; detail += " publish:outside-a-game"; }
            w.OnGameStart("S", "R", out line);
            w.ObserveRoomToken("R", TA);
            string drawn = w.TokenToPublish(true, true, TA, out why);
            string whyGuest, whyLate;
            checks++;
            if (!TokenValid(drawn) || drawn == TA || why != null
                || w.TokenToPublish(false, true, TA, out whyGuest) != "" || whyGuest != WhyNotHost
                || w.TokenToPublish(true, false, TA, out whyLate) != "" || whyLate != WhyLate)
            { pass = false; detail += " publish:draw"; }
            w.ArmPublished(drawn);
            checks++;
            if (w.TokenToPublish(true, true, TA, out why) != "" || why != WhyPublished) { pass = false; detail += " publish:twice-in-a-game"; }
            w.ObserveRoomToken("R", drawn);
            checks++;
            if (w.TokenFor("S", "R", drawn) != drawn || w.TokenToPublish(true, true, drawn, out why) != "" || why != WhyTaken)
            { pass = false; detail += " publish:own-echo"; }

            // The token's wire: its shape, both canonicals, the query, the pin.
            checks++;
            if (!TokenValid(PinToken) || !TokenValid(DrawToken()) || TokenValid("0123456789ABCDEF")
                || TokenValid("0123456789abcde") || TokenValid("0123456789abcdef0") || TokenValid("0123456789abcdeg")
                || TokenValid("") || TokenValid(null))
            { pass = false; detail += " token-valid"; }
            checks++;
            if (TokenCanonical("S", "P", 1, 2, 3, "room_x", TB) != "team-live-points-token:S:P:1:2:3:room_x:" + TB
                || DcTokenCanonical("P", "S", "Q", TB) != "team-dc-token:P:S:Q:" + TB)
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
                + untok.Settled + " settled, " + untok.FromAnother + " from another game)";
            return SentinelTag + " " + (pass ? "PASS" : "FAIL") + ": " + checks + " checks" + sweep + detail;
        }
    }
}
